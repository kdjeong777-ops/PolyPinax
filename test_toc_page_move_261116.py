# -*- coding: utf-8 -*-
"""261116-15: 목차를 썸네일로 뒤로 옮겨 저장한 뒤 다시 만들기 (책갈피창·저장 SOT §4.7.29 '쪽 편집 뒤').

사용자 보고: "목차만들기를 하고, 목차를 2페이지에서 뒤로 옮긴 후에, 기존 책갈피가 없어지고, 기존에 만들었던 목차가 되살아났어".
원인: 쪽 편집 저장(`page_edit_build.build`)이 목차 쪽 표식 `/PolyPDFToc` 를 옮기지 않았고, `marked_range` 는 2쪽만 봤다 —
다시 만들면 옛 목차 쪽이 남고 옛 '목차' 책갈피가 새 목차의 한 줄이 됐다.

A. 앱 길로 목차 만들기(2쪽) → 썸네일에서 목차 쪽을 뒤로 세 칸(실제 `_move_selected`) → 편집 모드 💾 저장(`_op_save`)
   → 표식이 옮긴 자리(5쪽)에 남음, 책갈피 그대로(본문 책갈피 모두·'목차' 는 5쪽)
B. 다시 '목차 페이지 만들기' → '바꿀까요?' [바꾸기] → 쪽 수 그대로(옛 목차가 남지 않음), 목차 쪽 하나·옮긴 자리(5쪽)에,
   '목차' 책갈피 하나(5쪽), 새 목차 줄에 옛 목차 제목이 없음, 번호·링크가 그 자리 기준, 다른 책갈피 그대로, 책갈피창 줄도
(수정 전 코드: A 표식 없음·B 쪽이 늘고 옛 목차가 남아 실패)
"""
import os, sys, tempfile, shutil, time, faulthandler
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(300, exit=True)
from pathlib import Path

import fitz
from PyQt6.QtCore import QStandardPaths, QCoreApplication
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtWidgets import QApplication, QMessageBox, QDialog
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_tocmove_%d" % os.getpid())   # 검사 작성 SOT §14.7.2 의 3
import modal_guard
modal_guard.install(label=lambda: "목차 옮긴 뒤", echo=False)             # §14.7.2 의 6
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def marked(o):
    """목차 표식 쪽(0-based) — 검사가 직접 읽는다(수정 전 코드에도 같은 판정)."""
    return [i for i in range(o.page_count) if o.xref_get_key(o[i].xref, "PolyPDFToc") == ("bool", "true")]


def spin(n=10, ms=20):
    for _ in range(n):
        app.processEvents(); QTest.qWait(ms)


