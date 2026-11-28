# -*- coding: utf-8 -*-
"""서명 아이콘 = 사인한 서명 곡선 하나, 굵은 단색·테마 따라감 (디자인 SOT §4.2·§4.8, 261128-12).

A. 곡선 하나가 왼쪽부터 오른쪽 끝까지, 아래 곧은 서명 줄은 없다(종전 꺾인 선 + 밑줄)
B. 왼쪽에서 높이 솟았다 깊이 내려오는 첫 획, 꼬리도 굵다
C. 실제 본문 도구 줄 전자서명 단추·책갈피창 서명된 파일 줄 그림이 같은 `sign`, 다크로 바꾸면 밝은 색으로 다시
"""
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_sign_icon_%d" % os.getpid())
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


from viewer.widgets.icons import themed_icon

img = themed_icon("sign", False, 32, dpr=1.0).pixmap(32, 32).toImage()
ink = lambda x, y: img.pixelColor(x, y).alpha() > 120         # noqa: E731
rows = lambda x: [y for y in range(32) if ink(x, y)]                            # noqa: E731
chk(not any(ink(x, y) for x in range(32) for y in range(27, 32)) and rows(3) and rows(29),
    "A 서명 곡선 하나가 왼쪽 끝부터 오른쪽 끝까지 — 아래 곧은 서명 줄은 없다(종전 꺾인 선 + 밑줄)", str((rows(3), rows(29))))
peak, trough = min(rows(11) or [99]), max(rows(10) or [0])
chk(peak <= 11 and trough >= 21, "B 왼쪽에서 높이 솟았다 깊이 내려온다(사인 첫 획)", str((peak, trough)))
thick = max((len(rows(x)) for x in range(22, 30)), default=0)
chk(thick >= 3, "B2 굵은 손글씨 획(오른쪽 꼬리 세로 3화소 이상)", str(thick))

from viewer import theme
from viewer.widgets.main_view import MainView
from viewer.widgets.bookmark_tree import BookmarkTree
key = lambda ic: ic.pixmap(16, 16).toImage()                  # noqa: E731
theme.set_dark(False)
mv, bt = MainView(), BookmarkTree()
chk(key(mv.btn_sign.icon()) == key(themed_icon("sign", False, 16)), "C1 도구 줄 전자서명 단추 = sign 그림")
chk(key(bt._signed_icon()) == key(themed_icon("sign", False)), "C2 책갈피창 서명된 파일 줄 = sign 그림")
theme.set_dark(True)
mv.refresh_theme_icons(True)
chk(key(mv.btn_sign.icon()) == key(themed_icon("sign", True, 16)), "C3 다크로 바꾸면 밝은 색으로 다시 칠함")
theme.set_dark(False)

print("ALL PASS" if not fails else f"{len(fails)} FAIL")
sys.stdout.flush()
os._exit(1 if fails else 0)
