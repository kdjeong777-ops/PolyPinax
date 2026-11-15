# -*- coding: utf-8 -*-
"""261115-30: 컷 칸에서 위아래로 가면 컷 끝에서 이전·다음 컷 — 아래 컷 목록 줄도 따라간다 (스크린샷 SOT §5).

사용자 보고: "2단의 화면에서 위아래로 옮길 때 스크린샷이 2개 있는데도, 다음 스크린샷으로 이동 안해"

A. 칸보다 긴 컷(폭 맞춤) — 실제 ↓ 키는 컷 안을 내리다 끝에서 다음 컷, 아래 목록 줄도 그 컷
B. 실제 ↑ 키 — 컷 맨 위에서 이전 컷
C. PgDn·PgUp 은 늘 컷 단위
D. 실제 휠 — 끝에 닿은 뒤 더 굴리면 다음 컷
E. 2단 오른쪽 컷을 둔 채 왼쪽 PDF 를 편집 모드에서 [저장]한 뒤에도 ↓·휠로 다음 컷(261115-29 가 그림 모드를 지킨다)
(수정 전 코드 — 261115-29 전: E 실패)
"""
import os, sys, tempfile, shutil, faulthandler
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(240, exit=True)
from pathlib import Path

import fitz
from PyQt6.QtCore import QStandardPaths, Qt, QPoint, QPointF
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QImage, QColor, QWheelEvent
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
from PyQt6.QtCore import QCoreApplication
QCoreApplication.setApplicationName("polypdf_shotstep_%d" % os.getpid())   # 검사 작성 SOT §14.7.2 의 3
import modal_guard
modal_guard.install(label=lambda: "컷 넘김", echo=False)                     # §14.7.2 의 6
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def spin(n=10, ms=20):
    for _ in range(n):
        app.processEvents(); QTest.qWait(ms)


errs = []
sys.excepthook = lambda t, v, tb: errs.append(f"{t.__name__}: {v}")
root = Path(tempfile.mkdtemp(prefix="polypdf_shotstep_"))
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
    for nm, col in (("s1", "#ff0000"), ("s2", "#00a000"), ("s3", "#0000ff")):
        img = QImage(400, 1200, QImage.Format.Format_RGB32); img.fill(QColor(col))   # 칸보다 긴 컷(스크롤 캡처처럼)
        p = root / f"261115_2214_{nm}.png"; img.save(str(p), "PNG"); cuts.append(str(p))
        mw.shot_strip.add_item(str(p), kind="image", label=p.stem, prepend=False)
    spin(10)
    st, rt = mw.shot_strip, mw.bookmark_tree_right
    mv = mw._mv[1]
    mv._img_fit = mv.FIT_WIDTH                     # 폭 맞춤 — 컷 안에 내릴 자리가 있다
    QTest.mouseClick(st.list.viewport(), Qt.MouseButton.LeftButton, pos=st.list.visualItemRect(st.list.item(0)).center()); spin(20)
    sb = mv.view.verticalScrollBar()
    chk(mw._current_shot_path == cuts[0] and sb.maximum() > sb.minimum(), "준비 — 긴 컷 s1, 컷 안에 내릴 자리", f"{sb.minimum()}..{sb.maximum()}")

    def shot():
        return Path(mw._current_shot_path).name if getattr(mw, "_current_shot_path", None) else None

    def row():
        it = rt.tree.currentItem()
        return Path(it.data(0, rt.DATA_FILE)).name if it is not None and it.data(0, rt.DATA_FILE) else None

    def press_until_change(key, limit=300):
        mv.view.setFocus()
        before, moved_in = mw._current_shot_path, False
        for _ in range(limit):
            v0 = sb.value()
            QTest.keyClick(mv.view, key); app.processEvents()
            if mw._current_shot_path != before:
                spin(5)
                return True, moved_in
            moved_in = moved_in or sb.value() != v0
        return False, moved_in

    def wheel(dy):
        vp = mv.view.viewport()
        pos = QPointF(vp.width() / 2, vp.height() / 2)
        ev = QWheelEvent(pos, QPointF(vp.mapToGlobal(pos.toPoint())), QPoint(0, 0), QPoint(0, dy),
                         Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(vp, ev)
        QTest.qWait(40)

    def wheel_until_change(dy, limit=200):
        before = mw._current_shot_path
        for _ in range(limit):
            wheel(dy)
            if mw._current_shot_path != before:
                spin(5)
                return True
        return False

    names = [Path(c).name for c in cuts]
    # ── A ──
    ok, moved_in = press_until_change(Qt.Key.Key_Down)
    chk(ok and moved_in and shot() == names[1], "A ↓ 는 컷 안을 내리다 끝에서 다음 컷 s2", f"{ok} {moved_in} {shot()}")
    chk(row() == names[1], "A 아래 컷 목록 줄도 s2", str(row()))
    # ── B ──
    ok, _ = press_until_change(Qt.Key.Key_Up)
    chk(ok and shot() == names[0], "B ↑ 는 컷 맨 위에서 이전 컷 s1", f"{ok} {shot()}")
    chk(row() == names[0], "B 아래 목록 줄 s1", str(row()))
    # ── C ──
    mv.view.setFocus(); QTest.keyClick(mv.view, Qt.Key.Key_PageDown); spin(10)
    chk(shot() == names[1] and row() == names[1], "C PgDn → 바로 다음 컷 s2", f"{shot()} {row()}")
    QTest.keyClick(mv.view, Qt.Key.Key_PageUp); spin(10)
    chk(shot() == names[0], "C PgUp → 이전 컷 s1", str(shot()))
    # ── D ──
    chk(wheel_until_change(-120) and shot() == names[1] and row() == names[1], "D 휠 아래 — 끝에서 더 굴리면 다음 컷 s2", f"{shot()} {row()}")
    chk(wheel_until_change(120) and shot() == names[0], "D 휠 위 — 이전 컷 s1", str(shot()))

    # ── E ── 왼쪽 PDF 저장 뒤
    vp0 = mw._mv[0].view.viewport()
    QTest.mouseClick(vp0, Qt.MouseButton.LeftButton, pos=QPoint(vp0.width() // 2, vp0.height() // 2)); spin(10)
    bt = mw.bookmark_tree
    bt.btn_edit.setChecked(True); spin(10)
    node = next(x for x in bt._iter_file_nodes() if x.childCount())
    node.child(0).setText(0, "ch1-renamed"); bt._dirty = True
    bt._op_save(); spin(40)
    vp1 = mv.view.viewport()
    QTest.mouseClick(vp1, Qt.MouseButton.LeftButton, pos=QPoint(vp1.width() // 2, vp1.height() // 2)); spin(10)
    ok, _ = press_until_change(Qt.Key.Key_Down)
    chk(ok and shot() == names[1] and row() == names[1], "E 저장 뒤에도 ↓ 로 다음 컷 s2", f"{ok} {shot()} {row()}")
    chk(wheel_until_change(-120) and shot() == names[2], "E 저장 뒤에도 휠로 다음 컷 s3", str(shot()))
    bt.btn_edit.setChecked(False); spin(5)

    chk(not errs, "예외 없음", str(errs))
    mw.close(); spin(5)
finally:
    shutil.rmtree(root, ignore_errors=True)

print("FAILS:", len(fails))
sys.exit(1 if fails else 0)
