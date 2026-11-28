# -*- coding: utf-8 -*-
"""261117-31(검색창 SOT §6·§10, 사용자 지시 '검색창의 검색 내용을 기억해'·결정 '검색창에 최근 목록만'):
탭 줄 검색창 아래 최근 검색어 펼침 목록.

A. 실제 마우스로 칸을 누르면 최근 검색어가 펼쳐진다 — 즐겨찾기 탭 메뉴와 같은 순서·꼴(`  Aa`·`  .*`)
B. 실제 ↓ 키로도 펼친다 · Esc 는 닫기만(찾지 않음)
C. 글자를 치면 그 글자를 담은 검색어로 좁힌다 · 맞는 것이 없으면 닫힌다
D. 실제 마우스로 고르면 칸을 채우고 그 검색어의 Aa·.* 를 되살려 **한 번** 찾는다 · 찾은 것이 맨 위로
E. ↓·Enter 로 고르기도 같다(한 번만 찾는다)
F. 목록이 비면 열지 않는다
G. 다시 켜면 칸은 빈 채, 목록은 남는다(새 설정 키 없음 — recent_searches 하나)
수정 전 코드에는 펼침 목록이 없다(A 부터 실패).
"""
import os, sys, faulthandler, tempfile, shutil
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(180, exit=True)

from PyQt6.QtCore import QStandardPaths, Qt, QPoint
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
import modal_guard
modal_guard.install(echo=False)                     # 검사 작성 SOT §14.7.2 의 6 — 뜬 모달을 닫는다
from PyQt6.QtCore import QCoreApplication as _QCA
_QCA.setApplicationName("polypdf_recent_popup_%d" % os.getpid())   # 공유 시험 설정 폴더를 쓰지 않는다
fails = []


def chk(c, m, extra=""):
    print(("PASS" if c else "FAIL"), "-", m, ("" if c else extra))
    if not c:
        fails.append(m)


