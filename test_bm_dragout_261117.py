# -*- coding: utf-8 -*-
"""261117-3: 책갈피창 → 파일 탐색기 끌기 (책갈피창·저장 SOT §4.7.30, 사용자 지시·결정 A·가).

사용자 지시: "책갈피창에서 파일을 선택하여 파일 탐색기 등에 복사 이동 가능 … 파일의 내부 책갈피로는 실제 파일 페이지의 복사 이동
불가능. 책갈피의 위치만 복사, 이동 가능" · "복사가 완료되기 전에 프로그램으로 커서가 이동하면 … +표시와 파일 썸네일들이 그대로".
결정 A = 셸 끌기(복사·이동은 탐색기가 자기 스레드에서), 가 = 그냥 끌기 복사·Shift 이동.

A. 보기 모드에서 파일 줄을 **실제 마우스**로 누르고 끌면 셸 끌기(`shell_drag.drag_files`)가 그 파일로 불린다 — 고른 여러 파일은 모두,
   책갈피 줄은 끌지 않는다(수정 전: 보기 모드 끌기 꺼짐 — 불리지 않음).
B. Shift 로 놓으면(이동) 놓기 전에 본문이 연 파일만 놓고(releaseFileRequested), 원본이 없어지면 그 줄을 빼고 fileOpCompleted(old, "").
   그냥 놓기(복사)는 아무것도 바꾸지 않는다. Shift 로 놓았는데 대상이 옮기지 않았으면 fileOpCompleted(old, old)(다시 열기).
C. 끄는 중 그 파일을 책갈피창에 다시 놓으면 아무 일도 없다(pathsDropped 없음).
D. 편집 모드 Ctrl+놓기 = 책갈피 위치 복사(같은 쪽 책갈피 하나 더, 원래 줄 그대로) — 수정 전 실패.
E. 실제 셸: `make_async_data_object` 자료를 셸 폴더 놓기 대상(탐색기와 같은 IDropTarget)에 — 그냥 = 복사, Shift = 이동,
   놓기가 복사 끝을 기다리지 않는다(비동기 시작), 한글 이름 파일이 도착한다.
"""
import os, sys, tempfile, shutil, time, faulthandler
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(300, exit=True)
from pathlib import Path

