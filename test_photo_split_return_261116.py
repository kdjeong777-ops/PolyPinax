# -*- coding: utf-8 -*-
"""2단 → 1단 → 2단이면 오른쪽 칸의 종류(PDF·PIX·스크린샷)와 파일·쪽을 되살린다 (사진 보기 SOT §4.47 '되돌아오기').

사용자 원문: '2단으로 있다, 1단으로 변경했다 2단으로 돌아왔을 경우 기존 모드와 선택했던 파일을 선택하여 열도록 수정해
(프로그램 종료하지 않고, 계속 사용시)'.
실제 MainWindow 로(오프스크린, 실제 설정 폴더를 쓰지 않는다 — 검사 작성 SOT §14.7.2 의 3). 단추·키는 실제 것으로.
A. PDF 모드 ▾ PIX 로 오른쪽 사진 p3 → 리본 `1단` → 리본 `2단` 본체 = 섞은 2단, 오른쪽 p3, 아래 사진 목록
B. 같은 것을 `Ctrl+1` → `Ctrl+2` 로
C. 종전 2단에서 오른쪽 나.pdf 3쪽 → `1단` → 사진 모드 갔다 오기 → `2단` = 오른쪽 나.pdf 3쪽
D. 스크린샷 컷 둘 중 둘째를 오른쪽에 → `1단` → `2단` = 아래 컷 목록·둘째 컷
E. 우클릭 '2단 보기'(`_on_split_view_requested`) 도 되살린다
F. 1단에서 ▾ 로 다른 종류를 고르면 고른 것(기억보다 고름이 먼저), 기억한 파일이 없어졌으면 종전 2단
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
QCoreApplication.setApplicationName("polypdf_split_return_%d" % os.getpid())
import modal_guard
modal_guard.install(label=lambda: "2단 되돌아오기")
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


tmp = Path(tempfile.mkdtemp(prefix="polypdf_split_return_"))
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
    mw = MainWindow(); mw._skip_save_on_close = True
    mw.resize(1400, 900); mw.show(); mw.activateWindow(); pump()
    mw._prefs.setdefault("picture", {})["view_kind"] = "mixed"
    mw._photo_apply_view_kind()
    top, bot = mw.bookmark_tree, mw.bookmark_tree_right

    mw._set_photo_mode(True); pump()
    mw.open_folder(pics); pump(lambda: len(mw._photo_tree_list()) == 3)
    mw._on_bookmark_activated(str(ph[0]), 0); pump()
    mw._set_photo_mode(False); pump()
    mw.open_folder(pdfs); pump(lambda: len(top.ordered_pdf_files() or []) == 2)
    mw._on_bookmark_activated(str(a_pdf), 1); pump(lambda: norm(mw._mv[0].current_file()) == norm(a_pdf))

    def ribbon_btn(key):
        act = mw._view_acts[key]
        bs = [b for b in mw.findChildren(QToolButton) if b.defaultAction() is act and b.isVisible()]
        return bs[0] if bs else None

    b1, b2 = ribbon_btn("single"), ribbon_btn("split")
    chk(b1 is not None and b2 is not None, "준비 — 리본 1단·2단 단추")

    def click(b):
        QTest.mouseClick(b, Qt.MouseButton.LeftButton, pos=QPoint(6, b.height() // 2)); pump()

    kinds = {a.objectName(): a for a in mw._view_acts["split"].menu().actions()}

    # A — 섞은 2단(PIX) 오른쪽 p3 → 1단 → 2단
    kinds["split_kind_pix"].trigger(); pump(lambda: len(mw._mix_list(1)) == 3)
    mw._on_bookmark_activated_right(str(ph[2]), 0); pump(lambda: norm(mw._mv[1].current_file()) == norm(ph[2]))
    chk(mw._mix_on_now() and norm(mw._mv[1].current_file()) == norm(ph[2]), "A 준비 — 섞은 2단 오른쪽 p3")
    click(b1)
    chk(not mw._split_on and not mw._mix_on_now(), "A 1단")
    click(b2); pump(lambda: norm(mw._mv[1].current_file()) == norm(ph[2]))
    chk(mw._split_on and mw._mix_on_now(), "A 2단 = 섞은 2단(PIX) 되살림", "split=%s mix=%s" % (mw._split_on, mw._mix_on_now()))
    chk(norm(mw._mv[1].current_file()) == norm(ph[2]), "A 오른쪽 = p3", str(mw._mv[1].current_file()))
    chk(bot._photo_on() and norm(mw._mv[0].current_file()) == norm(a_pdf), "A 아래 사진 목록·왼쪽 가.pdf 그대로")

    # B — 키로
    QTest.keyClick(mw, Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier); pump()
    chk(not mw._split_on, "B Ctrl+Shift+1 = 1단")
    QTest.keyClick(mw, Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    pump(lambda: norm(mw._mv[1].current_file()) == norm(ph[2]))
    chk(mw._split_on and mw._mix_on_now() and norm(mw._mv[1].current_file()) == norm(ph[2]),
        "B Ctrl+2 = 섞은 2단 p3", str(mw._mv[1].current_file()))

    # C — 종전 2단(PDF) 오른쪽 나.pdf 3쪽 → 1단 → 사진 모드 갔다 오기 → 2단
    kinds["split_kind_pdf"].trigger(); pump(lambda: not mw._mix_on_now())
    mw._on_bookmark_activated_right(str(b_pdf), 2); pump(lambda: norm(mw._mv[1].current_file()) == norm(b_pdf))
    pump(lambda: mw._mv[1].current_page() == 2)
    click(b1)
    mw._set_photo_mode(True); pump()
    mw._set_photo_mode(False); pump()
    pump(lambda: len(top.ordered_pdf_files() or []) == 2)
    click(b2); pump(lambda: norm(mw._mv[1].current_file()) == norm(b_pdf) and mw._mv[1].current_page() == 2)
    chk(mw._split_on and not mw._mix_on_now() and norm(mw._mv[1].current_file()) == norm(b_pdf)
        and mw._mv[1].current_page() == 2, "C 2단 = 오른쪽 나.pdf 3쪽",
        "%s p%s" % (mw._mv[1].current_file(), mw._mv[1].current_page()))

    # D — 스크린샷 컷 둘째
    cuts = []
    for i, c in enumerate(((250, 250, 0), (0, 250, 250))):
        cp = tmp / ("컷%d.png" % (i + 1))
        Image.new("RGB", (200, 120), c).save(cp)
        mw.shot_strip.add_item(str(cp), kind="image", label="컷%d" % (i + 1))
        cuts.append(str(cp))
    pump()
    i2 = mw.shot_strip.index_of_path(cuts[1])
    mw.shot_strip.activate_index(i2); pump(lambda: bot.in_shot_list())
    chk(bot.in_shot_list() and mw._current_shot_path == cuts[1], "D 준비 — 컷2 오른쪽·아래 컷 목록")
    mw.shot_strip.list.setCurrentRow(mw.shot_strip.index_of_path(cuts[0]))   # 띠의 고름은 컷1 로 옮겨 둔다
    click(b1)
    click(b2); pump(lambda: bot.in_shot_list())
    chk(mw._split_on and bot.in_shot_list() and mw.__dict__.get("_current_shot_path") == cuts[1],
        "D 2단 = 컷 목록·컷2", str(mw.__dict__.get("_current_shot_path")))

    # E — 우클릭 '2단 보기'
    kinds["split_kind_pix"].trigger(); pump(lambda: mw._mix_on_now())
    mw._on_bookmark_activated_right(str(ph[1]), 0); pump(lambda: norm(mw._mv[1].current_file()) == norm(ph[1]))
    click(b1)
    mw._on_split_view_requested(True, 0); pump(lambda: norm(mw._mv[1].current_file()) == norm(ph[1]))
    chk(mw._mix_on_now() and norm(mw._mv[1].current_file()) == norm(ph[1]), "E 우클릭 2단 보기 = 섞은 2단 p2",
        str(mw._mv[1].current_file()))

    # F — 1단에서 ▾ PDF 를 고르면 PDF(기억은 PIX), 기억한 파일이 없어졌으면 종전 2단
    click(b1)
    kinds["split_kind_pdf"].trigger(); pump(lambda: mw._mv[1].current_file() is not None)
    chk(mw._split_on and not mw._mix_on_now() and str(mw._mv[1].current_file() or "").lower().endswith(".pdf"),
        "F ▾ PDF = 고른 종류", str(mw._mv[1].current_file()))
    kinds["split_kind_pix"].trigger(); pump(lambda: mw._mix_on_now())
    mw._on_bookmark_activated_right(str(ph[2]), 0); pump(lambda: norm(mw._mv[1].current_file()) == norm(ph[2]))
    click(b1)
    os.remove(ph[2])
    click(b2); pump()
    chk(mw._split_on and not mw._mix_on_now(), "F 기억한 사진이 없으면 종전 2단")
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
