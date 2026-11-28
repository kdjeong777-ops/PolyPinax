# -*- coding: utf-8 -*-
"""법령 창 조문 이동·브라우저 열기 (법령·고시 SOT §4, 261128-2) — 네트워크는 가짜.

A. 같은 법령 안 조문 이동(클릭·↓ 키)은 본문을 다시 불러오지 않고 스크롤만
B. 다른 법령 잎·다른 법령의 조문은 다시 불러옴
C. 조문을 고른 채 🌐 → 법령은 한글주소 '/법령/<이름>/제N조', 행정규칙 조문은 상세링크
"""
import os, sys, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QUrl
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtTest import QTest
from urllib.parse import unquote

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_law_nav_%d" % os.getpid())
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


def pump(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return cond()


# --- 가짜 본문(네트워크 없음) ---
from viewer.study import law_api
calls = []


def fake_fetch(oc, row, timeout=12.0):
    calls.append(row.get("name"))
    arts, parts = [], []
    for n in range(1, 31):
        a = f"art_{n}"
        lbl = f"제{n}조(조목{n})" if n != 3 else "제2조의2(덧조)"
        arts.append((lbl, a))
        parts.append(f'<a name="{a}"></a><p><b>{lbl}</b></p>'
                     + "".join(f"<p>본문 {n}-{k} 줄입니다.</p>" for k in range(12)))
    return "<html><body>" + "".join(parts) + "</body></html>", [], arts


law_api.fetch_content_debug = fake_fetch

opened = []
QDesktopServices.openUrl = staticmethod(lambda u: opened.append(u.toString()) or True)

from viewer.widgets.law_search_dialog import LawSearchPanel

p = LawSearchPanel("OC")
p.resize(1100, 700)
p.show()
rows = [
    {"name": "건설기술 진흥법", "kind": "법률", "agency": "국토교통부", "date": "",
     "link": "https://www.law.go.kr/DRF/lawService.do?target=law&MST=1&type=HTML",
     "target": "law", "category": "법령", "ids": {"mst": "1", "law_id": "", "admrul_seq": "", "expc_seq": ""}},
    {"name": "가짜 고시", "kind": "고시", "agency": "국토교통부", "date": "",
     "link": "https://www.law.go.kr/DRF/lawService.do?target=admrul&ID=9&type=HTML",
     "target": "admrul", "category": "행정규칙", "ids": {"mst": "", "law_id": "", "admrul_seq": "9", "expc_seq": ""}},
]
p._on_search_done(rows)
grp_law = p.tree.topLevelItem(0)
leaf_law = grp_law.child(0)
leaf_adm = p.tree.topLevelItem(1).child(0)


def click(item):
    p.tree.scrollToItem(item)
    app.processEvents()
    r = p.tree.visualItemRect(item)
    QTest.mouseClick(p.tree.viewport(), Qt.MouseButton.LeftButton, pos=r.center())


# 법령 잎 → 한 번 불러옴
click(leaf_law)
chk(pump(lambda: leaf_law.childCount() == 30), "법령 잎 선택 → 조문 30개 붙음", leaf_law.childCount())
chk(calls == ["건설기술 진흥법"], "처음 한 번만 불러옴", calls)

# A. 조문 클릭·↓ 키 — 다시 불러오지 않음
n0 = len(calls)
click(leaf_law.child(9))                     # 제10조
pump(lambda: False, 0.4)
v1 = p.viewer.verticalScrollBar().value()
chk(len(calls) == n0, "같은 법령 조문 클릭 → 다시 불러오지 않음", calls)
chk(v1 > 0, "조문 클릭 → 그 자리로 스크롤", v1)
p.tree.setFocus()
for _ in range(3):
    QTest.keyClick(p.tree, Qt.Key.Key_Down)
pump(lambda: False, 0.4)
v2 = p.viewer.verticalScrollBar().value()
chk(p.tree.currentItem() is leaf_law.child(12), "↓ 세 번 → 제13조 항목", p.tree.currentItem().text(0))
chk(len(calls) == n0, "↓ 키로 조 이동 → 불러오기 0번", calls)
chk(v2 > v1, "↓ 키 → 아래 조문 자리로 스크롤", (v1, v2))
chk("본문 13-0" in p.viewer.toPlainText(), "본문은 그대로(불러오는 중 문구로 바뀌지 않음)")

# C. 조문을 고른 채 🌐
opened.clear()
QTest.mouseClick(p.btn_globe, Qt.MouseButton.LeftButton)
chk(len(opened) == 1 and unquote(opened[0]) == "https://www.law.go.kr/법령/건설기술 진흥법/제13조",
    "법령 조문 + 🌐 → 한글주소 그 조", [unquote(u) for u in opened])
click(leaf_law.child(2))                     # 제2조의2
opened.clear()
QTest.mouseClick(p.btn_globe, Qt.MouseButton.LeftButton)
chk(len(opened) == 1 and unquote(opened[0]).endswith("/법령/건설기술 진흥법/제2조의2"),
    "제N조의M 조문 → '제2조의2' 주소", [unquote(u) for u in opened])
click(leaf_law)                              # 법령 이름 → 상세링크, 다시 불러오지 않음
opened.clear()
QTest.mouseClick(p.btn_globe, Qt.MouseButton.LeftButton)
chk(opened == [rows[0]["link"]], "법령 이름 + 🌐 → 상세링크", opened)
chk(len(calls) == n0, "띄운 법령 이름으로 돌아와도 다시 불러오지 않음", calls)

# B. 다른 법령 → 불러옴, 그 조문 + 🌐 → 상세링크
click(leaf_adm)
chk(pump(lambda: leaf_adm.childCount() == 30), "다른 법령 잎 → 불러옴")
chk(calls[-1] == "가짜 고시" and len(calls) == n0 + 1, "다른 법령은 한 번 불러옴", calls)
click(leaf_adm.child(4))
pump(lambda: False, 0.3)
opened.clear()
QTest.mouseClick(p.btn_globe, Qt.MouseButton.LeftButton)
chk(opened == [rows[1]["link"]], "행정규칙 조문 + 🌐 → 상세링크", opened)
n1 = len(calls)
click(leaf_law.child(5))                     # 다른 법령의 조문 → 다시 불러옴
chk(pump(lambda: len(calls) == n1 + 1), "다른 법령의 조문 → 다시 불러옴", calls)

p.close()
print("\n" + ("ALL PASS" if not fails else f"FAIL {len(fails)}: {fails}"))
sys.exit(1 if fails else 0)
