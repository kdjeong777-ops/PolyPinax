# -*- coding: utf-8 -*-
"""261116-1(사용자 지시) 책갈피 자동 생성 창 — '입력' 묶음(PDF 파일 칸·[찾아보기]) 없음 — 마스터 §4.4.2 ⓪' · 디자인 SOT §2.12.

A. 창에 대상 파일을 고치는 칸·단추가 없다 — 대상은 고른 파일, 이름은 창 제목에
B. 그 파일로 기존 책갈피를 세고, 결과(input_pdf)도 그 파일
C. 고른 PDF 가 없으면(도구 메뉴를 PDF 없이) 창을 열지 않고 안내 — 편집 모드도 묻지 않는다
실제 경로: `MainWindow.action_open_bookmarker`(가짜 창 자리에 부름) · 실제 `BookmarkerDialog`.
"""
import os, sys, tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("POLYPDF_PROFILE", "ptest261116")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pathlib import Path
from types import SimpleNamespace
import fitz
from PyQt6.QtCore import QStandardPaths
from PyQt6.QtWidgets import QApplication, QMessageBox, QLineEdit, QPushButton, QGroupBox

QStandardPaths.setTestModeEnabled(True)
fails = []
def chk(c, m, extra=""):
    print(("PASS" if c else "FAIL"), "-", m, extra)
    if not c:
        fails.append(m)

app = QApplication.instance() or QApplication(sys.argv)
import modal_guard
guard = modal_guard.install(label=lambda: "책갈피 자동 생성 창", echo=False)   # 마스터 §14.7.2 의 6
infos = []
QMessageBox.information = staticmethod(lambda *a, **k: infos.append((a[1], a[2]) if len(a) > 2 else a))
QMessageBox.warning = staticmethod(lambda *a, **k: infos.append((a[1], a[2]) if len(a) > 2 else a))

from viewer.i18n import tr
root = Path(tempfile.mkdtemp(prefix="polypdf_bmdlg261116_"))
pdf = root / "보고서.pdf"
d = fitz.open()
for i in range(3):
    d.new_page().insert_text((72, 100), f"Chapter {i + 1}", fontsize=18)
d.set_toc([[1, "Chapter 1", 1], [1, "Chapter 2", 2]])
d.save(pdf); d.close()

# ── A·B. 창 ────────────────────────────────────────────────────────────
from viewer.widgets.bookmarker_dialog import BookmarkerDialog
dlg = BookmarkerDialog(default_pdf=pdf, prefs={})
dlg.show(); app.processEvents()
edits = [e.text() for e in dlg.findChildren(QLineEdit)]
chk(not any(str(pdf) == t or pdf.name in t for t in edits), "A1 대상 파일 경로 칸이 없다", str(edits))
browse = [b for b in dlg.findChildren(QPushButton) if b.text() == tr("찾아보기")]
chk(len(browse) == 1 and browse[0] is dlg.btn_browse_out, "A2 [찾아보기] 는 출력 폴더 것 하나뿐", str(len(browse)))
groups = [g.title() for g in dlg.findChildren(QGroupBox)]
chk(tr("입력") not in groups, "A3 '입력' 묶음이 없다", str(groups))
chk(dlg.windowTitle() == f"{tr('책갈피 자동 생성')} — {pdf.name}", "A4 창 제목에 파일 이름", dlg.windowTitle())
chk(not dlg.grp_exist.isHidden() and "2" in dlg.lbl_exist.text(), "B1 그 파일의 기존 책갈피 2개를 센다", dlg.lbl_exist.text())
chk(dlg.result_options()["input_pdf"] == str(pdf), "B2 결과의 대상 = 고른 파일", dlg.result_options()["input_pdf"])
dlg.close()

# ── C. 고른 PDF 없이 열기 ──────────────────────────────────────────────
import viewer.widgets.bookmarker_dialog as _bmd
from viewer.app import MainWindow
_made, _asked = [], []
_Real = _bmd.BookmarkerDialog
_bmd.BookmarkerDialog = lambda *a, **k: (_made.append(k), _Real(*a, **k))[1]
fake_bt = SimpleNamespace(ensure_edit_mode=lambda *a: (_asked.append(1), False)[1])
for cur in (None, str(root / "그림.png")):
    infos.clear(); _made.clear(); _asked.clear()
    fake = SimpleNamespace(_bookmarker_worker=None, main_view=SimpleNamespace(current_file=lambda c=cur: c),
                           _bm_tree_for_pane=lambda: fake_bt, _lite_heavy_notice=lambda *a: None, _prefs={})
    MainWindow.action_open_bookmarker(fake)
    chk(not _made and not _asked and infos and infos[-1][1] == tr("먼저 PDF를 여세요."),
        f"C1 고른 PDF 없음({cur and Path(cur).suffix}) → 창도 편집 모드 묻기도 없이 안내", f"{infos} made={len(_made)} asked={_asked}")
_bmd.BookmarkerDialog = _Real

# ── D. 검토 표 '단계' 열 — 첫 책갈피 = 1(책갈피창 단계와 같은 기준, 261116-2), 행의 level 은 0부터 그대로 ─────
from viewer.widgets import toc_review_dialog as _trd
rows = [{"title": "1. 장", "toc_page": None, "page": 1, "level": 0},
        {"title": "1.1 절", "toc_page": None, "page": 2, "level": 1},
        {"title": "1.1.1 항", "toc_page": None, "page": 3, "level": 2}]
tv = _trd.TocReviewDialog(pdf, [dict(r) for r in rows], method="toc")
hdr = tv.table.horizontalHeaderItem(_trd.COL_LEVEL).text()
shown = [tv.table.item(i, _trd.COL_LEVEL).text() for i in range(3)]
chk(hdr == tr("단계") and shown == ["1", "2", "3"], "D1 열 이름 '단계', 첫 책갈피 = 1", f"{hdr} {shown}")
chk([r["level"] for r in tv.rows()] == [0, 1, 2], "D2 결과 행의 level 은 0부터 그대로(책갈피창에 넣는 값)", str([r["level"] for r in tv.rows()]))
chk(_trd._IndentDelegate.indent_px(tv.table.item(0, _trd.COL_LEVEL).text()) == 0
    and _trd._IndentDelegate.indent_px(tv.table.item(2, _trd.COL_LEVEL).text()) == 2 * _trd.INDENT_PX,
    "D3 들여쓰기 = (단계−1) × INDENT_PX")
tv.table.selectRow(0); tv._level(-1)
chk(tv.table.item(0, _trd.COL_LEVEL).text() == "1" and tv.rows()[0]["level"] == 0, "D4 ◀ 는 단계 1 아래로 내려가지 않는다")
tv.table.item(1, _trd.COL_LEVEL).setText("9")
chk(tv.rows()[1]["level"] == 5, "D5 손으로 큰 단계를 적어도 최대 단계 6(level 5)", str(tv.rows()[1]["level"]))
tv.close()

print()
print("ALL PASS" if not fails else f"FAILED {len(fails)}: {fails}")
sys.exit(1 if fails else 0)
