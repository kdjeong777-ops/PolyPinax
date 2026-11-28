# -*- coding: utf-8 -*-
"""구글 싱크 — '남김' 은 짝만 풀림·구글에서 지운 값은 따로 묻기 (구글 싱크 SOT §5.29 '지운 것'·'구글에서 지운 값', 261120-62).
가짜 구글(메모리 안)·가짜 값만.

A 구글에서 지워진 사람을 체크하지 않고 [반영] → 짝만 풀림(명함 그대로), 다음 싱크에 '새 연락처' 로 다시 제안
B 명함에서 지워진 사람을 체크하지 않고 [반영] → 짝만 풀림(구글 그대로), 그 연락처는 '구글에만 둠' — 다음 싱크에 '새 명함' 으로 다시 내지 않음(261122-8)
C 구글에서 번호 하나를 지우고 직함을 고침 → 직함은 '명함 고침', 번호는 '구글에서 지운 값'(처음 꺼짐) —
  안 고르면 명함 번호 그대로·구글로 다시 올림, 다시 계획하면 바꿀 것 없음
D '구글에서 지운 값' 을 고르면 명함에서도 지움
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
QCoreApplication.setApplicationName("polypdf_bizcard_gone_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_gone_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
from viewer.bizcard import people as P, store as S, gsync as G
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


NOW = lambda: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() + 5))


class FakeApi:
    def __init__(self):
        self.people, self.n = {}, itertools.count(100)

    def list_people(self):
        return [copy.deepcopy(p) for p in self.people.values()]

    def create(self, p):
        rn = "people/n%d" % next(self.n)
        q = dict(copy.deepcopy(p), resourceName=rn, etag="e1", metadata={"sources": [{"type": "CONTACT", "updateTime": "2020-01-01T00:00:00.000Z"}]})
        self.people[rn] = q
        return copy.deepcopy(q)

    def update(self, rn, p):
        self.people[rn].update({k: copy.deepcopy(v) for k, v in p.items() if k != "etag"})
        return copy.deepcopy(self.people[rn])

    def delete(self, rn):
        self.people.pop(rn, None)


def dialog_apply(st, api, rows, checked_kinds=None):
    """미리보기 창이 넘기는 줄 그대로(체크한 것 + 체크하지 않은 지워짐·지운 값의 뒷처리)."""
    from viewer.widgets.bizcard_gsync_dialog import GSyncDialog
    dlg = GSyncDialog(None, db=str(st.path), start=False)
    dlg._planned(rows, api.list_people(), "")
    for i in range(dlg.tree.topLevelItemCount()):
        top = dlg.tree.topLevelItem(i)
        for j in range(top.childCount()):
            it = top.child(j)
            r = rows[it.data(0, Qt.ItemDataRole.UserRole)]
            if checked_kinds is not None:
                it.setCheckState(0, Qt.CheckState.Checked if r["kind"] in checked_kinds else Qt.CheckState.Unchecked)
    out = dlg.to_apply() if hasattr(dlg, "to_apply") else dlg.chosen()
    dlg.close()
    return G.apply(st, api, out, people=api.list_people())


try:
    st = S.BizcardStore(TMP / "local" / "bizcard.db")
    api = FakeApi()
    a = P._insert_contact(st, {"name": "가짜일", "title": "과장", "phones": [("cell", "010-0000-0001"), ("work", "02-0000-0001")],
                              "emails": ["one@example.com"]}, ["명함"])
    b = P._insert_contact(st, {"name": "가짜이", "phones": [("cell", "010-0000-0002")]}, ["명함"])
    c = P._insert_contact(st, {"name": "가짜삼", "phones": [("cell", "010-0000-0003")]}, ["명함"])
    st.con.commit()
    G.apply(st, api, G.plan(st, api.list_people()), people=api.list_people())          # 셋 다 구글로
    rn = {cid: l["rn"] for cid, l in G.links(st).items()}

    # ── A ──
    print("=== A. 구글에서 지워짐 — 남김 ===")
    api.delete(rn[b])
    st.delete_card(c)                                       # B 준비 — 명함에서 지워짐
    rows = G.plan(st, api.list_people())
    kinds = sorted(r["kind"] for r in rows)
    chk(kinds == sorted([G.GONE_GOOGLE, G.GONE_CARD]), "(전제) 지워짐 두 줄", str(kinds))
    dialog_apply(st, api, rows)                              # 처음 체크 그대로(둘 다 '남김')
    chk(b not in G.links(st) and c not in G.links(st) and P.card_by_id(st, b) is not None and rn[c] in api.people,
        "A·B 체크하지 않은 지워짐은 짝만 풀림(명함·구글 그대로)", str(G.links(st)))
    rows2 = G.plan(st, api.list_people())
    k2 = sorted((r["kind"], r.get("card_id") or r.get("rn")) for r in rows2)
    # 구글에서 지워짐을 남긴 명함은 새 연락처로 다시 제안, 명함에서 지워짐을 남긴 구글 연락처는 '구글에만 둠' — 다시 가져오라 하지 않음(261122-8)
    chk((G.NEW_GOOGLE, b) in k2 and (G.NEW_CARD, rn[c]) not in k2, "A·B 다음 싱크 — 남긴 명함은 새 연락처로 제안, 남긴 구글 연락처는 구글에만 둠", str(k2))
    api.delete(rn[c])

    # ── C ──
    print("\n=== C. 구글에서 지운 값 ===")
    p = api.people[rn[a]]
    p["phoneNumbers"] = [x for x in p["phoneNumbers"] if not x["value"].startswith(("02", "+82 2-"))]   # 구글엔 국제 꼴로 올라감(261128-18)
    p["organizations"] = [{"name": "", "title": "부장"}]
    p["metadata"] = {"sources": [{"type": "CONTACT", "updateTime": NOW()}]}
    rows = [r for r in G.plan(st, api.list_people()) if r["card_id"] == a]
    to_card = [r for r in rows if r["kind"] == G.TO_CARD]
    gv = [r for r in rows if r["kind"] == getattr(G, "GONE_VALUE", "?")]
    chk(to_card and to_card[0]["fields"] == ["title"] and gv and gv[0]["fields"] == ["phones"] and not G.row_default(gv[0]),
        "C 직함은 '명함 고침', 번호는 '구글에서 지운 값'(처음 꺼짐)", str([(r["kind"], r.get("fields")) for r in rows]))
    dialog_apply(st, api, rows)
    ca = P.card_by_id(st, a)
    gp = [x["value"] for x in api.people[rn[a]]["phoneNumbers"]]
    chk(ca["title"] == "부장" and len(ca["phones"]) == 2 and len(gp) == 2, "C 안 고르면 명함 번호 그대로·구글로 다시 올림·직함은 고침",
        str((ca["title"], ca["phones"], gp)))
    chk(not [r for r in G.plan(st, api.list_people()) if r["card_id"] == a], "C 다시 계획하면 바꿀 것 없음",
        str(G.plan(st, api.list_people())))

    # ── D ──
    print("\n=== D. 고르면 명함에서도 ===")
    p = api.people[rn[a]]
    p["emailAddresses"] = []
    p["metadata"] = {"sources": [{"type": "CONTACT", "updateTime": NOW()}]}
    rows = [r for r in G.plan(st, api.list_people()) if r["card_id"] == a]
    dialog_apply(st, api, rows, checked_kinds={getattr(G, "GONE_VALUE", "?")})
    chk(P.card_by_id(st, a)["emails"] == [], "D 고르면 명함에서도 지움", str(P.card_by_id(st, a)["emails"]))
    st.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외")
print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
