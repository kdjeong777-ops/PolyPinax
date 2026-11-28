# -*- coding: utf-8 -*-
"""261128-11(입력 장치 SOT §2.12): 휠은 **영영 막히지 않는다** — 어떤 휠 순서 뒤에도 보통 휠 몇 칸이면 쪽이 넘어간다.

사용자 지시 '마우스 스크롤 기능 관련하여 … 앞으로 관련 문제가 생기지 않도록하고, 업그레이드시 문제가 발생하지 않도록'.
'휠이 계속 안 됨(다시 켜야 풀림)' 은 휠 판정의 **남는 상태**(관성 표식·새 손짓 기다림·늦음 기준·창 묶음)가 풀리지 않은 것이었다
(261102-4 관성 표식, 261128-7 두 시계 벌어짐). 상태 하나하나의 검사와 별도로, 무작위로 섞은 휠 순서(고전 휠·작은 값 흐름·
위상 있는 손짓의 끊긴 끝·시각 없는 이벤트·멈춘 사이 늦은 칸·**두 시계가 통째로 밀림**·32비트 되돌이)를 넣은 뒤
보통 휠(시각 맞음, 300ms 간격)로 아래·위 모두 넘어가는지 본다. 앱 전체 휠 묶음(`WheelLatch`)도 건다.
씨앗은 고정 — 실패하면 그 씨앗으로 다시 재현된다. 수정 전 코드(261128-7 앞)는 '시계 밀림' 이 든 씨앗에서 실패한다.
"""
import os, sys, time, random

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


from viewer.widgets.main_view import MainView, _perf_ms
from viewer.wheel_latch import WheelLatch
from test_fixtures import text_pdf

latch = WheelLatch()
app.installEventFilter(latch)                          # 앱과 같게 — 휠 묶음도 막힘의 후보다
m = MainView()
m.resize(900, 800)
m.show(); pump()
m.set_page_flip_anim(False)
m.load_document(text_pdf(), 0)
if m.shown_fit() != MainView.FIT_PAGE:
    m.choose_fit(MainView.FIT_PAGE)
pump(100)
vp = m.view.viewport()
N = m._doc.page_count
P = Qt.ScrollPhase


class _Wheel(QWheelEvent):
    """OS 가 붙이는 이벤트 시각 — PyQt6 엔 setTimestamp 가 없어 timestamp() 를 바꾼다(전달은 같은 객체)."""
    ts = 0

    def timestamp(self):
        return self.ts


clock = {"shift": 0}                                   # 이벤트 시계가 처리 시계보다 뒤처진 몫(ms) — 절전에서 깨면 통째로 바뀐다


def send(dy, phase=P.NoScrollPhase, late=0, ts=None):
    ev = _Wheel(QPointF(200, 200), QPointF(vp.mapToGlobal(QPoint(200, 200))), QPoint(0, 0), QPoint(0, dy),
                Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, phase, False)
    ev.ts = (int(_perf_ms()) - clock["shift"] - late) & 0xFFFFFFFF if ts is None else ts
    QApplication.sendEvent(vp, ev)


def chaos(rng, n=28):
    """무작위 휠 순서 — 실제로 본 막힘의 재료를 섞는다."""
    kinds = []
    for _ in range(n):
        k = rng.choice(("notch", "smooth", "phased_cut", "zero_ts", "late", "shift", "wrap", "burst"))
        kinds.append(k)
        d = rng.choice((-1, 1))
        if k == "notch":
            send(-120 * d); pump(rng.randint(5, 260))
        elif k == "smooth":
            for _ in range(rng.randint(3, 12)):
                send(-rng.randint(8, 70) * d); pump(rng.randint(6, 18))
        elif k == "phased_cut":                        # 손을 뗀 관성이 끝(ScrollEnd) 없이 끊김
            send(-30 * d, P.ScrollBegin); pump(10)
            for _ in range(rng.randint(1, 5)):
                send(-40 * d, P.ScrollUpdate); pump(10)
            for _ in range(rng.randint(0, 6)):
                send(-25 * d, P.ScrollMomentum); pump(12)
        elif k == "zero_ts":
            send(-120 * d, ts=0); pump(rng.randint(5, 200))
        elif k == "late":                              # 창이 멈춘 사이 굴린 칸
            send(-120 * d, late=rng.randint(300, 3000)); pump(rng.randint(5, 120))
        elif k == "shift":                             # 절전에서 깨어남 — 두 시계가 통째로 밀림(앞으로·뒤로)
            clock["shift"] += rng.choice((rng.randint(400, 50000), -rng.randint(400, 50000)))
        elif k == "wrap":                              # 32비트 시각 되돌이(49.7일)
            clock["shift"] += rng.choice((2 ** 32 - 5000, -(2 ** 32) + 5000))
        elif k == "burst":                             # 멈춘 사이 쌓였다 한꺼번에 처리
            lt = rng.randint(300, 2000)
            for i in range(rng.randint(2, 5)):
                send(-120 * d, late=lt - 15 * i)
            pump(50)
    return kinds


def recovers(direction):
    """보통 휠(시각 맞음, 300ms 간격) 4칸 — 그 방향으로 두 쪽 이상 넘어가야 한다(첫 칸은 버려도 된다)."""
    p0 = m.current_page()
    for _ in range(4):
        send(-120 * direction); pump(300)
    return (m.current_page() - p0) * direction >= 2, p0, m.current_page()


SEEDS = list(range(1, 13))
bad = []
for seed in SEEDS:
    rng = random.Random(seed)
    m.go_to_page(N // 2); pump(150)
    kinds = chaos(rng)
    pump(450)                                          # 휠을 멈추고 잠깐 — 사람이 다시 굴리기 전
    m.go_to_page(N // 2); pump(150)
    ok_dn, a, b = recovers(+1)
    ok_up, c, d = recovers(-1)
    if not (ok_dn and ok_up):
        bad.append((seed, sorted(set(kinds)), (a, b), (c, d)))
chk(not bad, "A 어떤 휠 순서 뒤에도 보통 휠로 아래·위 모두 넘어간다(씨앗 %d개)" % len(SEEDS), str(bad[:4]))

# B — 가장 흔한 실제 경우만 따로: 앱을 켠 채 절전했다 깨어남(처리 시계가 앞섬 — 사용자 노트북 실측 119초)
m.go_to_page(5); pump(150)
clock["shift"] = 0
for _ in range(2):
    send(-120); pump(300)
clock["shift"] = 119382
ok, a, b = recovers(+1)
chk(ok, "B 절전에서 깨어난 뒤(시계 119초 밀림) 쪽 맞춤 휠이 넘어간다", "%d → %d" % (a, b))

print()
print("FAILED:", len(fails)) if fails else print("ALL PASS")
sys.stdout.flush()
os._exit(1 if fails else 0)
