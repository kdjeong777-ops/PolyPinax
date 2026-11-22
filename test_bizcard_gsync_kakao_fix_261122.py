# -*- coding: utf-8 -*-
"""구글 싱크 '#'(카톡 친구추가 방지) 어긋남 고침 (명함 SOT §5.29 '카톡 친구추가 방지', 261120-72) — 가짜 구글·가짜 명함만.

A 구글 흔적이 자동 표시보다 먼저 — 구글 출처 기록이 있는 (그림) 명함은 자동 '#' 표시가 있어도 새로 올릴 때 # 없이
A2 구글에서 가져온 그림 없는 명함의 '#' 표시(구글 이름을 받아 적은 것)는 그대로 — 바로잡기에 걸지 않음
B 같은 010 번호(종류·꼴 무관, 0082 꼴 포함)가 구글 출처 명함에 있으면 # 없이 — 새 연락처 줄에 '# 없음 — 같은 휴대폰…'
C 직접 정한 표시(set_at > 0)가 제일 먼저
D 합치기 — 지워지는 명함에 구글 흔적이 있으면 남는 명함의 자동 '#' 표시를 # 없음으로
E 이미 구글에 붙은 잘못된 '#' — '# 바로잡기' 줄(처음 체크), [적용] 하면 구글 이름에서 # 뗌, 다시 계획하면 없음
F 구글에서 직접 이름을 고친 사람·직접 정한 표시는 '# 바로잡기' 에서 뺌
"""
import os, sys, tempfile, time, copy, itertools
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_kfix_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_kfix_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
from viewer.bizcard import people as P, store as S, gsync as G, phone as PH
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


class FakeApi:
    def __init__(self):
        self.people, self.n = {}, itertools.count(100)

    def list_people(self):
        return [copy.deepcopy(p) for p in self.people.values()]

    def create(self, p):
        rn = "people/n%d" % next(self.n)
        self.people[rn] = dict(copy.deepcopy(p), resourceName=rn, etag="e1",
                               metadata={"sources": [{"type": "CONTACT", "updateTime": "2020-01-01T00:00:00.000Z"}]})
        return copy.deepcopy(self.people[rn])

    def update(self, rn, p):
        self.people[rn].update({k: copy.deepcopy(v) for k, v in p.items() if k != "etag"})
        return copy.deepcopy(self.people[rn])


def gname(api, rn):
    return api.people[rn]["names"][0]["unstructuredName"]


def card(st, name, cell):
    return P._insert_contact(st, {"name": name, "phones": [("cell", cell)]}, ["명함"])


def scan_card(st, name, cell):
    """그림 명함(스캔) — 사용자 사례처럼 우리가 올리며 '#' 를 붙인 명함."""
    from PIL import Image
    fold = TMP / "cards"
    fold.mkdir(exist_ok=True)
    f = fold / ("%s_가짜사.jpg" % name)
    Image.new("RGB", (60, 40), "white").save(f)
    return st.upsert({"front": str(f), "name": name, "phones": [("cell", cell)]})


