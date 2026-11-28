# -*- coding: utf-8 -*-
"""특허 창 — 고른 특허가 바로 열리게 (법령·고시 SOT §10.1, 261128-15). 네트워크는 가짜.

A. 🌐 단추(실제 클릭): 고른 특허 → KIPRIS 출원번호 검색 화면, 안 고르면 첫 화면
B. 명세서 PDF: 전문 조회가 http://plus.kipris.or.kr 주소를 주면 https 로 올려 받는다, 다른 호스트 http 는 거부
C. PDF 실패 안내줄: 첫 실패 사유(서버 응답)가 보인다
D. 같은 행 다시 클릭: 원문 보기가 지워지지 않는다, 다른 행 → 그 행 상세
"""
import os, sys, tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QPoint
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
from PyQt6.QtGui import QDesktopServices

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_kipo_open_%d" % os.getpid())
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


opened = []
QDesktopServices.openUrl = staticmethod(lambda u: opened.append(u.toString()) or True)

from viewer.study import kipo_api
from viewer.widgets.kipo_search_dialog import KipoSearchPanel

ROWS = [
    {"inventionTitle": "아스팔트 포장 공법", "applicationNumber": "1020150012345", "registerNumber": "1012345670000"},
    {"inventionTitle": "콘크리트 양생", "applicationNumber": "10-2019-0054321", "registerNumber": ""},
]

p = KipoSearchPanel("FAKEKEY")
p.resize(1000, 600); p.show(); app.processEvents()
p._on_results(ROWS, 2, ["ok"]); app.processEvents()


def click_row(i):
    it = p.tree.topLevelItem(i)
    r = p.tree.visualItemRect(it)
    QTest.mouseClick(p.tree.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, r.center())
    app.processEvents()


# ---- A. 🌐 ----
p.tree.setCurrentItem(None); app.processEvents()
opened.clear()
QTest.mouseClick(p.btn_globe, Qt.MouseButton.LeftButton)
chk(opened and opened[-1].rstrip("/") == "https://www.kipris.or.kr", "A1 고른 것 없으면 KIPRIS 첫 화면", opened)
click_row(0)
opened.clear()
QTest.mouseClick(p.btn_globe, Qt.MouseButton.LeftButton)
u = opened[-1] if opened else ""
from urllib.parse import urlsplit, parse_qs
q = parse_qs(urlsplit(u).query)
chk("searchResult.do" in u and q.get("searchKind") == ["keywordSearch"] and q.get("searchRight") == ["kpat"]
    and q.get("queryText") == ["AN=[1020150012345]"],
    "A2 고른 특허 → 출원번호 검색식으로 바로 검색되는 화면(keywordSearch·kpat·AN=[…])", u)
click_row(1)
opened.clear()
QTest.mouseClick(p.btn_globe, Qt.MouseButton.LeftButton)
u = opened[-1] if opened else ""
chk(parse_qs(urlsplit(u).query).get("queryText") == ["AN=[1020190054321]"], "A3 하이픈 든 출원번호는 숫자만", u)

# ---- B. PDF 주소 ----
got = []


class _Resp:
    status = 200

    def __init__(self, body): self._b = body; self._pos = 0
    def read(self, n=-1):
        if n is None or n < 0:
            b, self._pos = self._b[self._pos:], len(self._b)
            return b
        b = self._b[self._pos:self._pos + n]; self._pos += len(b); return b
    def __enter__(self): return self
    def __exit__(self, *a): return False


PDF_BYTES = b"%PDF-1.4\n" + b"0" * 4000
FULLTEXT_PATH = {"v": "http://plus.kipris.or.kr/kiprisplusws/fileToss.jsp?arg=abc"}


def fake_urlopen(req, timeout=None):
    url = req.full_url if hasattr(req, "full_url") else str(req)
    got.append(url)
    if "FullTextInfoSearch" in url:
        body = ("<response><header><successYN>Y</successYN></header><body><item>"
                "<docName>1020150012345.pdf</docName><path>%s</path></item></body></response>"
                % FULLTEXT_PATH["v"].replace("&", "&amp;")).encode()
        return _Resp(body)
    return _Resp(PDF_BYTES)


kipo_api.urllib.request.urlopen = fake_urlopen
d = tempfile.mkdtemp(prefix="kipo_t_")
path, dbg = kipo_api.download_fulltext_pdf_debug("FAKEKEY", "1020150012345", d, "아스팔트 포장 공법")
chk(bool(path) and os.path.exists(path), "B1 http://plus.kipris.or.kr PDF 주소도 받음", dbg)
chk(any(g.startswith("https://plus.kipris.or.kr/kiprisplusws/fileToss.jsp") for g in got),
    "B2 받기는 https 로 올린 주소로", got[-1:])
got.clear()
FULLTEXT_PATH["v"] = "http://evil.example.com/a.pdf"
path, dbg = kipo_api.download_fulltext_pdf_debug("FAKEKEY", "1020150012345", d, "x")
chk(not path and not any("evil" in g for g in got), "B3 다른 호스트 평문 http 는 거부", dbg)

# ---- C. 실패 안내 ----
p._on_pdf("", ["공개전문 200 실패: SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
               "공고전문 200 실패: SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
               "전문(공개/공고) PDF 를 찾지 못했습니다."])
chk("SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in p.info.text(), "C1 안내줄에 첫 실패 사유", p.info.text())

# ---- D. 같은 행 다시 클릭 ----
click_row(0)
p._on_detail("<p>원문청구범위XYZ</p>", ["ok"]); app.processEvents()
click_row(0)
chk("원문청구범위XYZ" in p.viewer.toPlainText(), "D1 같은 행 다시 눌러도 원문 유지")
click_row(1)
chk("콘크리트 양생" in p.viewer.toPlainText(), "D2 다른 행 → 그 행 상세")

p.close()
print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL", flush=True)
sys.exit(1 if fails else 0)
