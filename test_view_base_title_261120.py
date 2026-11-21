# -*- coding: utf-8 -*-
"""261120-29·-30: 보기 기준 폴더 — 창 제목에 지금 파일의 폴더 전체(기준은 ▸ 로 가름), 파일↔폴더 왕복은 기준을 지킨다
(책갈피창·저장 SOT §4.9.4).

사용자 지시
  "현재 단일보기 상태에서 현재 보기기준이 되는 폴더만 상단에 보여주고 있어. -> 현재 파일의 모든 폴더를 보여주는 걸로 수정해.
   (다만, 보기기준이 되는 폴더를 강조하는 방안을 마련해)"
  "하위 폴더에 있는 상태에서 목록보기를 하면, 해당 폴더로 고정된 상태에서 보기가 되. -> 기존 보기기준이 되는 폴더 기준으로 보이게(토글)"
사용자 결정: ▸ 로 가름 · 길면 앞쪽을 … 로 · 폴더 모드로 돌아오면 원래 기준 폴더.

A 폴더 모드 — 하위 폴더 파일: 제목 '<기준> ▸ sub\\deep  —  D.pdf'
B [📄 파일] 단추 — 파일 모드에서도 기준을 지킨다(제목 그대로)
C [📁 폴더] 단추 — 기준 폴더로 돌아가고 그 파일을 고른다(종전: sub\\deep 에 고정)
D 기준 바로 아래 파일은 종전 제목 '<기준>  —  A.pdf'
E PDF 를 바로 연 파일 모드는 그 폴더가 기준(▸ 없음), 폴더 모드로 가면 그 폴더(종전대로)
F 긴 경로 — 기준 앞쪽만 '…\\' 로 줄이고 기준 이름·하위 경로·파일 이름은 남는다
"""
import os, sys, tempfile, shutil, faulthandler
os.environ["QT_QPA_PLATFORM"] = "offscreen"
faulthandler.dump_traceback_later(300, exit=True)
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pathlib import Path

import fitz
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)                  # 검사 작성 SOT §14.7.2 의 3
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_view_base_%d" % os.getpid())   # §14.7.2 의 3
import modal_guard
modal_guard.install(label=lambda: "보기 기준 폴더", echo=False)               # §14.7.2 의 6
fails = []
SEP = "  —  "


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


def mk(p):
    d = fitz.open(); d.new_page().insert_text((72, 72), p.stem); d.save(str(p)); d.close()


def spin(n=10, ms=30):
    for _ in range(n):
        app.processEvents(); QTest.qWait(ms)


root = Path(tempfile.mkdtemp(prefix="polypdf_vbase_"))
try:
    deep = root / "sub" / "deep"
    deep.mkdir(parents=True)
    mk(root / "A.pdf"); mk(deep / "D.pdf")
    longbase = root / ("L" * 30) / ("M" * 30) / "basefolder"
    (longbase / "child").mkdir(parents=True)
    mk(longbase / "child" / "Z.pdf")

    from viewer.app import MainWindow
    mw = MainWindow(); mw.resize(1300, 850); mw.show(); spin()
    bt = mw.bookmark_tree

    def path_part():
        t = mw.windowTitle()
        return t.split(SEP, 1)[1] if SEP in t else ""

    def pick(name):
        for _ in range(100):
            for it in bt._iter_file_nodes():
                if Path(str(it.data(0, bt.DATA_FILE))).name == name:
                    bt.tree.setCurrentItem(it); spin(15)
                    return True
            spin(2)
        return False

    def click(btn):
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton); spin(25)

    cur = lambda: Path(str(mw.main_view.current_file() or "")).name   # noqa: E731

    mw.open_folder(root); spin(30)
    chk(pick("D.pdf") and cur() == "D.pdf", "준비 — 폴더 모드에서 하위 폴더의 D.pdf 를 연다")
    # 실행기가 주는 TEMP 가 길면 80자 줄임이 함께 걸린다 — 기대값은 같은 규칙(`_title_base_sub`)으로
    want = f"{MainWindow._title_base_sub(root, 'sub' + os.sep + 'deep')}{SEP}D.pdf"
    chk(path_part() == want and f"{root.name} ▸ sub{os.sep}deep{SEP}D.pdf" in path_part(),
        "A 제목 '<기준> ▸ sub\\deep  —  D.pdf'", repr(path_part()))

    click(bt.btn_mode)
    chk(bt._is_file_mode(), "준비 — [📄 파일] 단추로 파일 모드")
    chk(path_part() == want, "B 파일 모드에서도 기준 폴더를 지킨다(제목 그대로)", repr(path_part()))

    click(bt.btn_mode)
    chk(not bt._is_file_mode() and Path(bt._root_dir) == root,
        "C [📁 폴더] 단추 — **원래 기준 폴더**로 돌아간다(종전: sub\\deep 고정)", str(bt._root_dir))
    it = bt.tree.currentItem()
    chk(it is not None and Path(str(bt._file_node_of(it).data(0, bt.DATA_FILE))).name == "D.pdf",
        "C 돌아온 목록에서 그 파일이 골라져 있다", it.text(0) if it else "")
    chk(path_part() == want, "C 제목도 그대로", repr(path_part()))

    chk(pick("A.pdf") and path_part() == f"{root}{SEP}A.pdf", "D 기준 바로 아래 파일은 종전 제목", repr(path_part()))

    mw.open_pdf(deep / "D.pdf"); spin(20)
    chk(bt._is_file_mode() and path_part() == f"{deep}{SEP}D.pdf",
        "E PDF 를 바로 열면 그 폴더가 기준(▸ 없음)", repr(path_part()))
    click(bt.btn_mode)
    chk(not bt._is_file_mode() and Path(bt._root_dir) == deep, "E 폴더 모드로 가면 그 폴더(종전대로)", str(bt._root_dir))

    mw.open_folder(longbase); spin(30)
    chk(pick("Z.pdf"), "준비 — 긴 경로 기준 폴더의 하위 파일")
    pp = path_part()
    chk(pp.startswith("…" + os.sep) and pp == f"…{os.sep}{'M' * 30}{os.sep}basefolder ▸ child{SEP}Z.pdf",
        "F 길면 기준 앞쪽만 '…\\' 로 — 기준 이름·하위 경로·파일 이름은 남는다", repr(pp))
finally:
    shutil.rmtree(root, ignore_errors=True)

print("\n=== " + ("ALL PASS" if not fails else f"FAILURE ({len(fails)})") + " ===")
for m in fails:
    print(" -", m)
sys.stdout.flush()
os._exit(1 if fails else 0)
