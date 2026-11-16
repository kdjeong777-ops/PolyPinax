# -*- coding: utf-8 -*-
"""261116-29 섞은 PDF 칸 흐리게 막기 (사진 보기 SOT §4.47 원칙·D23) — 사진 모드 ▾ PDF 의 PDF 칸이 활성이면 그 PDF 를 고치는 일을 막는다.

실제 MainWindow 로(오프스크린, 실제 설정 폴더를 쓰지 않는다 — 검사 작성 SOT §14.7.2 의 3). 칸 바꾸기는 실제 클릭, Del 은 실제 키.
A. 사진 모드·편집 모드에서 ▾ PDF → 섞은 PDF 칸 활성: 쪽 썸네일 편집에서 빠지고, 텍스트 창 `PDF 에 반영` 흐리게
B. 크롭 요청(쪽 썸네일 '크롭' 신호) → 크롭 창이 뜨지 않고 상태 줄 안내
C. 본문 Del(실제 키) → 쪽이 지워지지 않는다
D. `PDF 에 반영` 을 불러도 안내만
E. 왼쪽 사진 칸을 누르면 풀리고(쪽 썸네일 편집 모드 되살림), 오른쪽을 다시 누르면 다시 막힘
F. 섞은 2단을 놓으면(▾ PIX = 같은 종류) 풀린다
G. PDF 모드 1단에서 PDF 를 열면 `PDF 에 반영` 이 켜진다(사진 텍스트 창이 끈 뒤 되살리는 곳이 없던 것, 같은 함수)
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
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_mix_lock_%d" % os.getpid())
import modal_guard
modal_guard.install(label=lambda: "섞은 PDF 칸 막기")
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


tmp = Path(tempfile.mkdtemp(prefix="polypdf_mix_lock_"))
try:
    from PIL import Image
    pdfs, pics = tmp / "문서", tmp / "사진"
    pdfs.mkdir(); pics.mkdir()
    a_pdf = pdfs / "가.pdf"
    shutil.copy(test_fixtures.text_pdf(), a_pdf)
    p1 = pics / "p1.jpg"
    Image.new("RGB", (640, 480), (200, 60, 60)).save(p1)

    import viewer.widgets.crop_dialog as cd
    crop_opened = []
    cd.CropDialog.exec = lambda dlg: (crop_opened.append(1), 0)[1]

    from viewer.app import MainWindow
    mw = MainWindow(); mw._skip_save_on_close = True
    mw.resize(1400, 900); mw.show(); pump()
    mw._prefs.setdefault("picture", {})["view_kind"] = "mixed"
    mw._prefs["open_edit_mode"] = True
    mw._photo_apply_view_kind()
    mw._confirm_edit_save = lambda switching=False: "discard"
    msgs = []
    _show = mw.status.showMessage
    mw.status.showMessage = lambda t, *a: (msgs.append(t), _show(t, *a))[1]
    top = mw.bookmark_tree

    # PDF 모드의 기억 — 가.pdf, 그 뒤 사진 모드에서 p1
    mw.open_folder(pdfs); pump(lambda: len(top.ordered_pdf_files() or []) == 1)
    mw._on_bookmark_activated(str(a_pdf), 0); pump(lambda: norm(mw._mv[0].current_file()) == norm(a_pdf))
    mw._set_photo_mode(True); pump()
    mw.open_folder(pics); pump(lambda: len(mw._photo_tree_list()) == 1)
    mw._on_bookmark_activated(str(p1), 0); pump(lambda: norm(mw._mv[0].current_file()) == norm(p1))
    if not top.is_edit_mode():
        top.btn_edit.setChecked(True); pump()
    chk(mw._photo_mode and top.is_edit_mode(), "준비 — 사진 모드·편집 모드")

    # A — ▾ PDF
    kinds = {a.objectName(): a for a in mw._view_acts["split"].menu().actions()}
    kinds["split_kind_pdf"].trigger(); pump(lambda: norm(mw._mv[1].current_file()) == norm(a_pdf))
    mv1 = mw._mv[1]
    pump(lambda: mw.page_thumbs.list.count() > 0, 5)
    chk(mw._mix_on_now() and mw._active_pane == 1 and norm(mv1.current_file()) == norm(a_pdf), "A 섞은 PDF 칸 활성(가.pdf)")
    chk(not mw.page_thumbs._edit_mode, "A 쪽 썸네일은 편집에서 빠진다(편집 모드여도)")
    chk(not mw.text_panel.btn_apply.isEnabled(), "A 텍스트 창 'PDF 에 반영' 흐리게")

    # B — 크롭
    n0 = len(msgs)
    mw.page_thumbs.cropPagesRequested.emit([0]); pump()
    chk(not crop_opened, "B 쪽 썸네일 '크롭' — 크롭 창 안 뜸", str(crop_opened))
    chk(any("섞은 PDF 칸은 보기만" in m for m in msgs[n0:]), "B 상태 줄 안내", str(msgs[n0:])[:120])

    # C — Del
    seq0 = list(mw.page_thumbs.current_page_sequence())
    mv1.view.setFocus(); QTest.keyClick(mv1.view, Qt.Key.Key_Delete); pump()
    chk(mw.page_thumbs.current_page_sequence() == seq0 and len(seq0) > 1, "C 본문 Del — 쪽이 지워지지 않는다",
        "%s → %s" % (seq0, mw.page_thumbs.current_page_sequence()))

    # D — PDF 에 반영
    n0 = len(msgs)
    mw._on_text_apply_pdf(); pump()
    chk(any("섞은 PDF 칸은 보기만" in m for m in msgs[n0:]), "D 'PDF 에 반영' — 안내만", str(msgs[n0:])[:120])

    # E — 칸 바꾸기
    QTest.mouseClick(mw._mv[0].view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(40, 40)); pump()
    chk(mw._active_pane == 0 and mw.page_thumbs._edit_mode, "E 왼쪽 사진 칸 — 풀림(쪽 썸네일 편집 모드 되살림)")
    QTest.mouseClick(mv1.view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(40, 40)); pump()
    chk(mw._active_pane == 1 and not mw.page_thumbs._edit_mode and not mw.text_panel.btn_apply.isEnabled(), "E 오른쪽 다시 — 막힘")

    # F — 놓기
    kinds["split_kind_pix"].trigger(); pump(lambda: not mw._mix_on_now())
    chk(not mw._mix_on_now() and mw.page_thumbs._edit_mode, "F 섞은 2단을 놓으면 풀림")

    # G — PDF 모드에서 반영 단추
    mw.act_split.setChecked(False); pump()
    mw._set_photo_mode(False); pump()
    mw._on_bookmark_activated(str(a_pdf), 0); pump(lambda: norm(mw._mv[0].current_file()) == norm(a_pdf))
    mw.search_tabs.setCurrentWidget(mw.text_panel); pump()
    mw._reload_text_panel(); pump()
    chk(mw.text_panel.btn_apply.isEnabled(), "G PDF 모드 1단 PDF — 'PDF 에 반영' 켜짐")
    mw.close(); pump()
except Exception:
    import traceback
    traceback.print_exc()
    fails.append("예외")
finally:
    shutil.rmtree(str(tmp), ignore_errors=True)

print("\n=== " + ("ALL PASS" if not fails else "FAILURE (%d)" % len(fails)) + " ===")
for m in fails:
    print(" -", m)
sys.stdout.flush()
os._exit(1 if fails else 0)
