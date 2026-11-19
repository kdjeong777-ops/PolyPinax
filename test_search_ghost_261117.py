# -*- coding: utf-8 -*-
"""261117-39(검색창 SOT §6, 사용자 지시 '검색한 후 다른 항목을 선택하여 선택이 해제되면 검색한 내용이 흐리게 …'):
탭 줄 검색창 — 찾은 글은 떠나면 흐린 자리표시로, 빈 칸에서 → 로 되살린다.

A. 실제 Enter 로 찾은 뒤 실제 마우스로 다른 칸을 누르면 칸이 비고 찾은 글이 자리표시(흐린 글)가 된다
B. 결과는 그대로 — 다시 찾지 않고, 검색 막대 글도 남는다
C. 다시 누르고 치면 지울 것 없이 새 글만 들어간다(최근 목록이 열려 있어도)
D. 빈 칸에서 → 로 흐린 글을 되살린다(커서 끝) — 최근 목록이 열려 있어도
E. 목록을 닫은 뒤 빈 칸에서 Esc 면 흐린 글을 버리고 '검색' 으로
F. 쳐 놓기만 한 글은 떠나도 그대로
G. 찾은 뒤 고친 글도 그대로
H. 자리표시 색은 칸 글보다 흐리다(디자인 SOT §2.3)
수정 전 코드에는 흐린 글이 없다(A 부터 실패).
"""
import os, sys, faulthandler, tempfile, shutil
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(180, exit=True)

from PyQt6.QtCore import QStandardPaths, Qt, QPoint
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
import modal_guard
modal_guard.install(echo=False)                     # 검사 작성 SOT §14.7.2 의 6 — 뜬 모달을 닫는다
from PyQt6.QtCore import QCoreApplication as _QCA
_QCA.setApplicationName("polypdf_search_ghost_%d" % os.getpid())   # 공유 시험 설정 폴더를 쓰지 않는다
fails = []


def chk(c, m, extra=""):
    print(("PASS" if c else "FAIL"), "-", m, ("" if c else extra))
    if not c:
        fails.append(m)


def target(ed):
    """실제 키가 가는 곳 — 열린 팝업이 있으면 팝업, 없으면 칸."""
    return QApplication.activePopupWidget() or ed


def key(ed, k):
    QTest.keyClick(target(ed), k); QTest.qWait(60)


def type_(ed, s):
    for ch in s:
        QTest.keyClicks(target(ed), ch)
    QTest.qWait(60)


