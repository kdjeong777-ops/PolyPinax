# -*- coding: utf-8 -*-
"""261116-18: 영역 캡처 모양 펴기 — Shift+점 끌기 = 그 점만, 캡처하면 펴서 (스크린샷 SOT §3.1).

A. 고치기 단계에서 Shift+꼭짓점 끌기 = 그 귀만 움직인다(다른 귀 그대로, 곧은 이웃 변 가운데 점은 따라감)
B. Shift+변 가운데 점 끌기 = 그 점만(그 변이 휜다, 꼭짓점 그대로) — 사진 크롭 모양 펴기와 같은 뜻
C. Shift 없이 끌면 종전처럼 사각형 크기(점 모드가 되지 않는다)
D. 꼬이는 자리로는 옮기지 않는다 · 안쪽 끌기·화살표 = 모양 그대로 옮기기 · 오른쪽 클릭 = 다시 고르기(사각형)
E. Enter 로 캡처 — 원근으로 찍힌 사각형을 펴서 돌려준다(공용 photo_warp, 배경 스레드, 메인 하트비트 공백 < 1초),
   region_out = 감싸는 사각형
F. 안내 줄에 Shift+점 끌기 · 점 모드의 안내
"""
import os, sys, time, threading
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtCore import QStandardPaths, Qt, QPoint, QPointF, QRect, QTimer, QElapsedTimer
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QPainter, QColor, QPolygonF
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


from viewer.widgets.region_capture import RegionCaptureOverlay

L, R = Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton
SH = Qt.KeyboardModifier.ShiftModifier
NO = Qt.KeyboardModifier.NoModifier


def overlay(bg=None, **k):
    ov = RegionCaptureOverlay(mode="region", **k)
    if bg is not None:
        ov._bg = bg
        ov._dpr = 1.0
    ov.resize(800, 600)
    ov.show(); app.processEvents()
    return ov


