# -*- coding: utf-8 -*-
"""261116-3: 책갈피는 끌어도 그 파일 밖으로 나가지 않는다 (책갈피창·저장 SOT §4.7.28, 사용자 지시).

사용자 지시: "책갈피를 마우스로 찍어 이동시 잘못하여 해당 파일 밖으로 나갈 수가 있는데 이때 전반적으로 책갈피창에 오류가 발생됨 …
파일의 책갈피를 마우스 등으로 이동시 해당 파일 밖으로는 이동 등이 불가능하게 수정"

실제 끌기 이벤트(QDragMoveEvent·QDropEvent, 트리 자신의 끌기 자료 = 고른 줄의 mimeData)를 트리 viewport 에 보낸다.
★ 오프스크린에서는 실제 QDrag 가 곧바로 끝나고(끌기 없음), Qt 는 출처가 자기가 아닌 내부 끌기를 늘 거절한다 —
  그래서 이벤트가 판정(`drop_allowed`)을 **어느 놓을 부모로 불렀고 무엇을 받았는지**, 금지 자리에서 이벤트를 받지 않고
  바뀜 표시(dropped)를 내지 않는지를 본다(실제 옮기기는 Windows 끌기에서만 — 손 확인).
A. 책갈피를 파일 줄 사이(파일 목록 단계)·다른 파일 안·다른 파일 책갈피 아래로 → 판정 '안 됨', 받지 않음, 놓아도 바뀜 표시 없음
B. 같은 파일 안 다른 책갈피 아래로 → 판정 '됨'
C. 파일 줄을 다른 파일 안으로 → 판정 '안 됨'
(수정 전 코드: 판정이 없어 실패)
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
from PyQt6.QtGui import QDragMoveEvent, QDropEvent, QDragEnterEvent
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
from PyQt6.QtCore import QCoreApplication
QCoreApplication.setApplicationName("polypdf_bmdrag_%d" % os.getpid())   # 검사 작성 SOT §14.7.2 의 3
import modal_guard
modal_guard.install(label=lambda: "책갈피 끌기", echo=False)               # §14.7.2 의 6
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
root = Path(tempfile.mkdtemp(prefix="polypdf_bmdrag_"))
try:
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    import test_fixtures as _TFX; _TFX.autotag_off()
    from viewer.widgets.bookmark_tree import BookmarkTree
    for nm in ("P", "Q"):
        d = fitz.open()
        for i in range(6):
            d.new_page().insert_text((72, 72), f"{nm} {i}")
        d.set_toc([[1, f"{nm}-a", 1], [1, f"{nm}-b", 3], [2, f"{nm}-b1", 4], [1, f"{nm}-c", 5]])
        d.save(str(root / f"{nm}.pdf")); d.close()
    bt = BookmarkTree(); bt.resize(420, 700); bt.show(); app.processEvents()
    bt.load_folder(root); spin(20)
    files = {Path(n.data(0, bt.DATA_FILE)).stem: n for n in bt._iter_file_nodes()}
    for fnode in files.values():
        fnode.setExpanded(True)
        for _ in range(100):
            if fnode.data(0, bt.DATA_TOC_LOADED):
                break
            spin(1)
    bt.btn_edit.setChecked(True); spin(5)
    tree = bt.tree
    P, Q = files["P"], files["Q"]

    def find(fnode, title):
        for i in range(fnode.childCount()):
            c = fnode.child(i)
            if c.text(0).split("  (p.")[0] == title:
                return c
            r = find(c, title)
            if r is not None:
                return r
        return None

    def shape():
        out = []

        def walk(n, dpt):
            for i in range(n.childCount()):
                c = n.child(i)
                out.append((dpt, c.text(0)[:12]))
                walk(c, dpt + 1)
        for i in range(tree.topLevelItemCount()):
            t = tree.topLevelItem(i)
            out.append((0, t.text(0)[:12]))
            walk(t, 1)
        return out

    calls = []
    real = getattr(tree, "drop_allowed", None)
    if callable(real):
        def spy(items, dest):
            v = real(items, dest)
            calls.append((dest, v))
            return v
        tree.drop_allowed = spy

    def drag_to(src, dst, where):
        """src 줄을 끌어 dst 줄의 where('on'·'above') 자리에 — 실제 끌기 이벤트. (판정 놓을 부모, 판정, 받았나, 바뀜 표시)."""
        tree.clearSelection(); src.setSelected(True); tree.setCurrentItem(src); spin(2)
        md = tree.mimeData([src])
        if dst is not None:
            tree.scrollToItem(dst); spin(2)
        if dst is None:                                  # 빈 곳(마지막 줄 아래) — 맨 위 단계
            last = tree.topLevelItem(tree.topLevelItemCount() - 1)
            while last.childCount() and last.isExpanded():
                last = last.child(last.childCount() - 1)
            r = tree.visualItemRect(last)
            pt = QPoint(r.center().x(), min(tree.viewport().height() - 2, r.bottom() + 40))
        else:
            r = tree.visualItemRect(dst)
            pt = r.center() if where == "on" else QPoint(r.center().x(), r.top() + 1)
        acts = Qt.DropAction.MoveAction
        # 앱 배달(QApplication.notify)은 출처 없는 내부 끌기의 진입을 Qt 가 거절하면 그 뒤 이벤트를 걸러 버린다 —
        #   같은 이벤트 객체를 트리의 처리기에 직접 넣는다(실제 처리기·실제 놓을 자리 계산).
        tree.dragEnterEvent(QDragEnterEvent(pt, acts, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        calls.clear()
        mv = QDragMoveEvent(pt, acts, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        tree.dragMoveEvent(mv)
        verdict = calls[-1] if calls else (None, None)
        marks = []
        tree.dropped.connect(lambda: marks.append(1))
        tree.dropEvent(QDropEvent(QPointF(pt), acts, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        spin(3)
        try:
            tree.dropped.disconnect()
        except TypeError:
            pass
        tree.dropped.connect(bt._on_tree_dropped)
        return verdict[0], verdict[1], mv.isAccepted(), bool(marks)

    before = shape()
    # ── A ──
    dest, ok, took, marked = drag_to(find(P, "P-b"), None, "on")
    chk(ok is False and dest is None, "A 빈 곳(파일 목록 단계) — 판정 '안 됨'(놓을 부모 = 맨 위)", f"{ok} {dest}")
    chk(not took and not marked and shape() == before, "A 받지 않고, 놓아도 트리 그대로·바뀜 표시 없음", f"{took} {marked}")
    # 줄 사이 자리는 Qt 가 끄는 동안 정한다(합성 이벤트는 그 표시를 갱신하지 않는다) — 판정 결과만 본다
    dest, ok, took, marked = drag_to(find(P, "P-b"), Q, "above")
    chk(ok is False and not marked and shape() == before, "A 다른 파일 줄 자리 — 판정 '안 됨'·그대로", f"{ok} {marked}")
    dest, ok, took, marked = drag_to(find(P, "P-c"), Q, "on")
    chk(ok is False and dest is Q, "A 다른 파일(Q) 안으로 — 판정 '안 됨'", f"{ok}")
    chk(not took and not marked and shape() == before, "A 다른 파일에 놓아도 그대로", f"{took} {marked}")
    dest, ok, took, marked = drag_to(find(P, "P-a"), find(Q, "Q-b"), "on")
    chk(ok is False, "A 다른 파일의 책갈피 아래로 — 판정 '안 됨'", f"{ok}")
    chk(not marked and shape() == before, "A 놓아도 그대로")
    # ── B ──
    dest, ok, took, marked = drag_to(find(P, "P-c"), find(P, "P-b"), "on")
    chk(ok is True and dest is find(P, "P-b"), "B 같은 파일 안 다른 책갈피 아래로 — 판정 '됨'", f"{ok}")
    dest, ok, _t, _m = drag_to(find(P, "P-c"), P, "on")
    chk(ok is True and dest is P, "B 같은 파일 줄 위(그 파일 맨 끝 책갈피로) — 판정 '됨'", f"{ok} {dest is P}")
    # ── C ──
    dest, ok, took, marked = drag_to(Q, P, "on")
    chk(ok is False and not marked and shape() == before, "C 파일 줄을 다른 파일 안으로 — 판정 '안 됨'·그대로", f"{ok} {marked}")

    chk(not errs, "예외 없음", str(errs))
finally:
    shutil.rmtree(root, ignore_errors=True)

print("FAILS:", len(fails))
sys.exit(1 if fails else 0)
