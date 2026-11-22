# -*- coding: utf-8 -*-
"""명함찾기 아래 줄·'#' 풀다운 (명함 SOT §5.24.1 '아래 줄'·'# 풀다운'·'≡ 메뉴', 261120-66) — 가짜 명함·임시 DB 만(§2.1).

A 아래 단추 줄 없음 — 종전 단추 다섯 항목은 ≡ 메뉴에(주소록은 하위 메뉴), 명함 보기는 그림 없는 명함이면 흐림
B (261120-75 에 없앰 — 해시태그는 세부 칸, test_bizcard_layout_261122)
C '#' 풀다운 — 단추 글 '#', 속성(옵션)·주제(체크)·개수, #명함 없음, 체크 = 찾기 칸 #태그(목록이 그만큼), 단추 '#n',
  둘째 체크 = 그리고, 풀면 빠짐, 맨 아래 '찾기 비우기'·'해시태그 수정'
"""
import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QPoint
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox, QPushButton, QCheckBox, QRadioButton
from PyQt6.QtTest import QTest
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_bottom_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_bottom_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
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


try:
    from viewer.bizcard import people as P, store as S
    db = TMP / "local" / "bizcard.db"
    st = S.BizcardStore(db)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    a = P._insert_contact(st, {"name": "가짜일", "company": "가짜사", "phones": [("cell", "010-0000-0001")]}, ["명함", "한글", "가짜사"])
    b = P._insert_contact(st, {"name": "가짜이", "company": "가짜사", "phones": [("cell", "010-0000-0002")]}, ["명함", "한글", "가짜사", "골프"])
    c = P._insert_contact(st, {"name": "Fake Three", "phones": [("cell", "010-0000-0003")]}, ["명함", "영어", "골프"])
    st.con.commit()
    st.close()

    from viewer.widgets import bizcard_find_dialog as FD
    fd = FD.BizcardFindDialog(None, db=db)
    fd.resize(1100, 760)
    fd.show()
    pump(lambda: fd.table.rowCount() == 3)

    # ── A ──
    print("=== A. 아래 단추 없음·≡ 메뉴 ===")
    olds = ("새 명함 입력", "명함 관리", "중복 검토", "주소록", "명함 보기")
    vis = [w.text() for w in fd.findChildren(QPushButton) if w.isVisible() and w.text() in olds]
    chk(vis == [], "A 아래 단추 줄(새 명함 입력·명함 관리·중복 검토·주소록·명함 보기) 없음", str(vis))
    fd.main_menu.aboutToShow.emit()
    acts = [x for x in fd.main_menu.actions() if not x.isSeparator()]
    names = [x.text() for x in acts]
    chk(names == ["새 명함 입력", "중복 검토", "주소록", "명함 보기", "종료"], "A ≡ 메뉴 항목·차례(본 뷰어 없으면 명함 관리 없음)", str(names))
    sub = next((x.menu() for x in acts if x.text() == "주소록"), None)
    chk(sub is not None and "변경 기록·되살리기" in [x.text() for x in sub.actions()], "A 주소록은 하위 메뉴(가져오기·내보내기·싱크·변경 기록)",
        str(sub and [x.text() for x in sub.actions()]))
    en = {x.text(): x.isEnabled() for x in acts}
    chk(en.get("명함 보기") is False and en.get("새 명함 입력") is True, "A 그림 없는 명함 — 명함 보기 흐림", str(en))

    # ── B ── 고른 명단은 261120-75 에 없앰(해시태그는 세부 칸 — test_bizcard_layout_261122)

    print("\n=== C. '#' 풀다운 ===")
    bt = fd.btn_tags
    chk(bt.text() == "#" and bt.menu() is not None, "C 찾기 칸 옆 단추 '#' + 풀다운", repr(bt.text()))
    tm = bt.menu()

    def boxes():
        tm.hide()
        tm.popup(bt.mapToGlobal(bt.rect().bottomLeft()))          # 단추를 누른 것처럼 펼침(exec 대신 — 오프스크린에서 막히지 않게)
        pump(lambda: tm.isVisible(), timeout=2)
        out = {}
        for x in tm.actions():
            w = getattr(x, "defaultWidget", lambda: None)()
            if w is not None:
                for cb in w.findChildren(QCheckBox) + w.findChildren(QRadioButton):
                    out[cb.text()] = cb
        return out
    def hit(cb):                                                  # 체크 칸 네모 자리를 실제로 누름(글 오른쪽 빈자리는 누름이 아님)
        QTest.mouseClick(cb, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(7, cb.height() // 2))
    bx = boxes() if tm is not None else {}
    keys = sorted(bx)
    chk("#골프  (2)" in bx and "#가짜사  (2)" in bx and "#한글  (2)" in bx and "#영어  (1)" in bx
        and not any(k.startswith("#명함") for k in bx), "C 태그·개수(#명함 없음)", str(keys))
    chk(isinstance(bx.get("#한글  (2)"), QRadioButton) and isinstance(bx.get("#골프  (2)"), QCheckBox),
        "C 속성(한글·영어)은 옵션 단추, 주제는 체크 칸")
    if "#골프  (2)" in bx:
        hit(bx["#골프  (2)"])
        pump(lambda: fd.table.rowCount() == 2, timeout=3)
        chk("#골프" in fd.ed_find.text() and fd.table.rowCount() == 2 and bt.text() == "#1",
            "C 체크 = 찾기 칸 #골프·목록 2·단추 '#1'", str((fd.ed_find.text(), fd.table.rowCount(), bt.text())))
        bx = boxes()
        k = next((k for k in bx if k.startswith("#가짜사")), None)
        chk(bx.get("#골프  (2)") is not None and bx["#골프  (2)"].isChecked() and k == "#가짜사  (1)",
            "C 다시 열면 체크 복원·개수는 지금 목록 기준", str(sorted(bx)))
        if k:
            hit(bx[k])
            pump(lambda: fd.table.rowCount() == 1, timeout=3)
            chk(fd.table.rowCount() == 1 and bt.text() == "#2", "C 둘째 체크 = 그리고(골프·가짜사 → 1)", str((fd.ed_find.text(), fd.table.rowCount())))
        bx = boxes()
        hit(bx["#골프  (1)"] if "#골프  (1)" in bx else bx.get("#골프  (2)"))
        pump(lambda: "#골프" not in fd.ed_find.text() and fd.table.rowCount() == 2, timeout=3)
        chk("#골프" not in fd.ed_find.text() and fd.table.rowCount() == 2, "C 풀면 찾기 칸에서 빠짐", str((fd.ed_find.text(), fd.table.rowCount())))
    texts = [x.text() for x in tm.actions()] if tm is not None else []
    chk("찾기 비우기" in texts and "해시태그 수정" in texts and texts.index("해시태그 수정") > texts.index("찾기 비우기"),
        "C 맨 아래 '찾기 비우기'·'해시태그 수정'", str(texts))
    if "찾기 비우기" in texts:
        next(x for x in tm.actions() if x.text() == "찾기 비우기").trigger()
        pump(lambda: fd.table.rowCount() == 3, timeout=3)
        chk(fd.ed_find.text() == "" and bt.text() == "#", "C '찾기 비우기' — 칸 비움·단추 '#'", repr(fd.ed_find.text()))
    fd.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외")
print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
