# -*- coding: utf-8 -*-
"""PDF 지우기도 사진과 같은 길 (책갈피창·저장 SOT §4.7.17.1, 261117-6 — 사진 보기 SOT §4.25.1 을 PDF 로).

실제 MainWindow 로(오프스크린, 실제 설정 폴더를 쓰지 않는다 — 검사 작성 SOT §14.7.2 의 3). 휴지통 함수는 send2trash(Windows) 흉내 —
누가 파일을 열고 있으면 `OLE error 0x80270027` 로 거부하고, 아니면 검사 폴더로 옮긴다(사용자 휴지통에 보내지 않는다).
잠금은 실제 파일 핸들(Python open — 지우기 공유 없음, 다른 PDF 뷰어처럼). 지우기는 책갈피창에서 실제 Del 키.
A. 본문이 연 PDF + 잠깐(0.6초) 다른 프로그램이 잡은 PDF — 본문 파일은 놓고, 기다렸다 다시 해 지운다(안내 창 없음), 본문은 비운다
B. 끝내 잡힌 PDF(본문에 열림) + 풀린 PDF — 풀린 것만 지우고, 잡힌 것은 목록에 남고 본문에 다시 열린다, 창 하나로 이름·까닭(OLE 문자열 없음)
D. 휴지통 보내기는 메인 스레드에서 하지 않는다
(수정 전 코드: 메인에서 한 번만 시도·오류 원문 그대로 — A·B·D 실패)
"""
import os, sys, tempfile, shutil, time, threading
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2 의 3
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtTest import QTest
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_pdf_delete_fail_%d" % os.getpid())
import modal_guard
modal_guard.install(label=lambda: "PDF 지우기 실패", echo=False)
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

tmp = Path(tempfile.mkdtemp(prefix="polypdf_pdf_delfail_"))
trash = Path(tempfile.mkdtemp(prefix="polypdf_pdf_delfail_trash_"))
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
    import fitz
    for i in range(1, 6):
        d = fitz.open()
        for k in range(3):
            d.new_page().insert_text((72, 72), "PDF %d-%d" % (i, k))
        d.save(str(tmp / ("%d.pdf" % i))); d.close()
    P = lambda n: str(tmp / n)
    import test_fixtures as _TFX; _TFX.autotag_off()
    import viewer.widgets.bookmark_tree as _btm
    _btm._trash_fn = lambda: fake_send2trash

    from viewer.app import MainWindow
    mw = MainWindow(); mw._skip_save_on_close = True
    mw.resize(1200, 800); mw.show(); pump()
    bt = mw.bookmark_tree
    mw.open_folder(tmp)
    chk(pump(lambda: sum(1 for _ in bt._iter_file_nodes()) == 5), "준비 — PDF 5개 목록")
    bt.set_sort_mode(bt.SORT_NAME); pump()
    names = lambda: sorted(Path(str(it.data(0, bt.DATA_FILE))).name for it in bt._iter_file_nodes())
    node = lambda n: next(it for it in bt._iter_file_nodes() if Path(str(it.data(0, bt.DATA_FILE))).name == n)
    cur = lambda: (lambda f: Path(str(f)).name if f else None)(mw.main_view.current_file())

    def del_rows(*ns):
        tree = bt.tree
        tree.clearSelection()
        tree.setCurrentItem(node(ns[0]))
        for n in ns:
            node(n).setSelected(True)
        tree.setFocus()
        QTest.keyClick(tree, Qt.Key.Key_Delete)

    # A — 본문이 연 2.pdf + 0.6초 잡힌 3.pdf
    mw._on_bookmark_activated(P("2.pdf"), 0); pump(lambda: cur() == "2.pdf", 5)
    chk(cur() == "2.pdf", "A 준비 — 본문에 2.pdf")
    fh = open(P("3.pdf"), "rb")
    threading.Timer(0.6, fh.close).start()
    warns.clear(); threads.clear()
    del_rows("2.pdf", "3.pdf"); pump(lambda: "3.pdf" not in names() and "2.pdf" not in names(), 6)
    chk(not Path(P("2.pdf")).exists() and (trash / "2.pdf").exists(), "A 본문이 연 PDF 를 놓고 지운다", str(warns))
    chk(not Path(P("3.pdf")).exists() and (trash / "3.pdf").exists(), "A 잠깐 잡힌 PDF — 기다렸다 다시 해 지운다", str(warns))
    chk(not warns, "A 안내 창 없음", str(warns))
    chk("2.pdf" not in names() and "3.pdf" not in names(), "A 책갈피창에서 빠진다", str(names()))
    chk(cur() != "2.pdf", "A 본문은 지운 파일을 보이지 않는다", str(cur()))

    # D
    chk(threads and not any(threads), "D 휴지통 보내기는 메인 스레드가 아니다", str(threads))

    # B — 본문이 연 4.pdf 를 다른 프로그램도 끝내 잡음 + 풀린 5.pdf
    mw._on_bookmark_activated(P("4.pdf"), 0); pump(lambda: cur() == "4.pdf", 5)
    held = open(P("4.pdf"), "rb")
    warns.clear()
    del_rows("4.pdf", "5.pdf"); pump(lambda: bool(warns), 10); pump(timeout=0.5)
    held.close()
    chk(not Path(P("5.pdf")).exists(), "B 풀린 PDF 는 지운다")
    chk(Path(P("4.pdf")).exists() and "4.pdf" in names() and "5.pdf" not in names(),
        "B 잡힌 PDF 는 목록에 남는다", str(names()))
    pump(lambda: cur() == "4.pdf", 5)
    chk(cur() == "4.pdf", "B 놓았던 본문 PDF 를 다시 연다", str(cur()))
    w = "\n".join(warns)
    chk(len(warns) == 1 and "4.pdf" in w and "다른 프로그램이 쓰고 있습니다" in w, "B 창 하나로 이름·까닭", w[:200])
    chk("OLE" not in w and "WinError" not in w and "0x8027" not in w, "B 셸 오류 문자열을 그대로 보이지 않는다", w[:200])
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
