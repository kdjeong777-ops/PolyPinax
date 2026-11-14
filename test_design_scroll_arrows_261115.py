# -*- coding: utf-8 -*-
"""다크 테마 스크롤바 화살표가 바탕과 또렷이 다르다 (261115-2, 사용자 지시 — 화면 디자인 SOT §2.5 '스크롤바 화살표').

사용자: "모든 세로 스크롤 바의 상하 이동버튼이 다크모드에서 잘 안보여. 좀더 밝게 조정해".
종전 Fusion 은 화살표를 글자색 알파 160 으로 그려 다크에서 밝기 166 / 단추 바탕 77 이었다.
실제 MainWindow(오프스크린, 시험 모드 설정 — 검사 작성 SOT §14.7.2 의 3)를 다크로 바꿔 실제 스크롤바를 그린다.
A. 책갈피창 목록·쪽 썸네일 목록의 실제 세로 스크롤바 — 위·아래 단추 가운데가 밝기 ≥ 215, 단추 바탕보다 ≥ 120 밝다
B. 가로 스크롤바 ◀▶ 도 같은 규칙
C. 가리킴·눌림은 흰색(#ffffff), 꺼진 스크롤바는 회색(#808080) — 토큰 `scroll_arrows.ARROW`
D. 스타일시트가 걸린 위젯 안 스크롤바도 같다(앱 스타일 한 곳)
E. 라이트 테마는 Fusion 그대로 — 감싼 스타일과 맨 Fusion 그림이 픽셀까지 같다
"""
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2 의 3 — 실제 설정 폴더를 쓰지 않는다
from PyQt6.QtWidgets import QApplication, QScrollBar, QStyle, QStyleOptionSlider, QStyleFactory, QListWidget
from PyQt6.QtGui import QPixmap, QPainter, QColor
from PyQt6.QtTest import QTest
app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_scroll_arrows_%d" % os.getpid())
import modal_guard
modal_guard.install(label=lambda: "스크롤바 화살표", echo=False)   # 검사 작성 SOT §14.7.2 의 6

fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def lum(c):
    return int(0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue())


def arrow_vs_bg(sb):
    """스크롤바를 그려 (sub 단추 가운데 밝기, sub 단추 바탕 밝기, add 가운데, add 바탕)."""
    img = sb.grab().toImage()
    opt = QStyleOptionSlider(); sb.initStyleOption(opt)
    st = sb.style()
    out = []
    for sc in (QStyle.SubControl.SC_ScrollBarSubLine, QStyle.SubControl.SC_ScrollBarAddLine):
        r = st.subControlRect(QStyle.ComplexControl.CC_ScrollBar, opt, sc, sb)
        c = r.center()
        mid = max(lum(img.pixelColor(c.x() + dx, c.y() + dy)) for dx in (-1, 0, 1) for dy in (-1, 0, 1))
        corner = lum(img.pixelColor(r.left() + 2, r.top() + 2) if sb.orientation() == Qt.Orientation.Vertical
                     else img.pixelColor(r.left() + 2, r.bottom() - 2))
        out += [mid, corner]
    return out


def pump(n=10):
    for _ in range(n):
        app.processEvents(); QTest.qWait(15)


from viewer.app import MainWindow
try:
    from viewer.widgets import scroll_arrows as sa
except ImportError:                                   # 종전 코드 — C 는 실패로 센다
    sa = None
mw = MainWindow(); mw._skip_save_on_close = True
mw.resize(1300, 800); mw.show(); pump(20)
mw.apply_theme("dark"); pump()

# A — 실제 목록
lists = []
bt = mw.bookmark_tree
for name, view in (("책갈피창 목록", getattr(bt, "tree", None)), ("쪽 썸네일", getattr(getattr(mw, "page_thumbs", None), "list", None))):
    if view is None:
        chk(False, "A %s 를 찾는다" % name); continue
    sb = view.verticalScrollBar()
    sb.setRange(0, 100); sb.resize(16, 220)
    lists.append((name, sb))
    m1, b1, m2, b2 = arrow_vs_bg(sb)
    chk(m1 >= 215 and m2 >= 215 and m1 - b1 >= 120 and m2 - b2 >= 120,
        "A 다크 %s 세로 스크롤바 ▲▼ 가 바탕과 또렷이(밝기 ≥ 215, 차이 ≥ 120)" % name,
        "▲ %d/바탕 %d · ▼ %d/바탕 %d" % (m1, b1, m2, b2))

