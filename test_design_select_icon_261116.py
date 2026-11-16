# -*- coding: utf-8 -*-
"""편집 도구 줄 '개체 선택'·지우개·청소 그림이 다크에서도 보인다 (261116-10, 사용자 보고 — 화면 디자인 SOT §4.2·§4.5).

사용자: "다크모드에서 개체선택의 점선 상자가 안 보임". 종전 아이콘은 PNG(어두운 회색 #3a3a3a 고정)라 다크 바탕(58)에서
점선 상자가 사라지고, 같은 줄의 지우개 2종·청소 PNG 도 테두리가 사라졌다. 이제 테마 그림(`select_box`·`eraser_*`).
실제 MainWindow(오프스크린, 시험 모드 설정 — 검사 작성 SOT §14.7.2 의 3)의 편집 도구 줄을 다크·라이트로 그린다.
A. 다크: 개체 선택 단추의 왼쪽 위(점선 상자 자리)에 바탕보다 ≥ 100 밝은 점이 충분하다(점선이 보인다)
B. 라이트: 같은 자리에 바탕보다 ≥ 100 어두운 점이 충분하다
C. 다크 지우개 2종·청소: 단추 그림에 '아이콘 전경'(#e8e8e8 근처) 테 점이 충분하다(테가 보인다)
D. 테마를 바꾸면 다시 그린다 — 단추 그림 = 그 테마의 `themed_icon`/`color_icon` 그림(라이트 → 다크 → 라이트)
E. 켜진 개체 선택(살구색 바탕)은 테마와 상관없이 밝은 바탕용 그림, 끄면 다크 그림으로 돌아온다
"""
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, QSize
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2 의 3 — 실제 설정 폴더를 쓰지 않는다
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
from PyQt6.QtCore import Qt
app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_select_icon_%d" % os.getpid())
import modal_guard
modal_guard.install(label=lambda: "개체 선택 아이콘", echo=False)   # 검사 작성 SOT §14.7.2 의 6

fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def lum(c):
    return 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()


def pump(n=8):
    for _ in range(n):
        app.processEvents(); QTest.qWait(15)


def icon_region(b, frac=1.0):
    """단추를 그려 (그림, 바탕 밝기, 아이콘 칸 왼쪽 위 frac 부분의 점들)."""
    img = b.grab().toImage()
    bg = lum(img.pixelColor(2, img.height() // 2))
    s = b.iconSize()
    x0 = (img.width() - s.width()) // 2; y0 = (img.height() - s.height()) // 2
    pts = [img.pixelColor(x, y) for y in range(y0, y0 + int(s.height() * frac))
           for x in range(x0, x0 + int(s.width() * frac))]
    return bg, pts


def same_icon(btn, ref):
    sz = btn.iconSize()
    a = btn.icon().pixmap(sz, 2.0).toImage().convertToFormat(ref.pixmap(sz, 2.0).toImage().format())
    b = ref.pixmap(sz, 2.0).toImage()
    return (not a.isNull()) and a == b


from viewer.app import MainWindow
from viewer.widgets import icons
mw = MainWindow(); mw.resize(1300, 700); mw.show()
mv = mw.main_view
mw.apply_theme("dark")
mv.set_draw_mode(True)
pump()
sel = mv._draw_select_btn
er = list(mv._draw_erase_btns)

# A. 다크 점선 상자
bg, pts = icon_region(sel, 0.5)
bright = sum(1 for c in pts if c.alpha() > 0 and lum(c) - bg >= 100)
chk(bright >= 6, "A. 다크: 개체 선택 점선 상자가 바탕보다 밝다(≥100)", "바탕 %d · 밝은 점 %d" % (bg, bright))

# C. 다크 지우개·청소 테
FG = icons.fg_color(True)
for name, b in (("지우개(얇게)", er[0]), ("지우개(두껍게)", er[1]), ("청소", mv._draw_clear_btn if hasattr(mv, "_draw_clear_btn") else None)):
    if b is None:
        chk(False, "C. 다크 %s 단추를 찾음" % name); continue
    bg, pts = icon_region(b, 1.0)
    edge = sum(1 for c in pts if abs(lum(c) - 232) <= 30 and max(c.red(), c.green(), c.blue()) - min(c.red(), c.green(), c.blue()) < 25)
    darkfill = sum(1 for c in pts if lum(c) < bg - 8)
    chk(edge >= 15 and darkfill >= 6, "C. 다크 %s: 밝은 테(아이콘 전경)·어두운 몸통" % name, "테 점 %d · 어두운 몸통 점 %d · 바탕 %d" % (edge, darkfill, bg))

# D. 테마를 바꾸면 다시 그린다
LPX = getattr(icons, "LINE_ICON_PX", 18)
for mode, dark in (("light", False), ("dark", True), ("light", False)):
    mw.apply_theme(mode); pump(4)
    ok_sel = same_icon(sel, icons.themed_icon("select_box", dark=dark, size=LPX, dpr=2.0)) if "select_box" in icons._DRAW else False
    ok_er = all(same_icon(b, icons.color_icon(n, dark=dark, size=LPX)) for b, n in zip(er, ("eraser_thin", "eraser_thick"))) \
        if "eraser_thin" in icons._COLOR_DRAW else False
    chk(ok_sel and ok_er, "D. %s 로 바꾸면 개체 선택·지우개 그림이 그 테마 그림" % mode)
    if mode == "light" and not dark:
        bg, pts = icon_region(sel, 0.5)
        darkp = sum(1 for c in pts if c.alpha() > 0 and bg - lum(c) >= 100)
        chk(darkp >= 6, "B. 라이트(%s): 점선 상자가 바탕보다 어둡다(≥100)" % mode, "바탕 %d · 어두운 점 %d" % (bg, darkp))

# E. 켜진 개체 선택
mw.apply_theme("dark"); pump(4)
QTest.mouseClick(sel, Qt.MouseButton.LeftButton); pump(4)
on_ok = sel.isChecked() and "select_box" in icons._DRAW and same_icon(sel, icons.themed_icon("select_box", dark=False, size=LPX, dpr=2.0))
chk(on_ok, "E. 다크에서 켠 개체 선택은 밝은 바탕용(어두운) 그림", "checked=%s" % sel.isChecked())
QTest.mouseClick(sel, Qt.MouseButton.LeftButton); pump(4)
off_ok = (not sel.isChecked()) and "select_box" in icons._DRAW and same_icon(sel, icons.themed_icon("select_box", dark=True, size=LPX, dpr=2.0))
chk(off_ok, "E. 끄면 다크 그림으로 돌아온다", "checked=%s" % sel.isChecked())

print()
print("ALL PASS" if not fails else "%d FAIL: %s" % (len(fails), fails))
sys.stdout.flush()
os._exit(0 if not fails else 1)
