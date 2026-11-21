# -*- coding: utf-8 -*-
"""261117-52: 병합 결과를 책갈피창 폴더 **밖**에 저장한 뒤 창 제목이 저장 위치를 바르게 보이는지 (책갈피창·저장 SOT §4.8.3).

사용자 보고(설치본 v1.1.0-beta.17)
  "만들어진 pdf를 병합하고, downloads 폴더에 저장했는데, 상단에 documents 폴더에 저장했다고 나왔어.
   실제로는 downloads 폴더에 저장된게 맞아."
가상 프린터가 연 PDF(파일 모드, 기준 폴더 = Documents\\PolyPDF 인쇄)들을 병합해 Downloads 에 저장 →
제목 줄이 'PolyPinax v… — …\\Documents\\PolyPDF 인쇄 — <병합 파일 이름>' 으로 남아 Documents 에 저장된 것처럼 보였다.

A 파일 모드 — 다른 폴더에 저장: 제목에 **저장한 파일의 전체 경로**(그 폴더가 보인다), 본문·목록은 새 파일
B 같은 길 — 병합 뒤 열기도 '저장 뒤 여는 길' 하나(`_open_saved_file` — 색인을 **먼저** 걸고 연다, 응답성 SOT §4.4)
C 기준 폴더 안에 저장하면 제목은 종전대로 '폴더 — 이름'
D 폴더 모드 — 하위 폴더 저장은 이름만(그 폴더 안), 폴더 밖은 종전대로 완료창
"""
import os, sys, tempfile, shutil, faulthandler
os.environ["QT_QPA_PLATFORM"] = "offscreen"
faulthandler.dump_traceback_later(300, exit=True)
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pathlib import Path

import fitz
from PyQt6.QtCore import QStandardPaths, QCoreApplication
QStandardPaths.setTestModeEnabled(True)                  # 검사 작성 SOT §14.7.2 의 3
from PyQt6.QtWidgets import QApplication, QMessageBox, QFileDialog
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_merge_title_%d" % os.getpid())   # §14.7.2 의 3
import modal_guard
modal_guard.install(label=lambda: "병합 뒤 창 제목", echo=False)                # §14.7.2 의 6
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def make_pdf(p, n=3):
    d = fitz.open()
    for i in range(n):
        d.new_page().insert_text((72, 72), f"{p.stem} PAGE {i + 1}")
    d.save(str(p)); d.close()


def spin(n=10, ms=30):
    for _ in range(n):
        app.processEvents(); QTest.qWait(ms)


