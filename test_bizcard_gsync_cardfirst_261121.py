# -*- coding: utf-8 -*-
"""구글 싱크 '명함 기준으로 올리기'·새로 올릴 때 '#' 기준 (구글 싱크 SOT §5.29 '명함 기준으로 올리기'·'카톡 친구추가 방지', 261120-59).
가짜 구글(메모리 안 사전)·가짜 값만 — 실제 구글·실제 명함 DB 에 붙지 않는다(§2.1).

A 구글 연락처를 통째로 지운 뒤 명함 기준 — 짝 있던 명함은 '새 연락처'로 다시(지워짐 줄 없음), 반영하면 새 짝, 다시 계획하면 바꿀 것 없음
B 명함 기준이면 구글 → 명함 고침·구글에만 있는 사람 가져오기 줄 없음(대신 '구글에만 있음 — 지울까요' 기본 체크, 261122-17), 값이 다르면 '구글 고침'
C '#' — 예전 구글에 있던 사람(구글 출처·예전 짝·그와 같은 휴대폰)은 # 없이, 나머지는 #, 사람 표시가 먼저
D 미리보기 창 체크 '명함 기준으로 올리기' 를 켜면 다시 계획(창 [반영] 전엔 안 바뀜)
"""
import os, sys, tempfile, time, copy, itertools
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QPoint
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_cardfirst_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_cardfirst_"))
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


class FakeApi:
    def __init__(self):
        self.people, self.n = {}, itertools.count(100)

    def list_people(self):
        return [copy.deepcopy(p) for p in self.people.values()]

    def create(self, p):
        rn = "people/n%d" % next(self.n)
        q = dict(copy.deepcopy(p), resourceName=rn, etag="e1",
                 metadata={"sources": [{"type": "CONTACT", "updateTime": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())}]})
        self.people[rn] = q
        return copy.deepcopy(q)

    def update(self, rn, p):
        q = self.people[rn]
        q.update({k: copy.deepcopy(v) for k, v in p.items() if k != "etag"})
        return copy.deepcopy(q)

    def delete(self, rn):
        self.people.pop(rn, None)


def person(rn, name, cells=(), when="2020-01-01T00:00:00.000Z"):
    return {"resourceName": rn, "etag": "e", "names": [{"unstructuredName": name}],
            "phoneNumbers": [{"value": c, "type": "mobile"} for c in cells],
            "metadata": {"sources": [{"type": "CONTACT", "updateTime": when}]}}