def drag(ov, a, b, mod=NO):
    QTest.mousePress(ov, L, mod, QPoint(*a))
    QTest.mouseMove(ov, QPoint((a[0] + b[0]) // 2, (a[1] + b[1]) // 2))
    QTest.mouseMove(ov, QPoint(*b))
    QTest.mouseRelease(ov, L, mod, QPoint(*b))


def pts(ov):
    return getattr(ov, "_pts", None)


def near(p, q, tol=1.01):
    return abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol


# ── A. Shift+꼭짓점 ─────────────────────────────────────────────────
ov = overlay()
drag(ov, (100, 100), (400, 300))
chk(ov._phase == "edit" and ov._rect.normalized() == QRect(QPoint(100, 100), QPoint(400, 300)), "준비 — 영역 정함")
h_rect = ov.hint()
drag(ov, (400, 300), (440, 340), SH)
P = pts(ov)
ok = (P is not None and near(P[2], (440, 340)) and near(P[0], (100, 100)) and near(P[1], (400, 100))
      and near(P[3], (100, 300)) and near(P[5], (420, 220)) and near(P[6], (270, 320)) and near(P[4], (250, 100)))
chk(ok, "A Shift+꼭짓점 끌기 = 그 귀만(곧은 이웃 변 가운데는 따라감)", str(P))

# ── B. Shift+변 가운데 점 ────────────────────────────────────────────
ov2 = overlay()
drag(ov2, (100, 100), (400, 300))
drag(ov2, (250, 100), (250, 70), SH)              # 위 변 가운데
P2 = pts(ov2)
ok = (P2 is not None and near(P2[4], (250, 70)) and near(P2[0], (100, 100)) and near(P2[1], (400, 100))
      and near(P2[2], (400, 300)) and near(P2[3], (100, 300)))
chk(ok, "B Shift+변 가운데 끌기 = 그 점만(꼭짓점 그대로 — 그 변이 휜다)", str(P2))
h_shape = ov2.hint()

# ── C. Shift 없이 = 종전 크기 ────────────────────────────────────────
ov3 = overlay()
drag(ov3, (100, 100), (400, 300))
drag(ov3, (400, 300), (450, 350))
chk(pts(ov3) is None and ov3._rect.normalized() == QRect(QPoint(100, 100), QPoint(450, 350)),
    "C Shift 없이 끌면 종전처럼 사각형 크기", f"{pts(ov3)} {ov3._rect}")
ov3.close()

# ── D. 꼬임 막기·옮기기·다시 고르기 ───────────────────────────────────
before = list(pts(ov))
drag(ov, (440, 340), (50, 50))                    # 오른쪽 아래 귀를 왼쪽 위 너머로 — 꼬인다
chk(pts(ov) is not None and near(pts(ov)[2], before[2], 40) and pts(ov)[2][0] > 300,
    "D 꼬이는 자리로는 옮기지 않는다", str(pts(ov)))
b1 = list(pts(ov))
drag(ov, (250, 200), (270, 230))                  # 안쪽 끌기
b2 = list(pts(ov))
chk(all(near(q, (p[0] + 20, p[1] + 30)) for p, q in zip(b1, b2)), "D 안쪽 끌기 = 모양 그대로 옮기기", str(b2))
QTest.keyClick(ov, Qt.Key.Key_Left, SH)
b3 = list(pts(ov))
chk(all(near(q, (p[0] - 10, p[1])) for p, q in zip(b2, b3)), "D Shift+화살표 = 10px 옮기기")
QTest.mouseClick(ov, R, pos=QPoint(10, 10))
chk(ov._phase == "place" and pts(ov) is None, "D 오른쪽 클릭 = 다시 고르기(사각형으로)")
ov.close()

# ── F. 안내 ──────────────────────────────────────────────────────
chk("Shift" in h_rect and "그 점만" in h_rect, "F 고치기 단계 안내에 Shift+점 끌기", h_rect)
chk(h_shape != h_rect and "펴서" in h_shape, "F 점 모드 안내", h_shape)
ov2.close()

# ── E. 캡처 = 펴서 ────────────────────────────────────────────────
W, H = 1600, 1000
bg = QPixmap(W, H)
bg.fill(QColor("white"))
quad = [(300, 200), (1300, 260), (1200, 850), (350, 800)]   # 원근으로 찍힌 검은 판
pp = QPainter(bg)
pp.setPen(Qt.PenStyle.NoPen)
pp.setBrush(QColor("black"))
pp.drawPolygon(QPolygonF([QPointF(x, y) for x, y in quad]))
pp.end()

ov = overlay(bg)
ov.resize(W, H); app.processEvents()
drag(ov, (300, 200), (1300, 850))
for i, (x, y) in ((1, quad[1]), (2, quad[2]), (3, quad[3])):
    name = {1: (1300, 200), 2: (1300, 850), 3: (300, 850)}[i]
    cur = pts(ov)[i] if pts(ov) is not None else name
    drag(ov, (int(round(cur[0])), int(round(cur[1]))), (x, y), SH)
P = pts(ov)
chk(P is not None and all(near(P[i], quad[i]) for i in range(4)), "E 준비 — 네 귀를 검은 판에 맞춤", str(P))

import viewer.photo_warp as pwmod
seen = {}
_orig = pwmod.unwarp


def spy(*a, **k):
    seen["thread"] = threading.current_thread() is threading.main_thread()
    time.sleep(1.5)                                    # 무거운 펴기 흉내 — 메인이 멈추지 않아야 한다
    return _orig(*a, **k)


pwmod.unwarp = spy
gaps = []
el = QElapsedTimer(); el.start()
last = [el.elapsed()]


def beat():
    now = el.elapsed(); gaps.append(now - last[0]); last[0] = now


hb = QTimer(); hb.timeout.connect(beat); hb.start(20)
QTimer.singleShot(0, lambda: QTest.keyClick(ov, Qt.Key.Key_Return))
res = None
t0 = time.time()
ov._loop = None
from PyQt6.QtCore import QEventLoop
loop = QEventLoop()
ov._loop = loop
QTimer.singleShot(8000, loop.quit)
loop.exec()
hb.stop()
pwmod.unwarp = _orig
res = ov._result
chk(seen.get("thread") is False, "E 펴기는 배경 스레드에서", str(seen))
chk(gaps and max(gaps) < 1000, "E 펴는 동안 메인 하트비트 공백 < 1초", f"max={max(gaps) if gaps else None}ms")
if res is not None and not res.isNull():
    im = res.toImage()
    w, h = im.width(), im.height()
    dark = 0
    tot = 0
    for yy in range(4, h - 4, max(1, h // 40)):
        for xx in range(4, w - 4, max(1, w // 40)):
            tot += 1
            if QColor(im.pixel(xx, yy)).lightness() < 60:
                dark += 1
    chk(dark / max(1, tot) > 0.97, "E 결과는 편 그림 — 검은 판이 가장자리까지 꽉 참", f"{dark}/{tot} size={w}x{h}")
    chk(800 <= w <= 1100 and 500 <= h <= 700, "E 크기 = 마주 보는 변 평균(photo_warp.out_size)", f"{w}x{h}")
else:
    chk(False, "E Enter 로 캡처하면 펴진 그림", str(res))
out = ov.region_out
chk(out is not None and out[:4] == [300, 200, 1000, 650], "E region_out = 감싸는 사각형", str(out))

print("\n=== " + ("ALL PASS" if not fails else f"FAILURE ({len(fails)})") + " ===")
for m in fails:
    print(" -", m)
sys.stdout.flush()
os._exit(1 if fails else 0)
