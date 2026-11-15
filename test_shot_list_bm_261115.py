# -*- coding: utf-8 -*-
"""261115-27: 스크린샷 컷을 2단에 띄우면 아래 책갈피창은 컷 목록 (책갈피창·저장 SOT §4.7.26, 사용자 결정 '컷 목록으로 바꿈').

사용자 지시: "스크린샷 창의 썸네일을 눌러서 2단에 썸네일해당 내용이 띄워졌을 때, 책갈피 창의 아래에 스크린샷 창의 썸네일 내용이 보여지도록 수정"

A. 스트립 컷을 실제로 누르면 아래 목록 = 스트립 순서 컷 목록, 누른 컷 줄이 골라짐, 위 목록·왼쪽 본문 그대로
B. 다른 컷을 누르거나 ◀ 로 넘기면 줄만 옮긴다(다시 만들지 않는다)
C. 아래 목록 줄을 실제로 누르면 그 컷을 띄운다(스트립 순번 i/N 도)
D. 새 컷·컷 지우기를 목록이 따라간다
E. 오른쪽 창에 PDF 를 열면 원래 폴더 목록(그 파일 줄), 다시 컷 → 1단으로 돌아가면 원래 목록
(수정 전 코드: A~E 실패)
"""
import os, sys, tempfile, shutil, faulthandler
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(240, exit=True)
from pathlib import Path

import fitz
from PyQt6.QtCore import QStandardPaths, Qt
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QImage, QColor
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
from PyQt6.QtCore import QCoreApplication
QCoreApplication.setApplicationName("polypdf_shotlist_%d" % os.getpid())   # 검사 작성 SOT §14.7.2 의 3
import modal_guard
modal_guard.install(label=lambda: "컷 목록", echo=False)                     # §14.7.2 의 6
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
root = Path(tempfile.mkdtemp(prefix="polypdf_shotlist_"))
try:
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    import test_fixtures as _TFX; _TFX.autotag_off()
    from viewer.app import MainWindow
    from viewer.history import HistoryItem
    mw = MainWindow(); mw.resize(1300, 850); mw.show(); app.processEvents()
    bt, rt, strip = mw.bookmark_tree, mw.bookmark_tree_right, mw.shot_strip

    fo = root / "fo"; fo.mkdir()
    for nm in ("A", "B", "C"):
        d = fitz.open(); d.new_page().insert_text((72, 72), nm); d.save(str(fo / f"{nm}.pdf")); d.close()
    shots = root / "shots"; shots.mkdir()

    def make_cut(nm, color):
        img = QImage(240, 160, QImage.Format.Format_RGB32); img.fill(QColor(color))
        p = shots / f"261115_2144_{nm}.png"; img.save(str(p), "PNG")
        strip.add_item(str(p), kind="image", label=p.stem, prepend=False)
        return str(p)

    mw.open_folder(fo); spin(20)
    mw._load_main(HistoryItem(str(fo / "A.pdf"), 0, "", "bookmark"), sync=True); spin(10)
    cuts = [make_cut("s1", "red"), make_cut("s2", "green"), make_cut("s3", "blue")]
    spin(10)
    top_before = [bt.tree.topLevelItem(i).data(0, bt.DATA_FILE) for i in range(bt.tree.topLevelItemCount())]

    def listed(t):
        return [Path(it.data(0, t.DATA_FILE)).name for it in t._iter_file_nodes()]

    def picked(t):
        it = t.tree.currentItem()
        node = t._file_node_of(it) if it is not None else None
        return Path(node.data(0, t.DATA_FILE)).name if node is not None else None

    def click_card(path):
        i = strip.index_of_path(path)
        it = strip.list.item(i)
        strip.list.scrollToItem(it)
        QTest.mouseClick(strip.list.viewport(), Qt.MouseButton.LeftButton, pos=strip.list.visualItemRect(it).center())
        spin(15)

    def click_row(t, name):
        it = next(x for x in t._iter_file_nodes() if Path(x.data(0, t.DATA_FILE)).name == name)
        t.tree.scrollToItem(it)
        QTest.mouseClick(t.tree.viewport(), Qt.MouseButton.LeftButton, pos=t.tree.visualItemRect(it).center())
        spin(15)

    names = [Path(c).name for c in cuts]

    # ── A ──
    click_card(cuts[1])
    chk(getattr(mw, "_split_on", False) and getattr(mw, "_current_shot_path", None) == cuts[1], "준비 — 컷 s2 가 2단 오른쪽에")
    chk(listed(rt) == names, "A 아래 목록 = 스트립 순서 컷 목록", str(listed(rt)))
    chk(picked(rt) == names[1] and bool(rt.tree.selectedItems()), "A 누른 컷 s2 줄이 골라짐", str(picked(rt)))
    chk([bt.tree.topLevelItem(i).data(0, bt.DATA_FILE) for i in range(bt.tree.topLevelItemCount())] == top_before,
        "A 위 목록 그대로")
    chk(Path(str(mw._mv[0].current_file())).name == "A.pdf", "A 왼쪽 본문 그대로", str(mw._mv[0].current_file()))

    # ── B ──
    first_obj = rt.tree.topLevelItem(0)
    click_card(cuts[2])
    chk(picked(rt) == names[2], "B 다른 컷 s3 → 줄만 s3", str(picked(rt)))
    chk(rt.tree.topLevelItem(0) is first_obj, "B 목록을 다시 만들지 않는다")
    mw._on_image_step(-1); spin(15)
    chk(picked(rt) == names[1] and mw._current_shot_path == cuts[1], "B ◀ → s2 줄", str(picked(rt)))

    # ── C ──
    click_row(rt, names[0])
    chk(getattr(mw, "_current_shot_path", None) == cuts[0], "C 아래 목록 s1 줄 누름 → s1 을 띄움", str(getattr(mw, "_current_shot_path", None)))
    chk(picked(rt) == names[0], "C 고른 줄 s1", str(picked(rt)))

    # ── D ──
    c4 = make_cut("s4", "yellow"); spin(15)
    chk(listed(rt) == names + [Path(c4).name], "D 새 컷 s4 가 목록 끝에", str(listed(rt)))
    strip.remove_key(cuts[2], 0); spin(15)
    chk(listed(rt) == [names[0], names[1], Path(c4).name], "D 지운 컷 s3 는 목록에서 빠짐", str(listed(rt)))
    chk(picked(rt) == names[0], "D 띄운 컷 s1 줄은 그대로 골라짐", str(picked(rt)))

    # ── E ──
    mw._set_active_pane(1)
    mw._load_main(HistoryItem(str(fo / "B.pdf"), 0, "", "bookmark"), sync=True); spin(20)
    chk(sorted(listed(rt)) == ["A.pdf", "B.pdf", "C.pdf"], "E 오른쪽 창에 PDF → 원래 폴더 목록", str(listed(rt)))
    chk(picked(rt) == "B.pdf", "E 그 파일 B 줄이 골라짐", str(picked(rt)))
    click_card(cuts[0])
    chk(listed(rt)[:1] == [names[0]], "E 다시 컷 → 컷 목록", str(listed(rt)))
    mw.act_split.setChecked(False); spin(15)
    chk(sorted(listed(rt)) == ["A.pdf", "B.pdf", "C.pdf"], "E 1단으로 → 아래 목록은 원래 목록", str(listed(rt)))

    chk(not errs, "예외 없음", str(errs))
    mw.close(); spin(5)
finally:
    shutil.rmtree(root, ignore_errors=True)

print("FAILS:", len(fails))
sys.exit(1 if fails else 0)
