# -*- coding: utf-8 -*-
"""261115-29: 2단 오른쪽에 컷을 띄운 채 왼쪽 PDF 를 저장해도 컷 칸은 그대로 (책갈피창·저장 SOT §4.7.20 '그림 칸은 비우지 않는다').

사용자 보고: "스크린샷 관련하여 2단에 있을 경우, 1단으로 마우스를 옮기면, 2단이 회색으로 보여. 다시 2단을 찍으면 원래의 화면이 보여."
원인: 저장 길의 `_close_main_view_doc` 가 그림 칸도 비우고 `_restore_other_panes` 는 PDF 칸만 되살렸다.

A. 컷을 실제로 눌러 오른쪽에 띄우고, 왼쪽 칸을 실제로 눌러 옮긴 뒤 편집 모드에서 책갈피 [저장] → 오른쪽은 그 컷 그대로(그림·픽셀)
B. 그 뒤 오른쪽 칸에서 ↓ 키 → 다음 컷 (그림 모드가 살아 있다)
C. 왼쪽은 저장한 PDF 를 다시 연 채
(수정 전 코드: A·B 실패)
"""
import os, sys, tempfile, shutil, faulthandler
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(240, exit=True)
from pathlib import Path

import fitz
from PyQt6.QtCore import QStandardPaths, Qt, QPoint
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QImage, QColor
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
from PyQt6.QtCore import QCoreApplication
QCoreApplication.setApplicationName("polypdf_shotkeep_%d" % os.getpid())   # 검사 작성 SOT §14.7.2 의 3
import modal_guard
modal_guard.install(label=lambda: "컷 칸 유지", echo=False)                  # §14.7.2 의 6
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def spin(n=10, ms=20):
    for _ in range(n):
        app.processEvents(); QTest.qWait(ms)


def center_color(mv):
    img = mv.grab().toImage()
    return img.pixelColor(img.width() // 2, img.height() // 2).name()


errs = []
sys.excepthook = lambda t, v, tb: errs.append(f"{t.__name__}: {v}")
root = Path(tempfile.mkdtemp(prefix="polypdf_shotkeep_"))
try:
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    import test_fixtures as _TFX; _TFX.autotag_off()
    from viewer.app import MainWindow
    from viewer.history import HistoryItem
    mw = MainWindow(); mw.resize(1300, 850); mw.show(); app.processEvents()
    fo = root / "fo"; fo.mkdir()
    d = fitz.open()
    for i in range(3):
        d.new_page().insert_text((72, 72), f"A {i}")
    d.set_toc([[1, "ch1", 1], [1, "ch2", 2]])
    d.save(str(fo / "A.pdf")); d.close()
    mw.open_folder(fo); spin(20)
    mw._load_main(HistoryItem(str(fo / "A.pdf"), 0, "", "bookmark"), sync=True); spin(10)
    cuts = []
    for nm, col in (("s1", "#ff0000"), ("s2", "#00a000")):
        img = QImage(400, 300, QImage.Format.Format_RGB32); img.fill(QColor(col))
        p = root / f"261115_2214_{nm}.png"; img.save(str(p), "PNG"); cuts.append(str(p))
        mw.shot_strip.add_item(str(p), kind="image", label=p.stem, prepend=False)
    spin(10)
    st = mw.shot_strip
    QTest.mouseClick(st.list.viewport(), Qt.MouseButton.LeftButton, pos=st.list.visualItemRect(st.list.item(0)).center()); spin(20)
    chk(center_color(mw._mv[1]) == "#ff0000", "준비 — 컷 s1 이 오른쪽에", center_color(mw._mv[1]))

    vp0 = mw._mv[0].view.viewport()
    QTest.mouseClick(vp0, Qt.MouseButton.LeftButton, pos=QPoint(vp0.width() // 2, vp0.height() // 2)); spin(20)
    chk(mw._active_pane == 0, "준비 — 왼쪽 칸을 눌러 옮김")
    bt = mw.bookmark_tree
    bt.btn_edit.setChecked(True); spin(10)
    node = next(x for x in bt._iter_file_nodes() if x.childCount())
    node.child(0).setText(0, "ch1-renamed"); bt._dirty = True
    bt._op_save(); spin(40)

    # ── A ──
    chk(getattr(mw._mv[1], "_is_image", False) and mw._mv[1]._page_item is not None, "A 저장 뒤에도 오른쪽은 그림 칸")
    chk(center_color(mw._mv[1]) == "#ff0000", "A 저장 뒤에도 오른쪽은 컷 s1(회색 아님)", center_color(mw._mv[1]))
    # ── C ──
    chk(Path(str(mw._mv[0].current_file())).name == "A.pdf", "C 왼쪽은 저장한 PDF", str(mw._mv[0].current_file()))
    # ── B ──
    vp1 = mw._mv[1].view.viewport()
    QTest.mouseClick(vp1, Qt.MouseButton.LeftButton, pos=QPoint(vp1.width() // 2, vp1.height() // 2)); spin(10)
    QTest.keyClick(mw._mv[1].view, Qt.Key.Key_Down); spin(20)
    chk(getattr(mw, "_current_shot_path", None) == cuts[1] and center_color(mw._mv[1]) == "#00a000",
        "B 저장 뒤 ↓ → 다음 컷 s2", f"{getattr(mw, '_current_shot_path', None)} {center_color(mw._mv[1])}")

    chk(not errs, "예외 없음", str(errs))
    bt.btn_edit.setChecked(False); spin(5)
    mw.close(); spin(5)
finally:
    shutil.rmtree(root, ignore_errors=True)

print("FAILS:", len(fails))
sys.exit(1 if fails else 0)