tmp = tempfile.mkdtemp(prefix="polypdf_recent_")
try:
    from viewer.app import MainWindow
    mw = MainWindow()
    mw.resize(1500, 900); mw.show(); mw.activateWindow(); QTest.qWait(200)
    mw._folder = tmp                                  # action_search 가 '폴더를 먼저' 로 멈추지 않게(빈 폴더)
    ed = mw.toolbar_search
    mw.act_toggle_search.setChecked(False); mw._sync_right_layout(); QTest.qWait(50)
    chk(ed.isVisible(), "준비 — 탭 줄 검색창이 보인다")

    calls = []
    _orig = mw.action_search

    def spy(q):
        calls.append((q, tuple(bool(x) for x in (mw.search_bar.mode() or (False, False)))))
        return _orig(q)
    mw.action_search = spy

    # F — 빈 목록
    mw._recent_searches = []; mw._refresh_recent_searches_menu()
    pop = getattr(getattr(mw, "_recent_popup", None), "completer", None)
    popup = pop.popup() if pop is not None else None
    QTest.mouseClick(ed, Qt.MouseButton.LeftButton, pos=QPoint(60, ed.height() // 2)); QTest.qWait(80)
    chk(popup is not None and not popup.isVisible(), "F 목록이 비면 열지 않는다")

    mw._touch_recent_search("asphalt", False, False)
    mw._touch_recent_search("Crack", True, False)
    mw._touch_recent_search("pave.*nt", False, True)
    menu_txt = [a.text().replace("🔍 ", "") for a in mw.menu_recent_searches.actions()]

    def shown():
        if popup is None or not popup.isVisible():
            return []
        m = popup.model()
        return [m.index(i, 0).data() for i in range(m.rowCount())]

    # A — 실제 마우스
    ed.clearFocus(); QTest.qWait(30)
    QTest.mouseClick(ed, Qt.MouseButton.LeftButton, pos=QPoint(60, ed.height() // 2)); QTest.qWait(120)
    chk(shown() == ["pave.*nt  .*", "Crack  Aa", "asphalt"], "A 누르면 펼친다 — 새 것 위·켠 토글 꼴", str(shown()))
    chk(shown() == menu_txt, "A 즐겨찾기 탭 '최근 검색어' 와 같은 목록·순서", str(menu_txt))
    QTest.keyClick(popup, Qt.Key.Key_Escape); QTest.qWait(60)
    chk(not popup.isVisible() and not calls, "B Esc 는 닫기만")

    # B — 실제 ↓
    ed.setFocus(); QTest.qWait(30)
    QTest.keyClick(ed, Qt.Key.Key_Down); QTest.qWait(120)
    chk(len(shown()) == 3, "B ↓ 로 펼친다", str(shown()))
    QTest.keyClick(popup, Qt.Key.Key_Escape); QTest.qWait(60)

    # C — 글자로 좁히기
    ed.clear(); ed.setFocus()
    QTest.keyClicks(ed, "ac"); QTest.qWait(120)
    chk(shown() == ["Crack  Aa"], "C 친 글자를 담은 것만(대소문자 무시)", str(shown()))
    QTest.keyClicks(ed, "zz"); QTest.qWait(120)
    chk(not popup.isVisible(), "C 맞는 것이 없으면 닫힌다")
    ed.clear(); QTest.qWait(30)

    # D — 실제 마우스로 고르기
    QTest.mouseClick(ed, Qt.MouseButton.LeftButton, pos=QPoint(60, ed.height() // 2)); QTest.qWait(120)
    m = popup.model()
    row = next((i for i in range(m.rowCount()) if m.index(i, 0).data() == "Crack  Aa"), -1)
    r = popup.visualRect(m.index(row, 0))
    QTest.mouseClick(popup.viewport(), Qt.MouseButton.LeftButton, pos=r.center()); QTest.qWait(200)
    # 261128-9(검색창 SOT §4.1): 한국어 화면엔 Aa 가 없고 대소문자 구분은 늘 끔 — 남긴 case 는 되살리지 않는다
    from viewer.i18n import language, KO
    case_on = language() != KO
    chk(calls == [("Crack", (case_on, False))], "D 고르면 그 검색어·토글(한국어 화면은 Aa 끔)로 한 번 찾는다", str(calls))
    chk(mw.search_bar.edit.text() == "Crack" and bool(mw.search_bar.mode() and mw.search_bar.mode()[0]) == case_on
        and not (mw.search_bar.mode() and mw.search_bar.mode()[1]),
        "D 검색 막대에 검색어·토글이 되살아난다", str(mw.search_bar.mode()))
    chk(mw._recent_searches[0] == {"query": "Crack", "case": case_on, "regex": False}, "D 찾은 것이 맨 위로", str(mw._recent_searches[:1]))

    # E — ↓·Enter
    calls.clear()
    mw.act_toggle_search.setChecked(False); mw._sync_right_layout(); QTest.qWait(50)
    ed.clear(); ed.setFocus(); QTest.qWait(30)
    QTest.keyClick(ed, Qt.Key.Key_Down); QTest.qWait(120)
    QTest.keyClick(popup, Qt.Key.Key_Down); QTest.keyClick(popup, Qt.Key.Key_Down); QTest.qWait(30)
    QTest.keyClick(popup, Qt.Key.Key_Return); QTest.qWait(250)
    chk(calls == [("pave.*nt", (False, True))], "E ↓·Enter 로 골라 .* 까지 되살려 한 번 찾는다", str(calls))

    # G — 다시 켜기
    keep = [dict(x) for x in mw._recent_searches]
    mw._save_settings_now()
    mw.close(); QTest.qWait(100)
    mw2 = MainWindow(); mw2.show(); QTest.qWait(200)
    chk(mw2.toolbar_search.text() == "", "G 다시 켜면 칸은 빈 채")
    chk([x.get("query") for x in mw2._recent_popup.items] == [x["query"] for x in keep], "G 목록은 남는다(recent_searches)",
        str(mw2._recent_popup.items))
    mw2.close()
except Exception:
    import traceback; traceback.print_exc()
    fails.append("예외")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
print("FAILED:", len(fails)) if fails else print("ALL PASS")
sys.stdout.flush()
os._exit(1 if fails else 0)          # Qt 소멸 단계 충돌을 피한다(MainWindow 검사 관례)
