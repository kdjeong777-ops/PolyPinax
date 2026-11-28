# -*- coding: utf-8 -*-
"""법령·건설기준·특허 창 아이콘 단추 = 파란 라인, 테마를 바꾸면 다시 칠함 (디자인 SOT §4.3·§2.5, 261128-6).

A. 밝게 테마에서 만든 창 — ⭐·🌐(·∧∨)·찾기 바 단추 그림이 ▶·캡처 카메라 파랑(ACCENT["play"] 밝게)
B. 다크로 바꾸면(apply_theme 과 같은 setStyle·setPalette) 밝은 파랑으로 다시 칠함, 법령 검색칸 바탕도 다크
C. 다시 밝게 → 밝게 파랑·검색칸 흰 바탕
"""
import gc, os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QStyleFactory
from PyQt6.QtGui import QColor, QPalette

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_law_accent_%d" % os.getpid())
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


from viewer import theme
from viewer.widgets.icons import ACCENT


def set_theme(dark):
    """MainWindow.apply_theme 과 같은 차례 — theme.set_dark → setStyle(GC 멈춤) → setPalette."""
    theme.set_dark(dark)
    gc.collect(); gc.disable()
    try:
        app.setStyle(QStyleFactory.create("Fusion"))
    finally:
        gc.enable()
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(45, 45, 48) if dark else QColor(240, 240, 240))
    app.setPalette(p)
    app.processEvents()


def ink(btn):
    """단추 그림에서 가장 진한(불투명) 화소 색."""
    img = btn.icon().pixmap(16, 16).toImage()
    best, col = -1, None
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() > best:
                best, col = c.alpha(), c
    return col.name() if col is not None and best > 0 else None


def near(a, b, tol=40):
    if not a:
        return False
    ca, cb = QColor(a), QColor(b)
    return max(abs(ca.red() - cb.red()), abs(ca.green() - cb.green()), abs(ca.blue() - cb.blue())) <= tol


set_theme(False)
from viewer.widgets.law_search_dialog import LawSearchPanel
from viewer.widgets.kcsc_search_dialog import KcscSearchPanel
from viewer.widgets.kipo_search_dialog import KipoSearchPanel

law = LawSearchPanel("OC"); law.show()
kcsc = KcscSearchPanel("K"); kcsc.show()
kipo = KipoSearchPanel("K"); kipo.show()
app.processEvents()


def buttons(p):
    fb = [b for b in p.find_bar.findChildren(type(p.btn_globe))]
    out = [("즐겨찾기", p.btn_fav), ("🌐", p.btn_globe)] + [("찾기 바 %d" % i, b) for i, b in enumerate(fb)]
    if hasattr(p, "btn_prev"):
        out += [("∧", p.btn_prev), ("∨", p.btn_next)]
    return out


PANELS = [("법령", law), ("건설기준", kcsc), ("특허", kipo)]


def check_all(dark, tag):
    want = ACCENT["play"][dark]
    for pname, p in PANELS:
        bad = [(n, ink(b)) for n, b in buttons(p) if not near(ink(b), want)]
        chk(not bad, "%s %s 창 아이콘 단추 = 파랑 %s" % (tag, pname, want), bad)


check_all(False, "A 밝게")
set_theme(True)
check_all(True, "B 다크로 바꾼 뒤")
chk("#3a3a3d" in law.ed.styleSheet(), "B 법령 검색칸 바탕도 다크", law.ed.styleSheet()[:60])
set_theme(False)
check_all(False, "C 다시 밝게")
chk("#ffffff" in law.ed.styleSheet(), "C 법령 검색칸 바탕 흰색", law.ed.styleSheet()[:60])

for _n, p in PANELS:
    p.close()
print("\n" + ("ALL PASS" if not fails else f"FAIL {len(fails)}: {fails}"))
sys.exit(1 if fails else 0)
