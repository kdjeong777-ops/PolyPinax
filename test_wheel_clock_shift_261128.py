# -*- coding: utf-8 -*-
"""261128-7(입력 장치 SOT §2.2 규칙 7): 이벤트 시계와 처리 시계가 통째로 벌어져도 휠로 쪽이 넘어간다.

사용자 보고 '검색항목을 선택한 후에 본화면을 클릭시 마우스의 스크롤 버튼이 안되'(쪽 맞춤, '계속 안 됨').
원인: 휠의 '늦게 처리된 칸' 판정은 (처리 시각 − 이벤트 시각) 을 가장 작았던 값에 견주는데, 사용자 노트북은 절전을 거치며
처리 시계(`perf_counter`)가 이벤트 시계보다 119초 앞섰다(실측) — 앱을 켠 채 깨어나면 모든 휠이 '늦음' 이라 쪽 맞춤에서
쪽이 영영 넘어가지 않았다(키보드는 됨). 실제 휠 이벤트(시각 붙임)를 뷰포트에 보내서:
  A  두 시계가 맞을 때 휠 한 칸에 한 쪽(종전 그대로)
  B  두 시계가 5초 벌어진 뒤에도 휠로 넘어간다(첫 칸만 버려도 됨) — 수정 전 코드는 0쪽이라 실패
  C  정말 늦게 처리된 칸(창이 멈춘 사이 굴린 칸)은 종전대로 넘기지 않는다 — 한 칸·몰려 처리된 여러 칸 모두
  D  그 뒤 보통 휠은 다시 넘어간다
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
        time.sleep(0.005)
    app.processEvents()


from viewer.widgets.main_view import MainView, _perf_ms
from test_fixtures import text_pdf

m = MainView()
m.resize(900, 800)
m.show(); pump()
m.set_page_flip_anim(False)
m.load_document(text_pdf(), 0)
if m.shown_fit() != MainView.FIT_PAGE:
    m.choose_fit(MainView.FIT_PAGE)
pump(100)
vp = m.view.viewport()
shift = [0]                                            # 이벤트 시계가 처리 시계보다 얼마나 뒤처졌나(ms)


class _Wheel(QWheelEvent):
    """OS 가 붙이는 이벤트 시각을 흉내 — PyQt6 에는 setTimestamp 가 없어 timestamp() 를 바꾼다(전달은 같은 객체)."""
    ts = 0

    def timestamp(self):
        return self.ts


def wheel(dy=-120, late=0, gap=300):
    ev = _Wheel(QPointF(200, 200), QPointF(vp.mapToGlobal(QPoint(200, 200))), QPoint(0, 0), QPoint(0, dy),
                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    ev.ts = int(_perf_ms()) - shift[0] - late           # late 는 정말 늦게 처리된 몫
    QApplication.sendEvent(vp, ev)
    if gap:
        pump(gap)


# A
p0 = m.current_page()
for _ in range(3):
    wheel()
chk(m.current_page() == p0 + 3, "A 두 시계가 맞으면 휠 한 칸에 한 쪽", "%d → %d" % (p0, m.current_page()))

# B — 절전에서 깨어남: 처리 시계가 5초 앞섰다
shift[0] = 5000
p1 = m.current_page()
for _ in range(4):
    wheel()
chk(m.current_page() >= p1 + 3, "B 두 시계가 벌어진 뒤에도 휠로 넘어간다(첫 칸만 버림)", "%d → %d" % (p1, m.current_page()))

# C — 정말 늦게 처리된 칸
p2 = m.current_page()
wheel(late=1000)
chk(m.current_page() == p2, "C 창이 멈춘 사이 굴린 한 칸은 넘기지 않는다", "%d → %d" % (p2, m.current_page()))
p3 = m.current_page()
for i in range(3):                                     # 멈춘 사이 쌓였다 한꺼번에 처리되는 칸들
    wheel(late=600 - 20 * i, gap=0)
pump(300)
chk(m.current_page() == p3, "C 몰려 처리된 늦은 칸들도 넘기지 않는다", "%d → %d" % (p3, m.current_page()))

# D
p4 = m.current_page()
for _ in range(2):
    wheel()
chk(m.current_page() == p4 + 2, "D 그 뒤 보통 휠은 다시 한 칸에 한 쪽", "%d → %d" % (p4, m.current_page()))

print()
print("FAILED:", len(fails)) if fails else print("ALL PASS")
sys.stdout.flush()
os._exit(1 if fails else 0)
