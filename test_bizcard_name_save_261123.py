# -*- coding: utf-8 -*-
"""명함 성명 바꿔 저장·'명함 있음' 거르기·명단 관리 '명함 사진 2장 이상' (명함 SOT §5.9 '저장'·§5.24.1 '구분'·§5.32, 261122-5)
— 가짜 명함(010-0000-…)·임시 폴더만.

A. 그림 파일이 없어진 명함(DB 경로만 남음)은 '명함 있음' 이 아니라 '명함 없음'(한글+명함 있음으로 거르면 빠짐)
B. 성명을 영어로 바꿔 [저장] — 새 이름이 파일 잃은 묵은 행의 경로와 겹쳐도 저장됨(다른 이름 ` (2)`), 저장 확인이 되풀이되지 않음
C. DB 고침이 실패하면 바꾼 파일 이름을 되돌리고 알림, 칸은 그대로 남아 다시 [저장] 하면 됨(DB 잠김 없음)
D. 명단 관리 보기 `명함 사진 2장 이상` — 인물 폴더의 명함 모양 그림 2장 이상만(앞·뒷면·얼굴 사진 빼고), 이유 칸 '명함 사진 n장'(261122-18)
"""
import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtTest import QTest
from pathlib import Path
from PIL import Image

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_namesave_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_namesave_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
ASKED, WARNED, ERRS = [], [], []
QMessageBox.question = staticmethod(lambda *a, **k: (ASKED.append(1), QMessageBox.StandardButton.Save)[1])
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: (WARNED.append(1), QMessageBox.StandardButton.Ok)[1])
sys.excepthook = lambda t, v, tb: ERRS.append(repr(v))   # 슬롯 예외 — 종전 코드는 저장 중 예외로 끝났다
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


def pump(cond, timeout=10.0):
    t = time.monotonic()
    while time.monotonic() - t < timeout:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


def num(n):
    return "010-0000-%04d" % (n * 1111)


def finish():
    print("FAILURES: %d" % len(fails))
    for f in fails:
        print("  -", f)
    sys.stdout.flush()
    os._exit(1 if fails else 0)