tmp = tempfile.mkdtemp(prefix="polypdf_ghost_")
try:
    from viewer.app import MainWindow
    mw = MainWindow()
    mw.resize(1500, 900); mw.show(); mw.activateWindow(); QTest.qWait(200)
    mw._folder = tmp                                  # action_search 가 '폴더를 먼저' 로 멈추지 않게(빈 폴더)
    ed = mw.toolbar_search
    mw.act_toggle_search.setChecked(False); mw._sync_right_layout(); QTest.qWait(50)
    chk(ed.isVisible() and ed.placeholderText() == "검색", "준비 — 탭 줄 검색창이 보이고 자리표시는 '검색'", ed.placeholderText())

    calls = []
    _orig = mw.action_search

    def spy(q):
        calls.append(q)
        return _orig(q)
    mw.action_search = spy

    def click(w):
        QTest.mouseClick(w, Qt.MouseButton.LeftButton, pos=QPoint(min(40, w.width() // 2), w.height() // 2)); QTest.qWait(120)

    def close_popup():
        if QApplication.activePopupWidget() is not None:
            key(ed, Qt.Key.Key_Escape)

    # A — 실제 Enter 로 찾고, 실제 마우스로 다른 칸
    click(ed); close_popup()
    type_(ed, "asphalt"); close_popup()
    key(ed, Qt.Key.Key_Return); QTest.qWait(150)
    chk(calls == ["asphalt"], "준비 — Enter 로 한 번 찾았다", str(calls))
    # 찾으면 검색 패널이 열리고 탭 줄 칸은 숨는다(초점이 떠남) — 패널을 닫아 칸을 다시 보인다
    mw.act_toggle_search.setChecked(False); mw._sync_right_layout(); mw.activateWindow(); QTest.qWait(80)
    chk(ed.isVisible() and not ed.hasFocus(), "준비 — 칸이 다시 보이고 초점은 떠나 있다")
    chk(ed.text() == "" and ed.placeholderText() == "asphalt", "A 찾고 떠나면(패널이 연 초점 이동) 칸은 비고 흐린 자리표시",
        "text=%r ph=%r" % (ed.text(), ed.placeholderText()))
    other = mw.bookmark_tree.tree.viewport()
    chk(other.isVisible(), "준비 — 다른 항목(책갈피창)이 보인다")
    # 실제 마우스로 다른 항목을 누를 때 — → 로 되살린 찾은 글
    click(ed); close_popup(); key(ed, Qt.Key.Key_Right)
    chk(ed.text() == "asphalt", "준비 — → 로 되살렸다", repr(ed.text()))
    click(other)
    chk(not ed.hasFocus(), "준비 — 초점이 떠났다")
    chk(ed.text() == "" and ed.placeholderText() == "asphalt", "A 실제 마우스로 다른 항목을 누르면 칸은 비고 흐린 자리표시",
        "text=%r ph=%r" % (ed.text(), ed.placeholderText()))

    # B — 결과는 그대로
    sb = mw.search_bar.edit
    chk(calls == ["asphalt"] and sb.text() == "asphalt", "B 다시 찾지 않고 검색 막대 글도 남는다", "%s %r" % (calls, sb.text()))

    # C — 다시 누르고 바로 새로 쓰기
    click(ed)
    type_(ed, "crack")
    chk(ed.text() == "crack", "C 지울 것 없이 새 글만", repr(ed.text()))

    # D — 빈 칸에서 → (최근 목록이 열린 채)
    ed.selectAll(); key(ed, Qt.Key.Key_Backspace)
    chk(ed.text() == "" and ed.placeholderText() == "asphalt", "준비 — 칸을 비우면 흐린 글이 다시 보인다", repr(ed.placeholderText()))
    if QApplication.activePopupWidget() is None:
        key(ed, Qt.Key.Key_Down)                     # 최근 목록을 열어 둔 채로 → 를 시험
    chk(QApplication.activePopupWidget() is not None, "준비 — 최근 목록이 열려 있다")
    key(ed, Qt.Key.Key_Right)
    chk(ed.text() == "asphalt" and ed.cursorPosition() == len("asphalt"), "D → 로 흐린 글을 되살린다(커서 끝)",
        "text=%r pos=%d" % (ed.text(), ed.cursorPosition()))
    close_popup()
    key(ed, Qt.Key.Key_Right)
    chk(ed.text() == "asphalt", "D 글이 있으면 → 는 종전대로(덧붙이지 않음)", repr(ed.text()))

    # E — Esc 로 버리기
    click(other); chk(ed.placeholderText() == "asphalt" and ed.text() == "", "준비 — 다시 흐린 글")
    click(ed); close_popup()
    chk(ed.placeholderText() == "asphalt", "E 목록의 Esc 는 목록만 닫는다(흐린 글 남음)", repr(ed.placeholderText()))
    key(ed, Qt.Key.Key_Escape)
    chk(ed.placeholderText() == "검색" and ed.text() == "", "E 빈 칸에서 Esc 면 흐린 글을 버리고 '검색'", repr(ed.placeholderText()))
    key(ed, Qt.Key.Key_Right)
    chk(ed.text() == "", "E 버린 뒤 → 는 아무것도 되살리지 않는다", repr(ed.text()))

    # F — 쳐 놓기만 한 글
    type_(ed, "draft"); close_popup()
    click(other)
    chk(ed.text() == "draft" and ed.placeholderText() == "검색", "F 찾지 않은 글은 떠나도 그대로", repr(ed.text()))

    # G — 찾은 뒤 고친 글
    click(ed); close_popup()
    ed.selectAll(); type_(ed, "crack"); close_popup()
    key(ed, Qt.Key.Key_Return); QTest.qWait(150)
    mw.act_toggle_search.setChecked(False); mw._sync_right_layout(); mw.activateWindow(); QTest.qWait(80)
    click(ed); close_popup(); key(ed, Qt.Key.Key_Right)
    chk(ed.text() == "crack", "준비 — 찾은 글을 → 로 되살렸다", repr(ed.text()))
    ed.end(False); type_(ed, "s"); close_popup()
    click(other)
    chk(ed.text() == "cracks", "G 찾은 뒤 고친 글은 그대로", repr(ed.text()))

    # H — 색
    ed.ensurePolished()
    pal = ed.palette()
    ph = pal.color(QPalette.ColorRole.PlaceholderText)
    tx = pal.color(QPalette.ColorRole.Text)
    chk(ph.name() != tx.name() and abs(ph.lightness() - 128) < abs(tx.lightness() - 128) + 1,
        "H 자리표시 색은 칸 글보다 흐리다", "%s %s" % (ph.name(), tx.name()))
    mw.close()
except Exception:
    import traceback; traceback.print_exc()
    fails.append("예외")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
print("FAILED:", len(fails)) if fails else print("ALL PASS")
sys.stdout.flush()
os._exit(1 if fails else 0)          # Qt 소멸 단계 충돌을 피한다(MainWindow 검사 관례)