errs = []
sys.excepthook = lambda t, v, tb: errs.append(f"{t.__name__}: {v}")
root = Path(tempfile.mkdtemp(prefix="polypdf_tocmove_"))
try:
    from viewer import toc_page
    pdf = root / "doc" / "doc.pdf"
    pdf.parent.mkdir()
    d = fitz.open()
    for i in range(12):
        d.new_page(width=595, height=842).insert_text((72, 100), "page %d" % (i + 1))
    d.set_toc([[1, "Cover", 1], [1, "1. General", 2], [2, "1.1 A", 3], [1, "2. Tests", 6], [1, "3. End", 10]])
    d.save(str(pdf)); d.close()

    import test_fixtures as _TFX; _TFX.autotag_off()
    from viewer.app import MainWindow
    from viewer.history import HistoryItem
    mw = MainWindow(); mw.resize(1200, 800); mw.show(); app.processEvents()
    bt = mw.bookmark_tree
    mw.open_folder(pdf.parent); spin(20)
    mw._load_main(HistoryItem(str(pdf), 0, "", "bookmark"), sync=True); spin(10)
    fn = next(iter(bt._iter_file_nodes()))
    fn.setExpanded(True); spin(20)
    bt.btn_edit.setChecked(True); spin(10)

    fin = {"n": 0}
    _of = mw._finalize_save

    def _f(*a, **k):
        fin["n"] += 1
        return _of(*a, **k)
    mw._finalize_save = _f

    def wait_fin(want):
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < 30 and fin["n"] < want:
            spin(1)
        spin(40)

    asked = []
    _mb = QMessageBox.exec

    def mb_exec(box, *a, **k):
        asked.append(box.text())
        for b in box.buttons():
            if b.text() == "바꾸기":
                b.click(); break
        return 0

    def make_toc(title):
        """실제 우클릭 메뉴 항목 → 창 [만들기]."""
        orig = QDialog.exec

        def fake(dlg, *a, **k):
            if type(dlg).__name__ == "TocPageDialog":
                dlg.ed_title.setText(title); dlg.accept(); return QDialog.DialogCode.Accepted
            return orig(dlg, *a, **k)
        QDialog.exec = fake
        QMessageBox.exec = mb_exec
        want = fin["n"] + 1
        try:
            bt._file_action("toc_page", [str(pdf)])          # 우클릭 '목차 페이지 만들기' 가 부르는 것
            wait_fin(want)
        finally:
            QDialog.exec = orig
            QMessageBox.exec = _mb

    make_toc("Contents")
    with fitz.open(str(pdf)) as o:
        chk(o.page_count == 13 and marked(o) == [1], "전제 — 목차 1쪽을 2쪽에", str((o.page_count, marked(o))))

    # ── A. 썸네일로 목차 쪽을 뒤로 세 칸 → 편집 모드 💾 저장 ──
    pt = mw.page_thumbs
    spin(20)
    pt.set_edit_mode(True); spin(5)
    pt.list.clearSelection(); pt.list.item(1).setSelected(True)
    for _ in range(3):
        pt._move_selected(1)
    spin(5)
    want = fin["n"] + 1
    bt._op_save()
    wait_fin(want)
    with fitz.open(str(pdf)) as o:
        pc_a, ms_a, toc_a = o.page_count, marked(o), o.get_toc()
    chk(pc_a == 13 and ms_a == [4], "A 쪽 편집 저장 뒤 목차 표식이 옮긴 자리(5쪽)에 남는다", str((pc_a, ms_a)))
    chk([t for _l, t, _p in toc_a if t != "Contents"] == ["Cover", "1. General", "1.1 A", "2. Tests", "3. End"]
        and ["Contents", 5] in [[t, p] for _l, t, p in toc_a], "A 책갈피 그대로('목차' 는 5쪽)", str(toc_a))

    # ── B. 다시 만들기 ──
    make_toc("New Contents")
    chk(any("바꿀까요" in t for t in asked), "B 옮긴 옛 목차도 알아보고 바꿀지 묻는다", str(asked))
    with fitz.open(str(pdf)) as o:
        pc, ms, toc = o.page_count, marked(o), o.get_toc()
        texts = [o[i].get_text() for i in range(o.page_count)]
        p5 = o[4].get_text()
        nums = [int(w[4]) for w in o[4].get_text("words") if w[4].isdigit() and w[2] > o[4].rect.width * 0.8]
        links = [l["page"] for l in o[4].get_links() if l.get("kind") == fitz.LINK_GOTO]
    chk(pc == 13, "B 쪽 수 그대로 — 옛 목차 쪽이 남지 않는다", str(pc))
    chk(ms == [4] and sum(1 for t in texts if "Contents" in t) == 1, "B 목차 쪽 하나 — 옮긴 자리(5쪽)에서 바뀐다", str(ms))
    chk("New Contents" in p5 and "Contents\n" not in p5.replace("New Contents", ""), "B 새 목차 줄에 옛 목차 제목이 없다", p5[:80])
    titles = [t for _l, t, _p in toc]
    chk(titles.count("New Contents") == 1 and "Contents" not in titles and ["New Contents", 5] in [[t, p] for _l, t, p in toc],
        "B '목차' 책갈피 하나(5쪽)·옛 것은 빠짐", str(toc))
    chk([t for t in titles if t != "New Contents"] == ["Cover", "1. General", "1.1 A", "2. Tests", "3. End"],
        "B 다른 책갈피 그대로", str(toc))
    body = {t: p for _l, t, p in toc}
    chk(nums == [body["Cover"], body["1. General"], body["1.1 A"], body["2. Tests"], body["3. End"]] and links == [n - 1 for n in nums],
        "B 번호·링크가 끼운 자리 기준(앞 쪽 그대로·뒤 쪽 +1)", str((nums, links, body)))
    spin(20)
    node = next(n for n in bt._iter_file_nodes() if Path(n.data(0, bt.DATA_FILE)).name == "doc.pdf")
    kids = [node.child(i).text(0) for i in range(node.childCount())]
    chk("New Contents" in kids and "Cover" in kids and "2. Tests" in kids, "B 책갈피창 줄도 새 책갈피", str(kids))

    chk(not errs, "예외 없음", str(errs[:3]))
    mw.close(); spin(5)
finally:
    shutil.rmtree(root, ignore_errors=True)

print("\n%s — 실패 %d" % ("ALL PASS" if not fails else "FAIL", len(fails)))
sys.exit(1 if fails else 0)
