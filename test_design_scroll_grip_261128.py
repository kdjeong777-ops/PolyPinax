# -*- coding: utf-8 -*-
"""다크 스크롤바 손잡이가 보이고, 창 나눔 손잡이는 점 3개 (261128-5, 사용자 지시 — 화면 디자인 SOT §2.4·§2.5).

사용자: 다크에서 책갈피창 스크롤 손잡이 색이 바탕과 같아 안 보이고, 창 나눔 막대의 회색 짧은 막대가 스크롤처럼 보인다 —
스크롤 손잡이는 그 회색 정도로, 창 나눔 막대는 동그란 점 3개로(결정 '점 3개만'·'앱 전체'·라이트 스크롤 손잡이 그대로).
실제 MainWindow(오프스크린, 시험 모드 설정 — 검사 작성 SOT §14.7.2 의 3)를 다크로 바꿔 실제 위젯을 그린다.
A. 실제로 보이는 목록의 세로 스크롤바 — 손잡이 가운데 = THUMB 보통(#6e6e6e), 홈(손잡이 밖)보다 밝기 ≥ 25 밝다
B. 가리킴·눌림 색 = THUMB 토큰(앱 스타일로 직접 그림)
C. 실제 창 나눔 손잡이(메인 ToggleSplitter·맨 QSplitter 가로 막대) — 점 색 덩어리가 정확히 3개, 각각 거의 정사각형(둥근 점), 막대 방향으로 늘어섬
D. 라이트도 창 나눔 손잡이는 점 3개, 스크롤바는 Fusion 그대로(픽셀 차 0 — 261115 검사 E 와 같은 규칙)
"""
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2 의 3 — 실제 설정 폴더를 쓰지 않는다
from PyQt6.QtWidgets import (QApplication, QScrollBar, QStyle, QStyleOptionSlider, QStyleFactory, QListWidget,
                             QSplitter, QWidget)
from PyQt6.QtGui import QPixmap, QPainter, QColor
from PyQt6.QtTest import QTest
app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_scroll_grip_%d" % os.getpid())
import modal_guard
modal_guard.install(label=lambda: "스크롤·창 나눔 손잡이", echo=False)   # 검사 작성 SOT §14.7.2 의 6

fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def lum(c):
    return int(0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue())


def pump(n=10):
    for _ in range(n):
        app.processEvents(); QTest.qWait(15)


from viewer.app import MainWindow
from viewer.widgets import scroll_arrows as sa
THUMB = getattr(sa, "THUMB", {"normal": "#6e6e6e", "hover": "#808080", "pressed": "#8c8c8c"})
GRIP = getattr(sa, "GRIP", {"dark": {"normal": "#6e6e6e"}, "light": {"normal": "#6e6e6e"}})

mw = MainWindow(); mw._skip_save_on_close = True
mw.resize(1300, 800); mw.show(); pump(20)
mw.apply_theme("dark"); pump()

# A — 실제로 보이는 목록 스크롤바(시험 프로필의 책갈피창은 비어 스크롤바가 숨는다 — 같은 앱 스타일의 목록으로)
lw = QListWidget(); lw.addItems(["줄 %d" % i for i in range(200)]); lw.resize(200, 260); lw.show(); pump()
sb = lw.verticalScrollBar()
img = sb.grab().toImage()
opt = QStyleOptionSlider(); sb.initStyleOption(opt)
st = sb.style()
sr = st.subControlRect(QStyle.ComplexControl.CC_ScrollBar, opt, QStyle.SubControl.SC_ScrollBarSlider, sb)
ar = st.subControlRect(QStyle.ComplexControl.CC_ScrollBar, opt, QStyle.SubControl.SC_ScrollBarAddPage, sb)
mid = img.pixelColor(sr.center())
groove = img.pixelColor(ar.center())
chk(mid.name() == THUMB["normal"] and lum(mid) - lum(groove) >= 25,      # 종전: 손잡이 47 < 홈 82(오프스크린 실측)
    "A 다크 목록 스크롤 손잡이 = %s, 홈보다 밝기 ≥ 25 밝다" % THUMB["normal"],
    "손잡이 %s(%d) / 홈 %s(%d)" % (mid.name(), lum(mid), groove.name(), lum(groove)))