root = Path(tempfile.mkdtemp(prefix="polypdf_mtitle_"))
docs = root / "Documents" / "PolyPDF 인쇄"
dl = root / "Downloads"
docs.mkdir(parents=True); dl.mkdir()
try:
    for nm in ("A", "B"):
        make_pdf(docs / f"{nm}.pdf")
    (docs / "sub").mkdir()
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    from viewer.app import MainWindow
    from viewer.widgets import merge_dialog as md
    mw = MainWindow(); mw.resize(1300, 850); mw.show(); app.processEvents()
    bt = mw.bookmark_tree
    after_calls = []
    mw._after_pdf_created = lambda p: after_calls.append(str(p))

    order = []
    real_index, real_load = mw._index_single_file, mw._load_main
    mw._index_single_file = lambda p, _f=real_index: (order.append(("index", Path(p).name)), _f(p))[1]
    mw._load_main = lambda item, *a, _f=real_load, **k: (order.append(("load", Path(item.file_path).name)), _f(item, *a, **k))[1]

    real_exec = md.MergeFilesDialog.exec

    def run_merge(out_path):
        def fake_exec(self):
            for i in range(self.left.count()):
                self.left.item(i).setSelected(Path(self.left.item(i).data(self._DATA)).stem in ("A", "B"))
            self._move_selected()
            self.chk_auto.setChecked(False)
            return md.QDialog.DialogCode.Accepted
        real_save = QFileDialog.getSaveFileName
        md.MergeFilesDialog.exec = fake_exec
        QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(out_path), "PDF (*.pdf)"))
        order.clear()
        try:
            mw._on_merge_files(None)
        finally:
            md.MergeFilesDialog.exec = real_exec
            QFileDialog.getSaveFileName = real_save
        for _ in range(200):
            spin(1, 30)
            cur = mw.main_view.current_file()
            if Path(out_path).exists() and cur and Path(cur).resolve() == Path(out_path).resolve():
                break
        spin(10)

    def cur_name():
        cur = mw.main_view.current_file()
        return Path(cur).name if cur else ""

    # ── A·B 파일 모드(가상 프린터가 연 모양) → Downloads 에 저장 ──
    mw.open_pdf(docs / "A.pdf"); spin(10)
    mw.open_pdfs([docs / "A.pdf", docs / "B.pdf"]); spin(10)
    chk(bt._is_file_mode(), "준비 — 파일 모드(기준 폴더 = Documents\\PolyPDF 인쇄)")
    out = dl / "AB_merged.pdf"
    run_merge(out)
    title = mw.windowTitle()
    chk(cur_name() == "AB_merged.pdf", "A 본문에 병합 파일이 열린다", cur_name())
    chk(str(out) in title, "A 제목에 **저장한 파일의 전체 경로**(Downloads)가 보인다", title)
    chk(not title.endswith("—  AB_merged.pdf") or str(dl) in title,
        "A 제목이 'Documents… — 병합 파일 이름' 으로 Documents 에 저장된 것처럼 보이지 않는다", title)
    idx = [i for i, (k, n) in enumerate(order) if k == "index" and n == "AB_merged.pdf"]
    lod = [i for i, (k, n) in enumerate(order) if k == "load" and n == "AB_merged.pdf"]
    chk(len(idx) == 1 and lod and idx[0] < lod[0],
        "B 병합 뒤 여는 길 = `_open_saved_file`(색인 한 번, **연 것보다 먼저**)", str(order))

    # ── C 파일 모드 — 기준 폴더 안에 저장 → 종전대로 이름만 ──
    out_c = docs / "AB_in.pdf"
    run_merge(out_c)
    title = mw.windowTitle()
    chk(cur_name() == "AB_in.pdf" and title.endswith("AB_in.pdf") and str(out_c) not in title,
        "C 기준 폴더 안이면 제목은 '폴더 — 이름'(전체 경로를 붙이지 않는다)", title)
    idx = [i for i, (k, n) in enumerate(order) if k == "index" and n == "AB_in.pdf"]
    lod = [i for i, (k, n) in enumerate(order) if k == "load" and n == "AB_in.pdf"]
    chk(len(idx) == 1 and lod and idx[0] < lod[0], "C 같은 길(색인 먼저·한 번)", str(order))

    # ── D 폴더 모드 ──
    mw.open_folder(docs); spin(30)
    after_calls.clear()
    out_d = docs / "sub" / "AB_sub.pdf"
    run_merge(out_d)
    title = mw.windowTitle()
    # 261120-29(§4.9.4): 하위 폴더면 '<폴더> ▸ <하위>  —  이름'
    chk(cur_name() == "AB_sub.pdf" and title.endswith("PolyPDF 인쇄 ▸ sub  —  AB_sub.pdf") and after_calls == [],
        "D 폴더 모드 하위 폴더 — 그 파일을 열고 제목은 '폴더 ▸ sub  —  이름'", title + " " + str(after_calls))
    idx = [i for i, (k, n) in enumerate(order) if k == "index" and n == "AB_sub.pdf"]
    lod = [i for i, (k, n) in enumerate(order) if k == "load" and n == "AB_sub.pdf"]
    chk(len(idx) == 1 and lod and idx[0] < lod[0], "D 같은 길(색인 먼저·한 번)", str(order))
    out_e = dl / "AB_out.pdf"
    run_merge(out_e)
    chk(after_calls == [str(out_e)], "D 폴더 모드에서 폴더 밖이면 종전대로 완료창", str(after_calls))
finally:
    shutil.rmtree(root, ignore_errors=True)

print("\n=== " + ("ALL PASS" if not fails else f"FAILURE ({len(fails)})") + " ===")
for m in fails:
    print(" -", m)
sys.stdout.flush()
os._exit(1 if fails else 0)
