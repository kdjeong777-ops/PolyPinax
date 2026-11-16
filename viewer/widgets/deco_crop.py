# -*- coding: utf-8 -*-
"""편집 모드 사진 꾸밈 `크롭` — Word 처럼 보이는 범위만 자르기, Shift+손잡이 = 그 점만(모양 펴기) (261116-24, 마스터 §4.6.11 '크롭').

- 원래 그림은 꾸밈 안에 보관한다(`extra.crop_src`, 벡터 조각이면 `extra.crop_pdf`) — 다시 `크롭` 하면 잘린 바깥이 다시 보이고
  `크롭 해제` 로 원래대로. `data` 는 늘 잘린(편) 그림이라 저장·인쇄·복사 등 읽는 길은 그대로다.
- `extra.crop` = `{pts: 점 8개(원래 그림 비율, photo_warp.POINT_NAMES 차례), full: [dx, dy, sw, sh]}` —
  full 은 지금 사진 자리(`rect`) 기준으로 잰 원래 그림 자리: full_x = x + dx·w, full_w = sw·w (y·h 도 같다). 옮기고 키워도 맞는다.
- 점의 뜻·펴기 계산은 `photo_warp`(사진 크롭 '모양 펴기'·영역 캡처와 같다). 펴기는 배경(응답성 SOT §5).
"""
from __future__ import annotations

import base64
import io
import math

from PyQt6.QtCore import Qt, QObject, QPointF, QRectF, QEvent, pyqtSignal
from PyQt6.QtGui import QColor, QPainterPath, QPen, QPixmap, QTransform

from viewer import photo_warp as pw

HANDLE_PX = 8           # 손잡이 잡는 반경(화면 px)
MIN_FRAC = 0.02         # 네모 크롭의 가장 작은 폭·높이(원래 그림 비율)
_CURVE_N = 16
_KEEP: list = []        # 배경 펴기 스레드·워커 참조(run_in_thread 가 끝나면 스스로 뺀다)


def is_rect(pts) -> bool:
    """네 귀가 축에 나란한 직사각형이고 변이 곧은가 — 손잡이 끌기가 '변 자르기' 인 모양."""
    tl, tr_, br, bl = pts[:4]
    t = pw.STRAIGHT_TOL
    return (pw.is_straight(pts) and abs(tl[1] - tr_[1]) <= t and abs(bl[1] - br[1]) <= t
            and abs(tl[0] - bl[0]) <= t and abs(tr_[0] - br[0]) <= t)


def rect_points(x0, y0, x1, y1) -> list:
    c = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return c + pw.mids_of(c)


def b64_png(img) -> str:
    bio = io.BytesIO()
    img.save(bio, "PNG")
    return base64.b64encode(bio.getvalue()).decode("ascii")


def _unwarp_png(src_b64: str, pts):
    """배경 스레드 몫 — 원래 그림(b64 PNG)을 점 8개로 펴서 (b64 PNG, 폭, 높이)."""
    from PIL import Image
    im = Image.open(io.BytesIO(base64.b64decode(src_b64))).convert("RGBA")
    out = pw.unwarp(im, pts)
    return b64_png(out), out.width, out.height


class _WarpWorker(QObject):
    """사진 꾸밈 크롭 모양 펴기 — 배경 한 번(응답성 SOT §4.4 표). 결과는 (b64, 폭, 높이), 실패면 None."""
    done = pyqtSignal(object)
    finished = pyqtSignal()

    def __init__(self, src_b64, pts):
        super().__init__()
        self._args = (src_b64, pts)

    def run(self):
        res = None
        try:
            res = _unwarp_png(*self._args)
        except Exception:
            res = None
        finally:
            self.done.emit(res)
            self.finished.emit()