# B — 상태 색
vsb = QScrollBar(Qt.Orientation.Vertical); vsb.setRange(0, 100); vsb.setPageStep(30); vsb.resize(16, 220)
SL = QStyle.SubControl.SC_ScrollBarSlider
def slider_color(state_add, active):
    o = QStyleOptionSlider(); vsb.initStyleOption(o)
    o.subControls = QStyle.SubControl.SC_All
    o.state |= state_add
    o.activeSubControls = active
    pm = QPixmap(vsb.size()); pm.fill(QColor("#000000"))
    p = QPainter(pm); app.style().drawComplexControl(QStyle.ComplexControl.CC_ScrollBar, o, p, vsb); p.end()
    r = app.style().subControlRect(QStyle.ComplexControl.CC_ScrollBar, o, SL, vsb)
    return pm.toImage().pixelColor(r.center()).name()
hov = slider_color(QStyle.StateFlag.State_MouseOver, SL)
prs = slider_color(QStyle.StateFlag.State_Sunken, SL)
chk(hov == THUMB["hover"] and prs == THUMB["pressed"], "B 가리킴·눌림 = THUMB 토큰", "%s %s" % (hov, prs))


def blobs(img, color):
    """그 색(±12) 픽셀의 4-연결 덩어리 → [(w, h, cx, cy)]."""
    tgt = QColor(color)
    W, H = img.width(), img.height()
    on = set()
    for y in range(H):
        for x in range(W):
            c = img.pixelColor(x, y)
            if abs(c.red() - tgt.red()) <= 12 and abs(c.green() - tgt.green()) <= 12 and abs(c.blue() - tgt.blue()) <= 12:
                on.add((x, y))
    out = []
    while on:
        stack = [on.pop()]; pts = []
        while stack:
            x, y = stack.pop(); pts.append((x, y))
            for q in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if q in on:
                    on.remove(q); stack.append(q)
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        out.append((max(xs) - min(xs) + 1, max(ys) - min(ys) + 1, sum(xs) / len(xs), sum(ys) / len(ys)))
    return out


def check_handle(name, h, theme):
    img = h.grab().toImage()
    bl = blobs(img, GRIP[theme]["normal"])
    ok = len(bl) == 3 and all(abs(w - hh) <= 1 for w, hh, _, _ in bl)
    if ok:
        vertical_bar = h.orientation() == Qt.Orientation.Horizontal     # 가로 splitter → 세로 막대
        cs = sorted(bl, key=lambda b: b[3] if vertical_bar else b[2])
        same = [b[2] if vertical_bar else b[3] for b in cs]
        ok = max(same) - min(same) <= 1
    chk(ok, "C %s %s 창 나눔 손잡이 = 둥근 점 3개(막대 방향)" % (theme, name),
        "덩어리 %d개 %s" % (len(bl), [(w, hh) for w, hh, _, _ in bl][:6]))


vs = QSplitter(Qt.Orientation.Vertical)             # 맨 QSplitter(책갈피창 위아래·오른쪽 패널과 같은 종류)
vs.addWidget(QWidget()); vs.addWidget(QWidget()); vs.setHandleWidth(6); vs.resize(240, 300); vs.show(); pump()


def splitters():
    return [("메인 ToggleSplitter", mw.splitter.handle(1)), ("맨 QSplitter 가로 막대", vs.handle(1))]


for name, h in splitters():
    check_handle(name, h, "dark")

# D — 라이트
mw.apply_theme("light"); pump()
for name, h in splitters():
    check_handle(name, h, "light")
fusion = QStyleFactory.create("Fusion")
ls = QScrollBar(Qt.Orientation.Vertical); ls.setRange(0, 100); ls.setPageStep(30); ls.resize(16, 220)
def render(style):
    o = QStyleOptionSlider(); ls.initStyleOption(o)
    o.subControls = QStyle.SubControl.SC_All
    pm = QPixmap(ls.size()); pm.fill(QColor("#ffffff"))
    p = QPainter(pm); style.drawComplexControl(QStyle.ComplexControl.CC_ScrollBar, o, p, ls); p.end()
    return pm.toImage()
a, b = render(app.style()), render(fusion)
diff = sum(1 for y in range(a.height()) for x in range(a.width()) if a.pixelColor(x, y) != b.pixelColor(x, y))
chk(diff == 0, "D 라이트 스크롤바는 Fusion 그대로(픽셀 차 0)", "%d px" % diff)
mw.close()

print()
print("ALL PASS" if not fails else "FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
