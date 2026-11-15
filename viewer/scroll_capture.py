"""스크롤 캡처 (261115-14, 스크린샷 SOT §3.2).

누른 PolyPDF 스크롤 칸에 앱 안 휠을 자동으로 보내며 내리고, 찍은 그림들을 줄(행) 단위로 겹침을 맞춰 한 장으로 잇는다.

- `RowStitcher` — 이어 붙이기(순수 계산, QImage 만). `add(img)` → 'first' | 'added' | 'same' | 'nomatch' | 'full'.
- `ScrollCaptureRun` — 진행(타이머만, 메인 반복문 없음). 찍기·휠은 주입한다(`grab_fn()`, `wheel_fn(notches)`).
- `ScrollCapturePanel` — 영역 밖에 뜨는 멈춤 띠(진행·[멈춤]).
- `ScrollPicker`·`target_at` — 눌러 시작(덮개가 누름을 받음), 대상 = 누른 PolyPDF 스크롤 칸의 보이는 폭 전체(261115-14 덧붙임).
- `ClickCatcher` — 진행 중 한 번 더 누르거나 Esc 면 끝(앱 안 이벤트 거르개, 누름은 위젯에 보내지 않음).
- `ScrollComposeWorker` — 합성·화질 맞춤·PNG 저장(배경 스레드).
- `own_widget_at`·`app_wheel`·`app_grab` — 앱 안 창 길(다른 프로그램 길은 없다 — 백신 오인 방지, 스크린샷 SOT §3.2).
"""
from __future__ import annotations

from typing import Callable, List, Optional

from PyQt6.QtCore import QObject, QPoint, QPointF, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QWidget

from viewer.i18n import tr

# ── 상수(스크린샷 SOT §3.2 와 같은 값) ─────────────────────────
WAIT_MS = 300          # 휠 뒤 첫 찍기까지
SETTLE_MS = 150        # 화면이 멎었나 다시 찍는 간격
SETTLE_TRIES = 6
POLL_MS = 50           # 멈춤 확인(stop_poll 을 줄 때)
FIRST_NOTCHES = 3
NOTCH_MIN, NOTCH_MAX = 1, 15
STEP_FRACTION = 0.6    # 한 번에 몸통 높이의 이만큼 움직이게
MATCH_MIN = 0.85
OVERLAP_MIN = 8
SAME_END = 2           # 바뀜 없음이 이만큼 잇따르면 끝
MAX_H = 16000          # 결과 높이 상한(장치 px)
MAX_PIXELS = 24_000_000   # 메인의 카드 썸네일(PNG 읽기)·클립보드가 1초 아래로(검사 F)
MAX_STEPS = 400
WHEEL_DELTA = 120


