# -*- coding: utf-8 -*-
"""261128-11(입력 장치 SOT §2.12 W6): 휠 값이 `angleDelta` 없이 `pixelDelta` 로만 와도 쪽 맞춤에서 쪽이 넘어간다.

지금 Windows 는 늘 `angleDelta`(한 칸 120)를 주지만 Qt 판이 바뀌어 `pixelDelta` 만 오면 종전 코드는 '가로 휠' 로 보고 쪽을 넘기지
않았다 — 업그레이드 뒤 '휠이 안 됨' 이 된다. 실제 휠 이벤트(시각 없음 = 합성)를 뷰포트에 보내서:
  A  `wheel_dy` — angleDelta 가 있으면 그 값, 0 이면 pixelDelta
  B  pixelDelta 만 오는 보통 칸(−120) 세 번 → 세 쪽
  C  pixelDelta 만 오는 작은 값 흐름(터치패드 꼴) 한 번 → 한 쪽(넘어가기는 한다)
  D  위로도(+120) 넘어간다
수정 전 코드는 B 부터 0쪽이라 실패한다(A 는 함수가 없어 실패).
"""
import os, sys, time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths
QStandardPaths.setTestModeEnabled(True)               # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPoint, QPointF
from PyQt6.QtGui import QWheelEvent
app = QApplication.instance() or QApplication([])
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def pump(ms=0):
    end = time.perf_counter() + ms / 1000.0
    app.processEvents()
    while time.perf_counter() < end:
        app.processEvents()
        time.sleep(0.003)
    app.processEvents()


def ev(px=0, ang=0):
    return QWheelEvent(QPointF(200, 200), QPointF(vp.mapToGlobal(QPoint(200, 200))), QPoint(0, px), QPoint(0, ang),
                       Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)


from viewer.widgets.main_view import MainView
from test_fixtures import text_pdf

m = MainView()
m.resize(900, 800)
m.show(); pump()
m.set_page_flip_anim(False)
m.load_document(text_pdf(), 3)
if m.shown_fit() != MainView.FIT_PAGE:
    m.choose_fit(MainView.FIT_PAGE)
pump(100)
vp = m.view.viewport()

# A
try:
    from viewer.wheel_latch import wheel_dy
    chk(wheel_dy(ev(px=-30, ang=-120)) == -120 and wheel_dy(ev(px=-45)) == -45 and wheel_dy(ev()) == 0,
        "A wheel_dy — angleDelta 먼저, 0 이면 pixelDelta")
except ImportError:
    chk(False, "A wheel_dy — angleDelta 먼저, 0 이면 pixelDelta", "없음")

# B
p0 = m.current_page()
for _ in range(3):
    QApplication.sendEvent(vp, ev(px=-120)); pump(300)
chk(m.current_page() == p0 + 3, "B pixelDelta 만 오는 보통 칸 세 번 → 세 쪽", "%d → %d" % (p0, m.current_page()))

# C
pump(400)
p1 = m.current_page()
for _ in range(14):
    QApplication.sendEvent(vp, ev(px=-15)); pump(12)
pump(400)
chk(m.current_page() == p1 + 1, "C pixelDelta 작은 값 흐름 한 번 → 한 쪽", "%d → %d" % (p1, m.current_page()))

# D
p2 = m.current_page()
for _ in range(2):
    QApplication.sendEvent(vp, ev(px=120)); pump(300)
chk(m.current_page() == p2 - 2, "D 위로도 넘어간다", "%d → %d" % (p2, m.current_page()))

print()
print("FAILED:", len(fails)) if fails else print("ALL PASS")
sys.stdout.flush()
os._exit(1 if fails else 0)
