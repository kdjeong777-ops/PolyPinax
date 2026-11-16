# -*- coding: utf-8 -*-
"""261116-13 보기 탭 `2단` ▾ `PDF`·`PIX`·`스크린샷` — 섞은 2단 (사진 보기 SOT §4.47, 디자인 SOT §2.9.5).

실제 MainWindow 로(오프스크린, 실제 설정 폴더를 쓰지 않는다 — 검사 작성 SOT §14.7.2 의 3). 단추·메뉴 항목·마우스·키는 실제 것으로.
A. 리본의 `2단` 은 분할 단추 — ▾ 메뉴 PDF·PIX·스크린샷. 본체를 누르면 종전 2단(PDF 모드 → 오른쪽 PDF)
B. ▾ PIX: 오른쪽 칸 = 사진 모드의 마지막 사진(사진 문서), 아래 책갈피창만 사진 목록, 창은 PDF 모드 그대로, 왼쪽 PDF 그대로, ▾ 체크 PIX
C. 썸네일 칸은 활성 창 따라 — 왼쪽(PDF)이면 쪽 썸네일, 오른쪽(사진)이면 사진 줄(아래 목록 차례)
D. 오른쪽에서 PageDown = 아래 목록 차례로 다음 사진, 사진 줄을 누르면 오른쪽에(왼쪽 그대로)
E. 편집 모드여도 섞은 칸에는 그리기 도구 줄이 없다(왼쪽은 있다)
   E2(261116-19). 아래 책갈피창도 보기만 — 우클릭(실제 QContextMenuEvent) = '사진 모드로 보기' 한 줄, Del·이름 변경 없음
F. 본체를 다시 누르면 종전 2단 — 오른쪽 PDF·아래 PDF 목록·사진 줄 숨김
G. 섞은 칸 우클릭 '사진 모드로 보기' = 사진 모드 1단에 그 사진
H. 사진 모드의 ▾ PDF = 오른쪽 PDF(PDF 모드의 마지막 자리)·아래 PDF 목록, 썸네일 칸 활성 창 따라, 1단이면 아래 목록은 사진으로
I. ▾ 스크린샷 — 컷이 없으면 알림만, 있으면 컷을 누른 것과 같은 길(오른쪽에 컷·아래 컷 목록), 섞은 2단은 놓는다
"""
import os, sys, tempfile, shutil, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pathlib import Path
from PyQt6.QtCore import QStandardPaths, QCoreApplication, QPoint, Qt
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2 의 3
from PyQt6.QtWidgets import QApplication, QToolButton
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_split_kind_%d" % os.getpid())
import modal_guard
modal_guard.install(label=lambda: "2단 칸 고르기")
import test_fixtures
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def pump(cond=None, timeout=10.0):
    t = time.monotonic()
    while time.monotonic() - t < timeout:
        app.processEvents()
        if cond is not None and cond():
            return True
        if cond is None and time.monotonic() - t > 0.3:
            return True
        time.sleep(0.01)
    return False


def norm(p):
    return os.path.normcase(str(Path(str(p)))) if p else None