try:
    st = S.BizcardStore(TMP / "local" / "bizcard.db")
    api = FakeApi()
    # 예전 싱크로 짝지은 명함 둘(구글에서 들어온 것 하나·명함에서 올린 것 하나)
    api.people["people/g1"] = person("people/g1", "가짜구글", ["010-0000-1111"])
    api.people["people/g2"] = person("people/g2", "가짜올림", ["010-0000-2222"])
    G.apply(st, api, [{"kind": G.NEW_CARD, "card_id": 0, "rn": "people/g1", "name": ""}], people=api.list_people())
    c2 = P._insert_contact(st, {"name": "가짜올림", "phones": [("cell", "010-0000-2222")]}, ["명함"])
    st.con.commit()
    G.apply(st, api, [r for r in G.plan(st, api.list_people()) if r["kind"] == "link"], people=api.list_people())
    lk = {l["rn"]: cid for cid, l in G.links(st).items()}
    c1 = lk.get("people/g1")
    chk(c1 and lk.get("people/g2") == c2, "(전제) 짝 둘", str(lk))
    # 구글 출처 vCard 명함(짝 없음)·그와 같은 휴대폰의 명함·처음 보는 사람
    P.apply_import(st, [{"name": "가짜브이", "phones": [("cell", "010-0000-3333")], "emails": [], "urls": []}], "주소록", "google")
    c4 = P._insert_contact(st, {"name": "가짜같은폰", "phones": [("cell", "010-0000-3333")]}, ["명함"])
    c5 = P._insert_contact(st, {"name": "가짜새사람", "phones": [("cell", "010-0000-5555")]}, ["명함"])
    c6 = P._insert_contact(st, {"name": "가짜표시", "phones": [("cell", "010-0000-6666")]}, ["명함"])
    G.kakao_set(st, [c6], False)
    st.con.commit()
    c3 = st.con.execute("SELECT id FROM cards WHERE name='가짜브이'").fetchone()[0]
    api.people.clear()                                    # 사용자가 구글 연락처를 통째로 지움
    api.people["people/z9"] = person("people/z9", "가짜구글만", ["010-0000-9999"], when=time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()))

    # ── A ──
    print("=== A. 명함 기준으로 올리기 ===")
    try:
        rows = G.plan(st, api.list_people(), card_first=True)
    except TypeError:
        rows = None
    chk(rows is not None, "A plan(card_first=True) 가 있다")
    rows = rows or []
    kinds = {(r["kind"], r.get("card_id")) for r in rows}
    chk((G.NEW_GOOGLE, c1) in kinds and (G.NEW_GOOGLE, c2) in kinds and not any(r["kind"] == G.GONE_GOOGLE for r in rows),
        "A 짝 있던 명함은 '구글에서 지워짐' 대신 '새 연락처'로 다시", str(sorted(kinds, key=str)))
    chk(not any(r["kind"] in (G.NEW_CARD, G.TO_CARD, G.KAKAO_DOWN, G.PHOTO_DOWN) for r in rows) and all(G.row_default(r) for r in rows),
        "B 구글 → 명함 줄 없음·모두 처음 체크(구글에 이미 있을 수 있음 끔 안 함)", str([(r["kind"], r.get("maybe_dup")) for r in rows]))

    # ── C ──
    print("\n=== C. '#' 기준 ===")
    kk = {r["card_id"]: r.get("kakao") for r in rows if r["kind"] == G.NEW_GOOGLE}
    chk(kk.get(c1) is False and kk.get(c2) is False and kk.get(c3) is False and kk.get(c4) is False,
        "C 예전 구글에 있던 사람(구글 출처·예전 짝·그와 같은 휴대폰)은 # 없이", str(kk))
    chk(kk.get(c5) is True and kk.get(c6) is False, "C 처음 보는 사람은 #, 사람 표시(해제)가 먼저", str(kk))

    res = G.apply(st, api, rows, people=api.list_people())
    names = sorted(p["names"][0]["unstructuredName"] for p in api.people.values())
    # 261122-17(사용자 결정): 명함 기준이면 구글에만 있는 연락처는 '구글에만 있음 — 지울까요'(기본 체크) — 처음 체크대로 반영하면 지움
    chk(res["failed"] == 0 and "#가짜새사람" in names and "가짜구글" in names and "가짜구글만" not in names,
        "A 반영 — 구글에 다시 만들고(#는 새 사람만), 구글에만 있던 연락처는 '지울까요' 기본 체크로 지움", str(names))
    again = G.plan(st, api.list_people(), card_first=True)
    chk(not again, "A 다시 계획하면 바꿀 것 없음(새 짝)", str([(r["kind"], r.get("name")) for r in again]))
    plain = G.plan(st, api.list_people())
    chk(not plain, "A 보통 싱크도 바꿀 것 없음(명함 기준으로 올린 뒤 = 0)", str([r["kind"] for r in plain]))
    st.close()

    # ── D ──
    print("\n=== D. 미리보기 창 ===")
    from viewer.widgets.bizcard_gsync_dialog import GSyncDialog
    dlg = GSyncDialog(None, db=str(TMP / "local" / "bizcard.db"), start=False)
    cb = getattr(dlg, "chk_card_first", None)
    seen = []
    dlg.load = lambda: seen.append(getattr(dlg, "_card_first", None))
    if cb is not None:
        from PyQt6.QtTest import QTest
        dlg.show()
        t0 = time.monotonic()
        while time.monotonic() - t0 < 0.3:
            app.processEvents()
        QTest.mouseClick(cb, Qt.MouseButton.LeftButton, pos=QPoint(8, cb.height() // 2))
        app.processEvents()
    chk(cb is not None and cb.isChecked() and seen == [True], "D 체크 '명함 기준으로 올리기' 를 켜면 다시 계획",
        str((seen, cb.isChecked() if cb else None)))
    dlg.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외")
print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