import fitz
from PyQt6.QtCore import QStandardPaths, Qt, QPoint, QPointF, QCoreApplication, QMimeData, QUrl, QEvent
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QDragMoveEvent, QDropEvent, QDragEnterEvent, QMouseEvent
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bmdragout_%d" % os.getpid())   # 검사 작성 SOT §14.7.2 의 3
import modal_guard
modal_guard.install(label=lambda: "책갈피창 끌어내기", echo=False)            # §14.7.2 의 6
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
root = Path(tempfile.mkdtemp(prefix="polypdf_bmdragout_"))
try:
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    import test_fixtures as _TFX; _TFX.autotag_off()
    from viewer.widgets.bookmark_tree import BookmarkTree
    from viewer import shell_drag
    src = root / "list"; src.mkdir()
    for nm in ("가나 A", "B", "C"):
        d = fitz.open()
        for i in range(5):
            d.new_page().insert_text((72, 72), f"{nm} {i}")
        d.set_toc([[1, f"{nm}-a", 1], [1, f"{nm}-b", 3], [1, f"{nm}-c", 4]])
        d.save(str(src / f"{nm}.pdf")); d.close()
    bt = BookmarkTree(); bt.resize(420, 700); bt.show(); app.processEvents()
    bt.load_folder(src); spin(20)
    tree = bt.tree
    files = {Path(n.data(0, bt.DATA_FILE)).stem: n for n in bt._iter_file_nodes()}
    A, B, C = files["가나 A"], files["B"], files["C"]
    pA, pB, pC = (str(n.data(0, bt.DATA_FILE)) for n in (A, B, C))
    chk(not bt._edit_mode, "준비 — 보기 모드")

    calls = []
    plan = {"fn": None}

    def fake_drag(paths, hwnd=0, on_move_drop=None, on_done=None):
        calls.append(list(paths))
        fn = plan["fn"]
        if fn:
            return fn(paths, on_move_drop, on_done)
        if on_done:
            on_done(0)
        return {"result": "cancel", "shift": False, "effect": 0, "async": False}
    shell_drag.drag_files = fake_drag

    def mouse_drag(item, mods=Qt.KeyboardModifier.NoModifier):
        """실제 마우스 — 줄을 누르고(왼쪽) 끌기 거리 넘게 움직인다."""
        tree.scrollToItem(item); spin(2)
        r = tree.visualItemRect(item)
        p0 = QPoint(r.left() + 30, r.center().y())
        vp = tree.viewport()
        QTest.mousePress(vp, Qt.MouseButton.LeftButton, mods, p0); spin(2)
        for dx in (6, 14, 30, 50):
            p = QPointF(p0.x() + dx, p0.y() + dx // 3)
            ev = QMouseEvent(QEvent.Type.MouseMove, p, QPointF(vp.mapToGlobal(p.toPoint())),
                             Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, mods)
            QApplication.sendEvent(vp, ev); spin(1)
        QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, mods, QPoint(p0.x() + 50, p0.y() + 16)); spin(3)

    def pick(*items):
        """실제 클릭으로 여러 줄 고르기 — 첫 줄은 그냥 클릭, 나머지는 Ctrl+클릭."""
        for i, it in enumerate(items):
            tree.scrollToItem(it); spin(1)
            r = tree.visualItemRect(it)
            QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton,
                             Qt.KeyboardModifier.ControlModifier if i else Qt.KeyboardModifier.NoModifier,
                             QPoint(r.left() + 30, r.center().y())); spin(3)

    # ── A. 보기 모드 파일 줄 → 셸 끌기
    tree.clearSelection(); spin(2)
    mouse_drag(B)
    chk(calls and calls[-1] == [pB], "A1 파일 줄을 끌면 셸 끌기가 그 파일로", str(calls))
    pick(A, C)
    calls.clear()
    mouse_drag(C, Qt.KeyboardModifier.NoModifier)
    chk(calls and sorted(calls[-1]) == sorted([pA, pC]), "A2 고른 두 파일을 함께", str(calls))
    A.setExpanded(True)
    for _ in range(100):
        if A.data(0, bt.DATA_TOC_LOADED):
            break
        spin(1)
    bm = A.child(1) if A.childCount() > 1 else None
    calls.clear()
    if bm is not None:
        tree.clearSelection(); spin(2)
        mouse_drag(bm)
    chk(bm is not None and not calls, "A3 책갈피 줄은 밖으로 끌지 않는다", str(calls))

    # ── B. 이동(Shift) — 본문이 연 파일만 놓고, 원본이 없어지면 줄을 뺀다
    rel, done_ops = [], []
    bt.releaseFileRequested.connect(lambda p: rel.append(p))
    bt.fileOpCompleted.connect(lambda o, n: done_ops.append((o, n)))
    bt._shown_file_fn = lambda: pA
    dest = root / "dest"; dest.mkdir()

    def move_ok(paths, on_move_drop, on_done):
        on_move_drop(list(paths))                 # 놓는 순간 Shift
        for p in paths:
            shutil.move(p, str(dest / Path(p).name))   # 탐색기가 옮김(여기서는 흉내)
        on_done(shell_drag.DROPEFFECT_MOVE)
        return {"result": "drop", "shift": True, "effect": 0, "async": True}
    plan["fn"] = move_ok
    pick(B, A)
    mouse_drag(A)
    for _ in range(150):
        if len(done_ops) >= 2:
            break
        spin(1)
    left = {Path(n.data(0, bt.DATA_FILE)).stem for n in bt._iter_file_nodes()}
    chk(rel == [pA], "B1 이동 — 놓기 전에 본문이 연 파일만 놓는다", str(rel))
    chk(sorted(done_ops) == sorted([(pA, ""), (pB, "")]) and left == {"C"},
        "B2 옮겨진 두 파일 — 줄이 빠지고 삭제 한 길(old, \"\")", "%s %s" % (done_ops, left))

    rel.clear(); done_ops.clear()
    plan["fn"] = lambda paths, mv, dn: (dn(shell_drag.DROPEFFECT_COPY),
                                        {"result": "drop", "shift": False, "effect": 1, "async": False})[1]
    mouse_drag(C); spin(10)
    chk(not rel and not done_ops and C.data(0, bt.DATA_FILE) == pC, "B3 복사 — 앱 상태 그대로", "%s %s" % (rel, done_ops))

    bt._shown_file_fn = lambda: pC
    bt.MOVE_WATCH_S = 5

    def move_refused(paths, on_move_drop, on_done):
        on_move_drop(list(paths))
        on_done(0)                                # 대상이 옮기지 않음(취소·충돌 건너뜀)
        return {"result": "drop", "shift": True, "effect": 0, "async": True}
    plan["fn"] = move_refused
    mouse_drag(C)
    for _ in range(250):
        if done_ops:
            break
        spin(1)
    chk(rel == [pC] and done_ops == [(pC, pC)] and C.data(0, bt.DATA_FILE) == pC,
        "B4 Shift 로 놓았는데 옮기지 않음 → 다시 열기(old, old)·줄 그대로", "%s %s" % (rel, done_ops))

    rel.clear(); done_ops.clear()

    def move_silent(paths, on_move_drop, on_done):
        on_move_drop(list(paths))                 # 끝 알림(EndOperation)을 주지 않는 대상
        return {"result": "drop", "shift": True, "effect": 0, "async": True}
    plan["fn"] = move_silent
    t0 = time.perf_counter()
    mouse_drag(C)
    for _ in range(600):
        if done_ops:
            break
        spin(1)
    el = time.perf_counter() - t0
    chk(done_ops == [(pC, pC)] and el < 15, "B5 끝 알림 없이 원본을 아무도 안 열면 몇 초 안에 다시 열기",
        "%s %.1fs" % (done_ops, el))

    # ── C. 끄는 중 그 파일을 책갈피창에 다시 놓음 → 아무 일도 없다
    dropped_paths = []
    bt.pathsDropped.connect(lambda ps: dropped_paths.append(ps))

    def drop_back(paths, on_move_drop, on_done):
        shell_drag._active = {__import__("viewer.pathutil", fromlist=["norm_key"]).norm_key(p) for p in paths}
        try:
            md = QMimeData(); md.setUrls([QUrl.fromLocalFile(p) for p in paths])
            pt = tree.visualItemRect(C).center()
            vp = tree.viewport()
            QApplication.sendEvent(vp, QDragEnterEvent(pt, Qt.DropAction.CopyAction, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
            QApplication.sendEvent(vp, QDragMoveEvent(pt, Qt.DropAction.CopyAction, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
            QApplication.sendEvent(vp, QDropEvent(QPointF(pt), Qt.DropAction.CopyAction, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        finally:
            shell_drag._active = None
        on_done(0)
        return {"result": "cancel", "shift": False, "effect": 0, "async": False}
    plan["fn"] = drop_back
    rel.clear(); done_ops.clear()
    mouse_drag(C); spin(5)
    chk(not dropped_paths, "C 끈 파일을 책갈피창에 다시 놓으면 아무 일도 없다", str(dropped_paths))

    # ── D. 편집 모드 Ctrl+놓기 = 책갈피 위치 복사
    C.setExpanded(True)
    for _ in range(100):
        if C.data(0, bt.DATA_TOC_LOADED):
            break
        spin(1)
    bt.btn_edit.setChecked(True); spin(5)
    n0 = C.childCount()
    s, t = C.child(0), C.child(2)
    tree.clearSelection(); s.setSelected(True); tree.setCurrentItem(s); spin(2)
    md = tree.mimeData([s])
    tree.scrollToItem(t); spin(2)
    pt = tree.visualItemRect(t).center()
    acts = Qt.DropAction.CopyAction | Qt.DropAction.MoveAction
    ctrl = Qt.KeyboardModifier.ControlModifier
    tree.dragEnterEvent(QDragEnterEvent(pt, acts, md, Qt.MouseButton.LeftButton, ctrl))
    tree.dragMoveEvent(QDragMoveEvent(pt, acts, md, Qt.MouseButton.LeftButton, ctrl))
    marks = []
    tree.dropped.connect(lambda: marks.append(1))
    tree.dropEvent(QDropEvent(QPointF(pt), acts, md, Qt.MouseButton.LeftButton, ctrl)); spin(3)
    titles = [C.child(i).text(0) for i in range(C.childCount())]
    copied = t.childCount() == 1 and t.child(0).data(0, bt.DATA_PAGE) == s.data(0, bt.DATA_PAGE)
    chk(C.childCount() == n0 and s.parent() is C and copied and marks,
        "D Ctrl+놓기 — 같은 쪽 책갈피 하나 더(원래 줄 그대로), 바뀜 표시", "%s %s" % (titles, t.childCount()))
    chk(bt._dirty, "D 편집 바뀜 표시")
    bt._dirty = False
    bt.btn_edit.setChecked(False); spin(3)

    # ── E. 실제 셸 놓기 대상(탐색기와 같은 IDropTarget)
    import pythoncom
    from win32com.shell import shell
    s_dir = root / "s"; d_dir = root / "d"; s_dir.mkdir(); d_dir.mkdir()
    big = s_dir / "한글 큰 파일.pdf"
    with open(big, "wb") as fh:
        blk = os.urandom(8 << 20)
        for _ in range(48):                      # 384MB — 놓기가 복사를 기다리면 눈에 띄게 느리다
            fh.write(blk)
    ends = []
    ado = shell_drag.make_async_data_object([str(big)], lambda e: ends.append(e))
    chk(ado is not None, "E 셸 끌기 자료를 만든다")
    pdo = pythoncom.ObjectFromAddress(ado.ptr, pythoncom.IID_IDataObject)
    pidl = shell.SHParseDisplayName(str(d_dir), 0)[0]
    dt = shell.SHGetDesktopFolder().GetUIObjectOf(0, [pidl], pythoncom.IID_IDropTarget, 0)
    dt = dt[1] if isinstance(dt, tuple) else dt
    e_plain = dt.DragEnter(pdo, 1, (0, 0), 3); dt.DragLeave()
    e_shift = dt.DragEnter(pdo, 1 | 4, (0, 0), 3); dt.DragLeave()
    chk(e_plain == 1 and e_shift == 2, "E 그냥 = 복사, Shift = 이동(같은 드라이브여도)", "%s %s" % (e_plain, e_shift))
    dt.DragEnter(pdo, 1, (0, 0), 3)
    t0 = time.perf_counter()
    dt.Drop(pdo, 1, (0, 0), 3)
    el = time.perf_counter() - t0
    chk(ado.started, "E 대상이 비동기로 받는다(StartOperation)")
    out = d_dir / big.name
    for _ in range(600):
        if out.exists() and out.stat().st_size == big.stat().st_size:
            try:
                os.rename(out, out)               # 아직 쓰는 중이면 실패
                break
            except OSError:
                pass
        pythoncom.PumpWaitingMessages(); time.sleep(0.05)
    chk(out.exists() and out.stat().st_size == big.stat().st_size, "E 한글 이름 파일이 도착한다")
    print("   놓기 %.2fs" % el)
    chk(el < 0.5, "E 놓기가 복사 끝을 기다리지 않는다", "%.2fs" % el)
    chk(not errs, "예외 없음", str(errs))
finally:
    shutil.rmtree(root, ignore_errors=True)

print("\n=== " + ("ALL PASS" if not fails else f"FAILURE ({len(fails)})") + " ===")
for m in fails:
    print(" -", m)
sys.stdout.flush()
os._exit(1 if fails else 0)
