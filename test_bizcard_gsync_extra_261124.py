# -*- coding: utf-8 -*-
"""구글 추가 칸 싱크·세부내용 칸 추가·사진 링크 기본 켬 (명함찾기 SOT §5.24.1 '구글 추가 칸'·§5.29 '오가는 칸'·'추가 칸 처음'·'드라이브', 261122-25).
가짜 구글(메모리 안 — 고칠 칸(updatePersonFields)을 지킴)·가짜 명함(010-0000-…)만 — 실제 구글에 붙지 않는다(§2.1 의 7).

A 추가 칸을 받은 적 없는 명함 + 구글 생일·별명·관계·메신저·둘째 주소·사용자 칸 → '명함 고침 — 추가 칸'(처음 체크) → 명함에 받아 적음, 다시 싱크하면 바꿀 것 없음
B 명함에서 기념일을 더하면 → '구글 고침 — 추가 칸' → 구글 events(날짜·이름표), 다시 싱크하면 바꿀 것 없음
C 구글에서 별명을 바꾸면 → 명함 별명도
D 추가 칸을 받은 적 없는 명함을 '구글 고침'(직함) 해도 구글 추가 칸은 그대로(고칠 칸에서 뺌)
E 구글에서 새로 가져온 명함은 추가 칸까지
F 세부내용 — 값 있는 추가 칸만 줄로, [+] 메뉴로 생일·관계(이름표) 더하고 [저장] → 명함 DB, 비우면 지움
G 사진 링크(드라이브) 기본 켬, 끄면 꺼짐
"""
import os, sys, tempfile, copy, itertools, time
from datetime import datetime, timezone
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox, QInputDialog
from PyQt6.QtTest import QTest
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_gextra_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_gextra_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
from viewer.bizcard import people as P, store as S, gsync as G, gsync_api as GA
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


def pump(cond=lambda: False, timeout=5.0):
    t = time.monotonic()
    while time.monotonic() - t < timeout:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat().replace("+00:00", "Z")


class FakeApi:
    """구글처럼 — 고칠 칸(updatePersonFields)에 든 칸만 바꾸고(보내지 않은 칸은 지움), 그 밖 칸은 그대로. 고칠 때마다 시각을 지금으로."""
    def __init__(self):
        self.people, self.n, self.masks = {}, itertools.count(100), []

    def _touch(self, rn, later=0.0):
        self.people[rn]["metadata"] = {"sources": [{"type": "CONTACT", "updateTime": iso(time.time() + later)}]}
        self.people[rn]["etag"] = "e%d" % next(self.n)

    def list_people(self):
        return [copy.deepcopy(p) for p in self.people.values()]

    def _make(self, p):
        rn = "people/n%d" % next(self.n)
        self.people[rn] = dict(copy.deepcopy({k: v for k, v in p.items() if k != "etag" and v}), resourceName=rn)
        self._touch(rn)
        return copy.deepcopy(self.people[rn])

    def create(self, p):
        return self._make(p)

    def batch_create(self, persons):
        return [self._make(p) for p in persons]

    def update(self, rn, p, fields=GA.UPDATE_FIELDS):
        self.masks.append(fields)
        for f in fields.split(","):
            if p.get(f):
                self.people[rn][f] = copy.deepcopy(p[f])
            else:
                self.people[rn].pop(f, None)
        self._touch(rn)
        return copy.deepcopy(self.people[rn])

    def batch_update(self, persons, fields=GA.UPDATE_FIELDS):
        return {rn: self.update(rn, p, fields) for rn, p in persons.items()}

    def delete(self, rn):
        self.people.pop(rn, None)

    def list_groups(self):
        return []


def apply_default(st, api, rows):
    out = [r for r in rows if G.row_default(r)]
    out += [dict(r, kind="unlink", was=r["kind"]) for r in rows if not G.row_default(r) and r["kind"] in G.UNLINK_IF_KEPT]
    order = {k: n for n, k in enumerate(G.KINDS + ("link", "unlink"))}
    return G.apply(st, api, sorted(out, key=lambda r: order.get(r["kind"], 99)), "", people=api.list_people())


def changes(rows):
    return [(r["kind"], r["card_id"], tuple(r.get("fields") or [])) for r in rows if r["kind"] in (G.TO_CARD, G.TO_GOOGLE, G.GONE_VALUE)]


def ex(cid):
    return P.card_by_id(st, cid).get("extra")


