# -*- coding: utf-8 -*-
"""261128-16(책갈피창·저장 SOT §4.9.5, 사용자 지시·결정): 새 창으로 열기 — [새 창]·Shift+[폴더 열기]·Shift+[파일 열기].

종전: [새 창] 은 인자 없이 하나 더 띄웠고(보던 파일과 무관), 폴더·파일 열기는 Shift 를 보지 않았다. 수정 전 코드로 A·B·C 가 실패한다.
새 프로세스는 띄우지 않는다 — `QProcess.startDetached` 를 가로채 넘길 명령줄만 본다. 누르기는 실제 리본 단추(QTest 마우스, Shift 포함).

A. [새 창] → `--new-window --folder <폴더> --page <쪽> --fit <맞춤> <파일>` (같은 쪽·맞춤·같은 폴더 목록), 직접 배율이면 `--scale`
B. Shift+[폴더 열기] → 고른 폴더를 새 창에(이 창 폴더 그대로) · Shift 없이 누르면 이 창에서(띄우지 않음)
C. Shift+[파일 열기] → 고른 PDF 를 새 창에(이 창 파일 그대로)
D. 저장하지 않은 편집이 있으면 상태줄 알림(묻는 창 없음)
E. 2단이면 활성 창(아래 창)의 파일·쪽
F. 사진 모드 [새 창] → `--photo <사진>`, Shift+[폴더 열기] → `--photo --folder`
G. `parse` 왕복·`--new-window` 없으면 그대로
H. `_nw_open`(새 창 쪽) — 폴더 목록·그 파일·쪽·맞춤을 연다
I. 띄우기 실패면 Shift+열기는 이 창에서 연다
J·K. (261128-23) 생성한 PDF 새 창·가상 프린터 새 창도 같은 `launch` 로 `--new-window <파일>` — 종전 코드로 실패
L. 지금 파일이 폴더 목록 밖이면 `--folder` 없이 그 파일만
"""
import os, sys, faulthandler, tempfile, shutil
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(240, exit=True)

from pathlib import Path
from PyQt6.QtCore import QStandardPaths, Qt, QProcess
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtGui import QImage, QColor
from PyQt6.QtWidgets import QApplication, QFileDialog, QToolButton
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
from PyQt6.QtCore import QCoreApplication as _QCA
_QCA.setApplicationName("polypdf_new_window_%d" % os.getpid())     # 검사 작성 SOT §14.7.2 의 3
import modal_guard
modal_guard.install(label=lambda: "새 창", echo=False)              # §14.7.2 의 6
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


launched = []
_ok = {"v": True}
QProcess.startDetached = staticmethod(lambda exe, args=None, *a, **k: (launched.append(list(args or [])), (_ok["v"], 1))[1])
popened = []                                                        # K — 종전 가상 프린터 새 창은 Popen(그 모듈 안에서만 가로챔)
_dlg = {"dir": "", "file": ""}
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: _dlg["dir"])
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (_dlg["file"], ""))


