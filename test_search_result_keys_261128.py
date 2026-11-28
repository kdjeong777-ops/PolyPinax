# -*- coding: utf-8 -*-
"""261128-7(검색창 SOT §7): 검색 결과 줄을 키보드로 옮기면 본문이 그 쪽으로 간다.

사용자 지시 '검색항목을 키보드로 이동시 본문이 해당 항목으로 이동하도록 수정해'.
실제 마우스·키로:
  A  줄을 누르면 그 쪽(종전 그대로)
  B  ↓ 한 번이면 다음 줄의 쪽으로 — 수정 전 코드는 본문이 그대로라 실패
  C  ↑ 도 같다 · PgDn·End 도 같다
  D  빠르게 여러 번 누르면(꾹) 지나가는 줄마다 가지 않고 마지막 줄 하나만 — 이동 신호 한 번
  E  마우스로 누른 줄은 한 번만 간다(키 따라가기가 겹치지 않음) · 결과를 새로 그려도 가지 않는다
"""
import os, sys, faulthandler
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
faulthandler.dump_traceback_later(180, exit=True)

from PyQt6.QtCore import QStandardPaths, Qt
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
import modal_guard
modal_guard.install(echo=False)
from PyQt6.QtCore import QCoreApplication as _QCA
_QCA.setApplicationName("polypdf_result_keys_%d" % os.getpid())
fails = []


def chk(c, m, extra=""):
    print(("PASS" if c else "FAIL"), "-", m, ("" if c else extra))
    if not c:
        fails.append(m)


try:
    from test_fixtures import text_pdf, wait_main_open
    from viewer.indexer import SearchResult
    from viewer.app import MainWindow, HistoryItem
    pdf = text_pdf()
    mw = MainWindow()
    mw.resize(1500, 900); mw.show(); mw.activateWindow(); QTest.qWait(200)
    mw._load_main(HistoryItem(pdf, 0, "", "open")); wait_main_open(mw); QTest.qWait(150)
    mw._vm_search(); QTest.qWait(100)
    mv = mw.main_view
    sr = mw.search_results
    pages = (2, 5, 9, 14, 20, 25)
    sr.set_results("line 3", [SearchResult(pdf, "x", p, 1, "line 3 of page %d" % (p + 1)) for p in pages])
    QTest.qWait(50)
    tree = sr.tree
    chk(tree.isVisible(), "준비 — 검색 결과 줄이 보인다")
    sent = []
    sr.resultActivated.connect(lambda f, p, q: sent.append(p))
    top = tree.topLevelItem(0)

    def click_row(i):
        r = tree.visualItemRect(top.child(i))
        QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=r.center()); QTest.qWait(300)

    def key(k, wait=300):
        QTest.keyClick(tree, k); QTest.qWait(wait)

    # A
    click_row(1)
    chk(mv.current_page() == 5 and sent == [5], "A 줄을 누르면 그 쪽", "page=%d sent=%s" % (mv.current_page(), sent))
    QTest.qWait(300)
    chk(sent == [5], "E 누른 줄은 한 번만 간다(키 따라가기가 겹치지 않음)", str(sent))

    # B
    sent.clear()
    key(Qt.Key.Key_Down)
    chk(mv.current_page() == 9 and sent == [9], "B ↓ 로 다음 줄 — 본문이 그 쪽으로", "page=%d sent=%s" % (mv.current_page(), sent))

    # C
    key(Qt.Key.Key_Up)
    chk(mv.current_page() == 5, "C ↑ 도 같다", "page=%d" % mv.current_page())
    key(Qt.Key.Key_End)
    chk(mv.current_page() == 25, "C End 로 마지막 줄", "page=%d" % mv.current_page())
    key(Qt.Key.Key_PageUp)
    chk(mv.current_page() != 25 and tree.currentItem() is not None, "C PgUp 도 따라간다", "page=%d" % mv.current_page())

    # D — 꾹(빠르게 여러 번)
    click_row(0)
    sent.clear()
    for _ in range(4):
        key(Qt.Key.Key_Down, wait=30)
    QTest.qWait(400)
    chk(sent == [20] and mv.current_page() == 20, "D 빠르게 여러 번 — 마지막 줄 하나만(이동 한 번)",
        "sent=%s page=%d" % (sent, mv.current_page()))

    # E — 새로 그리기
    sent.clear()
    sr.sort_combo.setCurrentIndex(1); QTest.qWait(300)
    chk(sent == [], "E 결과를 새로 그려도 가지 않는다", str(sent))
    mw.close()
except Exception:
    import traceback; traceback.print_exc()
    fails.append("예외")

print()
print("FAILED:", len(fails)) if fails else print("ALL PASS")
sys.stdout.flush()
os._exit(1 if fails else 0)          # Qt 소멸 단계 충돌을 피한다(MainWindow 검사 관례)
