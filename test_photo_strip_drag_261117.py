# -*- coding: utf-8 -*-
"""261117-7 — 사진 썸네일 줄·스크린샷 스트립 끌어내기 = 셸 끌기 (사진 보기 SOT §4.3, 스크린샷 SOT §4, 책갈피창·저장 SOT §4.7.30).

A. 스크린샷 스트립 — 실제 마우스로 컷을 끌면 `shell_drag.drag_files` 가 그 PNG 로, **복사만**(effects = 복사)·`mark_own=False`.
   고른 두 컷은 줄 차례로 함께.
B. 끄는 컷을 제 스트립에 놓으면 놓은 자리로 옮긴다(번호도 다시), PNG 는 그대로, 놓기 효과 = 복사.
C. 사진 썸네일 줄 — 실제 마우스로 끌면 앱이 넣은 `drag_out` 이 그 사진(고른 칸 모두)으로 불린다(Qt 끌기 없음).
D. `PhotoMixin._photo_drag_out` — zip 캐시·휴대 장치 캐시·없는 파일은 빼고 책갈피창 `drag_out` 으로, 다 빠지면 읽기 전용 안내.
E. (Windows, 별도 프로세스) 앱 안 놓기 대상 — 셸 끌기 자료를 쪽 썸네일 창의 **실제 OLE 놓기 대상**에 놓으면 새 쪽 요청(그림 경로),
   허락 효과가 복사뿐이면 복사로 받는다.
수정 전 코드: A·B·C·D 실패(Qt 끌기 — 셸 끌기·drag_out 이 불리지 않는다).
"""
import faulthandler
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(300, exit=True)
OLE = "--ole" in sys.argv
if not OLE:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"   # Qt 끌기(수정 전 코드)가 진짜 OLE 끌기로 바깥 창에 놓지 않게
from pathlib import Path

from PyQt6.QtCore import QStandardPaths, Qt, QPoint, QPointF, QCoreApplication, QMimeData, QUrl, QEvent, QTimer
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QDragMoveEvent, QDropEvent, QDragEnterEvent, QMouseEvent, QImage, QColor, QKeyEvent
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_stripdrag_%d" % os.getpid())   # 검사 작성 SOT §14.7.2 의 3
import modal_guard
modal_guard.install(label=lambda: "스트립 셸 끌기", echo=False)
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def spin(n=10, ms=20):
    for _ in range(n):
        app.processEvents(); QTest.qWait(ms)


def png(path, color):
    img = QImage(120, 90, QImage.Format.Format_RGB32)
    img.fill(QColor(color))
    img.save(str(path))
    return str(path)


def norm(ps):
    return [os.path.normcase(os.path.abspath(str(p))) for p in ps]


def ole_part(root):
    """E — 실제 Qt 창의 OLE 놓기 대상(탐색기에서 끌어올 때와 같은 IDropTarget)에 셸 끌기 자료를 놓는다."""
    import ctypes
    import fitz
    from ctypes import wintypes as W
    from viewer import shell_drag
    from viewer.widgets.thumbs_list import PageThumbs
    pdf = str(root / "doc.pdf")
    d = fitz.open()
    for i in range(3):
        d.new_page().insert_text((72, 72), "p%d" % i)
    d.save(pdf); d.close()
    shot = png(root / "컷 한글.png", "#c03030")
    pt = PageThumbs(); pt.resize(300, 600); pt.show()
    pt.load_document(pdf); spin(20)
    pt.set_edit_mode(True); spin(3)
    got = {}
    pt.addImagePagesRequested.connect(lambda row, ps: got.update(row=row, paths=list(ps)))
    hwnd = int(pt.window().winId())
    u32 = ctypes.windll.user32
    u32.GetPropW.restype = ctypes.c_void_p
    u32.GetPropW.argtypes = [W.HWND, ctypes.c_wchar_p]
    tgt = u32.GetPropW(W.HWND(hwnd), "OleDropTargetInterface")
    chk(bool(tgt), "E0 쪽 썸네일 창에 OLE 놓기 대상이 있다")
    if not tgt:
        return
    vp = pt.list.viewport()
    it = pt.list.item(1)
    gp = vp.mapToGlobal(pt.list.visualItemRect(it).center())
    ratio = pt.window().devicePixelRatioF() or 1.0
    ptl = ctypes.c_longlong(((int(gp.y() * ratio) & 0xffffffff) << 32) | (int(gp.x() * ratio) & 0xffffffff))
    ado = shell_drag.make_async_data_object([shot])
    chk(ado is not None, "E0 셸 끌기 자료")
    if ado is None:
        return
    eff = W.DWORD(shell_drag.DROPEFFECT_COPY)
    enter = shell_drag._method(tgt, 3, ctypes.c_long, ctypes.c_void_p, W.DWORD, ctypes.c_longlong, ctypes.POINTER(W.DWORD))
    over = shell_drag._method(tgt, 4, ctypes.c_long, W.DWORD, ctypes.c_longlong, ctypes.POINTER(W.DWORD))
    drop = shell_drag._method(tgt, 6, ctypes.c_long, ctypes.c_void_p, W.DWORD, ctypes.c_longlong, ctypes.POINTER(W.DWORD))
    enter(ado.ptr, 1, ptl, ctypes.byref(eff)); spin(2)
    eff = W.DWORD(shell_drag.DROPEFFECT_COPY)
    over(1, ptl, ctypes.byref(eff)); spin(2)
    eff = W.DWORD(shell_drag.DROPEFFECT_COPY)
    drop(ado.ptr, 0, ptl, ctypes.byref(eff)); spin(5)
    ado._release()
    chk(norm(got.get("paths") or []) == norm([shot]), "E1 셸 끌기 자료를 쪽 썸네일에 놓으면 그 그림으로 새 쪽 요청", got)
    chk(eff.value == shell_drag.DROPEFFECT_COPY, "E2 복사만 허락하면 복사로 받는다", eff.value)
    chk(os.path.exists(shot), "E3 컷 PNG 는 그대로")