# B — 가로
hsb = QScrollBar(Qt.Orientation.Horizontal); hsb.setRange(0, 100); hsb.resize(220, 16)
m1, b1, m2, b2 = arrow_vs_bg(hsb)
chk(m1 >= 215 and m2 >= 215 and m1 - b1 >= 120 and m2 - b2 >= 120, "B 다크 가로 스크롤바 ◀▶ 도 같다",
    "◀ %d/%d · ▶ %d/%d" % (m1, b1, m2, b2))

# C — 상태 색(앱 스타일로 직접 그린다 — 가리킴·눌림은 실제 마우스 상태 대신 그 옵션)
vsb = QScrollBar(Qt.Orientation.Vertical); vsb.setRange(0, 100); vsb.resize(16, 220)
def draw_with(state_add, active, enabled=True):
    opt = QStyleOptionSlider(); vsb.initStyleOption(opt)
    opt.subControls = QStyle.SubControl.SC_All          # QScrollBar.paintEvent 와 같다
    if not enabled:
        opt.state &= ~QStyle.StateFlag.State_Enabled
    opt.state |= state_add
    opt.activeSubControls = active
    pm = QPixmap(vsb.size()); pm.fill(QColor("#000000"))
    p = QPainter(pm); app.style().drawComplexControl(QStyle.ComplexControl.CC_ScrollBar, opt, p, vsb); p.end()
    r = app.style().subControlRect(QStyle.ComplexControl.CC_ScrollBar, opt, QStyle.SubControl.SC_ScrollBarSubLine, vsb)
    c = r.center()
    return pm.toImage().pixelColor(c.x(), c.y() + 1).name()
SUB = QStyle.SubControl.SC_ScrollBarSubLine
hov = draw_with(QStyle.StateFlag.State_MouseOver, SUB)
prs = draw_with(QStyle.StateFlag.State_Sunken, SUB)
dis = draw_with(QStyle.StateFlag(0), QStyle.SubControl.SC_None, enabled=False)
nor = draw_with(QStyle.StateFlag(0), QStyle.SubControl.SC_None)
tok = sa.ARROW if sa is not None else {}
chk(hov == tok.get("hover") and prs == tok.get("pressed"), "C 가리킴·눌림 = 흰색", "%s %s" % (hov, prs))
chk(nor == tok.get("normal") and dis == tok.get("disabled"), "C 보통 = 아이콘 전경 #e8e8e8, 꺼짐 = #808080", "%s %s" % (nor, dis))

# D — 스타일시트가 걸린 위젯 안
lw = QListWidget(); lw.setStyleSheet("QListWidget { background:#202020; color:#eee; }")
lw.addItems(["줄 %d" % i for i in range(200)]); lw.resize(200, 200); lw.show(); pump()
m1, b1, m2, b2 = arrow_vs_bg(lw.verticalScrollBar())
chk(m1 >= 215 and m1 - b1 >= 120, "D 스타일시트가 걸린 목록의 스크롤바도 같다", "▲ %d/%d" % (m1, b1))

# E — 라이트는 Fusion 그대로
mw.apply_theme("light"); pump()
fusion = QStyleFactory.create("Fusion")
ls = QScrollBar(Qt.Orientation.Vertical); ls.setRange(0, 100); ls.resize(16, 220)
def render(style):
    opt = QStyleOptionSlider(); ls.initStyleOption(opt)
    opt.subControls = QStyle.SubControl.SC_All
    pm = QPixmap(ls.size()); pm.fill(QColor("#ffffff"))
    p = QPainter(pm); style.drawComplexControl(QStyle.ComplexControl.CC_ScrollBar, opt, p, ls); p.end()
    return pm.toImage()
a, b = render(app.style()), render(fusion)
diff = sum(1 for y in range(a.height()) for x in range(a.width()) if a.pixelColor(x, y) != b.pixelColor(x, y))
chk(diff == 0, "E 라이트 테마는 Fusion 그대로(픽셀 차 0)", "%d px" % diff)
mw.close()

print()
print("ALL PASS" if not fails else "FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
