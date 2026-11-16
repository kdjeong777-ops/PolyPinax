# -*- coding: utf-8 -*-
"""261116-8·-9 꾸미기 — ▾ 끝 '입력 설정' 항목, 개체 선택에서 두 번 눌러 편집 (마스터 §4.6.3·§4.6.10, 디자인 SOT §2.10).

실제 창(오프스크린, 실제 설정 폴더를 쓰지 않는다 — 검사 작성 SOT §14.7.2 의 3):
A. 글쓰기 ▾ 끝 = '글쓰기 입력 설정'(누르면 입력 설정 창의 글쓰기 탭), 도형 ▾ 끝 = '도형 입력 설정'(선긋기 탭)
B. 개체 선택에서 글상자를 두 번 누르면(실제 QMouseEvent 누름·놓음·두 번·놓음) 그 글상자 글 고치기 — 친 글이 들어가고,
   바깥을 누르면 개체 선택으로 돌아온다(새 글상자를 만들지 않는다)
C. 같은 길에서 Esc = 개체 선택으로
D. 도형을 두 번 누르면 도형 편집(그 도형 고름) — 모서리 손잡이를 끌면 커지고, 바깥 누름 = 개체 선택(새 도형 안 그림)
E. 같은 것을 사진 모드 본문에서도(B 의 짧은 판)
"""
import os, sys, tempfile, shutil, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pathlib import Path
import fitz
from PyQt6.QtCore import QStandardPaths, QCoreApplication, QPointF, QEvent, Qt
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QMouseEvent, QKeyEvent
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
import modal_guard
modal_guard.install(label=lambda: "꾸미기 두 번 누름")
QCoreApplication.setApplicationName("polypdf_deco_dbl_%d" % os.getpid())
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def spin(sec=0.15):
    t0 = time.time()
    while time.time() - t0 < sec:
        app.processEvents(); time.sleep(0.01)


def mouse(mv, kind, p, buttons):
    vp = mv.view.viewport()
    mv.eventFilter(vp, QMouseEvent(kind, QPointF(p), Qt.MouseButton.LeftButton, buttons, Qt.KeyboardModifier.NoModifier))


def click_at(mv, p):
    mouse(mv, QEvent.Type.MouseButtonPress, p, Qt.MouseButton.LeftButton); spin(0.05)
    mouse(mv, QEvent.Type.MouseButtonRelease, p, Qt.MouseButton.NoButton); spin(0.05)


def dbl_at(mv, p):
    click_at(mv, p)
    mouse(mv, QEvent.Type.MouseButtonDblClick, p, Qt.MouseButton.LeftButton); spin(0.05)
    mouse(mv, QEvent.Type.MouseButtonRelease, p, Qt.MouseButton.NoButton); spin(0.1)


def new_box(mv, nx, ny, text):
    mv._draw_kind = "text"; mv._apply_tool(); spin(0.05)
    click_at(mv, mv._norm_to_view(nx, ny, mv._page_view_rect()))
    QTest.keyClicks(mv._text_editor, text); spin(0.1)
    mv._commit_text_editor(); spin(0.05)
    return len(mv._page_strokes) - 1


def box_center(mv, i):
    st = mv._page_strokes[i]
    cx, cy, _hw, _hh, _r = mv._shape_geom(st, mv._page_view_rect())
    from PyQt6.QtCore import QPoint
    return QPoint(int(cx), int(cy))


def check_text_edit(mv, tag):
    """B·C·E 공통 — 개체 선택에서 글상자를 두 번 눌러 고치고, 바깥 누름·Esc 로 돌아온다."""
    i = new_box(mv, 0.30, 0.30, "ABC")
    n = len(mv._page_strokes)
    mv._draw_select_btn.click(); spin(0.05)
    chk(mv._draw_kind == "select", tag + " 준비 — 개체 선택 단추")
    dbl_at(mv, box_center(mv, i))
    chk(mv._text_editor is not None and mv._text_edit_idx == i and mv._draw_kind == "text",
        tag + " 두 번 누르면 그 글상자 글 고치기", "%s %s %s" % (mv._text_editor, mv._text_edit_idx, mv._draw_kind))
    if mv._text_editor is not None:
        QTest.keyClicks(mv._text_editor, "D"); spin(0.05)
    pr = mv._page_view_rect()
    click_at(mv, mv._norm_to_view(0.8, 0.85, pr))      # 바깥
    chk(mv._draw_kind == "select" and mv._text_editor is None, tag + " 바깥 누름 = 개체 선택으로", str(mv._draw_kind))
    chk(len(mv._page_strokes) == n and mv._page_strokes[i].get("text") == "ABCD",
        tag + " 고친 글이 들어가고 새 글상자는 없다", "%d→%d %r" % (n, len(mv._page_strokes), mv._page_strokes[i].get("text")))
    return i