try:
    from viewer.bizcard import people as P, store as S, roster as RS
    OUT = TMP / "cards" / "정리"
    OUT.mkdir(parents=True)
    db = TMP / "local" / "bizcard.db"
    st = S.BizcardStore(db)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    P.src_init(st)
    f_a = OUT / "가짜갑_가짜사.jpg"
    Image.new("RGB", (300, 180), "white").save(f_a)
    a = st.upsert({"front": str(f_a), "name": "가짜갑", "company": "가짜사", "phones": [("cell", num(1))]})
    lost = st.upsert({"front": str(OUT / "Fake Kim_가짜사.jpg"), "name": "가짜을", "company": "가짜사",   # 파일 잃은 묵은 행
                      "phones": [("cell", num(2))]})
    P._insert_contact(st, {"name": "가짜병", "phones": [("cell", num(3))]}, ["명함"])       # 그림 없는 명함
    st.con.commit()
    st.close()
    settings_store.set_picture_prefs({"bizcard_folder": str(TMP / "cards")})

    from viewer.widgets import bizcard_find_dialog as FD
    fd = FD.BizcardFindDialog(None, db=db)
    fd._bz_folder = str(TMP / "cards")
    fd.show()
    pump(lambda: fd.table.rowCount() == 3)

    print("=== A 그림 파일을 잃은 명함 ===")
    names = lambda: sorted(c["name"] for c in fd._rows)          # noqa: E731
    fd.cb_kind.set_keys(["ko", "card"])
    fd._on_kind()
    pump(lambda: len(fd._rows) != 3, timeout=3)
    chk(names() == ["가짜갑"], "A 한글+명함 있음 — 그림 파일이 있는 명함만(파일 잃은 '을'·그림 없는 '병' 빠짐)", str(names()))
    fd.cb_kind.set_keys(["nocard"])
    fd._on_kind()
    pump(lambda: names() != ["가짜갑"], timeout=3)
    chk(names() == ["가짜병", "가짜을"], "A 명함 없음 — 파일 잃은 명함도", str(names()))
    fd.cb_kind.set_keys(["all"])
    fd._on_kind()
    pump(lambda: len(fd._rows) == 3, timeout=3)

    print("\n=== B 성명을 영어로 바꿔 저장 ===")
    fd.table.setCurrentCell(fd.row_of_id(a), 0)
    pump(lambda: fd._card and fd._card["id"] == a, timeout=3)
    ed = fd.eds["name"]
    ed.setFocus()
    ed.selectAll()
    QTest.keyClicks(ed, "Fake Kim")
    QTest.mouseClick(fd.btn_save, Qt.MouseButton.LeftButton)
    pump(lambda: False, timeout=0.5)
    st = S.BizcardStore(db)
    row = P.card_by_id(st, a)
    st.close()
    chk(not ERRS and not fd._dirty and not fd.btn_save.isEnabled(), "B [저장] 이 끝까지(예외 없음·고침 표시 꺼짐)", str(ERRS))
    chk(row["name"] == "Fake Kim" and os.path.exists(row["front"])
        and os.path.normcase(row["front"]) != os.path.normcase(str(OUT / "Fake Kim_가짜사.jpg")),
        "B DB 이름·앞면 — 묵은 행 경로를 피한 새 파일(` (2)`)", str(row and os.path.basename(row["front"])))
    chk(not f_a.exists() and fd.eds["name"].text() == "Fake Kim", "B 옛 파일 이름은 없어지고 칸은 새 이름")
    ASKED.clear()
    fd.table.setCurrentCell(fd.row_of_id(lost), 0)
    pump(lambda: fd._card and fd._card["id"] == lost, timeout=3)
    chk(not ASKED, "B 다른 줄로 가도 저장할까 묻지 않음")

    print("\n=== C DB 고침 실패 — 파일 이름 되돌림 ===")
    fd.table.setCurrentCell(fd.row_of_id(a), 0)
    pump(lambda: fd._card and fd._card["id"] == a, timeout=3)
    front_c = fd._card["front"]
    real0 = P._real(front_c)
    _upd = P.update_card
    import sqlite3

    def bad_update(*a_, **k_):
        raise sqlite3.IntegrityError("fake")
    P.update_card = bad_update
    try:
        ed.setFocus()
        ed.selectAll()
        QTest.keyClicks(ed, "Fake Park")
        WARNED.clear()
        ERRS.clear()
        QTest.mouseClick(fd.btn_save, Qt.MouseButton.LeftButton)
        pump(lambda: False, timeout=0.5)
    finally:
        P.update_card = _upd
    chk(not ERRS and WARNED and fd._dirty and os.path.exists(real0)
        and not any(n.startswith("Fake Park") for n in os.listdir(OUT)),
        "C 알리고, 바꾼 파일 이름은 되돌림·고친 칸은 남음", "%s %s %s" % (ERRS, WARNED, sorted(os.listdir(OUT))))
    QTest.mouseClick(fd.btn_save, Qt.MouseButton.LeftButton)
    pump(lambda: False, timeout=0.5)
    st = S.BizcardStore(db)
    row = P.card_by_id(st, a)
    st.close()
    chk(not fd._dirty and row["name"] == "Fake Park" and os.path.basename(P._real(row["front"])).startswith("Fake Park"),
        "C 다시 [저장] 하면 저장됨(DB 잠김 없음)", str(ERRS))

    print("\n=== E 고친 뒤 다른 줄을 누르고 '저장' — 누른 명함이 열림(다시 정렬돼도) ===")
    c_id = next(c["id"] for c in fd._rows if c["name"] == "가짜병")
    fd.table.setCurrentCell(fd.row_of_id(a), 0)
    pump(lambda: fd._card and fd._card["id"] == a, timeout=3)
    order0 = [c["id"] for c in (fd._card_at(i) for i in range(fd.table.rowCount()))]
    ed.setFocus()
    ed.selectAll()
    from PyQt6.QtGui import QInputMethodEvent
    ev = QInputMethodEvent("", [])
    ev.setCommitString("힣가짜")                          # 이름 차례가 바뀌는 고침(맨 뒤로) — 한글은 IME 꼴로(검사 작성 SOT §14.7.2 의 24)
    QApplication.sendEvent(ed, ev)
    ASKED.clear()
    r_click = fd.row_of_id(c_id)
    fd.table.setCurrentCell(r_click, 0)                  # 저장 안 한 채 다른 줄 → 묻기(저장)
    pump(lambda: False, timeout=0.5)
    order1 = [c["id"] for c in (fd._card_at(i) for i in range(fd.table.rowCount()))]
    chk(ASKED and order0 != order1, "E (전제) 묻고 저장 — 목록 차례가 바뀜", "%s %s" % (order0, order1))
    chk(fd._card and fd._card["id"] == c_id and fd.eds["name"].text() == "가짜병",
        "E 누른 명함('병')이 열림 — 같은 줄 번호의 다른 명함이 아님", str(fd._card and fd._card["name"]))
    e2 = fd.eds["title"]
    e2.setFocus()
    e2.selectAll()
    QTest.keyClicks(e2, "Boss")
    QTest.mouseClick(fd.btn_save, Qt.MouseButton.LeftButton)
    pump(lambda: False, timeout=0.5)
    st = S.BizcardStore(db)
    chk(P.card_by_id(st, c_id)["title"] == "Boss" and (P.card_by_id(st, a)["title"] or "") == "",
        "E 다음 고침은 누른 명함에 저장(엉뚱한 명함 아님)")
    st.close()

    print("\n=== D 명단 관리 '명함 사진 2장 이상' — 인물 폴더에 명함 모양 그림 2장 이상(261122-18) ===")
    st = fd._store()
    same = [P._insert_contact(st, {"name": "가짜무", "phones": [("cell", num(10 + i))]}, ["명함"]) for i in range(3)]   # 이름만 같음 — 아님
    fold = TMP / "cards"

    def img_card(nm, back, wide, tall):
        f = OUT / ("%s_가짜사.jpg" % nm)
        Image.new("RGB", (300, 180), "white").save(f)
        b = ""
        if back:
            b = str(OUT / ("%s_가짜사_뒷면.jpg" % nm))
            Image.new("RGB", (300, 180), "gray").save(b)
        cid = st.upsert({"front": str(f), "back": b, "name": nm, "company": "가짜사"})
        for size in [(340, 200)] * wide + [(60, 80)] * tall:     # 명함 모양(넓음)·얼굴 사진(세로)
            pp = P.next_photo_path(P.photo_front(P.card_by_id(st, cid), str(fold)))
            pp.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", size, "red").save(pp)
        return cid
    three = img_card("가짜삼", True, 3, 1)               # 인물 폴더에 명함 모양 3 + 얼굴 1 → 3장
    two = img_card("가짜사", False, 2, 0)                # 명함 모양 2 → 2장
    one = img_card("가짜하나", True, 1, 2)               # 앞·뒤 + 명함 모양 1 + 얼굴 2 → 아님(앞·뒷면은 세지 않음)
    faces = img_card("가짜얼굴", True, 0, 3)             # 얼굴 사진만 3 → 아님
    st.con.commit()
    got = RS.many_cards(RS.all_cards(st), str(fold))
    chk([(c["id"], n) for c, n in got] == [(three, 3), (two, 2)],
        "D 인물 폴더의 명함 모양 그림 2장 이상만(많은 차례) — 앞·뒷면·얼굴 사진·이름만 같은 명단은 세지 않음", str([(c["name"], n) for c, n in got]))
    rd = fd.open_roster(exec_=False)
    pump(lambda: not rd.loading, timeout=10)
    rd.set_view("many")
    pump(lambda: not rd.loading and rd.view() == "many" and rd.tree.topLevelItemCount() == 2, timeout=10)
    whys = [rd.tree.topLevelItem(i).text(rd.tree.columnCount() - 1) for i in range(rd.tree.topLevelItemCount())]
    chk(whys == ["명함 사진 3장", "명함 사진 2장"] and rd.cmb_view.itemText(rd.cmb_view.findData("many")) == "명함 사진 2장 이상",
        "D 보기 갈래 '명함 사진 2장 이상' — 이유 칸 '명함 사진 n장'", str(whys))
    chk([rd.cmb_view.itemData(i) for i in range(rd.cmb_view.count())] == ["all", "multi", "many", "vcf"],
        "D '010 둘 이상' 바로 옆 자리")
except Exception as e:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외", repr(e))
finish()