tmp = Path(tempfile.mkdtemp(prefix="polypdf_split_kind_"))
try:
    from PIL import Image
    pdfs = tmp / "문서"
    pics = tmp / "사진"
    pdfs.mkdir(); pics.mkdir()
    src = test_fixtures.text_pdf()
    a_pdf, b_pdf = pdfs / "가.pdf", pdfs / "나.pdf"
    shutil.copy(src, a_pdf); shutil.copy(src, b_pdf)
    ph = []
    for i, c in enumerate(((200, 60, 60), (60, 200, 60), (60, 60, 200))):
        p = pics / ("p%d.jpg" % (i + 1))
        Image.new("RGB", (320, 240), c).save(p)
        ph.append(p)

    from viewer.app import MainWindow
    from viewer.history import HistoryItem
    mw = MainWindow(); mw._skip_save_on_close = True
    mw.resize(1400, 900); mw.show(); pump()
    mw._prefs.setdefault("picture", {})["view_kind"] = "mixed"
    mw._photo_apply_view_kind()
    msgs = []
    _show = mw.status.showMessage
    mw.status.showMessage = lambda t, *a: (msgs.append(t), _show(t, *a))[1]
    top, bot = mw.bookmark_tree, mw.bookmark_tree_right

    # 사진 모드의 기억 — 사진 폴더에서 p2 를 보고 PDF 모드로
    mw._set_photo_mode(True); pump()
    mw.open_folder(pics); pump(lambda: len(mw._photo_tree_list()) == 3)
    mw._on_bookmark_activated(str(ph[1]), 0); pump()
    mw._set_photo_mode(False); pump()
    mw.open_folder(pdfs); pump(lambda: len(top.ordered_pdf_files() or []) == 2)
    mw._on_bookmark_activated(str(a_pdf), 3); pump(lambda: norm(mw._mv[0].current_file()) == norm(a_pdf))
    chk(not mw._photo_mode and norm(mw._mv[0].current_file()) == norm(a_pdf), "준비 — PDF 모드 왼쪽 가.pdf")

    # A — 분할 단추·▾ 메뉴·본체
    act = mw._view_acts["split"]
    btns = [b for b in mw.findChildren(QToolButton) if b.defaultAction() is act and b.isVisible()]
    chk(bool(btns), "A 리본에 2단 단추")
    btn = btns[0] if btns else None
    chk(btn is not None and btn.popupMode() == QToolButton.ToolButtonPopupMode.MenuButtonPopup,
        "A 2단은 분할 단추(본체 실행·▾ 메뉴)", str(btn.popupMode() if btn else None))
    m = act.menu()
    names = [a.text() for a in m.actions()] if m else []
    chk(names == ["PDF", "PIX", "스크린샷"], "A ▾ 항목 PDF·PIX·스크린샷", str(names))
    kinds = {a.objectName(): a for a in (m.actions() if m else [])}
    QTest.mouseClick(btn, Qt.MouseButton.LeftButton, pos=QPoint(6, btn.height() // 2)); pump()
    chk(mw._split_on and mw.act_split.isChecked() and not mw._mix_on_now() and not bot._photo_on(),
        "A 본체 = 종전 2단(2단을 켠다 — 아래 PDF 목록)")

    # B — PIX
    kinds["split_kind_pix"].trigger(); pump(lambda: mw._mv[1].current_file() is not None)
    pump(lambda: len(mw._mix_list(1)) == 3)
    mv1 = mw._mv[1]
    chk(mw._mix_on_now(), "B PIX = 섞은 2단")
    chk(norm(mv1.current_file()) == norm(ph[1]) and getattr(mv1._doc, "is_photo", False),
        "B 오른쪽 = 사진 모드의 마지막 사진(사진 문서)", str(mv1.current_file()))
    chk(not mw._photo_mode and norm(mw._mv[0].current_file()) == norm(a_pdf), "B 창은 PDF 모드·왼쪽 PDF 그대로")
    chk(bot._photo_on() and not top._photo_on(), "B 아래 책갈피창만 사진 목록")
    order = mw._mix_list(1)
    chk(sorted(norm(p) for p in order) == sorted(norm(p) for p in ph), "B 아래 목록 = 사진 셋", str(order))
    m.aboutToShow.emit()
    chk(kinds["split_kind_pix"].isChecked() and not kinds["split_kind_pdf"].isChecked(), "B ▾ 체크 = PIX")

    # C — 썸네일 칸은 활성 창 따라
    strip = mw._photo_strip_widget(create=False)
    pt = mw.page_thumbs
    chk(strip is not None and strip.isVisibleTo(pt) and not pt.list.isVisibleTo(pt), "C 오른쪽 활성 — 사진 줄")
    chk(strip is not None and [norm(p) for p in strip.paths()] == [norm(p) for p in order], "C 사진 줄 = 아래 목록 차례")
    QTest.mouseClick(mw._mv[0].view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(40, 40)); pump()
    chk(mw._active_pane == 0, "C 왼쪽을 누르면 왼쪽 활성", str(mw._active_pane))
    chk(not strip.isVisibleTo(pt) and pt.list.isVisibleTo(pt) and norm(getattr(pt._doc, "path", None)) == norm(a_pdf),
        "C 왼쪽 활성 — 쪽 썸네일(가.pdf)")
    QTest.mouseClick(mv1.view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(40, 40)); pump()
    chk(mw._active_pane == 1 and strip.isVisibleTo(pt), "C 오른쪽을 다시 누르면 사진 줄")

    # D — 넘김·사진 줄 누름
    mv1.view.setFocus(); pump()
    on = [norm(p) for p in order]
    want = order[on.index(norm(mv1.current_file())) + 1] if norm(mv1.current_file()) in on[:-1] else None
    QTest.keyClick(mv1.view, Qt.Key.Key_PageDown); pump(lambda: norm(mv1.current_file()) == norm(want))
    chk(want is not None and norm(mv1.current_file()) == norm(want), "D PageDown = 아래 목록 차례로 다음 사진", str(mv1.current_file()))
    pick = next(p for p in order if norm(p) != norm(mv1.current_file()))
    chk(norm(mw._mv[0].current_file()) == norm(a_pdf), "D 왼쪽 PDF 그대로")
    it = strip._items.get(str(pick))
    if it is not None:
        strip.scrollToItem(it); pump()
        r = strip.visualItemRect(it)
        QTest.mouseClick(strip.viewport(), Qt.MouseButton.LeftButton, pos=r.center()); pump(lambda: norm(mv1.current_file()) == norm(pick))
    chk(norm(mv1.current_file()) == norm(pick) and norm(mw._mv[0].current_file()) == norm(a_pdf),
        "D 사진 줄을 누르면 오른쪽에(왼쪽 그대로)", str(mv1.current_file()))

    # E — 편집 모드 그리기
    top.btn_edit.setChecked(True); pump()
    chk(not mw._mv[0]._draw_bar.isHidden() and mv1._draw_bar.isHidden(), "E 편집 모드 — 섞은 칸에는 그리기 줄 없음")

    # E2 — 261116-19: 섞은 2단 아래 책갈피창은 보기만 — 우클릭 = '사진 모드로 보기' 한 줄, Del·이름 변경 없음(편집 모드여도)
    from PyQt6.QtGui import QContextMenuEvent
    from viewer.widgets.ctx_menu import CtxMenu
    node = bot._file_node_for_path(str(Path(order[0])))
    chk(node is not None, "E2 준비 — 아래 창 사진 줄")
    menus, dels, edits = [], [], []
    _old_exec2 = CtxMenu.exec
    CtxMenu.exec = lambda menu, *a, **k: menus.append([x.text() for x in menu.actions() if not x.isSeparator()])
    _old_del, _old_ed = bot._op_delete, bot._edit_file_node
    bot._op_delete = lambda *a, **k: dels.append(1)
    bot._edit_file_node = lambda *a, **k: edits.append(1)
    try:
        if node is not None:
            bot.tree.scrollToItem(node); pump()
            vp2 = bot.tree.viewport()
            c = bot.tree.visualItemRect(node).center()
            QApplication.sendEvent(vp2, QContextMenuEvent(QContextMenuEvent.Reason.Mouse, c, vp2.mapToGlobal(c))); pump()
            bot.tree.setCurrentItem(node); node.setSelected(True)
            QTest.keyClick(bot.tree, Qt.Key.Key_Delete); pump()
            bot._edit_item(node); pump()
    finally:
        CtxMenu.exec = _old_exec2
        bot._op_delete, bot._edit_file_node = _old_del, _old_ed
    chk(menus == [["사진 모드로 보기"]], "E2 아래 창 우클릭 = '사진 모드로 보기' 한 줄", str(menus))
    chk(not dels and not edits and all(p.exists() for p in ph), "E2 Del·이름 변경 없음(편집 모드여도)",
        "del %d edit %d" % (len(dels), len(edits)))
    top.btn_edit.setChecked(False); pump()

    # F — 본체로 종전 2단
    QTest.mouseClick(btn, Qt.MouseButton.LeftButton, pos=QPoint(6, btn.height() // 2)); pump()
    pump(lambda: norm(mw._mv[1].current_file()) == norm(a_pdf))
    chk(not mw._mix_on_now() and not bot._photo_on(), "F 본체 = 종전 2단(아래 PDF 목록)")
    chk(norm(mw._mv[1].current_file()) == norm(a_pdf), "F 오른쪽 = 왼쪽 PDF", str(mw._mv[1].current_file()))
    chk(not strip.isVisibleTo(pt), "F 사진 줄 숨김")

    # G — 섞은 칸 우클릭 '사진 모드로 보기'
    kinds["split_kind_pix"].trigger(); pump(lambda: mw._mv[1].current_file() is not None)
    from viewer.widgets.ctx_menu import CtxMenu
    seen = []

    def _exec(menu, *a, **k):
        seen.append([x.text() for x in menu.actions()])
        for x in menu.actions():
            if x.objectName() == "mix_view_in_mode":
                x.trigger()
        return None
    _old_exec = CtxMenu.exec
    CtxMenu.exec = _exec
    right_now = mw._mv[1].current_file()
    try:
        mw._set_active_pane(1)
        vp = mw._mv[1].view.viewport()
        QTest.mouseClick(vp, Qt.MouseButton.RightButton, pos=QPoint(60, 60)); pump()
        if not seen:
            mw._on_viewer_context_menu(vp.mapToGlobal(QPoint(60, 60))); pump()
    finally:
        CtxMenu.exec = _old_exec
    chk(bool(seen) and seen[0] == ["사진 모드로 보기"], "G 섞은 칸 우클릭 = '사진 모드로 보기' 한 줄", str(seen))
    pump(lambda: mw._photo_mode and norm(mw._mv[0].current_file()) == norm(right_now))
    chk(right_now is not None and mw._photo_mode and not mw._split_on and norm(mw._mv[0].current_file()) == norm(right_now),
        "G 사진 모드 1단에 그 사진", "%s %s %s" % (mw._photo_mode, mw._split_on, mw._mv[0].current_file()))

    # H — 사진 모드의 ▾ PDF
    pump(lambda: len(mw._photo_tree_list()) == 3)
    kinds["split_kind_pdf"].trigger(); pump(lambda: mw._mv[1].current_file() is not None)
    pump(lambda: norm(mw._mv[1].current_file()) == norm(a_pdf))
    chk(mw._photo_mode and mw._mix_on_now(), "H 사진 모드의 PDF = 섞은 2단")
    chk(norm(mw._mv[1].current_file()) == norm(a_pdf) and not bot._photo_on() and top._photo_on(),
        "H 오른쪽 = PDF 모드의 마지막 PDF·아래 PDF 목록", str(mw._mv[1].current_file()))
    chk(mw._active_pane == 1 and not strip.isVisibleTo(pt) and norm(getattr(pt._doc, "path", None)) == norm(a_pdf),
        "H 오른쪽 활성 — 쪽 썸네일")
    QTest.mouseClick(mw._mv[0].view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(40, 40)); pump()
    chk(mw._active_pane == 0 and strip.isVisibleTo(pt), "H 왼쪽(사진) 활성 — 사진 줄")
    # 261116-19(사진 SOT §4.28): 섞은 2단이면 왼쪽 사진 우클릭에 '2분할 함께 움직이기' 없음(누르면 아무 일 없던 줄)
    hm = []
    _old_exec3 = CtxMenu.exec
    CtxMenu.exec = lambda menu, *a, **k: hm.append([x.text() for x in menu.actions()])
    try:
        mw._on_viewer_context_menu(mw._mv[0].view.viewport().mapToGlobal(QPoint(60, 60))); pump()
    finally:
        CtxMenu.exec = _old_exec3
    chk(bool(hm) and "사진 복사" in hm[0] and "2분할 함께 움직이기" not in hm[0],
        "H 섞은 2단 — 왼쪽 사진 메뉴에 '2분할 함께 움직이기' 없음", str(hm[:1])[:200])
    m.aboutToShow.emit()
    chk(kinds["split_kind_pdf"].isChecked(), "H ▾ 체크 = PDF")
    mw._vm_single(); pump()
    chk(not mw._split_on and not mw._mix_on_now() and bot._photo_on(), "H 1단 — 섞은 2단을 놓고 아래 목록은 사진 종류")

    # I — 스크린샷
    mw._set_photo_mode(False); pump()
    mw.shot_strip.clear()
    msgs.clear()
    kinds["split_kind_shot"].trigger(); pump()
    chk(any("스크린샷이 없습니다" in t for t in msgs) and not mw._split_on, "I 컷이 없으면 알림만", str(msgs))
    cut = tmp / "컷.png"
    Image.new("RGB", (200, 120), (250, 250, 0)).save(cut)
    mw.shot_strip.add_item(str(cut), kind="image", label="컷")
    kinds["split_kind_pix"].trigger(); pump(lambda: mw._mix_on_now())
    kinds["split_kind_shot"].trigger(); pump(lambda: bot.in_shot_list())
    chk(mw._split_on and bot.in_shot_list() and not mw._mix_on_now(), "I 컷을 오른쪽에·아래 컷 목록·섞은 2단 놓음")
    m.aboutToShow.emit()
    chk(kinds["split_kind_shot"].isChecked(), "I ▾ 체크 = 스크린샷")
    mw.shot_strip.clear()
    mw.close()
finally:
    pump(timeout=0.5)
    shutil.rmtree(tmp, ignore_errors=True)

if fails:
    print("\n=== FAIL %d ===" % len(fails))
    sys.stdout.flush()
    os._exit(1)
print("\n=== ALL PASS ===")
sys.stdout.flush()
os._exit(0)