root = Path(tempfile.mkdtemp(prefix="deco_dbl_"))
try:
    folder = root / "f"; folder.mkdir()
    pdf = folder / "꾸미기.pdf"
    d = fitz.open(); d.new_page(width=595, height=842).insert_text((72, 100), "PAGE1"); d.save(str(pdf)); d.close()
    from PIL import Image
    Image.new("RGB", (1200, 900), (250, 250, 250)).save(folder / "사진.jpg")

    seen = []
    import viewer.widgets.line_text_settings_dialog as ltd
    ltd.LineTextSettingsDialog.exec = lambda dlg: (seen.append(dlg._tabs.currentIndex() == dlg._text_tab_index and "text" or "line"), 0)[1]

    from viewer.app import MainWindow
    mw = MainWindow(); mw._skip_save_on_close = True
    mw._confirm_close_edit = lambda: True
    mw._confirm_edit_save = lambda switching=False: "discard"      # 편집 변경 확인 창 — 되돌리기(이 검사는 저장을 보지 않는다)
    mw.resize(1200, 900); mw.show(); spin(0.3)
    mw._prefs.setdefault("picture", {})["view_kind"] = "mixed"
    mw._photo_apply_view_kind()
    mw.open_folder(str(folder)); spin(0.6)
    mw.open_pdfs([str(pdf)]); spin(0.8)
    mv = mw.main_view
    mv.go_to_page(0); spin(0.2)
    mw.bookmark_tree.btn_edit.setChecked(True); spin(0.3)

    # A
    tacts = [a for a in mv._text_menu.actions() if not a.isSeparator()]
    sacts = [a for a in mv._shape_menu.actions() if not a.isSeparator()]
    chk(tacts and tacts[-1].text() == "글쓰기 입력 설정", "A 글쓰기 ▾ 끝 '글쓰기 입력 설정'", str([a.text() for a in tacts]))
    chk(sacts and sacts[-1].text() == "도형 입력 설정", "A 도형 ▾ 끝 '도형 입력 설정'", str([a.text() for a in sacts]))
    tacts[-1].trigger(); spin(0.1)
    sacts[-1].trigger(); spin(0.1)
    chk(seen == ["text", "line"], "A 누르면 입력 설정 창 — 글쓰기 탭·선긋기 탭", str(seen))
    mv.set_text_styles(mv._text_styles); spin(0.05)               # 스타일을 다시 넣어도(목록을 다시 만듦) 끝 항목은 하나
    tacts = [a.text() for a in mv._text_menu.actions() if not a.isSeparator()]
    chk(tacts.count("글쓰기 입력 설정") == 1, "A 목록을 다시 만들어도 한 번만", str(tacts))

    # B
    i = check_text_edit(mv, "B")

    # C — Esc
    dbl_at(mv, box_center(mv, i))
    ed = mv._text_editor
    chk(ed is not None, "C 다시 두 번 누르면 글 고치기")
    if ed is not None:
        mv.eventFilter(ed, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)); spin(0.05)
    chk(mv._draw_kind == "select" and mv._text_editor is None, "C Esc = 개체 선택으로", str(mv._draw_kind))

    # D — 도형
    mv._page_strokes.append({"shape": "rect", "rect": [0.50, 0.50, 0.70, 0.60], "color": "#ff0000", "width": 3,
                             "alpha": 100, "fill": "none", "rot": 0.0})
    mv._save_page_strokes(); spin(0.05)
    si = len(mv._page_strokes) - 1
    n = len(mv._page_strokes)
    pr = mv._page_view_rect()
    edge = mv._norm_to_view(0.50, 0.55, pr)                      # 왼쪽 변(채움 없음 — 변을 눌러야 닿는다)
    dbl_at(mv, edge)
    chk(mv._draw_kind == "shape" and mv._stroke_selected == si, "D 도형을 두 번 누르면 도형 편집(그 도형 고름)",
        "%s %s" % (mv._draw_kind, mv._stroke_selected))
    hp = mv._shape_handle_points(mv._page_strokes[si], pr)
    br = hp["br"]
    w0 = mv._page_strokes[si]["rect"][2] - mv._page_strokes[si]["rect"][0]
    mouse(mv, QEvent.Type.MouseButtonPress, br, Qt.MouseButton.LeftButton); spin(0.05)
    for k in range(1, 6):
        mouse(mv, QEvent.Type.MouseMove, br + type(br)(12 * k, 6 * k), Qt.MouseButton.LeftButton); spin(0.02)
    mouse(mv, QEvent.Type.MouseButtonRelease, br + type(br)(60, 30), Qt.MouseButton.NoButton); spin(0.05)
    rc = mv._page_strokes[si]["rect"]
    chk(abs(rc[2] - rc[0]) > w0 + 0.02, "D 모서리 손잡이를 끌면 커진다", "%.3f → %.3f" % (w0, abs(rc[2] - rc[0])))
    click_at(mv, mv._norm_to_view(0.15, 0.85, pr))
    chk(mv._draw_kind == "select" and len(mv._page_strokes) == n, "D 바깥 누름 = 개체 선택으로(새 도형 없음)",
        "%s %d→%d" % (mv._draw_kind, n, len(mv._page_strokes)))

    # E — 사진 모드
    mw.bookmark_tree.btn_edit.setChecked(False); spin(0.2)
    mw._set_photo_mode(True); spin(0.5)
    mw._on_bookmark_activated(str(folder / "사진.jpg"), 0); spin(0.8)
    mv = mw.main_view
    chk(getattr(mv._doc, "is_photo", False), "E 준비 — 사진 본문")
    mw.bookmark_tree.btn_edit.setChecked(True); spin(0.3)
    check_text_edit(mv, "E")
    mw.close(); spin(0.2)
except Exception:
    import traceback
    traceback.print_exc()
    fails.append("예외")
finally:
    shutil.rmtree(str(root), ignore_errors=True)

print("\n=== " + ("ALL PASS" if not fails else "FAILURE (%d)" % len(fails)) + " ===")
for m in fails:
    print(" -", m)
sys.stdout.flush()
os._exit(1 if fails else 0)