errs = []
sys.excepthook = lambda t, v, tb: errs.append(f"{t.__name__}: {v}")
root = Path(tempfile.mkdtemp(prefix="polypdf_stripdrag_"))
try:
    if OLE:
        ole_part(root)
    else:
        from viewer import shell_drag
        from viewer.widgets.strip import MiniStrip
        from viewer.widgets.photo_strip import PhotoStrip

        calls = []
        plan = {"fn": None}

        def fake_drag(paths, hwnd=0, on_move_drop=None, on_done=None, **kw):
            calls.append((list(paths), dict(kw)))
            if plan["fn"]:
                plan["fn"](paths)
            if on_done:
                on_done(0)
            return {"result": "cancel", "shift": False, "effect": 0, "async": False}
        shell_drag.drag_files = fake_drag
        shell_drag.available = lambda: True

        def esc_soon():
            """수정 전 코드의 Qt 끌기(오프스크린 끌기 고리)를 끝낸다 — 불리지 않으면 아무 일 없다."""
            def f():
                for w in (app.focusWidget(), app.activeWindow(), strip_w, ps_w):
                    if w is not None:
                        QApplication.sendEvent(w, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
                        break
            for ms in (300, 700, 1500):
                QTimer.singleShot(ms, f)

        def mouse_drag(lst, item, mods=Qt.KeyboardModifier.NoModifier):
            lst.scrollToItem(item); spin(2)
            r = lst.visualItemRect(item)
            p0 = r.center()
            vp = lst.viewport()
            esc_soon()
            QTest.mousePress(vp, Qt.MouseButton.LeftButton, mods, p0); spin(2)
            for dx in (6, 14, 30, 50):
                p = QPointF(p0.x() + dx, p0.y() + dx // 3)
                ev = QMouseEvent(QEvent.Type.MouseMove, p, QPointF(vp.mapToGlobal(p.toPoint())),
                                 Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, mods)
                QApplication.sendEvent(vp, ev); spin(1)
            QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, mods, QPoint(p0.x() + 50, p0.y() + 16)); spin(3)

        def click(lst, item, mods=Qt.KeyboardModifier.NoModifier):
            lst.scrollToItem(item); spin(1)
            QTest.mouseClick(lst.viewport(), Qt.MouseButton.LeftButton, mods, lst.visualItemRect(item).center()); spin(2)

        # ── A. 스크린샷 스트립
        sh = root / "shots"; sh.mkdir()
        shots = [png(sh / f"컷{i}.png", c) for i, c in enumerate(("#ff0000", "#00ff00", "#0000ff"))]
        strip = MiniStrip("스크린샷", draggable=True)
        strip.resize(600, 260); strip.show(); spin(3)
        for p in shots:
            strip.add_item(p, kind="image", prepend=False)
        spin(3)
        L = strip.list
        strip_w = L
        ps_w = None
        order = lambda: [str(L.item(i).data(MiniStrip.DATA_PATH)) for i in range(L.count())]
        chk(order() == shots, "준비 — 컷 3장", order())
        calls.clear()
        mouse_drag(L, L.item(0))
        chk(calls and norm(calls[-1][0]) == norm([shots[0]]), "A1 컷을 끌면 셸 끌기가 그 PNG 로", calls)
        chk(calls and calls[-1][1].get("effects") == shell_drag.DROPEFFECT_COPY, "A2 복사만(이동 막음)", calls[-1:])
        chk(calls and calls[-1][1].get("mark_own") is False, "A3 책갈피창의 '제 끌기' 표식은 세우지 않는다", calls[-1:])
        click(L, L.item(2)); click(L, L.item(0), Qt.KeyboardModifier.ControlModifier)
        calls.clear()
        mouse_drag(L, L.item(2))
        chk(calls and norm(calls[-1][0]) == norm([shots[0], shots[2]]), "A4 고른 두 컷을 줄 차례로", calls)

        # ── B. 제 스트립에 놓기 = 순서 바꾸기
        res = {}

        def drop_on_self(paths):
            md = QMimeData(); md.setUrls([QUrl.fromLocalFile(p) for p in paths])
            r = L.visualItemRect(L.item(2))
            pt = QPointF(r.right() - 3, r.center().y())
            acts = Qt.DropAction.CopyAction
            e1 = QDragEnterEvent(pt.toPoint(), acts, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            L.dragEnterEvent(e1)
            e2 = QDragMoveEvent(pt.toPoint(), acts, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            L.dragMoveEvent(e2)
            e3 = QDropEvent(pt, acts, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            L.dropEvent(e3)
            res.update(enter=e1.isAccepted(), drop=e3.isAccepted(), act=e3.dropAction())
        click(L, L.item(0))
        plan["fn"] = drop_on_self
        calls.clear()
        mouse_drag(L, L.item(0))
        plan["fn"] = None
        spin(3)
        chk(calls and res.get("drop"), "B1 끄는 컷을 제 스트립에 놓으면 받는다", res)
        chk(order() == [shots[1], shots[2], shots[0]], "B2 놓은 자리(맨 뒤 컷 오른쪽)로 옮긴다", [Path(p).name for p in order()])
        chk(res.get("act") == Qt.DropAction.CopyAction, "B3 놓기 효과 = 복사(파일은 그대로)", res)
        chk(all(os.path.exists(p) for p in shots), "B4 PNG 는 그대로")

        # ── C. 사진 썸네일 줄
        ph = root / "photos"; ph.mkdir()
        photos = [png(ph / f"사진{i}.jpg", c) for i, c in enumerate(("#123456", "#654321", "#abcdef"))]
        pst = PhotoStrip(); pst.resize(220, 600); pst.show()
        ps_w = pst
        pst.set_paths(photos, photos[0]); spin(10)
        outs = []
        pst.drag_out = lambda ps: outs.append(list(ps))
        mouse_drag(pst, pst.item(1))
        chk(outs and norm(outs[-1]) == norm([photos[1]]), "C1 썸네일을 끌면 앱의 drag_out 이 그 사진으로", outs)
        click(pst, pst.item(0)); click(pst, pst.item(2), Qt.KeyboardModifier.ControlModifier)
        outs.clear()
        mouse_drag(pst, pst.item(2))
        chk(outs and norm(outs[-1]) == norm([photos[0], photos[2]]), "C2 고른 두 칸을 줄 차례로", outs)

        # ── D. _photo_drag_out 거르기
        try:
            from viewer.photo_controller import PhotoMixin
            from viewer import photo_zip, photo_device
            zc = Path(photo_zip.cache_root()) / "z1"; zc.mkdir(parents=True, exist_ok=True)
            dc = Path(photo_device.cache_root()) / "d1"; dc.mkdir(parents=True, exist_ok=True)
            zp = png(zc / "zip안.jpg", "#111111"); dp = png(dc / "폰.jpg", "#222222")

            class _BT:
                def __init__(self):
                    self.got = []

                def drag_out(self, ps):
                    self.got.append(list(ps))
                    return {"result": "cancel"}

            class _Stub:
                pass
            st = _Stub(); st.bookmark_tree = _BT(); st.notes = []
            st._photo_any_cached = lambda ps: PhotoMixin._photo_any_cached(st, ps)
            st._photo_ro_notice = lambda: st.notes.append(1)
            PhotoMixin._photo_drag_out(st, [photos[0], zp, dp, str(ph / "없음.jpg"), photos[2]])
            chk(st.bookmark_tree.got and norm(st.bookmark_tree.got[-1]) == norm([photos[0], photos[2]]),
                "D1 zip·휴대 장치 캐시·없는 파일은 빼고 책갈피창 한 길로", st.bookmark_tree.got)
            st.bookmark_tree.got.clear()
            PhotoMixin._photo_drag_out(st, [zp, dp])
            chk(not st.bookmark_tree.got and st.notes, "D2 다 빠지면 끌지 않고 읽기 전용 안내", (st.bookmark_tree.got, st.notes))
        except AttributeError as e:
            chk(False, "D _photo_drag_out 이 있다", e)

        # ── E. OLE 놓기 대상(Windows — 실제 창이 필요해 별도 프로세스)
        if sys.platform == "win32":
            env = dict(os.environ, PYTHONIOENCODING="utf-8"); env.pop("QT_QPA_PLATFORM", None)
            r = subprocess.run([sys.executable, os.path.abspath(__file__), "--ole"], env=env,
                               capture_output=True, timeout=240)
            out = r.stdout.decode("utf-8", "replace")
            for ln in out.splitlines():
                if ln.startswith(("PASS", "FAIL")):
                    print("   ", ln)
            chk(r.returncode == 0, "E 앱 안 놓기 대상(별도 프로세스) 통과", out[-800:] + r.stderr.decode("utf-8", "replace")[-800:])
finally:
    chk(not errs, "처리 안 된 예외 없음", errs)
    print("ALL PASS" if not fails else f"FAIL {len(fails)}: {fails}")
    sys.stdout.flush()
    os._exit(1 if fails else 0)
