"""화면 영역 캡처 오버레이 (260606-17 → 261014-18 '영역 캡처', 스크린샷 SOT §3.1).

- mode='region'(영역 캡처): **누른 채 끌어 놓기** 로 영역(클릭 두 번 — 한 모서리·맞은편 모서리 — 도 된다).
  시작 단계에서 Enter/Space = 지난 영역(`last_region`, 같은 화면일 때).
- mode='fixed'(사용자 크기): 클릭한 곳을 좌상단으로 그 크기 상자를 놓는다.
- 고치기 단계: 안쪽 끌기 = 옮기기, 꼭짓점·변 끌기 = 크기, 화살표 = 1 px(Shift 10 px), Ctrl+화살표 = 크기.
- 확정: Enter 또는 더블클릭. 취소: Esc, 오른쪽 클릭(고치기 단계에서는 다시 고르기).
- 모양 펴기(261116-18): 고치기 단계에서 Shift+손잡이 끌기 = 그 점만(점 8개 — 사진 크롭 '모양 펴기'와 같은 뜻), 캡처하면
  `photo_warp.unwarp` 로 직사각형으로 펴서 돌려준다(배경 스레드 — 응답성 SOT §4.4).
- copy_mode='visible'(보이는 크기, 논리 픽셀) / 'original'(원본 = 장치 픽셀).

grab() 가 QPixmap(또는 None)을 반환(로컬 이벤트 루프). 끝난 뒤 `region_out` = `[x, y, w, h, 화면 이름]`(영역 캡처일 때).
"""
from __future__ import annotations

import math
from typing import Optional

from PyQt6.QtCore import Qt, QRect, QPoint, QPointF, QEventLoop, QSize, QObject, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QGuiApplication, QPixmap, QCursor, QPainterPath, QImage
from PyQt6.QtWidgets import QWidget
from viewer import photo_warp as pw
from viewer.i18n import tr
from viewer.workers import run_in_thread

_HANDLE = 8        # 핸들 히트 반경(px)
_MIN = 12          # 최소 박스 크기
DRAG_MIN = 4       # 이보다 덜 끌었으면 클릭으로 본다(클릭 두 번 방식) — 스크린샷 SOT §3.1
_CURVE_N = 24      # 휜 변을 그리고 감싸는 사각형을 잴 때 한 변의 마디 수
_KEEP: list = []   # 배경 펴기 스레드·워커 참조(run_in_thread 가 끝나면 스스로 뺀다)
# 손잡이 이름 → 점 8개(photo_warp.POINT_NAMES: TL·TR·BR·BL·T·R·B·L)의 번호
_PT_INDEX = {"tl": 0, "tr": 1, "br": 2, "bl": 3, "t": 4, "r": 5, "b": 6, "l": 7}


def _unwarp_bytes(data: bytes, w: int, h: int, bpl: int, pts, size):
    """배경 스레드 몫 — RGB888 바이트 그림을 점 8개(비율) 테두리로 펴서 (바이트, 폭, 높이)."""
    from PIL import Image
    im = Image.frombuffer("RGB", (w, h), data, "raw", "RGB", bpl, 1)
    out = pw.unwarp(im, pts, size=size).convert("RGB")
    return out.tobytes(), out.width, out.height


class _WarpWorker(QObject):
    """영역 캡처 모양 펴기 — 배경 한 번(응답성 SOT §4.4 표). 결과는 (바이트, 폭, 높이), 실패면 None."""
    done = pyqtSignal(object)
    finished = pyqtSignal()

    def __init__(self, args):
        super().__init__()
        self._args = args
        self._cancel = False

    def request_cancel(self):
        self._cancel = True

    def run(self):
        res = None
        try:
            if not self._cancel:
                res = _unwarp_bytes(*self._args)
        except Exception:
            res = None
        finally:
            self.done.emit(res)
            self.finished.emit()