def _scrollbar_margin(w: int, dpr: float) -> int:
    return min(int(round(18 * dpr)), w // 8)


class RowStitcher:
    """줄 지문으로 겹침을 찾아 잇는다. 그림은 모두 같은 크기여야 한다(장치 px)."""

    def __init__(self, dpr: float = 1.0, max_h: int = MAX_H, max_pixels: int = MAX_PIXELS):
        self.dpr = float(dpr or 1.0)
        self.max_h = int(max_h)
        self.max_pixels = int(max_pixels)
        self.first: Optional[QImage] = None
        self.last: Optional[QImage] = None
        self._last_rows: List[int] = []
        self.parts: List[QImage] = []     # 첫 그림(바닥 빼고) 다음에 이은 몸통 조각들
        self.head_cut = None              # 첫 그림에서 뺄 바닥 줄 수(첫 이음 때 정해짐)
        self.foot = 0                     # 마지막 그림의 바닥 고정 띠 줄 수
        self.frames = 0
        self.last_shift = 0               # 지난 이동량(줄)
        self.body_h = 0                   # 지난 비교의 몸통 높이

    # 줄 지문
    def _rows(self, img: QImage) -> List[int]:
        im = img.convertToFormat(QImage.Format.Format_RGB32)
        w, h, bpl = im.width(), im.height(), im.bytesPerLine()
        use = max(1, w - _scrollbar_margin(w, self.dpr)) * 4
        ptr = im.constBits()
        ptr.setsize(im.sizeInBytes())
        buf = bytes(ptr)
        return [hash(buf[y * bpl: y * bpl + use]) for y in range(h)]

    def height(self) -> int:
        if self.first is None:
            return 0
        h = self.first.height()
        if self.head_cut is None:
            return h
        return h - self.head_cut + sum(p.height() for p in self.parts) + self.foot

    def _full(self, extra: int) -> bool:
        if self.first is None:
            return False
        h = self.height() + extra
        return h >= self.max_h or h * self.first.width() >= self.max_pixels

    def add(self, img: QImage) -> str:
        img = img.convertToFormat(QImage.Format.Format_RGB32)
        rows = self._rows(img)
        if self.first is None:
            self.first = img
            self.last, self._last_rows = img, rows
            self.frames = 1
            return "first"
        if img.size() != self.last.size():
            return "nomatch"
        prev = self._last_rows
        h = len(rows)
        t = 0
        while t < h and rows[t] == prev[t]:
            t += 1
        if t >= h:
            return "same"
        b = 0
        while b < h - t and rows[h - 1 - b] == prev[h - 1 - b]:
            b += 1
        mp, mn = prev[t:h - b], rows[t:h - b]
        s = self._find_shift(mp, mn)
        if s is None:
            return "nomatch"
        n = len(mn)
        new_rows = s                               # 몸통 맨 아래 s 줄이 새로 나타났다
        if self.head_cut is None:
            self.head_cut = b
        if self._full(new_rows):
            # 상한까지만 잘라 잇는다
            room = max(0, min(self.max_h - self.height(),
                              self.max_pixels // max(1, img.width()) - self.height()))
            if room > 0:
                self.parts.append(img.copy(0, t + n - s, img.width(), min(room, s)))
            self.foot = 0
            self.frames += 1
            return "full"
        self.parts.append(img.copy(0, t + n - s, img.width(), s))
        self.foot = b
        self.last, self._last_rows = img, rows
        self.last_shift, self.body_h = s, n
        self.frames += 1
        return "added"

    def _find_shift(self, mp: List[int], mn: List[int]) -> Optional[int]:
        n = len(mn)
        if n < OVERLAP_MIN + 1:
            return None
        min_ov = max(OVERLAP_MIN, n // 20)
        # ① 정확히 같은 이동량
        exact = [s for s in range(1, n - min_ov + 1) if mn[:n - s] == mp[s:]]
        if exact:
            want = self.last_shift
            if want:
                return min(exact, key=lambda s: (abs(s - want), s))
            return exact[0]
        # ② 드문 줄을 닻으로 — 후보마다 일치 비율
        pos = {}
        for i, v in enumerate(mp):
            pos.setdefault(v, []).append(i)
        cnt = {}
        for v in mn:
            cnt[v] = cnt.get(v, 0) + 1
        cands = set()
        anchors = 0
        for i, v in enumerate(mn):
            if cnt[v] != 1 or v not in pos or len(pos[v]) > 3:
                continue
            for p in pos[v]:
                s = p - i
                if 1 <= s <= n - min_ov:
                    cands.add(s)
            anchors += 1
            if anchors >= 24:
                break
        best, best_r = None, 0.0
        for s in cands:
            ov = n - s
            hit = sum(1 for a, c in zip(mn[:ov], mp[s:]) if a == c)
            r = hit / ov
            if r > best_r or (r == best_r and best is not None and s < best):
                best, best_r = s, r
        if best is not None and best_r >= MATCH_MIN:
            return best
        return None

    def segments(self):
        """합성할 조각 [(그림, y0, 높이)…] — 첫 그림 머리+몸통, 이은 몸통들, 마지막 바닥."""
        if self.first is None:
            return []
        h = self.first.height()
        cut = self.head_cut or 0
        segs = [(self.first, 0, h - cut)]
        for p in self.parts:
            segs.append((p, 0, p.height()))
        if self.foot and self.last is not None and self.head_cut is not None:
            segs.append((self.last, h - self.foot, self.foot))
        return segs


def compose(segments, scale: float = 1.0) -> QImage:
    """조각을 위에서 아래로 그린 한 장(배경 스레드에서도 된다 — QImage·QPainter 만)."""
    if not segments:
        return QImage()
    w = segments[0][0].width()
    total = sum(hh for _im, _y, hh in segments)
    out = QImage(w, max(1, total), QImage.Format.Format_RGB32)
    out.fill(QColor("white"))
    p = QPainter(out)
    y = 0
    for im, y0, hh in segments:
        p.drawImage(QRect(0, y, w, hh), im, QRect(0, y0, w, hh))
        y += hh
    p.end()
    if scale and abs(scale - 1.0) > 1e-3:
        out = out.scaled(max(1, int(round(w / scale))), max(1, int(round(total / scale))),
                         Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return out


class ScrollComposeWorker(QObject):
    """합성 → (보이는 화질이면 배율로 줄임) → PNG 저장. 메인을 세우지 않게 배경에서."""
    done = pyqtSignal(object, object)     # (저장 경로 str | None, QImage)
    finished = pyqtSignal()

    def __init__(self, segments, scale: float, source_name: str):
        super().__init__()
        self._segs = segments
        self._scale = scale
        self._name = source_name

    def run(self):
        path, img = None, QImage()
        try:
            from viewer import screenshot as ss
            img = compose(self._segs, self._scale)
            if not img.isNull():
                path = str(ss.save_screenshot(img, source_name=self._name, suffix="_S"))
        except Exception:
            path = None
        self._segs = None
        self.done.emit(path, img)
        self.finished.emit()


# ── 진행 ────────────────────────────────────────────────────
class ScrollCaptureRun(QObject):
    """휠 → (대기) → 찍기 → 잇기 를 타이머로 되풀이. 끝나면 `finished(이유)`.

    이유: 'end'(끝까지) | 'noscroll'(휠을 받지 않는 창) | 'nomatch' | 'full'(상한) | 'stopped'(사용자 멈춤) | 'steps'."""
    progress = pyqtSignal(int, int)      # (찍은 장 수, 지금 높이)
    finished = pyqtSignal(str)

    def __init__(self, grab_fn: Callable[[], QImage], wheel_fn: Callable[[int], None],
                 dpr: float = 1.0, stop_poll: Optional[Callable[[], bool]] = None,
                 wait_ms: int = WAIT_MS, settle_ms: int = SETTLE_MS, parent=None):
        super().__init__(parent)
        self._grab = grab_fn
        self._wheel = wheel_fn
        self._stop_poll = stop_poll
        self.stitcher = RowStitcher(dpr)
        self.wait_ms, self.settle_ms = int(wait_ms), int(settle_ms)
        self.notches = FIRST_NOTCHES
        self.reason = None
        self._same = 0
        self._steps = 0
        self._pending: Optional[QImage] = None
        self._tries = 0
        self._step_timer = QTimer(self)
        self._step_timer.setSingleShot(True)
        self._step_timer.timeout.connect(self._on_grab)
        self._poll = QTimer(self)
        self._poll.setInterval(POLL_MS)
        self._poll.timeout.connect(self._on_poll)

    def start(self):
        img = self._grab()
        if img is None or img.isNull():
            self._end("nomatch")
            return
        self.stitcher.add(img)
        self.progress.emit(self.stitcher.frames, self.stitcher.height())
        if self._stop_poll is not None:
            self._poll.start()
        self._next()

    def stop(self):
        """사용자 멈춤 — 그때까지 찍은 것을 남긴다."""
        if self.reason is None:
            self._end("stopped")

    def _on_poll(self):
        try:
            if self._stop_poll and self._stop_poll():
                self.stop()
        except Exception:
            pass

    def _next(self):
        if self.reason is not None:
            return
        self._steps += 1
        if self._steps > MAX_STEPS:
            self._end("steps")
            return
        try:
            self._wheel(self.notches)
        except Exception:
            self._end("noscroll" if self.stitcher.frames <= 1 else "end")
            return
        self._pending = None
        self._tries = 0
        self._step_timer.start(self.wait_ms)

    def _on_grab(self):
        if self.reason is not None:
            return
        img = self._grab()
        if img is None or img.isNull():
            self._end("nomatch")
            return
        # 화면이 멎었나 — 앞 찍기와 같을 때까지(최대 SETTLE_TRIES)
        if self._pending is not None and self._tries < SETTLE_TRIES and img != self._pending:
            self._pending = img
            self._tries += 1
            self._step_timer.start(self.settle_ms)
            return
        if self._pending is None and self._tries == 0:
            self._pending = img
            self._tries = 1
            self._step_timer.start(self.settle_ms)
            return
        self._take(img)

    def _take(self, img: QImage):
        st = self.stitcher
        r = st.add(img)
        if r == "same":
            self._same += 1
            if self._same >= SAME_END:
                self._end("noscroll" if st.frames <= 1 else "end")
                return
            self._next()
            return
        if r == "nomatch":
            self._end("nomatch")
            return
        self.progress.emit(st.frames, st.height())
        if r == "full":
            self._end("full")
            return
        self._same = 0
        # 한 칸에 움직인 줄 수로 다음 칸 수를 맞춘다(겹침이 남게)
        per = st.last_shift / max(1, self.notches)
        if per > 0 and st.body_h > 0:
            want = int(st.body_h * STEP_FRACTION / per)
            self.notches = max(NOTCH_MIN, min(NOTCH_MAX, want))
        self._next()

    def _end(self, reason: str):
        if self.reason is not None:
            return
        self.reason = reason
        self._step_timer.stop()
        self._poll.stop()
        self.finished.emit(reason)


# ── 멈춤 띠 ─────────────────────────────────────────────────
class ScrollCapturePanel(QWidget):
    stopRequested = pyqtSignal()

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setObjectName("scrollCapturePanel")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 6, 6)
        self.label = QLabel(tr("스크롤 캡처 중 — 한 번 더 누르면 여기까지 저장 (Esc·[멈춤]도)"), self)
        lay.addWidget(self.label)
        self.btn = QPushButton(tr("멈춤"), self)
        self.btn.clicked.connect(self.stopRequested.emit)
        lay.addWidget(self.btn)
        self.setStyleSheet("#scrollCapturePanel{background:#202124;border:1px solid #2a7de1;}"
                           "#scrollCapturePanel QLabel{color:white;}")

    def set_progress(self, frames: int, height: int):
        self.label.setText(tr("스크롤 캡처 중 — {n}장 · 높이 {h}px · 한 번 더 누르면 여기까지 저장").format(
            n=frames, h=height))
        self.adjustSize()

    def place(self, region: QRect, screen_geo: QRect):
        """영역 밖 — 위, 모자라면 아래, 둘 다 없으면 화면 위 모서리."""
        self.adjustSize()
        w, h = self.sizeHint().width(), self.sizeHint().height()
        x = max(screen_geo.left(), min(region.left(), screen_geo.right() - w))
        if region.top() - h - 4 >= screen_geo.top():
            y = region.top() - h - 4
        elif region.bottom() + 4 + h <= screen_geo.bottom():
            y = region.bottom() + 4
        else:
            y = screen_geo.top()
        self.move(x, y)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.stopRequested.emit()
            return
        super().keyPressEvent(e)


# ── 앱 안 창 길 ──────────────────────────────────────────────
def own_widget_at(gpos: QPoint, exclude=()) -> Optional[QWidget]:
    """전역 좌표 아래의 PolyPDF 위젯(없으면 None — 다른 프로그램)."""
    try:
        w = QApplication.widgetAt(gpos)
    except Exception:
        return None
    if w is None:
        return None
    top = w.window()
    if top in exclude or w in exclude:
        return None
    return w


def app_wheel(target: QWidget, gpos: QPoint, notches: int):
    """앱 안 위젯에 휠(아래로)을 직접 — 커서를 옮기지 않는다."""
    from PyQt6.QtGui import QWheelEvent
    w = target
    while w is not None:                       # 받지 않으면(ignore) 부모로 — 실제 휠처럼 올라간다
        lp = w.mapFromGlobal(gpos)
        ev = QWheelEvent(QPointF(lp), QPointF(gpos), QPoint(0, 0), QPoint(0, -WHEEL_DELTA * int(notches)),
                         Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                         Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(w, ev)
        if ev.isAccepted() or w.isWindow():
            return
        w = w.parentWidget()


def app_grab(window: QWidget, grect: QRect) -> QImage:
    """앱 창의 그 영역(전역 논리 좌표)을 창 그림으로 — 멈춤 띠 같은 다른 창은 찍히지 않는다."""
    tl = window.mapFromGlobal(grect.topLeft())
    return window.grab(QRect(tl, grect.size())).toImage()


# ── 눌러 시작 (261115-14 덧붙임 — PolyPDF 화면만) ─────────────────
MIN_TARGET = 160          # 대상 스크롤 칸의 가로·세로 최소(장치 px)
CATCH_RELEASE_MS = 2000   # 끝난 뒤 누른 단추를 뗄 때까지 가로채기를 두는 최대 시간


class _PickOverlay(QWidget):
    """한 화면을 덮는 옅은 덮개 — 누름·뗌을 받아 아래 창에 보내지 않는다."""

    def __init__(self, picker: "ScrollPicker", screen, hint: bool):
        super().__init__(None)
        self._picker = picker
        self._hint = hint
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setObjectName("scrollPickOverlay")
        self.setGeometry(screen.geometry())
        self.text = tr("캡처할 곳을 누르세요 — PolyPDF 화면의 스크롤되는 곳을 자동으로 내리며 한 장으로 찍습니다 · Esc = 취소")
        self._pressed = False

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 48))
        if self._hint:
            f = p.font()
            f.setPointSizeF(max(11.0, f.pointSizeF() * 1.25))
            p.setFont(f)
            fm = p.fontMetrics()
            tw, th = fm.horizontalAdvance(self.text) + 32, fm.height() + 18
            box = QRect((self.width() - tw) // 2, 40, tw, th)
            p.fillRect(box, QColor(32, 33, 36, 235))
            p.setPen(QColor("#2a7de1"))
            p.drawRect(box.adjusted(0, 0, -1, -1))
            p.setPen(QColor("white"))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, self.text)
        p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            self._picker.cancel()
            return
        if e.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
        e.accept()

    def mouseReleaseEvent(self, e):
        e.accept()
        if e.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            self._picker._pick(e.globalPosition().toPoint())

    def mouseDoubleClickEvent(self, e):
        e.accept()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self._picker.cancel()
            return
        super().keyPressEvent(e)


class ScrollPicker(QObject):
    """'캡처할 곳을 누르세요' — 화면마다 덮개. 뗄 때 덮개를 닫고 `picked(전역 논리 점)`, Esc·오른쪽 클릭이면 `cancelled`."""
    picked = pyqtSignal(QPoint)
    cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.overlays: List[_PickOverlay] = []
        self.done = False

    def start(self):
        from PyQt6.QtGui import QCursor
        cur = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        for s in QGuiApplication.screens():
            ov = _PickOverlay(self, s, hint=(s is cur))
            self.overlays.append(ov)
            ov.show()
            if s is cur:
                ov.raise_()
                ov.activateWindow()
                ov.setFocus()

    def _close(self):
        for ov in self.overlays:
            try:
                ov.hide()
                ov.close()
            except RuntimeError:
                pass
        self.overlays = []

    def _pick(self, gpos: QPoint):
        if self.done:
            return
        self.done = True
        self._close()
        self.picked.emit(QPoint(gpos))

    def cancel(self):
        if self.done:
            return
        self.done = True
        self._close()
        self.cancelled.emit()


def target_at(gpos: QPoint, exclude=()):
    """누른 점 → (대상 QRect 전역 논리 좌표 | None, 이유). 이유: 'ok' | 'outside'(PolyPDF 창 아님) | 'noscroll'(스크롤되는 곳 아님).

    대상 = 그 점 아래 PolyPDF 창에서 점을 담은 스크롤 영역(QAbstractScrollArea)의 보이는 칸 가운데 가장 작은 것 —
    본문처럼 위에 덮개 위젯이 겹쳐도 찾는다. 폭은 그 칸의 보이는 폭 전체(스크린샷 SOT §3.2)."""
    from PyQt6.QtWidgets import QAbstractScrollArea
    w = own_widget_at(gpos, exclude=exclude)
    if w is None:
        return None, "outside"
    win = w.window()
    cands = list(win.findChildren(QAbstractScrollArea))
    if isinstance(win, QAbstractScrollArea):
        cands.append(win)
    best, best_a = None, None
    for sa in cands:
        try:
            if not sa.isVisible():
                continue
            vp = sa.viewport()
            if vp is None or not vp.isVisible():
                continue
            r = QRect(vp.mapToGlobal(QPoint(0, 0)), vp.size())
            dpr = float(vp.devicePixelRatioF() or 1.0)
            if not r.contains(gpos) or r.width() * dpr < MIN_TARGET or r.height() * dpr < MIN_TARGET:
                continue
            a = r.width() * r.height()
            if best_a is None or a < best_a:
                best, best_a = r, a
        except RuntimeError:
            continue
    if best is None:
        return None, "noscroll"
    return best, "ok"


class ClickCatcher(QObject):
    """스크롤 캡처 진행 중 PolyPDF 화면의 누름(클릭·터치)과 Esc 를 받아 `clicked` 를 낸다 — 앱 안 이벤트 거르개만
    (전역 훅·키 상태 엿보기 없음 — 백신 오인 방지, 스크린샷 SOT §3.2). 누름·뗌은 삼켜 그 아래 위젯에 보내지 않고,
    `close()` 뒤에도 누른 단추를 뗄 때까지(최대 CATCH_RELEASE_MS) 남아 뗌이 홀로 가지 않게 한다."""
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        from PyQt6.QtCore import QEvent
        self._press_types = (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick)
        self._release_type = QEvent.Type.MouseButtonRelease
        self._key_type = QEvent.Type.KeyPress
        self._held = False
        self._closing = False
        self._active = False

    def start(self):
        self._active = True
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t in self._press_types:
            if not self._held:
                self._held = True
                if not self._closing:
                    self.clicked.emit()
            return True
        if t == self._release_type:
            if self._held:
                self._held = False
                if self._closing:
                    QTimer.singleShot(0, self._finish)
            return True
        if t == self._key_type and not self._closing:
            try:
                if ev.key() == Qt.Key.Key_Escape:
                    self.clicked.emit()
                    return True
            except Exception:
                pass
        return False

    def close(self):
        """가로채기를 끝낸다 — 단추가 눌려 있으면 뗄 때까지(최대 CATCH_RELEASE_MS)."""
        if not self._active or self._closing:
            return
        self._closing = True
        if self._held:
            QTimer.singleShot(CATCH_RELEASE_MS, self._finish)
        else:
            self._finish()

    def _finish(self):
        if not self._active:
            return
        self._active = False
        try:
            QApplication.instance().removeEventFilter(self)
        except Exception:
            pass
        self.deleteLater()