def wait_until(cond, ms=8000):
    for _ in range(ms // 20):
        if cond():
            return True
        QTest.qWait(20)
    return cond()


def file_btn(mw, act):
    mw._ribbon.select("file"); QTest.qWait(30)
    for b in mw._ribbon.row("file").findChildren(QToolButton):
        if b.defaultAction() is act and b.isVisible():
            return b
    return None


def press(mw, act, shift=False):
    """실제 리본 단추를 마우스로 누른다(Shift 면 Shift 를 누른 채) — 띄운 명령줄(없으면 None)."""
    n = len(launched)
    b = file_btn(mw, act)
    if b is None:
        chk(False, "리본 단추 찾기", act.text())
        return None
    QTest.qWait(150)                         # 모드 바꿈 뒤 리본 다시 놓기가 끝나게
    QTest.mouseClick(b, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier)
    wait_until(lambda: len(launched) > n, 600)
    return launched[-1] if len(launched) > n else None


def opt(args, name):
    return args[args.index(name) + 1] if args and name in args else None


root = Path(tempfile.mkdtemp(prefix="polypdf_newwin_"))
try:
    import test_fixtures as _fx
    from viewer.app import MainWindow
    from viewer import new_window
    d1 = root / "폴더1"; d1.mkdir(); d2 = root / "폴더2"; d2.mkdir(); d3 = root / "사진"; d3.mkdir()
    f1 = d1 / "가.pdf"; shutil.copy(_fx.text_pdf(), f1)
    f1b = d1 / "나.pdf"; shutil.copy(_fx.text_pdf(), f1b)
    f2 = d2 / "다.pdf"; shutil.copy(_fx.text_pdf(), f2)
    img = QImage(64, 48, QImage.Format.Format_RGB32); img.fill(QColor(200, 60, 60))
    jp = d3 / "사진1.jpg"; img.save(str(jp))

    # G parse
    a = new_window.build_args(file=str(f1), folder=str(d1), page=3, fit="width", scale=None)
    o, rest = new_window.parse(a)
    chk(o is not None and o["folder"] == str(d1) and o["page"] == 3 and o["fit"] == "width" and rest == [str(f1)],
        "G parse 왕복", (o, rest))
    chk(new_window.parse([str(f1)]) == (None, [str(f1)]), "G --new-window 없으면 그대로")
    chk(new_window.build_args() == [], "G 파일·폴더 없으면 빈 인자(종전 새 창)")

    mw = MainWindow()
    mw.resize(1600, 900); mw.show(); QTest.qWait(100)
    mw.open_folder(d1); QTest.qWait(100)
    mw._load_main(__import__("viewer.app", fromlist=["HistoryItem"]).HistoryItem(str(f1), 2, "", "bookmark"))
    wait_until(lambda: mw.main_view.current_file() and mw.main_view.current_page() == 2)
    mw.main_view.set_fit_mode("width"); QTest.qWait(50)

    # A
    args = press(mw, mw._sc_act_new_window)
    chk(bool(args) and new_window.FLAG in args, "A [새 창] → --new-window", args)
    chk(bool(args) and args[-1] == str(f1), "A 지금 보는 파일", args)
    chk(opt(args, "--page") == "2", "A 같은 쪽", args)
    chk(opt(args, "--fit") == "width", "A 같은 맞춤", args)
    chk(bool(opt(args, "--folder")) and Path(opt(args, "--folder")).resolve() == d1.resolve(), "A 같은 폴더 목록", args)
    mw.main_view._zoom_by(1.5); QTest.qWait(50)
    args = press(mw, mw._sc_act_new_window)
    chk(opt(args, "--fit") == "none" and opt(args, "--scale") is not None
        and abs(float(opt(args, "--scale")) - mw.main_view._zoom) < 0.01, "A 직접 배율이면 그 배율", args)
    mw.main_view.set_fit_mode("width"); QTest.qWait(30)

    # B
    _dlg["dir"] = str(d2)
    args = press(mw, mw._sc_act_open, shift=True)
    chk(bool(args) and new_window.FLAG in args and opt(args, "--folder") == str(d2) and "--photo" not in args,
        "B Shift+폴더 열기 → 새 창에 그 폴더", args)
    chk(mw.main_view.current_file() and Path(mw.main_view.current_file()) == f1, "B 이 창은 그대로")
    args = press(mw, mw._sc_act_open, shift=False)
    chk(args is None, "B Shift 없이는 띄우지 않는다", args)
    wait_until(lambda: mw.bookmark_tree.view_base() and Path(mw.bookmark_tree.view_base()).resolve() == d2.resolve(), 3000)
    chk(mw.bookmark_tree.view_base() and Path(mw.bookmark_tree.view_base()).resolve() == d2.resolve(),
        "B Shift 없이는 이 창에서 연다")

    # C
    mw.open_folder(d1); QTest.qWait(60)
    mw.open_pdf(f1); wait_until(lambda: mw.main_view.current_file() and Path(mw.main_view.current_file()) == f1)
    _dlg["file"] = str(f2)
    args = press(mw, mw._sc_act_open_file, shift=True)
    chk(bool(args) and new_window.FLAG in args and args[-1] == str(f2), "C Shift+파일 열기 → 새 창에 그 PDF", args)
    QTest.qWait(100)
    chk(Path(mw.main_view.current_file()) == f1, "C 이 창 파일은 그대로", mw.main_view.current_file())

    # D
    mw.status.clearMessage()
    mw._in_edit = lambda: True
    mw._edit_dirty = True
    press(mw, mw._sc_act_new_window)
    chk("저장하지 않은 편집" in mw.status.currentMessage(), "D 저장 안 한 편집 → 상태줄 알림", mw.status.currentMessage())
    del mw._in_edit
    mw._edit_dirty = False

    # I 띄우기 실패 → 이 창에서
    _ok["v"] = False
    _dlg["file"] = str(f1b)
    press(mw, mw._sc_act_open_file, shift=True)
    wait_until(lambda: mw.main_view.current_file() and Path(mw.main_view.current_file()) == f1b, 4000)
    chk(mw.main_view.current_file() and Path(mw.main_view.current_file()) == f1b, "I 띄우기 실패면 이 창에서 연다",
        mw.main_view.current_file())
    _ok["v"] = True

    # E 2단 — 아래(활성) 창
    mw.open_pdf(f1); wait_until(lambda: Path(mw.main_view.current_file() or ".") == f1)
    mw._vm_split(); QTest.qWait(100)
    mw._set_active_pane(1); QTest.qWait(30)
    mw.open_pdf(f2, page=4)
    wait_until(lambda: mw.main_view.current_file() and Path(mw.main_view.current_file()) == f2
               and mw.main_view.current_page() == 4)
    args = press(mw, mw._sc_act_new_window)
    chk(bool(args) and args[-1] == str(f2) and opt(args, "--page") == "4", "E 2단이면 활성 창의 파일·쪽", args)
    mw._vm_single(); QTest.qWait(60)

    # H 새 창 쪽 — 폴더 목록·그 파일·쪽·맞춤
    mw.open_folder(d2); QTest.qWait(60)
    o, rest = new_window.parse(new_window.build_args(file=str(f1b), folder=str(d1), page=5, fit="width"))
    mw._nw_open(o, rest, [])
    wait_until(lambda: mw.main_view.current_file() and Path(mw.main_view.current_file()) == f1b
               and mw.main_view.current_page() == 5)
    chk(Path(mw.main_view.current_file() or ".") == f1b and mw.main_view.current_page() == 5, "H 그 파일·그 쪽",
        (mw.main_view.current_file(), mw.main_view.current_page()))
    chk(mw.bookmark_tree.view_base() and Path(mw.bookmark_tree.view_base()).resolve() == d1.resolve(), "H 그 폴더 목록")
    wait_until(lambda: mw.main_view._fit_mode == "width", 2000)
    chk(mw.main_view._fit_mode == "width", "H 그 맞춤", mw.main_view._fit_mode)

    # F 사진 모드
    if mw._photo_enabled():
        mw._photo_open_arg(str(jp))
        wait_until(lambda: mw._photo_mode and mw.main_view.current_file()
                   and Path(mw.main_view.current_file()) == jp, 5000)
        args = press(mw, mw._sc_act_new_window)
        chk(bool(args) and "--photo" in args and args[-1] == str(jp), "F 사진 모드 [새 창] → 사진 모드 새 창에 그 사진", args)
        _dlg["dir"] = str(d3)
        args = press(mw, mw._sc_act_open, shift=True)
        chk(bool(args) and "--photo" in args and opt(args, "--folder") == str(d3), "F 사진 모드 Shift+폴더 열기 → 사진 모드 새 창", args)
    else:
        chk(False, "F 사진 모드를 쓸 수 있어야 한다(기본 혼용)")

    # J·K 다른 새 창 길도 --new-window(261128-23) — 종전: 생성한 PDF 는 표시 없이, 가상 프린터는 따로 Popen
    del launched[:]
    mw._open_pdf_new_window(str(f2))
    chk(bool(launched) and new_window.FLAG in launched[-1] and launched[-1][-1] == str(f2),
        "J 생성한 PDF 새 창 → --new-window <파일>", launched)
    del launched[:]
    import types, viewer.vprinter_controller as _vpc
    _real_sp = getattr(_vpc, "subprocess", None)
    _vpc.subprocess = types.SimpleNamespace(Popen=lambda cmd, *a, **k: popened.append(list(cmd)))
    try:
        mw._vprinter_new_window(str(f2))
    finally:
        if _real_sp is not None:
            _vpc.subprocess = _real_sp
    chk(bool(launched) and new_window.FLAG in launched[-1] and launched[-1][-1] == str(f2),
        "K 가상 프린터 새 창 → 같은 launch·--new-window <파일>", (launched, popened))
    chk(not popened, "K 따로 Popen 하지 않는다", popened)

    # L 목록 밖 파일이면 폴더 없이 그 파일만(§4.9.5)
    mw.open_pdf(f2); wait_until(lambda: Path(mw.main_view.current_file() or ".") == f2)
    mw.bookmark_tree.view_base = lambda: str(d1)                    # 목록은 폴더1, 본문은 폴더2 파일(검색 결과로 연 꼴)
    args = press(mw, mw._sc_act_new_window)
    del mw.bookmark_tree.view_base
    chk(bool(args) and args[-1] == str(f2) and opt(args, "--folder") is None, "L 목록 밖 파일 → 폴더 없이", args)
    mw.close()
finally:
    shutil.rmtree(root, ignore_errors=True)

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
sys.stdout.flush()
os._exit(1 if fails else 0)
