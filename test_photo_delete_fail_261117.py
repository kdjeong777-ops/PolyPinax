# -*- coding: utf-8 -*-
"""사진 지우기 실패 처리 (사진 보기 SOT §4.25.1, 261117-4 사용자 보고 '썸네일로 사진 삭제 시 실패').

실제 MainWindow 로(오프스크린, 실제 설정 폴더·사진 색인을 쓰지 않는다 — 검사 작성 SOT §14.7.2 의 3).
휴지통 함수는 send2trash 의 Windows 동작을 흉내 내는 가짜 — 누가 파일을 열고 있으면 `OLE error 0x80270027`(winerror -2144927705)로
거부하고, 아니면 검사 폴더로 옮긴다(사용자 휴지통에 보내지 않는다). 잠금은 실제 파일 핸들(Python open — 지우기 공유 없음, PIL·색인과 같다).
A. 잠깐(0.6초) 잡힌 사진 — 썸네일 줄 Del 로 지우면 기다렸다 다시 해 지운다(안내 창 없음)
B. 끝내 잡힌 사진 + 풀린 사진을 함께 — 풀린 것만 지우고, 잡힌 것은 책갈피창·썸네일 줄·본문에 그대로, 창 하나로 이름·까닭(OLE 문자열 없음)
C. 지운 사진의 사진 정보 색인 행이 빠진다
D. 휴지통 보내기는 메인 스레드에서 하지 않는다
"""
import os, sys, tempfile, shutil, time, threading
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2 의 3
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtTest import QTest
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_photo_delete_fail_%d" % os.getpid())
import modal_guard
modal_guard.install(label=lambda: "사진 지우기 실패", echo=False)
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def pump(cond=None, timeout=15.0):
    t = time.monotonic()
    while time.monotonic() - t < timeout:
        app.processEvents()
        if cond is not None and cond():
            return True
        if cond is None and time.monotonic() - t > 0.3:
            return True
        time.sleep(0.01)
    return False


QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
warns = []
QMessageBox.warning = staticmethod(lambda *a, **k: (warns.append("%s|%s" % (a[1], a[2])), QMessageBox.StandardButton.Ok)[1])

tmp = Path(tempfile.mkdtemp(prefix="polypdf_photo_delfail_"))
trash = Path(tempfile.mkdtemp(prefix="polypdf_photo_delfail_trash_"))
threads = []


def fake_send2trash(p):
    """send2trash(Windows) 흉내 — 잡힌 파일은 셸 파일 작업처럼 OLE 오류, 아니면 휴지통(검사 폴더)으로."""
    threads.append(threading.current_thread() is threading.main_thread())
    try:
        os.rename(p, str(trash / Path(p).name))
    except OSError as e:
        if getattr(e, "winerror", None) == 32:
            raise OSError(22, "OLE error 0x80270027", p, -2144927705) from None
        raise


try:
    from PIL import Image
    for i in range(1, 7):
        Image.new("RGB", (300 + i, 200), (30 * i, 90, 160)).save(tmp / ("%d.jpg" % i), "JPEG")
    P = lambda n: str(tmp / n)
    import viewer.widgets.bookmark_tree as _btm
    _btm._trash_fn = lambda: fake_send2trash

    from viewer.app import MainWindow
    mw = MainWindow(); mw._skip_save_on_close = True
    mw.resize(1200, 800); mw.show(); pump()
    bt = mw.bookmark_tree
    mw._prefs.setdefault("picture", {})["view_kind"] = "mixed"
    mw._photo_apply_view_kind()
    msgs = []
    _show = mw.status.showMessage
    mw.status.showMessage = lambda t, *a: (msgs.append(t), _show(t, *a))[1]
    mw._set_photo_mode(True)
    mw.open_folder(tmp)
    chk(pump(lambda: sum(1 for _ in bt._iter_file_nodes()) == 6), "사진 6장 목록")
    bt.set_sort_mode(bt.SORT_NAME); pump()
    pump(lambda: any("사진 색인" in m for m in msgs), 20)          # 색인 훑기가 끝나야 C 의 행이 있다
    if not bt.is_edit_mode():
        bt.btn_edit.setChecked(True); pump()
    names = lambda: sorted(Path(str(it.data(0, bt.DATA_FILE))).name for it in bt._iter_file_nodes())
    strip = mw._photo_strip

    # A — 잠깐 잡힌 사진
    mw._on_bookmark_activated(P("2.jpg"), 0); pump(timeout=0.5)
    fh = open(P("2.jpg"), "rb")
    threading.Timer(0.6, fh.close).start()
    warns.clear(); threads.clear()
    strip.setFocus(); QTest.keyClick(strip, Qt.Key.Key_Delete); pump(timeout=1.5)
    chk(not Path(P("2.jpg")).exists() and (trash / "2.jpg").exists(), "A 잠깐 잡힌 사진 — 기다렸다 다시 해 지운다", str(warns))
    chk(not warns, "A 안내 창 없음", str(warns))
    chk("2.jpg" not in names(), "A 책갈피창에서 빠진다", str(names()))

    # D
    chk(threads and not any(threads), "D 휴지통 보내기는 메인 스레드가 아니다", str(threads))

    # C — 색인 행
    from viewer import photo_index
    def has_row(name):
        con = photo_index.connect_read()
        try:
            return con.execute("SELECT 1 FROM photos WHERE key=?", (os.path.normcase(os.path.abspath(P(name))),)).fetchone() is not None
        finally:
            con.close()
    chk(has_row("4.jpg"), "C 준비 — 4.jpg 색인 행이 있다")

    # B — 끝내 잡힌 사진(3) + 풀린 사진(4)
    mw._on_bookmark_activated(P("3.jpg"), 0); pump(timeout=0.5)
    held = open(P("3.jpg"), "rb")
    warns.clear()
    t0 = time.monotonic()
    mw._photo_delete([P("3.jpg"), P("4.jpg")]); pump(timeout=0.5)
    held.close()
    chk(not Path(P("4.jpg")).exists(), "B 풀린 사진은 지운다")
    chk(Path(P("3.jpg")).exists() and "3.jpg" in names() and any(Path(p).name == "3.jpg" for p in strip.paths()),
        "B 잡힌 사진은 책갈피창·썸네일 줄에 남는다", str(names()))
    cur = mw.main_view.current_file()
    chk(cur and Path(str(cur)).name == "3.jpg", "B 본문은 보던 사진 그대로", str(cur))
    w = "\n".join(warns)
    chk(len(warns) == 1 and "3.jpg" in w and "다른 프로그램이 쓰고 있습니다" in w, "B 창 하나로 이름·까닭", w[:200])
    chk("OLE" not in w and "WinError" not in w and "0x8027" not in w, "B 셸 오류 문자열을 그대로 보이지 않는다", w[:200])

    # C
    chk(not has_row("4.jpg") and has_row("3.jpg"), "C 지운 사진의 색인 행만 빠진다")
    mw.close(); pump()
except Exception:
    import traceback
    traceback.print_exc()
    fails.append("예외")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(trash, ignore_errors=True)

print()
print("ALL PASS" if not fails else "FAILURES: %d" % len(fails))
for m in fails:
    print(" -", m)
sys.stdout.flush()
os._exit(1 if fails else 0)