class DecoCrop:
    """크롭 틀 하나 — `MainView` 가 들고 그림·마우스·키를 넘긴다."""

    def __init__(self, owner, idx: int):
        self.o = owner
        self.objs = owner._img_objects                  # 쪽을 넘겨도 이 목록·이 자리에 저장한다
        self.key = (str(owner.current_file() or ""), int(owner._current_page))
        self.obj = self.objs[idx]
        ex = dict(self.obj.get("extra") or {})
        self.src_b64 = ex.get("crop_src") or self.obj.get("data") or owner._pix_to_b64(self.obj["pix"])
        self.src_pix = QPixmap()
        self.src_pix.loadFromData(base64.b64decode(self.src_b64), "PNG")
        r = list(self.obj["rect"])
        # 돌린 사진(사용자 결정 '돌린 것도 포함'): 모든 계산은 돌리기 전 틀(`rect` 와 같은 쪽 비율)에서 하고,
        #   화면에는 지금 사진 가운데(c0)를 축으로 `rot` 만큼 돌려 보인다 — 사진 자체를 그리는 `_img_geom` 과 같은 축·방향
        self.rot = float(self.obj.get("rot", 0.0) or 0.0)
        self.c0 = (r[0] + r[2] / 2.0, r[1] + r[3] / 2.0)
        crop = ex.get("crop")
        if crop:
            dx, dy, sw, sh = crop["full"]
            self.full = [r[0] + dx * r[2], r[1] + dy * r[3], sw * r[2], sh * r[3]]
            self.pts = [tuple(p) for p in crop["pts"]]
        else:
            self.full = r
            self.pts = pw.default_points(0.0)
        self.pts0 = list(self.pts)
        self.drag = None

    # ── 좌표 ──
    def _full_v(self, pr) -> QRectF:
        fx, fy, fw, fh = self.full
        return QRectF(pr.left() + fx * pr.width(), pr.top() + fy * pr.height(), fw * pr.width(), fh * pr.height())

    def _center_v(self, pr) -> QPointF:
        return QPointF(pr.left() + self.c0[0] * pr.width(), pr.top() + self.c0[1] * pr.height())

    def _xf(self, pr) -> QTransform:
        """돌리기 전 화면 좌표 → 보이는 화면 좌표(지금 사진 가운데를 축으로 rot)."""
        c = self._center_v(pr)
        t = QTransform()
        t.translate(c.x(), c.y())
        t.rotate(self.rot)
        t.translate(-c.x(), -c.y())
        return t

    def _to_v_flat(self, pr, p) -> QPointF:
        f = self._full_v(pr)
        return QPointF(f.left() + p[0] * f.width(), f.top() + p[1] * f.height())

    def _to_v(self, pr, p) -> QPointF:
        return self._xf(pr).map(self._to_v_flat(pr, p))

    def _to_f(self, pr, pos):
        q, _ok = self._xf(pr).inverted()
        u = q.map(QPointF(pos))
        f = self._full_v(pr)
        return ((u.x() - f.left()) / max(1.0, f.width()), (u.y() - f.top()) / max(1.0, f.height()))

    def _path(self, pr) -> QPainterPath:
        return self._xf(pr).map(self._path_flat(pr))

    def _path_flat(self, pr) -> QPainterPath:
        v = [(q.x(), q.y()) for q in (self._to_v_flat(pr, p) for p in self.pts)]
        tl, tr_, br, bl, tm, rm, bm, lm = v
        path = QPainterPath(QPointF(*tl))
        for a, m, b in ((tl, tm, tr_), (tr_, rm, br), (br, bm, bl), (bl, lm, tl)):
            for i in range(1, _CURVE_N + 1):
                path.lineTo(QPointF(*pw._quad_curve(a, m, b, i / _CURVE_N)))
        path.closeSubpath()
        return path

    def _hit(self, pr, pos):
        for i, p in enumerate(self.pts):
            q = self._to_v(pr, p)
            if abs(q.x() - pos.x()) <= HANDLE_PX and abs(q.y() - pos.y()) <= HANDLE_PX:
                return i
        return None

    # ── 점 옮기기 ──
    def move_point(self, i: int, xy) -> bool:
        """그 점만 — 꼭짓점이면 곧은 채였던 이웃 변 가운데도 따라간다(영역 캡처·사진 크롭과 같은 뜻). 꼬이면 안 옮긴다."""
        x, y = min(1.0, max(0.0, xy[0])), min(1.0, max(0.0, xy[1]))
        pts = list(self.pts)
        if i < 4:
            before = pw.mids_of(pts[:4])
            follow = [math.hypot(pts[4 + k][0] - before[k][0], pts[4 + k][1] - before[k][1]) <= pw.STRAIGHT_TOL for k in range(4)]
            pts[i] = (x, y)
            after = pw.mids_of(pts[:4])
            for k in range(4):
                if follow[k]:
                    pts[4 + k] = after[k]
        else:
            pts[i] = (x, y)
        if not pw.is_valid(pts):
            return False
        self.pts = pts
        return True

    def move_edge(self, i: int, xy) -> None:
        """네모 크롭 — 꼭짓점은 두 변, 변 가운데는 그 변. 원래 그림 밖으로는 못 나간다."""
        x0, y0 = self.pts[0]
        x1, y1 = self.pts[2]
        x, y = min(1.0, max(0.0, xy[0])), min(1.0, max(0.0, xy[1]))
        if i in (0, 3, 7):
            x0 = min(x, x1 - MIN_FRAC)
        if i in (1, 2, 5):
            x1 = max(x, x0 + MIN_FRAC)
        if i in (0, 1, 4):
            y0 = min(y, y1 - MIN_FRAC)
        if i in (2, 3, 6):
            y1 = max(y, y0 + MIN_FRAC)
        self.pts = rect_points(x0, y0, x1, y1)

    # ── 마우스 ──
    def event(self, t, ev, pr):
        """처리했으면 True, 아니면 None. 틀 밖을 누르면 적용하고 그 누르기는 먹는다."""
        if t == QEvent.Type.MouseButtonPress and ev.button() == Qt.MouseButton.LeftButton:
            pos = ev.position()
            i = self._hit(pr, pos)
            shift = bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            if i is not None:
                self.drag = ("pt", i, shift)
            elif self._path(pr).contains(pos):
                self.drag = ("move", list(self.pts), self._to_f(pr, pos))
            else:
                self.o.finish_image_crop(True)
            return True
        if t == QEvent.Type.MouseMove and self.drag is not None:
            f = self._to_f(pr, ev.position())
            if self.drag[0] == "pt":
                _k, i, shift = self.drag
                shift = shift or bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                if shift or not is_rect(self.pts):
                    self.move_point(i, f)
                else:
                    self.move_edge(i, f)
            else:
                base, start = self.drag[1], self.drag[2]
                xs, ys = [p[0] for p in base], [p[1] for p in base]
                dx = max(-min(xs), min(1.0 - max(xs), f[0] - start[0]))
                dy = max(-min(ys), min(1.0 - max(ys), f[1] - start[1]))
                self.pts = [(x + dx, y + dy) for x, y in base]
            self.o._draw_overlay.update()
            return True
        if t == QEvent.Type.MouseButtonRelease and self.drag is not None:
            self.drag = None
            return True
        if t in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease, QEvent.Type.MouseMove):
            return True                                  # 틀이 떠 있는 동안 본문 끌기·그리기는 하지 않는다
        return None

    # ── 그리기 ──
    def paint(self, p, pr):
        fv = self._full_v(pr)
        p.save()
        p.setTransform(self._xf(pr), True)               # 돌린 사진 — 사진과 같은 축으로 돌려 그린다
        p.setOpacity(0.35)                               # 잘린 바깥 — 흐리게
        p.drawPixmap(fv.toRect(), self.src_pix)
        p.setOpacity(1.0)
        path = self._path_flat(pr)
        p.setClipPath(path)
        p.drawPixmap(fv.toRect(), self.src_pix)
        p.setClipping(False)
        p.setPen(QPen(QColor("#202020"), 1.5, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.setPen(QPen(QColor("#ffffff"), 1.5))
        p.setBrush(QColor("#202020"))
        for i, pt in enumerate(self.pts):
            q = self._to_v_flat(pr, pt)
            if i < 4:
                p.drawRect(QRectF(q.x() - 5, q.y() - 5, 10, 10))
            else:
                p.drawEllipse(q, 5, 5)
        p.restore()

    def _placed(self, rect):
        """돌리기 전 틀의 새 자리 → 실제 `rect`. 사진은 제 가운데를 축으로 돌므로, 가운데가 바뀌면 보이는 자리가 어긋난다 —
        새 가운데를 옛 축(c0)으로 rot 만큼 돌린 자리로 옮겨, 보이는 그림이 틀 그대로 남게 한다. 0° 면 그대로."""
        if abs(self.rot) < 1e-9:
            return list(rect)
        pr = self.o._page_view_rect()
        W, H = (pr.width(), pr.height()) if pr is not None and pr.width() > 0 else (1.0, 1.0)
        nx, ny = rect[0] + rect[2] / 2.0, rect[1] + rect[3] / 2.0
        dx, dy = (nx - self.c0[0]) * W, (ny - self.c0[1]) * H
        a = math.radians(self.rot)
        rx, ry = dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)
        cx, cy = self.c0[0] + rx / W, self.c0[1] + ry / H
        return [cx - rect[2] / 2.0, cy - rect[3] / 2.0, rect[2], rect[3]]

    # ── 적용 ──
    def apply(self):
        """지금 점으로 꾸밈을 바꾼다. 네모면 바로, 점을 옮겼으면 배경에서 펴고 끝나면."""
        pts = pw.clamp_points(self.pts)
        if all(abs(a[0] - b[0]) < 1e-4 and abs(a[1] - b[1]) < 1e-4 for a, b in zip(pts, self.pts0)):
            return                                       # 바뀐 것 없음
        if is_rect(pts):
            x0, y0 = pts[0]
            x1, y1 = pts[2]
            if x0 <= 1e-4 and y0 <= 1e-4 and x1 >= 1 - 1e-4 and y1 >= 1 - 1e-4:
                self.reset()
                return
            from PIL import Image
            im = Image.open(io.BytesIO(base64.b64decode(self.src_b64))).convert("RGBA")
            W, H = im.size
            out = im.crop((int(round(x0 * W)), int(round(y0 * H)), max(int(round(x0 * W)) + 1, int(round(x1 * W))),
                           max(int(round(y0 * H)) + 1, int(round(y1 * H)))))
            fx, fy, fw, fh = self.full
            rect = [fx + x0 * fw, fy + y0 * fh, (x1 - x0) * fw, (y1 - y0) * fh]
            self._set(b64_png(out), rect, pts, rect_crop=(x0, y0, x1, y1))
            return
        from viewer.workers import run_in_thread
        wk = _WarpWorker(self.src_b64, pts)
        wk.done.connect(lambda res, pts=pts: self._warp_done(res, pts))
        run_in_thread(wk, _KEEP)                          # 응답성 SOT §4.3 규약

    def _warp_done(self, res, pts):
        if not res:
            return
        b64, ow, oh = res
        fx, fy, fw, fh = self.full
        xs = [fx + x * fw for x, _ in pts[:4]]
        ys = [fy + y * fh for _, y in pts[:4]]
        bx, by, bw = min(xs), min(ys), max(xs) - min(xs)
        pr = self.o._page_view_rect()
        aspect = (pr.width() / max(1.0, pr.height())) if pr is not None else 1.0
        rect = [bx, by, bw, bw * (oh / max(1, ow)) * aspect]
        self._set(b64, rect, pts, rect_crop=None)

    def _set(self, data_b64, rect, pts, rect_crop):
        o = self.obj
        ex = dict(o.get("extra") or {})
        ex.setdefault("crop_src", self.src_b64)
        if "pdf" in ex and "crop_pdf" not in ex:
            ex["crop_pdf"] = ex["pdf"]
        ex.pop("pdf", None)
        if rect_crop and ex.get("crop_pdf"):              # 벡터 조각 — 네모면 벡터 그대로 잘라 둔다
            try:
                from viewer import stamp_core
                ex["pdf"] = base64.b64encode(stamp_core.crop_piece(base64.b64decode(ex["crop_pdf"]), rect_crop)).decode("ascii")
            except Exception:
                pass
        fx, fy, fw, fh = self.full
        ex["crop"] = {"pts": [[round(x, 5), round(y, 5)] for x, y in pts],
                      "full": [round((fx - rect[0]) / rect[2], 6), round((fy - rect[1]) / rect[3], 6),
                               round(fw / rect[2], 6), round(fh / rect[3], 6)]}
        pix = QPixmap()
        pix.loadFromData(base64.b64decode(data_b64), "PNG")
        o.update(pix=pix, data=data_b64, rect=self._placed(rect), extra=ex)    # full 은 돌리기 전 틀끼리 잰 값이라 옮겨도 맞다
        self.o._crop_save(self)

    def reset(self):
        """크롭 해제 — 원래 그림·원래 자리로."""
        o = self.obj
        ex = dict(o.get("extra") or {})
        if "crop" not in ex:
            return
        src = ex.pop("crop_src", None) or o.get("data")
        if ex.get("crop_pdf"):
            ex["pdf"] = ex.pop("crop_pdf")
        ex.pop("crop", None)
        pix = QPixmap()
        pix.loadFromData(base64.b64decode(src), "PNG")
        o.update(pix=pix, data=src, rect=self._placed(self.full), extra=ex)
        self.o._crop_save(self)