try:
    st = S.BizcardStore(TMP / "local" / "bizcard.db")
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    P.src_init(st)
    api = FakeApi()
    chk(PH.mobile_key("home", "0082 10 0000 1234") == "01000001234", "B 0082 꼴도 010 열쇠", PH.mobile_key("home", "0082 10 0000 1234"))

    # ── A·C ──
    print("=== A·C. 새로 올릴 때 차례 ===")
    a = scan_card(st, "가짜일", "010-0000-0001")
    G.kakao_set(st, [a], True, set_at=0.0)                    # 예전 싱크가 적어 둔 자동 '#'
    P._set_srcs(st, a, ["name"], G.SRC)                       # 구글 흔적(구글에서 가져온 칸)
    e = scan_card(st, "가짜오", "010-0000-0005")
    P._set_srcs(st, e, ["name"], G.SRC)
    G.kakao_set(st, [e], True)                                # 사람이 직접 정한 표시(set_at > 0)
    # ── B ──
    d = card(st, "가짜사", "010-0000-0004")
    P._set_srcs(st, d, ["name"], G.SRC)                       # 구글 출처 명함(구글엔 없음)
    c = P._insert_contact(st, {"name": "가짜삼", "phones": [("work", "0082 10 0000 0004")]}, ["명함"])   # 같은 번호, 다른 종류·꼴
    b = card(st, "가짜이", "010-0000-0002")
    h = card(st, "가짜팔", "010-0000-0008")                   # 구글에서 '#가짜팔' 로 가져온 그림 없는 명함(옛 기록 — set_at 0)
    P._set_srcs(st, h, ["name"], G.SRC)
    G.kakao_set(st, [h], True, set_at=0.0)
    st.con.commit()
    rows = G.plan(st, api.list_people())
    by = {r["card_id"]: r for r in rows if r["kind"] == G.NEW_GOOGLE}
    chk(by.get(a, {}).get("kakao") is False and by[a].get("kakao_why") == "google_src", "A 구글 흔적이 자동 '#' 표시보다 먼저 — # 없이",
        str(by.get(a)))
    chk(by.get(c, {}).get("kakao") is False and by[c].get("kakao_why") == "same_mobile", "B 같은 010(종류·꼴 무관) — # 없이·까닭", str(by.get(c)))
    chk(by.get(e, {}).get("kakao") is True and by[e].get("kakao_why") == "user", "C 직접 정한 표시가 제일 먼저", str(by.get(e)))
    chk(by.get(b, {}).get("kakao") is True, "B 미등록 새 사람은 # 붙임", str(by.get(b)))
    chk(by.get(h, {}).get("kakao") is True and by[h].get("kakao_why") == "google_name", "A2 구글 이름의 '#' 를 받아 적은 그림 없는 명함은 그대로", str(by.get(h)))
    from viewer.widgets.bizcard_gsync_dialog import GSyncDialog
    dlg = GSyncDialog(None, db=str(st.path), start=False)
    dlg._planned(rows, api.list_people(), "")
    texts = [dlg.tree.topLevelItem(i).child(j).text(0) for i in range(dlg.tree.topLevelItemCount())
             for j in range(dlg.tree.topLevelItem(i).childCount())]
    dlg.close()
    chk(any("가짜삼" in t and "# 없음" in t and "같은 휴대폰" in t for t in texts) and any("가짜이" in t and "# 붙임" in t for t in texts),
        "B 새 연락처 줄에 '# 붙임'·'# 없음 — 까닭'", str(texts))

    # ── D ──
    print("\n=== D. 합치기 ===")
    k = scan_card(st, "가짜육", "010-0000-0006")
    gdrop = card(st, "가짜육", "010-0000-0006")
    G.kakao_set(st, [k], True, set_at=0.0)
    P._set_srcs(st, gdrop, ["name"], G.SRC)
    st.con.commit()
    G.merge_links(st, k, [gdrop])
    chk(G.kakao_rows(st).get(k, (None,))[0] is False, "D 지워지는 명함에 구글 흔적 — 남는 명함 자동 '#' 를 # 없음으로", str(G.kakao_rows(st).get(k)))

    # ── E·F ──
    print("\n=== E·F. '# 바로잡기' ===")
    st.con.execute("DELETE FROM contact_src WHERE card_id IN (?,?)", (a, e))   # 올릴 땐 흔적 없던 새 사람으로 — 자동 '#' 로 올라감
    st.con.commit()
    f = scan_card(st, "가짜칠", "010-0000-0007")
    st.con.commit()
    G.apply(st, api, [r for r in G.plan(st, api.list_people()) if r["kind"] == G.NEW_GOOGLE and r["card_id"] in (a, e, f)],
            people=api.list_people())
    rn = {cid: G.links(st)[cid]["rn"] for cid in (a, e, f)}
    chk(gname(api, rn[a]).startswith("#") and gname(api, rn[f]).startswith("#"), "(전제) 자동 '#' 로 올라감", str([gname(api, rn[x]) for x in (a, f)]))
    P._set_srcs(st, a, ["name"], G.SRC)                       # 뒤에 드러난 구글 흔적(예: 구글 명함과 합침)
    P._set_srcs(st, e, ["name"], G.SRC)                       # e 는 직접 정한 표시 — 빼야 함
    P._set_srcs(st, f, ["name"], G.SRC)
    api.people[rn[f]]["names"][0]["unstructuredName"] = "가짜칠"   # f 는 구글에서 직접 # 를 뗌
    api.people[rn[f]]["metadata"] = {"sources": [{"type": "CONTACT", "updateTime": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() + 5))}]}
    st.con.commit()
    rows = G.plan(st, api.list_people())
    fix = [r for r in rows if r["kind"] == getattr(G, "KAKAO_FIX", "kakao_fix")]
    chk([r["card_id"] for r in fix] == [a] and all(G.row_default(r) for r in fix), "E '# 바로잡기' 는 자동 '#' 가 어긋난 사람만(처음 체크)",
        str([(r["kind"], r["card_id"]) for r in rows]))
    chk(not any(r["card_id"] == f and r["kind"] == getattr(G, "KAKAO_FIX", "kakao_fix") for r in rows)
        and not any(r["card_id"] == e and r["kind"] == getattr(G, "KAKAO_FIX", "kakao_fix") for r in rows), "F 구글에서 직접 고친 사람·직접 정한 표시는 뺌")
    G.apply(st, api, fix, people=api.list_people())
    chk(not gname(api, rn[a]).startswith("#") and G.kakao_rows(st)[a][0] is False, "E [적용] 하면 구글 이름에서 # 뗌·표시도", gname(api, rn[a]))
    chk(not [r for r in G.plan(st, api.list_people()) if r["kind"] == getattr(G, "KAKAO_FIX", "kakao_fix")], "E 다시 계획하면 없음")
    st.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외")
print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
