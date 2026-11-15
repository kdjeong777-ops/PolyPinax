# -*- coding: utf-8 -*-
"""261115-20: 새 분할기의 bookmarks.json(뷰어보다 큰 version)은 쓰지 않는다 (책갈피창·저장 SOT §4.7.25, 마스터 §8.1).

A. version 2 폴더를 실제 open_folder 로 열면 json 모드가 아니고 PDF 목록(평탄)으로 보이며 업데이트 알림이 뜬다
B. 그 폴더의 검색 '책갈피 순' 은 bookmarks.json 을 쓰지 않는다(빈 순서)
C. version 1·version 없음은 종전대로 json 트리·검색 순서
(수정 전 코드: A·알림·B 3건 실패)
"""
import os, sys, json, tempfile, shutil, faulthandler
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(240, exit=True)
from pathlib import Path

import fitz
from PyQt6.QtCore import QStandardPaths
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
from PyQt6.QtCore import QCoreApplication
QCoreApplication.setApplicationName("polypdf_bmjsonver_%d" % os.getpid())   # 검사 작성 SOT §14.7.2 의 3
import modal_guard
modal_guard.install(label=lambda: "bookmarks.json version", echo=False)      # §14.7.2 의 6
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def spin(n=10, ms=20):
    for _ in range(n):
        app.processEvents(); QTest.qWait(ms)


def make_split(folder: Path, version):
    folder.mkdir()
    for nm in ("ch1", "ch2"):
        d = fitz.open(); d.new_page().insert_text((72, 72), nm); d.save(str(folder / f"{nm}.pdf")); d.close()
    data = {"source_pdf": "src.pdf", "total_pages": 2, "generated_at": "2026-11-15T00:00:00",
            "bookmarks": [{"title": "제1장", "page": 1, "page_start": 1, "page_end": 2, "file": None, "children": [
                {"title": "1.1", "page": 1, "page_start": 1, "page_end": 1, "file": "ch1.pdf", "children": []},
                {"title": "1.2", "page": 2, "page_start": 2, "page_end": 2, "file": "ch2.pdf", "children": []}]}]}
    if version is not None:
        data["version"] = version
    (folder / "bookmarks.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


errs = []
sys.excepthook = lambda t, v, tb: errs.append(f"{t.__name__}: {v}")
root = Path(tempfile.mkdtemp(prefix="polypdf_bmjsonver_"))
try:
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    import test_fixtures as _TFX; _TFX.autotag_off()
    from viewer.app import MainWindow
    mw = MainWindow(); mw.resize(1200, 800); mw.show(); app.processEvents()
    bt = mw.bookmark_tree
    notices = []
    bt.noticeRequested.connect(lambda text, ms: notices.append(text))

    def files_listed():
        return sorted(Path(it.data(0, bt.DATA_FILE)).name for it in bt._iter_file_nodes())

    # A·B — 새 형식
    f2 = root / "v2"; make_split(f2, 2)
    mw.open_folder(f2); spin(30)
    chk(bt._mode != "json", "A. version 2 는 json 트리로 그리지 않는다", f"mode={bt._mode}")
    chk(files_listed() == ["ch1.pdf", "ch2.pdf"], "A. 그 폴더의 PDF 목록은 보인다", str(files_listed()))
    chk(any("bookmarks.json" in n and "2" in n for n in notices), "A. 업데이트 알림", str(notices))
    chk(not mw.search_results._order_map, "B. 검색 '책갈피 순' 은 새 형식 파일을 쓰지 않는다",
        str(mw.search_results._order_map))

    # C — 같은 형식·version 없음은 종전대로
    for nm, ver in (("v1", 1), ("vnone", None)):
        notices.clear()
        fo = root / nm; make_split(fo, ver)
        mw.open_folder(fo); spin(30)
        chk(bt._mode == "json", f"C. {nm} 는 json 트리", f"mode={bt._mode}")
        chk(files_listed() == ["ch1.pdf", "ch2.pdf"], f"C. {nm} 파일 줄", str(files_listed()))
        chk(len(mw.search_results._order_map) == 2, f"C. {nm} 검색 순서", str(mw.search_results._order_map))
        chk(not any("업데이트" in n for n in notices), f"C. {nm} 알림 없음", str(notices))

    chk(not errs, "예외 없음", str(errs))
    mw.close(); spin(5)
finally:
    shutil.rmtree(root, ignore_errors=True)

print("FAILS:", len(fails))
sys.exit(1 if fails else 0)
