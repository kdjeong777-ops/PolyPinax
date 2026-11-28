# -*- coding: utf-8 -*-
"""261128-9(검색창 SOT §4.1·§4.3): 한국어 화면엔 Aa 가 없고(대소문자 구분 늘 끔), [?] 단추가 검색 도움말 창을 연다.

사용자 지시 '대소문자 구분 버튼은 한글모드에서 안보이게 해(기본 대소문자 구분 안함)', '정규식에서 해당 설명 내용이 호버될 때 ? 등을 눌러 …
별도의 창으로 볼 수 있도록 해. 사용 방법 설명시 가장 많이 사용하는 내용을 앞에 설명해'. 결정 '한글모드 = 화면 언어 한국어'·'[?] 단추 + 풍선 안내'·'& 는 AND 가 아니라고 안내'.
  A  ko: Aa 단추가 숨고, 기억된 search_case·즐겨찾기 case 가 켜져 와도 mode() 는 대소문자 구분 끔
  B  ko: Aa·.* 풍선 끝에 [?] 안내, [?] 를 실제 마우스로 누르면 비모달 도움말 창 — 다시 눌러도 하나
  C  도움말 차례 = 많이 쓰는 것 먼저(보통 검색 → 연산자 → 정규식), 띄어쓰기 AND·& 안내·.* 가 정규식 절 첫 줄, ko 엔 Aa 절 없음
  D  en: Aa 가 보이고 켜면 대소문자 구분, 도움말은 영어·Aa 절 있음
수정 전 코드는 Aa 가 보이고 [?] 단추가 없어 실패한다.
"""
import os, sys, faulthandler
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.pop("POLYPDF_LANG", None)
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
faulthandler.dump_traceback_later(120, exit=True)

from PyQt6.QtCore import QStandardPaths, Qt
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout
from PyQt6.QtTest import QTest
app = QApplication.instance() or QApplication(sys.argv[:1])
import modal_guard
modal_guard.install(echo=False)
from viewer import i18n
fails = []


def chk(c, m, extra=""):
    print(("PASS" if c else "FAIL"), "-", m, ("" if c else extra))
    if not c:
        fails.append(m)


def bar():
    from viewer.widgets.search_panel import SearchBar
    host = QWidget(); lay = QVBoxLayout(host)
    sb = SearchBar(); lay.addWidget(sb)
    host.resize(700, 60); host.show(); QTest.qWait(50)
    return host, sb


try:
    # ── ko ──
    i18n.install(app, "ko")
    host, sb = bar()
    chk(not sb.btn_case.isVisible() and sb.btn_regex.isVisible(), "A ko: Aa 는 숨고 .* 는 보인다")
    sb.set_mode(True, False)                         # 기억된 search_case·즐겨찾기 case 가 켜져 왔다
    chk(sb.mode() is None, "A ko: 켜진 case 가 와도 대소문자 구분은 끔", str(sb.mode()))
    sb.set_mode(True, True)
    chk(sb.mode() == (False, True), "A ko: 정규식은 그대로", str(sb.mode()))
    chk("[?]" in sb.btn_regex.toolTip(), "B ko: .* 풍선 끝에 [?] 안내", sb.btn_regex.toolTip())
    btn = getattr(sb, "btn_help", None)
    chk(btn is not None and btn.isVisible() and btn.text() == "?", "B ko: [?] 단추가 보인다")
    if btn is None:
        raise SystemExit("[?] 단추가 없다 — 나머지는 볼 수 없다")
    from viewer.widgets import search_help
    QTest.mouseClick(btn, Qt.MouseButton.LeftButton); QTest.qWait(100)
    d1 = search_help._dlg
    chk(d1 is not None and d1.isVisible() and not d1.isModal(), "B [?] 를 누르면 비모달 도움말 창")
    QTest.mouseClick(btn, Qt.MouseButton.LeftButton); QTest.qWait(100)
    chk(search_help._dlg is d1, "B 다시 눌러도 창은 하나")
    txt = d1.browser.toPlainText()
    i_basic, i_ops, i_rx = txt.find("보통 검색"), txt.find("연산자"), txt.find("정규식")
    chk(0 <= i_basic < i_ops < i_rx, "C 차례 = 보통 검색 → 연산자 → 정규식", "%d %d %d" % (i_basic, i_ops, i_rx))
    chk("띄어쓰기" in txt and "& 는 AND 가 아니라" in txt, "C 띄어쓰기 AND 와 & 안내")
    rx_part = txt[i_rx:]
    chk(rx_part.find(".*") >= 0 and rx_part.find(".*") < rx_part.find("\\d"), "C 정규식 절은 .* 가 먼저")
    chk("[Aa]" not in txt, "C ko: Aa 절은 없다")
    d1.close(); host.close()

    # ── en ──
    i18n.install(app, "en")
    search_help._dlg = None
    host, sb = bar()
    chk(sb.btn_case.isVisible(), "D en: Aa 가 보인다")
    sb.set_mode(True, False)
    chk(sb.mode() == (True, False), "D en: 켜면 대소문자 구분", str(sb.mode()))
    QTest.mouseClick(sb.btn_help, Qt.MouseButton.LeftButton); QTest.qWait(100)
    txt = search_help._dlg.browser.toPlainText()
    chk("[Aa]" in txt and "Ordinary search" in txt, "D en: 영어 도움말·Aa 절", txt[:80])
    search_help._dlg.close(); host.close()
except SystemExit as e:
    print("멈춤 -", e)
except Exception:
    import traceback; traceback.print_exc()
    fails.append("예외")

print()
print("FAILED:", len(fails)) if fails else print("ALL PASS")
sys.stdout.flush()
os._exit(1 if fails else 0)
