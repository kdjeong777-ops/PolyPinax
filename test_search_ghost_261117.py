# -*- coding: utf-8 -*-
"""261117-39·261117-42·261117-60(검색창 SOT §6.1): 검색 칸 공통 — 찾은 글은 떠나면 흐리게.

사용자 지시 '검색한 후 다른 항목을 선택하여 선택이 해제되면 검색한 내용이 흐리게 … 다시 포인터되면 새로운 키워드로
지우지 않고 그냥 작성 … 화살표키로 우측으로 이동시 다시 사용', 보고 '검색창(책갈피창, 명함창 등)에서 … 적용 안됐어',
보고(-60) '다시 선택되면 커서가 가장 앞에 있게하고, 글을 쓸 경우 뒤에 있는 글자가 지워지고, 쓴 글만 있도록'.

A. 탭 줄 칸 — 실제 Enter 로 찾고 칸이 숨었다 다시 보이면 글은 그대로·흐린 색
B. 결과는 그대로(다시 찾지 않음)
C. 실제 마우스로 다시 누르면 흐린 채·고름 없이 커서 맨 앞, 최근 목록은 전부 · 목록이 열린 채 친 글이 옛 글을 지우고 새 검색어(제 색)
D. 찾은 뒤 다른 항목을 실제 마우스로 누르면 흐림 · 글 가운데를 누르기·두 번 누르기도 커서 맨 앞 · ←·Home 은 흐린 채 · → 면 글·제 색·커서 끝
D2. 첫 입력 — Backspace·붙여넣기(Ctrl+V)·한글 조합(QInputMethodEvent preedit→commit)도 옛 글을 지우고 친 것만
E. Enter 칸은 쳐 놓기만 한 글은 떠나도 그대로
F. 검색 패널 칸 — Enter 로 찾은 글·다른 길(최근 검색어)로 찾은 글 모두 흐림, 다시 누르면 커서 맨 앞, 치면 새 글
G. 책갈피창 거르기(즉시 칸) — 친 글은 떠나면 흐림, 걸러 둔 것(칸 글)은 그대로, Tab 으로 와도 커서 맨 앞(다 고르지 않음),
   → 로 제 색 · 팔레트 길(스타일시트 없는 칸)도 되돌림 · 첫 글자로 거르기 칸 글이 곧바로 그 글자 하나
H. 창 바꾸기로 떠나는 초점은 흐리지 않는다
I. §6.1 표의 모든 칸에 SearchGhost 가 붙어 있다(즉시·Enter 구분까지)
수정 전 코드(-42: 다시 누르면 다 고름·커서 끝)는 C·D·D2·F·G 에서 실패한다.
"""
import os, sys, faulthandler, tempfile, shutil, re
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
faulthandler.dump_traceback_later(180, exit=True)

from PyQt6.QtCore import QStandardPaths, Qt, QPoint, QEvent
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QFocusEvent, QInputMethodEvent
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
import modal_guard
modal_guard.install(echo=False)                     # 검사 작성 SOT §14.7.2 의 6 — 뜬 모달을 닫는다
from PyQt6.QtCore import QCoreApplication as _QCA
_QCA.setApplicationName("polypdf_search_ghost_%d" % os.getpid())   # 공유 시험 설정 폴더를 쓰지 않는다
fails = []
GHOST = "#8a8a8a"


def chk(c, m, extra=""):
    print(("PASS" if c else "FAIL"), "-", m, ("" if c else extra))
    if not c:
        fails.append(m)


def looks_dim(ed):
    if GHOST in ed.styleSheet():
        return True
    return ed.palette().color(QPalette.ColorRole.Text).name() == GHOST


def target(ed):
    return QApplication.activePopupWidget() or ed


def key(ed, k):
    QTest.keyClick(target(ed), k); QTest.qWait(60)


def type_(ed, s):
    for ch in s:
        QTest.keyClicks(target(ed), ch)
    QTest.qWait(60)


