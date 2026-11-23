# -*- coding: utf-8 -*-
"""명함 읽기 확인 표 — 머리말 정렬·지금 칸 테두리 (명함 SOT §5.10 '정렬'·'지금 칸') — 가짜 명함만(명함 SOT §2.1).

오프스크린, 실제 설정·데이터 폴더를 쓰지 않는다(검사 작성 SOT §14.7.2).
A. 머리말을 실제 마우스로 누르면 그 열 오름차순, 다시 누르면 내림차순(화살표), 빈 칸은 끝 — 표의 줄과 명함(_items)이 같이 옮겨짐
B. 고른 줄·미리 보기는 같은 명함을 따라감
C. 읽는 도중 정렬해도 결과가 맞는 줄에 들어감(배경 결과는 명함으로 찾음)
D. ←→ 로 칸을 옮기면 지금 칸에 테두리(같은 줄의 다른 칸과 픽셀이 다름)
"""
import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QPoint
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtTest import QTest
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
from PyQt6.QtWidgets import QStyleFactory
if "windows11" in [k.lower() for k in QStyleFactory.keys()]:
    app.setStyle("windows11")                       # 앱이 쓰는 스타일 — 기본(Fusion)은 점선 초점 틀이 있어 D 를 못 가린다
QCoreApplication.setApplicationName("polypdf_bizcard_sort_%d" % os.getpid())
fails = []
TMP = Path(tempfile.mkdtemp(prefix="bizcard_sort_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def pump(cond=None, timeout=15.0):
    t = time.monotonic()
    while time.monotonic() - t < timeout:
        app.processEvents()
        if cond is not None and cond():
            return True
        if cond is None and time.monotonic() - t > 0.3:
            return True
        time.sleep(0.01)
    return False


def finish():
    print("FAILURES: %d" % len(fails))
    for f in fails:
        print("  -", f)
    sys.stdout.flush()
    os._exit(1 if fails else 0)


NAMES = [("라마바", "김철수"), ("가나다", "홍길동"), ("사아자", "이영희"), ("차카타", "박민수"), ("파하", "")]


def make(folder):
    from PIL import Image
    folder.mkdir()
    for i, (co, nm) in enumerate(NAMES):
        Image.new("RGB", (339, 186), (200 + i * 10, 220, 240)).save(folder / ("%s_%s_1.jpg" % (co, nm or "x")))


try:
    from viewer.bizcard import recognize as R
    SLOW = {"on": False}

    def fake(path, ui_lang="ko"):
        if SLOW["on"]:
            time.sleep(0.25)
        hn, hc = R.parse_hint(path)
        hn = "" if hn in ("x", None) else hn
        return R.CardResult(name=hn, company=hc, phones=[("cell", "010-0000-0009")], emails=["user@example.com"],
                            name_cands=[R.Cand(hn, 4.0)] if hn else [], company_cands=[R.Cand(hc, 2.0)], langs=("한글",),
                            back_promo=None, need_check=())
    R.recognize = fake
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    from viewer.widgets import bizcard_import_dialog as BD
    F = TMP / "cards"
    make(F)
    dlg = BD.BizcardImportDialog(str(F), None, db=TMP / "local" / "b.db")
    dlg.resize(1300, 700)
    dlg.show()
    dlg.activateWindow()
    pump(lambda: dlg.bar.value() == 5 and not dlg._pending, timeout=30)
    t = dlg.table
    hh = t.horizontalHeader()

    def click_head(col):
        x = hh.sectionViewportPosition(col) + hh.sectionSize(col) // 2
        QTest.mouseClick(hh.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(x, hh.height() // 2))
        pump(None)

    def names():
        return [t.item(r, BD.C_NAME).text() for r in range(t.rowCount())]

    def consistent():
        return all(t.item(r, BD.C_NAME).text() == (R.parse_hint(dlg._items[r].front)[0] or "").replace("x", "")
                   for r in range(t.rowCount()))

    print("=== A·B. 머리말 정렬 ===")
    r_kim = names().index("김철수")
    t.setFocus()
    t.setCurrentCell(r_kim, BD.C_NAME)
    pv_before = dlg._items[r_kim]
    click_head(BD.C_NAME)
    chk(names() == ["김철수", "박민수", "이영희", "홍길동", ""], "A 이름 머리말 — 오름차순, 빈 칸은 끝", repr(names()))
    chk(hh.isSortIndicatorShown() and hh.sortIndicatorSection() == BD.C_NAME
        and hh.sortIndicatorOrder() == Qt.SortOrder.AscendingOrder, "A 머리말에 화살표(오름)")
    chk(consistent(), "A 표의 줄과 명함이 같이 옮겨짐")
    chk(t.currentRow() >= 0 and dlg._items[t.currentRow()] is pv_before and t.item(t.currentRow(), BD.C_NAME).text() == "김철수",
        "B 고른 줄은 같은 명함(김철수)을 따라감", str(t.currentRow()))
    click_head(BD.C_NAME)
    chk(names() == ["홍길동", "이영희", "박민수", "김철수", ""] and hh.sortIndicatorOrder() == Qt.SortOrder.DescendingOrder,
        "A 다시 누르면 내림차순(빈 칸은 그래도 끝)", repr(names()))
    click_head(BD.C_COMP)
    comps = [t.item(r, BD.C_COMP).text() for r in range(t.rowCount())]
    chk(comps == sorted(comps) and consistent(), "A 다른 머리말(회사) — 그 열 오름차순", repr(comps))

    print("\n=== C. 읽는 도중 정렬 ===")
    G = TMP / "cards2"
    make(G)
    SLOW["on"] = True
    d2 = BD.BizcardImportDialog(str(G), None, db=TMP / "local" / "b2.db")
    d2.show()
    pump(lambda: d2.bar.value() >= 1, timeout=10)
    t2 = d2.table
    hh2 = t2.horizontalHeader()
    x = hh2.sectionViewportPosition(BD.C_DATE) + 5
    QTest.mouseClick(hh2.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(x, hh2.height() // 2))
    QTest.mouseClick(hh2.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(x, hh2.height() // 2))  # 내림 — 차례를 뒤집음
    mid = d2.bar.value()
    pump(lambda: d2._worker.done_event.is_set() and not d2._pending, timeout=30)
    ok = all(t2.item(r, BD.C_NAME).text() == (R.parse_hint(d2._items[r].front)[0] or "").replace("x", "")
             and t2.item(r, BD.C_COMP).text() == R.parse_hint(d2._items[r].front)[1] for r in range(t2.rowCount()))
    chk(mid < 5 and ok, "C 읽는 도중(%d/5) 정렬해도 결과가 그 명함 줄에" % mid,
        repr([(t2.item(r, BD.C_COMP).text(), Path(d2._items[r].front).name) for r in range(t2.rowCount())]))
    SLOW["on"] = False
    d2.close()

    print("\n=== D. 지금 칸 테두리 ===")
    dlg.raise_()
    dlg.activateWindow()                             # 두 번째 창을 닫은 뒤 — 키보드로 옮길 때처럼 표가 포커스를 갖게
    pump(lambda: dlg.isActiveWindow(), timeout=3)
    t.setFocus()
    t.setCurrentCell(0, BD.C_NAME)
    pump(None)
    QTest.keyClick(t, Qt.Key.Key_Right)
    pump(None)
    chk(t.currentColumn() == BD.C_COMP and t.currentRow() == 0, "D → 로 지금 칸이 회사로", "%d %d" % (t.currentRow(), t.currentColumn()))
    def edge(img, col):
        """칸 왼쪽 안쪽 세로 띠(테두리 자리)의 색들 — 같은 칸이 지금 칸일 때와 아닐 때 비교."""
        r = t.visualRect(t.model().index(0, col))
        return [img.pixelColor(r.left() + dx, r.center().y()).name() for dx in (1, 2, 3)]
    img = t.viewport().grab().toImage()
    comp_cur, dept_not = edge(img, BD.C_COMP), edge(img, BD.C_DEPT)
    QTest.keyClick(t, Qt.Key.Key_Right)
    pump(None)
    img2 = t.viewport().grab().toImage()
    comp_not, dept_cur = edge(img2, BD.C_COMP), edge(img2, BD.C_DEPT)
    chk(comp_cur != comp_not, "D 지금 칸(회사)에 테두리 — 지금 칸이 아닐 때와 다름", "%s %s" % (comp_cur, comp_not))
    chk(dept_cur != dept_not and t.currentColumn() == BD.C_DEPT, "D 한 칸 더 옮기면 테두리도 옮겨 감(부서)",
        "%s %s" % (dept_cur, dept_not))
    dlg.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "예외 없이 끝남")
finish()
