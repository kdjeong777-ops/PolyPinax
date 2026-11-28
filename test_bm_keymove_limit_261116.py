# -*- coding: utf-8 -*-
"""261116-3 덧붙임: 키보드·단추로 옮겨도 책갈피는 그 파일 밖으로 나가지 않는다 (책갈피창·저장 SOT §4.7.28).

사용자 덧붙임: "키보드로 옮길때도 마찬가지야"

실제 ▲▼◀▶ 단추를 누른다(마우스 클릭, 그리고 포커스 + Space).
A. 파일 첫 책갈피 ▲ / 마지막 책갈피 ▼ → 그 자리, 상태줄 알림, 바뀜 표시 없음, 본문 쪽 그대로
B. 단계 1 책갈피 ◀ / 첫 하위 ▶ → 그 자리, 알림, 바뀜 없음
C. 가운데 책갈피 ▲▼ → 같은 파일 안에서 한 칸, 고른 줄 그대로, 본문이 옆 책갈피로 튀지 않음
(수정 전 코드: 실패)
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
from PyQt6.QtWidgets import QApplication, QMessageBox, QAbstractButton
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
from PyQt6.QtCore import QCoreApplication
QCoreApplication.setApplicationName("polypdf_bmkey_%d" % os.getpid())   # 검사 작성 SOT §14.7.2 의 3
import modal_guard
modal_guard.install(label=lambda: "책갈피 단추 이동", echo=False)          # §14.7.2 의 6
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
root = Path(tempfile.mkdtemp(prefix="polypdf_bmkey_"))
try:
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    import test_fixtures as _TFX; _TFX.autotag_off()
    from viewer.app import MainWindow
    from viewer.history import HistoryItem
    for nm in ("P", "Q"):
        d = fitz.open()
        for i in range(8):
            d.new_page().insert_text((72, 72), f"{nm} {i}")
        d.set_toc([[1, f"{nm}-a", 1], [1, f"{nm}-b", 3], [2, f"{nm}-b1", 4], [2, f"{nm}-b2", 5], [1, f"{nm}-c", 7]])
        d.save(str(root / f"{nm}.pdf")); d.close()
    mw = MainWindow(); mw.resize(1200, 800); mw.show(); app.processEvents()
    bt = mw.bookmark_tree
    mw.open_folder(root); spin(20)
    mw._load_main(HistoryItem(str(root / "P.pdf"), 0, "", "bookmark"), sync=True); spin(10)
    files = {Path(n.data(0, bt.DATA_FILE)).stem: n for n in bt._iter_file_nodes()}
    for f in files.values():
        f.setExpanded(True)
        for _ in range(100):
            if f.data(0, bt.DATA_TOC_LOADED):
                break
            spin(1)
    bt.btn_edit.setChecked(True); spin(10)
    P = files["P"]
    notes = []
    bt.noticeRequested.connect(lambda t, ms: notes.append(t))
    # 261128-24: 261128-10 부터 단추 글은 비고 그림이 파란 꺾쇠(디자인 SOT §4.8 ②) — 그림 이름으로 찾는다
    _SYM = {"chevron_left": "◀", "chevron_right": "▶", "chevron_up": "▲", "chevron_down": "▼"}
    btns = {_SYM[chev]: b for b, chev in bt._arrow_btns}

    def find(title, node=P):
        for i in range(node.childCount()):
            c = node.child(i)
            if c.text(0).split("  (p.")[0] == title:
                return c
            r = find(title, c)
            if r is not None:
                return r
        return None

    def shape():
        out = []

        def walk(n, dpt):
            for i in range(n.childCount()):
                c = n.child(i)
                out.append((dpt, c.text(0).split("  (p.")[0]))
                walk(c, dpt + 1)
        for f in files.values():
            out.append((0, f.text(0)[:8]))
            walk(f, 1)
        return out

    def pick(it):
        bt.tree.blockSignals(True)
        bt.tree.clearSelection(); it.setSelected(True); bt.tree.setCurrentItem(it)
        bt.tree.blockSignals(False)
        spin(3)

    def press(sym, by_key=False):
        b = btns[sym]
        notes.clear()
        bt._dirty = False
        page0 = mw._mv[0].current_page()
        if by_key:
            b.setFocus(); spin(2)
            QTest.keyClick(b, Qt.Key.Key_Space)
        else:
            QTest.mouseClick(b, Qt.MouseButton.LeftButton)
        spin(8)
        return bool(notes), bt._dirty, page0, mw._mv[0].current_page()

    before = shape()
    # ── A ──
    pick(find("P-a"))
    noted, dirty, p0, p1 = press("▲")
    chk(shape() == before and noted and not dirty and p0 == p1, "A 파일 첫 책갈피 ▲ — 그 자리·알림·바뀜 없음·본문 그대로", f"{noted} {dirty} {p0}->{p1}")
    pick(find("P-c"))
    noted, dirty, p0, p1 = press("▼", by_key=True)
    chk(shape() == before and noted and not dirty, "A 파일 마지막 책갈피 ▼(Space) — 그 자리·알림·바뀜 없음", f"{noted} {dirty}")
    # ── B ──
    pick(find("P-b"))
    noted, dirty, _p0, _p1 = press("◀")
    chk(shape() == before and noted and not dirty, "B 단계 1 책갈피 ◀ — 파일 밖으로 안 나감·알림", f"{noted} {dirty}")
    pick(find("P-b1"))
    noted, dirty, _p0, _p1 = press("▶")
    chk(shape() == before and noted and not dirty, "B 첫 하위 ▶ — 더 못 들임·알림", f"{noted} {dirty}")
    # ── C ──
    b2 = find("P-b2")
    pick(b2)
    noted, dirty, p0, p1 = press("▲")
    chk(find("P-b").child(0) is b2 and dirty and not noted, "C 가운데 책갈피 ▲ — 같은 부모 안에서 한 칸", str([find("P-b").child(i).text(0) for i in range(find("P-b").childCount())]))
    chk(bt.tree.currentItem() is b2, "C 고른 줄 그대로")
    chk(p0 == p1, "C 본문이 옆 책갈피로 튀지 않음", f"{p0}->{p1}")
    chk(all(d >= 1 for d, _t in shape() if _t.startswith("P-")) and find("P-b2", files["Q"]) is None,
        "C 다른 파일로 넘어가지 않음")

    chk(not errs, "예외 없음", str(errs))
    bt._dirty = False
    mw.close(); spin(5)
finally:
    shutil.rmtree(root, ignore_errors=True)

print("FAILS:", len(fails))
sys.exit(1 if fails else 0)