def click(w, x=None):
    QTest.mouseClick(w, Qt.MouseButton.LeftButton, pos=QPoint(min(40, w.width() // 2) if x is None else x, w.height() // 2)); QTest.qWait(120)


def mid_x(ed):
    """칸 글 가운데의 x — 글 사이를 누른다(커서가 맨 앞으로 가야 한다)."""
    r = ed.cursorRect()
    m = ed.textMargins()
    fm = ed.fontMetrics()
    return ed.contentsRect().left() + m.left() + 2 + fm.horizontalAdvance(ed.text()[: max(1, len(ed.text()) // 2)])


def at_home(ed, txt):
    return ed.text() == txt and not ed.hasSelectedText() and ed.cursorPosition() == 0 and looks_dim(ed)


def ime(ed, preedit="", commit=""):
    e = QInputMethodEvent(preedit, [])
    if commit:
        e.setCommitString(commit)
    QApplication.sendEvent(target(ed), e); QTest.qWait(60)


def close_popup(ed):
    if QApplication.activePopupWidget() is not None:
        key(ed, Qt.Key.Key_Escape)


tmp = tempfile.mkdtemp(prefix="polypdf_ghost_")
try:
    from viewer.app import MainWindow
    mw = MainWindow()
    mw.resize(1500, 900); mw.show(); mw.activateWindow(); QTest.qWait(200)
    mw._folder = tmp                                  # action_search 가 '폴더를 먼저' 로 멈추지 않게(빈 폴더)
    ed = mw.toolbar_search
    tree = mw.bookmark_tree.tree.viewport()
    mw.act_toggle_search.setChecked(False); mw._sync_right_layout(); QTest.qWait(50)
    chk(ed.isVisible() and tree.isVisible(), "준비 — 탭 줄 칸·책갈피창이 보인다")

    calls = []
    _orig = mw.action_search

    def spy(q):
        calls.append(q)
        return _orig(q)
    mw.action_search = spy
    mw._touch_recent_search("older", False, False)
    mw._touch_recent_search("oldest", False, False)

    def hide_panel():
        mw.act_toggle_search.setChecked(False); mw._sync_right_layout(); mw.activateWindow(); QTest.qWait(80)

    # A
    click(ed); close_popup(ed)
    type_(ed, "asphalt"); close_popup(ed)
    key(ed, Qt.Key.Key_Return); QTest.qWait(150)
    chk(calls == ["asphalt"], "준비 — Enter 로 한 번 찾았다", str(calls))
    hide_panel()
    chk(ed.isVisible() and not ed.hasFocus(), "준비 — 칸이 다시 보이고 초점은 떠나 있다")
    chk(ed.text() == "asphalt" and looks_dim(ed), "A 글은 그대로·흐린 색", "text=%r ss=%r" % (ed.text(), ed.styleSheet()[-120:]))

    # B
    chk(calls == ["asphalt"] and mw.search_bar.edit.text() == "asphalt", "B 다시 찾지 않고 검색 막대 글도 남는다")

    # C
    click(ed, mid_x(ed))
    chk(at_home(ed, "asphalt"), "C 글 가운데를 다시 눌러도 흐린 채·고름 없이 커서 맨 앞",
        "sel=%r pos=%d dim=%s" % (ed.selectedText(), ed.cursorPosition(), looks_dim(ed)))
    pop = QApplication.activePopupWidget()
    n = pop.model().rowCount() if pop is not None else -1
    chk(n == len(mw._recent_searches) and n >= 3, "C 흐린 글로 누르면 최근 목록은 전부", "%d / %d" % (n, len(mw._recent_searches)))
    type_(ed, "crack")
    chk(ed.text() == "crack" and not looks_dim(ed), "C 목록이 열린 채 친 글이 옛 글을 지우고 새 검색어(제 색)", repr(ed.text()))
    close_popup(ed)

    # D
    key(ed, Qt.Key.Key_Return); QTest.qWait(150)
    hide_panel()
    click(ed); close_popup(ed); key(ed, Qt.Key.Key_End)
    chk(ed.text() == "crack" and not looks_dim(ed), "준비 — 찾은 글로 칸에 있다(제 색)")
    click(tree)
    chk(not ed.hasFocus() and looks_dim(ed) and ed.text() == "crack", "D 실제 마우스로 다른 항목을 누르면 흐림")
    click(ed, mid_x(ed)); close_popup(ed)
    chk(at_home(ed, "crack"), "D 다시 누르면 커서 맨 앞", "pos=%d sel=%r" % (ed.cursorPosition(), ed.selectedText()))
    QTest.mouseDClick(ed, Qt.MouseButton.LeftButton, pos=QPoint(mid_x(ed), ed.height() // 2)); QTest.qWait(120); close_popup(ed)
    chk(at_home(ed, "crack"), "D 두 번 눌러도 고르지 않고 커서 맨 앞", "pos=%d sel=%r" % (ed.cursorPosition(), ed.selectedText()))
    key(ed, Qt.Key.Key_Left); key(ed, Qt.Key.Key_Home)
    chk(at_home(ed, "crack"), "D ←·Home 은 흐린 채 그대로")
    key(ed, Qt.Key.Key_Right)
    chk(ed.text() == "crack" and not ed.hasSelectedText() and ed.cursorPosition() == 5 and not looks_dim(ed),
        "D → 로 고름이 풀리고 글·제 색 되살림", "pos=%d sel=%r" % (ed.cursorPosition(), ed.selectedText()))

    # D2 — 첫 입력: Backspace·붙여넣기·한글 조합
    def search_and_leave(s):
        ed.selectAll(); type_(ed, s); close_popup(ed)
        key(ed, Qt.Key.Key_Return); QTest.qWait(150)
        hide_panel(); click(ed, mid_x(ed))
        return at_home(ed, s)
    chk(search_and_leave("crack"), "준비 — 찾은 글로 다시 들어와 커서 맨 앞")
    key(ed, Qt.Key.Key_Backspace)
    chk(ed.text() == "" and not looks_dim(ed), "D2 Backspace 첫 입력 — 옛 글이 지워진다", repr(ed.text()))
    close_popup(ed)
    chk(search_and_leave("seal"), "준비 — seal 로 찾고 다시 들어옴")
    QApplication.clipboard().setText("rut")
    QTest.keyClick(target(ed), Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier); QTest.qWait(80)
    chk(ed.text() == "rut" and not looks_dim(ed), "D2 붙여넣기 첫 입력 — 붙인 글만", repr(ed.text()))
    close_popup(ed)
    chk(search_and_leave("rut"), "준비 — rut 로 찾고 다시 들어옴")
    ime(ed, preedit="\u314e")
    chk(ed.text() == "" and not looks_dim(ed), "D2 한글 조합 첫 글자 — 조합 중에 옛 글이 지워진다", repr(ed.text()))
    ime(ed, commit="\ud55c")
    chk(ed.text() == "\ud55c", "D2 한글 조합을 마치면 친 글만", repr(ed.text()))
    close_popup(ed)

    # E
    ed.selectAll(); type_(ed, "draft"); close_popup(ed)
    click(tree)
    chk(ed.text() == "draft" and not looks_dim(ed), "E Enter 칸 — 쳐 놓기만 한 글은 그대로")

    # F — 검색 패널 칸
    sb = mw.search_bar.edit
    mw.act_toggle_search.setChecked(True); mw._sync_right_layout(); QTest.qWait(80)
    chk(sb.isVisible(), "준비 — 검색 패널 칸이 보인다")
    calls.clear()
    click(sb); sb.selectAll(); type_(sb, "pave")
    QTest.keyClick(sb, Qt.Key.Key_Return); QTest.qWait(150)
    click(tree)
    chk(sb.text() == "pave" and looks_dim(sb), "F 검색 패널 칸 — Enter 로 찾은 글은 떠나면 흐림",
        "%s %r" % (calls, sb.text()))
    click(sb, mid_x(sb))
    chk(at_home(sb, "pave"), "F 다시 누르면 커서 맨 앞", "pos=%d sel=%r" % (sb.cursorPosition(), sb.selectedText()))
    type_(sb, "x")
    chk(sb.text() == "x" and not looks_dim(sb), "F 친 글이 새 글", repr(sb.text()))
    click(tree)
    chk(not looks_dim(sb), "F 쳐 놓기만 한 글은 그대로")
    mw._open_recent_search({"query": "older", "case": False, "regex": False}); QTest.qWait(150)
    mw.act_toggle_search.setChecked(True); mw._sync_right_layout(); QTest.qWait(50)
    click(sb); click(tree)
    chk(sb.text() == "older" and looks_dim(sb), "F 다른 길(최근 검색어)로 찾은 글도 흐림", repr(sb.text()))

    # G — 책갈피창 거르기(즉시)
    fe = mw.bookmark_tree.search_edit
    if not fe.isVisible():
        fe.show(); QTest.qWait(30)
    chk(fe.isVisible() and not fe.styleSheet(), "준비 — 책갈피창 거르기 칸(스타일시트 없음 → 팔레트 길)")
    click(fe); type_(fe, "abc")
    click(sb)
    chk(fe.text() == "abc" and looks_dim(fe), "G 즉시 칸 — 친 글은 떠나면 흐리고 걸러 둔 글은 그대로", repr(fe.text()))
    fe.setFocus(Qt.FocusReason.TabFocusReason); QTest.qWait(80)
    chk(at_home(fe, "abc"), "G Tab 으로 와도 다 고르지 않고 커서 맨 앞", "pos=%d sel=%r" % (fe.cursorPosition(), fe.selectedText()))
    key(fe, Qt.Key.Key_Right)
    chk(not looks_dim(fe) and not fe.testAttribute(Qt.WidgetAttribute.WA_SetPalette),
        "G → 로 제 색 — 팔레트는 테마를 계속 따른다(직접 둔 팔레트 없음)")
    seen = []
    fe.textChanged.connect(seen.append)
    click(sb); click(fe, mid_x(fe))
    chk(at_home(fe, "abc"), "준비 — 다시 흐린 채 들어옴")
    seen.clear(); type_(fe, "q")
    chk(fe.text() == "q" and seen == ["q"], "G 첫 글자로 거르기 칸 글이 곧바로 그 글자 하나(옛 글이 섞인 글로 거르지 않음)", str(seen))

    # H — 창 바꾸기
    click(fe); fe.end(False)
    QApplication.sendEvent(fe, QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.ActiveWindowFocusReason)); QTest.qWait(30)
    chk(not looks_dim(fe), "H 창 바꾸기로 떠나는 초점은 흐리지 않는다")
    mw.close()

    # I — 표의 모든 칸(소스) — 명함찾기 칸은 명함 세션 파일이라 붙은 뒤 이 표에 든다
    TABLE = [
        ("viewer/app.py", "self.toolbar_search", False),
        ("viewer/widgets/search_panel.py", "self.edit", False),
        ("viewer/widgets/bookmark_tree.py", "self.search_edit", True),
        ("viewer/widgets/content_find_overlay.py", "self.edit", True),
        ("viewer/widgets/settings_dialog.py", "self.ed_search", True),
        ("viewer/widgets/tag_apply_dialog.py", "self.ed_find", True),
        ("viewer/widgets/user_terms_dialog.py", "self.ed_q", True),
        ("viewer/widgets/law_search_dialog.py", "self.ed", False),
        ("viewer/widgets/law_search_dialog.py", "self.find_edit", True),
        ("viewer/widgets/kipo_search_dialog.py", "self.ed", False),
        ("viewer/widgets/kipo_search_dialog.py", "self.find_edit", True),
        ("viewer/widgets/kcsc_search_dialog.py", "self.ed", False),
        ("viewer/widgets/kcsc_search_dialog.py", "self.find_edit", True),
        ("viewer/widgets/image_search_dialog.py", "self.ed", False),
    ]
    if "SearchGhost" in open(os.path.join(HERE, "viewer/widgets/bizcard_find_dialog.py"), encoding="utf-8").read():
        TABLE.append(("viewer/widgets/bizcard_find_dialog.py", "self.ed_find", True))
    miss = []
    for f, name, instant in TABLE:
        src = open(os.path.join(HERE, f), encoding="utf-8").read()
        m = re.search(r"SearchGhost\(%s(, instant=True)?(, extra=[^\n]*)?\)" % re.escape(name), src)
        if not m or bool(m.group(1)) != instant:
            miss.append("%s %s" % (f, name))
    chk(not miss, "I §6.1 표의 모든 칸에 붙어 있다(즉시·Enter 구분까지)", str(miss))
except Exception:
    import traceback; traceback.print_exc()
    fails.append("예외")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
print("FAILED:", len(fails)) if fails else print("ALL PASS")
sys.stdout.flush()
os._exit(1 if fails else 0)          # Qt 소멸 단계 충돌을 피한다(MainWindow 검사 관례)