class RegionCaptureOverlay(QWidget):
    def __init__(self, mode: str = "region", fixed_size=None,
                 copy_mode: str = "visible", parent=None, last_region=None):
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._mode = mode
        self._fixed = QSize(*fixed_size) if fixed_size else QSize(300, 200)
        self._copy_mode = copy_mode
        self._result: Optional[QPixmap] = None
        self._loop: Optional[QEventLoop] = None
        self.region_out = None

        scr = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        self._screen = scr
        self._dpr = scr.devicePixelRatio()
        self._bg = scr.grabWindow(0)                 # 장치픽셀 픽스맵
        geo = scr.geometry()
        self.setGeometry(geo)

        self._rect = QRect()           # 현재 선택 박스(위젯 좌표)
        self._phase = "place"          # place → (region: sizing) → edit
        self._drag = None              # 'move' | 'tl','tr','bl','br','l','r','t','b'
        self._drag_off = QPoint()
        self._origin = QPoint()
        self._pressed = False          # sizing 중 누른 채인가(끌어 고르기)
        self._pts = None               # 모양 펴기 점 8개(위젯 좌표, float) — None 이면 사각형(261116-18)
        self._move_base = None         # 모양 옮기기 시작 때의 점
        self._warp_thread = None       # 배경 펴기(캡처 때)
        self._warp_box = None
        self._last = None              # 지난 영역(같은 화면일 때만)
        try:
            if mode == "region" and last_region and len(last_region) == 5 \
                    and str(last_region[4]) == scr.name():
                x, y, w, h = (int(v) for v in last_region[:4])
                r = QRect(x, y, w, h).intersected(QRect(QPoint(0, 0), geo.size()))
                if r.width() >= _MIN and r.height() >= _MIN:
                    self._last = r
        except Exception:
            self._last = None

    # ── 공개 ──────────────────────────────────────────────────
    def grab(self) -> Optional[QPixmap]:
        self.showFullScreen()
        self.activateWindow()
        self.raise_()
        self.setFocus()
        self._loop = QEventLoop()
        self._loop.exec()
        return self._result

    def _finish(self, ok: bool):
        if self._warp_thread is not None:            # 이미 펴는 중
            return
        if ok and self._pts is not None:
            self._start_warp()
            return
        if ok and self._rect.isValid() and self._rect.width() >= _MIN and self._rect.height() >= _MIN:
            r = self._rect.normalized()
            # 위젯 좌표 → 장치픽셀
            dp = QRect(int(r.x() * self._dpr), int(r.y() * self._dpr),
                       int(r.width() * self._dpr), int(r.height() * self._dpr))
            pm = self._bg.copy(dp)
            if self._copy_mode == "visible" and self._dpr != 1.0:
                pm = pm.scaled(r.width(), r.height(),
                               Qt.AspectRatioMode.IgnoreAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            self._result = pm
            if self._mode == "region":
                self.region_out = [r.x(), r.y(), r.width(), r.height(), self._screen.name()]
        else:
            self._result = None
        self.close()
        if self._loop:
            self._loop.quit()

    # ── 모양 펴기(261116-18, 스크린샷 SOT §3.1) ───────────────────
    def _curve_points(self) -> list:
        """테두리를 따라 찍은 점들(위젯 좌표) — 휜 변까지."""
        tl, trc, br, bl, tm, rm, bm, lm = self._pts
        out = [tl]
        for p0, mid, p2 in ((tl, tm, trc), (trc, rm, br), (br, bm, bl), (bl, lm, tl)):
            out += [pw._quad_curve(p0, mid, p2, i / _CURVE_N) for i in range(1, _CURVE_N + 1)]
        return out

    def _shape_path(self) -> QPainterPath:
        path = QPainterPath()
        pts = self._curve_points()
        path.moveTo(QPointF(*pts[0]))
        for q in pts[1:]:
            path.lineTo(QPointF(*q))
        path.closeSubpath()
        return path

    def _shape_box(self) -> QRect:
        """테두리를 감싸는 사각형(위젯 좌표, 화면 안으로)."""
        pts = self._curve_points()
        x0 = max(0, int(math.floor(min(p[0] for p in pts))))
        y0 = max(0, int(math.floor(min(p[1] for p in pts))))
        x1 = min(self.width(), int(math.ceil(max(p[0] for p in pts))))
        y1 = min(self.height(), int(math.ceil(max(p[1] for p in pts))))
        return QRect(x0, y0, max(1, x1 - x0), max(1, y1 - y0))

    def _start_warp(self):
        """캡처 — 테두리를 감싸는 사각형만큼 화면 그림을 잘라 배경에서 편다. 덮개는 먼저 닫고, 로컬 루프가 끝나기를 기다린다."""
        box = self._shape_box()
        d = self._dpr
        dp = QRect(int(box.x() * d), int(box.y() * d), max(1, int(box.width() * d)), max(1, int(box.height() * d)))
        img = self._bg.copy(dp).toImage().convertToFormat(QImage.Format.Format_RGB888)
        w, h, bpl = img.width(), img.height(), img.bytesPerLine()
        data = bytes(img.constBits().asstring(img.sizeInBytes()))
        pts = [((x - box.x()) / box.width(), (y - box.y()) / box.height()) for x, y in self._pts]
        pts = pw.clamp_points(pts)
        size = None
        if self._copy_mode == "visible" and d != 1.0:            # 보이는 크기 — 논리 픽셀로 바로 편다
            ow, oh = pw.out_size(pts, w, h)
            size = (max(pw.OUT_MIN_SIDE, int(round(ow / d))), max(pw.OUT_MIN_SIDE, int(round(oh / d))))
        self._warp_box = box
        self.hide()                                   # 덮개는 숨기고 닫기는 결과가 온 뒤(_warp_done)
        wk = _WarpWorker((data, w, h, bpl, pts, size))
        wk.done.connect(self._warp_done)              # 신호는 grab() 의 로컬 루프가 메인에서 받는다
        self._warp_thread = run_in_thread(wk, _KEEP)  # 응답성 SOT §4.3 규약

    def _warp_done(self, res):
        self._result = None
        if res:
            buf, ow, oh = res
            self._result = QPixmap.fromImage(QImage(buf, ow, oh, 3 * ow, QImage.Format.Format_RGB888).copy())
            if self._mode == "region":
                b = self._warp_box
                self.region_out = [b.x(), b.y(), b.width(), b.height(), self._screen.name()]
        self._warp_thread = None
        self.close()
        if self._loop:
            self._loop.quit()

    def _enter_shape(self):
        """사각형 → 점 8개(네 귀 + 곧은 변 가운데)."""
        r = self._rect.normalized()
        c = [(float(r.left()), float(r.top())), (float(r.right()), float(r.top())),
             (float(r.right()), float(r.bottom())), (float(r.left()), float(r.bottom()))]
        self._pts = c + pw.mids_of(c)

    def move_point(self, i: int, xy) -> bool:
        """점 하나만 옮긴다 — 꼭짓점이면 곧은 채였던 이웃 변의 가운데 점도 따라간다(사진 크롭 `WarpCanvas.move_point` 와 같은 뜻).
        꼬이면(볼록하지 않으면) 옮기지 않는다."""
        x = float(min(self.width() - 1, max(0, xy[0])))
        y = float(min(self.height() - 1, max(0, xy[1])))
        pts = list(self._pts)
        if i < 4:
            tol = pw.STRAIGHT_TOL * max(self.width(), self.height())
            before = pw.mids_of(pts[:4])
            follow = [math.hypot(pts[4 + k][0] - before[k][0], pts[4 + k][1] - before[k][1]) <= tol for k in range(4)]
            pts[i] = (x, y)
            after = pw.mids_of(pts[:4])
            for k in range(4):
                if follow[k]:
                    pts[4 + k] = after[k]
        else:
            pts[i] = (x, y)
        if not pw.is_valid(pts):
            return False
        self._pts = pts
        return True

    def _move_shape(self, base, dx: float, dy: float):
        """점 8개를 모양 그대로 옮긴다 — 화면 밖으로 나가지 않게."""
        xs, ys = [p[0] for p in base], [p[1] for p in base]
        dx = max(-min(xs), min(self.width() - 1 - max(xs), dx))
        dy = max(-min(ys), min(self.height() - 1 - max(ys), dy))
        self._pts = [(x + dx, y + dy) for x, y in base]

    # ── 안내 ──────────────────────────────────────────────────
    def hint(self) -> str:
        """지금 단계에서 되는 조작만(스크린샷 SOT §3.1 표와 같은 말)."""
        if self._phase == "place":
            if self._mode == "fixed":
                return tr('클릭 = {w}×{h} 상자 놓기 · Esc·오른쪽 클릭 = 취소').format(
                    w=self._fixed.width(), h=self._fixed.height())
            s = tr("끌어서 영역 고르기(클릭 두 번도 됩니다) · Esc·오른쪽 클릭 = 취소")
            if self._last is not None:
                s += tr(" · Enter = 지난 영역")
            return s
        if self._phase == "sizing":
            return tr("놓거나 한 번 더 클릭하면 영역이 정해집니다 · Esc·오른쪽 클릭 = 취소")
        if self._pts is not None:
            return tr("Enter·더블클릭 = 펴서 캡처 · 점 끌기 = 그 점만 · 안쪽 끌기·화살표 = 옮기기 · "
                      "오른쪽 클릭 = 다시 고르기 · Esc = 취소")
        if self._mode != "region":       # 사용자 크기 — 오른쪽 클릭은 취소, 모양 펴기 없음(261116-20)
            return tr("Enter·더블클릭 = 캡처 · 끌기 = 옮기기·크기 · 화살표 = 1px(Shift 10px, Ctrl 크기) · "
                      "Esc·오른쪽 클릭 = 취소")
        return (tr("Enter·더블클릭 = 캡처 · 끌기 = 옮기기·크기 · 화살표 = 1px(Shift 10px, Ctrl 크기) · "
                   "오른쪽 클릭 = 다시 고르기 · Esc = 취소")
                + tr(" · Shift+점 끌기 = 그 점만(모양 펴기)"))

    # ── 그리기 ────────────────────────────────────────────────
    def paintEvent(self, _e):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self._bg, self._bg.rect())   # 화면 배경
        p.fillRect(self.rect(), QColor(0, 0, 0, 110))          # 어둡게
        if self._pts is not None:                              # 모양 펴기 — 테두리 안만 밝게, 점 8개(261116-18)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            path = self._shape_path()
            p.save()
            p.setClipPath(path)
            p.drawPixmap(self.rect(), self._bg, self._bg.rect())
            p.restore()
            p.setPen(QPen(QColor("#2a7de1"), 2))
            p.drawPath(path)
            for i, (x, y) in enumerate(self._pts):
                p.setBrush(QColor("#2a7de1") if i < 4 else QColor("white"))
                p.setPen(QPen(QColor("#2a7de1"), 2 if i >= 4 else 1))
                if i < 4:
                    p.drawRect(QRect(int(x) - 3, int(y) - 3, 6, 6))
                else:
                    p.drawEllipse(QPointF(x, y), 4, 4)
            b = self._shape_box()
            p.setPen(QColor("white"))
            p.drawText(b.x(), max(12, b.y() - 6), f"{b.width()} × {b.height()}")
        elif self._rect.isValid():
            r = self._rect.normalized()
            p.drawPixmap(r, self._bg, QRect(
                int(r.x() * self._dpr), int(r.y() * self._dpr),
                int(r.width() * self._dpr), int(r.height() * self._dpr)))  # 선택영역 밝게
            p.setPen(QPen(QColor("#2a7de1"), 2))
            p.drawRect(r)
            if self._phase == "edit":                              # 손잡이는 고칠 수 있을 때만
                p.setBrush(QColor("#2a7de1"))
                for hp in self._handle_points(r).values():
                    p.drawRect(QRect(hp.x() - 3, hp.y() - 3, 6, 6))
            # 크기 — 끄는 동안·고치는 동안
            p.setPen(QColor("white"))
            p.drawText(r.x(), max(12, r.y() - 6), f"{r.width()} × {r.height()}")
        # 안내 — 어두운 띠 위에
        txt = self.hint()
        fm = p.fontMetrics()
        p.fillRect(QRect(8, 6, fm.horizontalAdvance(txt) + 16, fm.height() + 10), QColor(0, 0, 0, 170))
        p.setPen(QColor("white"))
        p.drawText(16, 6 + 5 + fm.ascent(), txt)

    def _handle_points(self, r: QRect) -> dict:
        cx, cy = r.center().x(), r.center().y()
        return {
            "tl": r.topLeft(), "tr": r.topRight(),
            "bl": r.bottomLeft(), "br": r.bottomRight(),
            "t": QPoint(cx, r.top()), "b": QPoint(cx, r.bottom()),
            "l": QPoint(r.left(), cy), "r": QPoint(r.right(), cy),
        }

    def _hit_handle(self, pos: QPoint):
        if self._pts is not None:                     # 모양 펴기 — 'p0'..'p7'(꼭짓점 먼저), 테두리 안 = 옮기기
            best, bd = None, _HANDLE + 1
            for i, (x, y) in enumerate(self._pts):
                d = max(abs(pos.x() - x), abs(pos.y() - y))
                if d < bd - (0.5 if i < 4 else 0):
                    best, bd = "p%d" % i, d
            if best is not None:
                return best
            return "move" if self._shape_path().contains(QPointF(pos)) else None
        if not self._rect.isValid():
            return None
        for name, hp in self._handle_points(self._rect.normalized()).items():
            if abs(pos.x() - hp.x()) <= _HANDLE and abs(pos.y() - hp.y()) <= _HANDLE:
                return name
        if self._rect.normalized().contains(pos):
            return "move"
        return None

    def _to_edit(self, r: QRect):
        self._rect = r.normalized()
        self._phase = "edit"
        self._pressed = False
        self.update()

    # ── 마우스 ────────────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            if self._phase == "edit" and self._mode == "region":   # 다시 고르기
                self._rect = QRect()
                self._pts = None
                self._phase = "place"
                self.setCursor(Qt.CursorShape.CrossCursor)
                self.update()
            else:
                self._finish(False)
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        pos = e.position().toPoint()
        if self._phase == "place":
            if self._mode == "fixed":
                w = min(self._fixed.width(), self.width())
                h = min(self._fixed.height(), self.height())
                self._to_edit(QRect(pos, QSize(w, h)))
            else:
                self._origin = pos
                self._rect = QRect(pos, QSize(1, 1))
                self._phase = "sizing"
                self._pressed = True
                self.update()
            return
        if self._phase == "sizing":
            # 클릭 두 번 방식 — 두 번째 클릭이 맞은편 모서리
            self._to_edit(QRect(self._origin, pos))
            return
        # edit: 핸들/이동 시작
        h = self._hit_handle(pos)
        if (self._pts is None and self._mode == "region" and h in _PT_INDEX
                and e.modifiers() & Qt.KeyboardModifier.ShiftModifier):   # Shift+손잡이 = 그 점만(모양 펴기, 261116-18) — 영역 캡처만(261116-20)
            self._enter_shape()
            h = "p%d" % _PT_INDEX[h]
            self.update()
        self._drag = h
        if h == "move":
            if self._pts is not None:
                self._move_base = (e.position(), list(self._pts))
            else:
                self._drag_off = pos - self._rect.normalized().topLeft()

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._phase == "sizing":
            self._rect = QRect(self._origin, pos)
            self.update()
            return
        if self._phase == "edit" and self._drag and self._pts is not None:   # 모양 펴기 — 점 하나·통째로
            fp = e.position()
            if self._drag == "move":
                p0, base = self._move_base
                self._move_shape(base, fp.x() - p0.x(), fp.y() - p0.y())
            elif self._drag.startswith("p"):
                self.move_point(int(self._drag[1:]), (fp.x(), fp.y()))
            self.update()
            return
        if self._phase == "edit" and self._drag:
            r = self._rect.normalized()
            if self._drag == "move":
                np = pos - self._drag_off
                np.setX(max(0, min(np.x(), self.width() - r.width())))
                np.setY(max(0, min(np.y(), self.height() - r.height())))
                self._rect = QRect(np, r.size())
            else:
                l, t, rr, b = r.left(), r.top(), r.right(), r.bottom()
                if "l" in self._drag:
                    l = min(pos.x(), rr - _MIN)
                if "r" in self._drag:
                    rr = max(pos.x(), l + _MIN)
                if "t" in self._drag:
                    t = min(pos.y(), b - _MIN)
                if "b" in self._drag:
                    b = max(pos.y(), t + _MIN)
                self._rect = QRect(QPoint(l, t), QPoint(rr, b))
            self.update()
            return
        # edit 중 커서 모양
        if self._phase == "edit":
            h = self._hit_handle(pos)
            self.setCursor(self._cursor_for(h))

    def mouseReleaseEvent(self, e):
        self._drag = None
        if self._phase == "sizing" and self._pressed and e.button() == Qt.MouseButton.LeftButton:
            pos = e.position().toPoint()
            self._pressed = False
            d = pos - self._origin
            if abs(d.x()) >= DRAG_MIN or abs(d.y()) >= DRAG_MIN:     # 끌어 놓기 — 영역이 정해진다
                self._to_edit(QRect(self._origin, pos))
            # 아니면 클릭 — 두 번째 클릭을 기다린다(클릭 두 번 방식)

    def mouseDoubleClickEvent(self, e):
        if self._phase == "edit" and e.button() == Qt.MouseButton.LeftButton:
            self._finish(True)

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key.Key_Escape:
            self._finish(False)
            return
        if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if self._phase == "edit":
                if k != Qt.Key.Key_Space:
                    self._finish(True)
            elif self._phase == "place" and self._last is not None:
                self._to_edit(QRect(self._last))               # 지난 영역
            return
        arrows = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0),
                  Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1)}
        if self._phase == "edit" and k in arrows:
            dx, dy = arrows[k]
            step = 10 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
            if self._pts is not None:                                    # 모양 펴기 — 옮기기만(크기 없음)
                if not e.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    self._move_shape(list(self._pts), dx * step, dy * step)
                    self.update()
                return
            r = self._rect.normalized()
            if e.modifiers() & Qt.KeyboardModifier.ControlModifier:      # 크기
                w = max(_MIN, min(self.width() - r.x(), r.width() + dx * step))
                h = max(_MIN, min(self.height() - r.y(), r.height() + dy * step))
                self._rect = QRect(r.topLeft(), QSize(w, h))
            else:                                                         # 옮기기
                x = max(0, min(self.width() - r.width(), r.x() + dx * step))
                y = max(0, min(self.height() - r.height(), r.y() + dy * step))
                self._rect = QRect(QPoint(x, y), r.size())
            self.update()

    @staticmethod
    def _cursor_for(h):
        if h in ("tl", "br"):
            return Qt.CursorShape.SizeFDiagCursor
        if h in ("tr", "bl"):
            return Qt.CursorShape.SizeBDiagCursor
        if h in ("l", "r"):
            return Qt.CursorShape.SizeHorCursor
        if h in ("t", "b"):
            return Qt.CursorShape.SizeVerCursor
        if h == "move" or (h and h.startswith("p")):
            return Qt.CursorShape.SizeAllCursor
        return Qt.CursorShape.CrossCursor
