# -*- coding: utf-8 -*-
"""261128-23(디자인 SOT §2.5 '명함 세부 카드', SOT 점검·사용자 결정 '리본 줄 바탕 따라감'): 카드 색은 새 값 없이 리본 토큰만.

종전: 261128-4 로 리본 줄 바탕 ROW_BG 다크가 #2b2b2e 가 됐는데 명함 카드 띠(head) 다크는 #38383c 그대로라
'띠 = ROW_BG' 가 깨졌다. 수정 전 코드로 A 가 실패한다.

A. 띠(head) = ROW_BG · 테두리(border) = ROW_BORDER · 본문(body) = TAB_ROW_BG · 고른 줄(sel) = GROUP_BG — 밝게·다크 둘 다
"""
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtCore import QStandardPaths
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv[:1])

from viewer.widgets import ribbon as R
from viewer.widgets import bizcard_find_dialog as BF
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


for theme, dark in (("light", False), ("dark", True)):
    d = BF.DETAIL_BG[theme]
    for key, tok, name in (("head", R.ROW_BG, "ROW_BG"), ("border", R.ROW_BORDER, "ROW_BORDER"),
                           ("body", R.TAB_ROW_BG, "TAB_ROW_BG"), ("sel", R.GROUP_BG, "GROUP_BG")):
        chk(d[key].lower() == tok[dark].lower(), "A %s %s = %s" % (theme, key, name), (d[key], tok[dark]))

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
sys.stdout.flush()
sys.exit(1 if fails else 0)