try:
    st = S.BizcardStore(TMP / "local" / "bizcard.db")
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    P.src_init(st)
    a = P._insert_contact(st, {"name": "가짜갑", "phones": [("cell", "010-0000-1111")]}, ["명함"])
    st.con.commit()
    chk(ex(a) is None, "준비 — 옛 명함은 추가 칸을 받은 적 없음(NULL)")
    api = FakeApi()
    ga = api._make({"names": [{"unstructuredName": "가짜갑"}], "phoneNumbers": [{"value": "010-0000-1111", "type": "mobile"}],
                    "birthdays": [{"date": {"year": 1990, "month": 5, "day": 1}}], "nicknames": [{"value": "가짜별명"}],
                    "relations": [{"person": "가짜인", "type": "배우자"}], "imClients": [{"username": "fake_id", "protocol": "KakaoTalk"}],
                    "addresses": [{"formattedValue": ""}, {"formattedValue": "가짜시 가짜로 2", "type": "home"}],
                    "userDefined": [{"key": "혈액형", "value": "가짜형"}]})["resourceName"]

    print("=== A 처음 받아 적기 ===")
    rows = G.plan(st, api.list_people(), "")
    ch = changes(rows)
    row = next((r for r in rows if r["kind"] == G.TO_CARD and "extra" in (r.get("fields") or [])), None)
    chk(row is not None and G.row_default(row), "A '명함 고침 — 추가 칸'(처음 체크)", str(ch))
    chk(row is not None and "생일: 1990-05-01" in row["changes"][-1][2] and "관계 (배우자): 가짜인" in row["changes"][-1][2],
        "A 미리보기 옛 값 → 새 값에 '생일: …'·'관계 (배우자): …'", str(row and row["changes"]))
    apply_default(st, api, rows)
    got = ex(a) or []
    want = {("birthday", "", "1990-05-01"), ("nickname", "", "가짜별명"), ("relation", "배우자", "가짜인"), ("im", "KakaoTalk", "fake_id"),
            ("address", "home", "가짜시 가짜로 2"), ("custom", "혈액형", "가짜형")}
    chk({tuple(x) for x in got} == want, "A 명함에 추가 칸 여섯 줄", str(got))
    chk(api.people[ga].get("birthdays") and api.people[ga].get("userDefined"), "A 구글 추가 칸은 그대로")
    again = changes(G.plan(st, api.list_people(), ""))
    chk(not again, "A 다시 싱크하면 바꿀 것 없음", str(again))

    print("\n=== B 명함에서 기념일 더함 → 구글 ===")
    time.sleep(0.05)
    P.update_card(st, a, {"extra": got + [["event", "결혼기념일", "2015.10.10"]]})
    st.con.commit()
    rows = G.plan(st, api.list_people(), "")
    chk(changes(rows) == [(G.TO_GOOGLE, a, ("extra",))], "B '구글 고침 — 추가 칸' 한 건", str(changes(rows)))
    apply_default(st, api, rows)
    ev = api.people[ga].get("events") or []
    chk(ev == [{"date": {"year": 2015, "month": 10, "day": 10}, "type": "결혼기념일"}], "B 구글 기념일(날짜·이름표)", str(ev))
    chk(api.people[ga].get("birthdays") == [{"date": {"year": 1990, "month": 5, "day": 1}}] and
        [x.get("formattedValue") for x in api.people[ga].get("addresses") or []][1:] == ["가짜시 가짜로 2"],
        "B 나머지 추가 칸(생일·둘째 주소)도 구글에 그대로", str(api.people[ga].get("addresses")))
    again = changes(G.plan(st, api.list_people(), ""))
    chk(not again, "B 다시 싱크하면 바꿀 것 없음('2015.10.10' → 같은 날짜)", str(again))

    print("\n=== C 구글에서 별명 바꿈 → 명함 ===")
    time.sleep(0.05)
    api.people[ga]["nicknames"] = [{"value": "새별명"}]
    api._touch(ga, later=2.0)
    rows = G.plan(st, api.list_people(), "")
    chk(changes(rows) == [(G.TO_CARD, a, ("extra",))], "C '명함 고침 — 추가 칸'", str(changes(rows)))
    apply_default(st, api, rows)
    chk(("nickname", "", "새별명") in {tuple(x) for x in ex(a) or []}, "C 명함 별명도 바뀜", str(ex(a)))

    print("\n=== D 받은 적 없는 명함을 구글로 고쳐도 구글 추가 칸은 그대로 ===")
    b = P._insert_contact(st, {"name": "가짜을", "phones": [("cell", "010-0000-2222")]}, ["명함"])
    st.con.commit()
    gb = api._make({"names": [{"unstructuredName": "가짜을"}], "phoneNumbers": [{"value": "010-0000-2222", "type": "mobile"}],
                    "birthdays": [{"date": {"month": 3, "day": 4}}]})["resourceName"]
    apply_default(st, api, [r for r in G.plan(st, api.list_people(), "") if r["card_id"] == b])   # 짝 맺기
    st.con.execute("UPDATE cards SET extra=NULL WHERE id=?", (b,))   # 짝만 맺고 추가 칸은 받지 않은 모습
    st.con.commit()
    time.sleep(0.05)
    P.update_card(st, b, {"title": "가짜과장"})
    st.con.commit()
    rows = G.plan(st, api.list_people(), "")
    up = [r for r in rows if r["card_id"] == b and r["kind"] == G.TO_GOOGLE]
    api.masks.clear()
    G.apply(st, api, up, "", people=api.list_people())    # '명함 고침 — 추가 칸' 은 고르지 않고 '구글 고침' 만
    chk(up and api.people[gb].get("organizations", [{}])[0].get("title") == "가짜과장", "D 직함은 구글로", str(changes(rows)))
    chk(api.people[gb].get("birthdays") == [{"date": {"month": 3, "day": 4}}] and api.masks == [GA.UPDATE_BASE],
        "D 구글 생일은 그대로(고칠 칸에서 추가 칸을 뺌)", str((api.people[gb].get("birthdays"), api.masks)))
    chk(ex(b) is None, "D 명함은 여전히 '받은 적 없음'")
    chk(any(r["card_id"] == b and r["kind"] == G.TO_CARD and "extra" in r["fields"] for r in G.plan(st, api.list_people(), "")),
        "D 다음 싱크에 다시 '명함 고침 — 추가 칸' 으로 제안")

    print("\n=== E 구글에서 새로 가져온 명함 ===")
    gn = api._make({"names": [{"unstructuredName": "가짜병"}], "phoneNumbers": [{"value": "010-0000-3333", "type": "mobile"}],
                    "occupations": [{"value": "가짜직업"}]})["resourceName"]
    rows = [r for r in G.plan(st, api.list_people(), "") if r["kind"] == G.NEW_CARD]
    apply_default(st, api, rows)
    cn = next((cid for cid, l in G.links(st).items() if l["rn"] == gn), None)
    chk(cn is not None and ex(cn) == [["occupation", "", "가짜직업"]], "E 새 명함에 추가 칸(직업)", str(cn and ex(cn)))
    st.close()

    print("\n=== F 세부내용 ===")
    from viewer.widgets import bizcard_find_dialog as FD
    fd = FD.BizcardFindDialog(None, db=TMP / "local" / "bizcard.db")
    fd.resize(1200, 800)
    fd.show()
    pump(lambda: fd.table.rowCount() == 3)
    fd.table.setCurrentCell(fd.row_of_id(a), 0)
    pump(lambda: fd._card is not None and fd._card["id"] == a, timeout=3)
    gx = [(k, ed.text()) for g, k, ed in fd.extra_eds if g == "gextra"]
    chk(len(gx) == 7 and (("event", "결혼기념일"), "2015-10-10") in gx, "F 추가 칸 일곱 줄이 세부에", str(gx))
    fd.table.setCurrentCell(fd.row_of_id(b), 0)
    pump(lambda: fd._card is not None and fd._card["id"] == b, timeout=3)
    chk(not [1 for g, _k, _e in fd.extra_eds if g == "gextra"], "F 추가 칸 없는 명함은 줄 없음")
    menu = fd.btn_add_field.menu()
    names = [x.text() for x in menu.actions()]
    chk(names == ["생일", "별명", "기념일", "관계", "메신저", "주소", "직업", "사용자 칸"], "F [+] 메뉴 여덟 갈래", str(names))
    next(x for x in menu.actions() if x.text() == "생일").trigger()
    ed = next((e for g, k, e in fd.extra_eds if g == "gextra" and k[0] == "birthday"), None)
    if ed is not None:
        QTest.keyClicks(ed, "1985-01-02")
    QInputDialog.getText = staticmethod(lambda *a_, **k_: ("동생", True))
    next(x for x in menu.actions() if x.text() == "관계").trigger()
    ed2 = next((e for g, k, e in fd.extra_eds if g == "gextra" and k[0] == "relation"), None)
    if ed2 is not None:
        QTest.keyClicks(ed2, "fake-sibling")   # 오프스크린 QTest.keyClicks 로 한글을 치면 프로세스가 죽는다 — 값은 ASCII
    chk(fd._dirty and fd.save(), "F 입력 → [저장]")
    st2 = fd._store()
    got_b = {tuple(x) for x in P.card_by_id(st2, b).get("extra") or []}
    chk(got_b == {("birthday", "", "1985-01-02"), ("relation", "동생", "fake-sibling")}, "F 명함 DB 에 생일·관계(이름표)", str(got_b))
    fd.table.setCurrentCell(fd.row_of_id(b), 0)
    pump(timeout=0.3)
    ed3 = next((e for g, k, e in fd.extra_eds if g == "gextra" and k[0] == "relation"), None)
    if ed3 is not None:
        ed3.setFocus()
        ed3.selectAll()
        QTest.keyClick(ed3, Qt.Key.Key_Delete)
    fd.save()
    got_b2 = {tuple(x) for x in P.card_by_id(st2, b).get("extra") or []}
    chk(got_b2 == {("birthday", "", "1985-01-02")}, "F 비운 줄은 지움", str(got_b2))
    fd.ed_find.setText("fake-sibling")
    pump(timeout=0.8)
    fd.ed_find.setText("1985-01-02")
    pump(lambda: fd.table.rowCount() == 1, timeout=3)
    chk(fd.table.rowCount() == 1 and fd._card_at(0)["id"] == b, "F 추가 칸 값으로도 찾음", str(fd.table.rowCount()))

    print("\n=== G 사진 링크 기본 켬 ===")
    chk(G.drive_on(st2), "G 처음은 켬")
    st2.meta_set(G.OPT_DRIVE, False)
    chk(not G.drive_on(st2), "G 끄면 꺼짐")
    fd.close()
except Exception as e:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외", repr(e))
print("FAILURES: %d" % len(fails))
for f in fails:
    print("  -", f)
sys.stdout.flush()
os._exit(1 if fails else 0)
