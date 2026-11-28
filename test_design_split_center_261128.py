# -*- coding: utf-8 -*-
"""261128-17(디자인 SOT §2.9.5, 사용자 지시): 리본 분할 단추(`2단` ▾)의 글은 ▾ 칸을 뺀 본체 폭의 가운데.

종전: 스타일시트 단추가 글을 ▾ 칸까지 포함한 전체 폭 가운데에 놓아 `2단` 이 ▾ 쪽으로 붙어 보였다. 수정 전 코드로 A 가 실패한다.
실제 단추 그림(grab)에서 글 잉크의 가로 가운데를 재고, ▾ 칸(SC_ToolButtonMenu) 왼쪽 끝까지를 본체로 본다. 밝게·다크 둘 다.

A. 글 잉크 가운데 x ↔ 본체([0, ▾ 칸 왼쪽]) 가운데 ±2px
B. ▾ 화살표 잉크는 ▾ 칸 안
C. 모음 줄에 넣은 `2단` 도 같은 규칙
"""
import os, sys, faulthandler
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(180, exit=True)

from PyQt6.QtCore import QStandardPaths
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication, QToolButton, QStyleOptionToolButton, QStyle
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
from PyQt6.QtCore import QCoreApplication as _QCA
_QCA.setApplicationName("polypdf_split_center_%d" % os.getpid())     # 검사 작성 SOT §14.7.2 의 3
import modal_guard
modal_guard.install(label=lambda: "분할 단추 가운데", echo=False)     # §14.7.2 의 6
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def split_buttons(row):
    return [b for b in row.findChildren(QToolButton)
            if b.isVisible() and b.popupMode() == QToolButton.ToolButtonPopupMode.MenuButtonPopup]


def measure(b):
    """(글 잉크 가운데 x, 본체 가운데 x, ▾ 칸 왼쪽, 화살표 잉크 [x0, x1]) — 논리 px."""
    opt = QStyleOptionToolButton(); b.initStyleOption(opt)
    mr = b.style().subControlRect(QStyle.ComplexControl.CC_ToolButton, opt, QStyle.SubControl.SC_ToolButtonMenu, b)
    img = b.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
    dpr = img.devicePixelRatio() or 1.0
    bg = img.pixelColor(int(4 * dpr), img.height() // 2).lightness()
    cols = []
    for x in range(int(3 * dpr), img.width() - int(3 * dpr)):
        if any(abs(img.pixelColor(x, y).lightness() - bg) > 90 for y in range(int(5 * dpr), img.height() - int(5 * dpr))):
            cols.append(x / dpr)
    text = [x for x in cols if x < mr.left() - 1]
    arrow = [x for x in cols if x >= mr.left() - 1]
    tc = (text[0] + text[-1] + 1 / dpr) / 2 if text else -1
    return tc, mr.left() / 2.0, mr.left(), (arrow[0], arrow[-1]) if arrow else None, mr


from viewer.app import MainWindow
mw = MainWindow()
mw.resize(1600, 900); mw.show(); QTest.qWait(150)
for dark in (False, True):
    mw._ribbon.apply_style(dark); QTest.qWait(50)
    mw._ribbon.select("view"); QTest.qWait(80)
    bs = split_buttons(mw._ribbon.row("view"))
    chk(len(bs) == 1 and bs[0].defaultAction().property("ribbonSplit"), "보기 탭에 분할 단추 `2단` 하나", len(bs))
    for b in bs:
        tc, bc, ml, arr, mr = measure(b)
        tag = "다크" if dark else "밝게"
        chk(abs(tc - bc) <= 2.0, f"A {tag} 글 가운데가 ▾ 칸을 뺀 본체 가운데(±2px)", f"글 {tc:.1f} 본체 {bc:.1f} 폭 {b.width()} ▾ {mr}")
        chk(arr is not None and arr[0] >= ml - 1 and arr[1] <= b.width(), f"B {tag} 화살표는 ▾ 칸 안", (arr, mr))

# C 모음
from viewer.widgets.ribbon import COLLECTION
split_act = next(b.defaultAction() for b in split_buttons(mw._ribbon.row("view")))
mw._ribbon.set_collection([split_act]); mw._ribbon.select(COLLECTION); QTest.qWait(80)
bs = split_buttons(mw._ribbon.row(COLLECTION))
chk(len(bs) == 1, "C 모음 줄에도 분할 단추", len(bs))
for b in bs:
    tc, bc, ml, arr, mr = measure(b)
    chk(abs(tc - bc) <= 2.0, "C 모음 `2단` 글도 본체 가운데", f"글 {tc:.1f} 본체 {bc:.1f}")
mw.close()

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
sys.stdout.flush()
os._exit(1 if fails else 0)
