# -*- coding: utf-8 -*-
"""261116-2: 책갈피 단계 — 기준·표기·추가·편집·정렬 (책갈피창·저장 SOT §4.7.27, 사용자 지시).

③ 기준: 파일 바로 아래 첫 책갈피 = 단계 1 (종전: 파일 줄까지 세어 '레벨 2')
①② 추가 창: 하위 단계에 있으면 '(단계 1) 상위 단계'…, '(단계 b) 윗 책갈피와 같은 단계'(기본), '(단계 b+1) 윗 책갈피의 하위' — 이름 앞 표기,
    상위 단계를 고르면 그 단계 조상 바로 뒤 형제로
④ 편집 창(실제 우클릭 '책갈피 수정'): '단계' 고르기 — 범위 1 ~ 바로 위 줄 단계+1, 바꾸면 하위와 함께 옮김
⑤ 우클릭 '페이지순 책갈피 정렬(선택 파일)' — '책갈피 수정' 바로 아래, 같은 부모 안에서 쪽 순·단계 유지
(수정 전 코드: 실패)
"""
import os, sys, tempfile, shutil, faulthandler
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(240, exit=True)
from pathlib import Path

import fitz
from PyQt6.QtCore import QStandardPaths
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtWidgets import QApplication, QMessageBox, QDialog, QMenu, QComboBox, QLineEdit
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
from PyQt6.QtCore import QCoreApplication
QCoreApplication.setApplicationName("polypdf_bmdepth_%d" % os.getpid())   # 검사 작성 SOT §14.7.2 의 3
import modal_guard
modal_guard.install(label=lambda: "책갈피 단계", echo=False)                 # §14.7.2 의 6
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def spin(n=10, ms=20):
    for _ in range(n):
        app.processEvents(); QTest.qWait(ms)


errs = []
sys.excepthook = lambda t, v, tb: errs.append(f"{t.__name__}: {v}")
root = Path(tempfile.mkdtemp(prefix="polypdf_bmdepth_"))
try:
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    import test_fixtures as _TFX; _TFX.autotag_off()
    from viewer.app import MainWindow
    from viewer.history import HistoryItem
    pdf = root / "doc.pdf"
    d = fitz.open()
    for i in range(12):
        d.new_page().insert_text((72, 72), f"page {i + 1}")
    d.set_toc([[1, "A", 2], [2, "A1", 3], [3, "A1a", 4], [1, "C", 9], [2, "C2", 11], [2, "C1", 10], [1, "B", 6]])
    d.save(str(pdf)); d.close()
    mw = MainWindow(); mw.resize(1200, 800); mw.show(); app.processEvents()
    bt = mw.bookmark_tree
    mw.open_folder(root); spin(20)
    mw._load_main(HistoryItem(str(pdf), 0, "", "bookmark"), sync=True); spin(10)
    fn = next(iter(bt._iter_file_nodes()))
    fn.setExpanded(True)
    for _ in range(100):
        if fn.data(0, bt.DATA_TOC_LOADED):
            break
        spin(1)
    bt.btn_edit.setChecked(True); spin(10)

    def find(title, node=None):
        node = node or fn
        for i in range(node.childCount()):
            c = node.child(i)
            if c.text(0).split("  (p.")[0] == title:
                return c
            r = find(title, c)
            if r is not None:
                return r
        return None

    def pick(it):
        bt.tree.clearSelection(); it.setSelected(True); bt.tree.setCurrentItem(it); spin(3)

    def depth(it):
        n, p = 0, it
        while p is not None and p is not fn:
            n += 1; p = p.parent()
        return n

    def drive(handler):
        """실제 창을 만들게 두고, 띄우는 대신 handler 가 그 창의 칸을 고르고 [확인]."""
        orig = QDialog.exec
        seen = {}

        def fake(dlg, *a, **k):
            seen["r"] = handler(dlg)
            return QDialog.DialogCode.Accepted
        QDialog.exec = fake
        return orig, seen

    def menu_actions(it):
        got = []
        orig = QMenu.exec

        def fake_exec(menu, *a, **k):
            got.extend(menu.actions())
            return None
        QMenu.exec = fake_exec
        try:
            bt.tree.scrollToItem(it)
            bt._on_tree_context_menu(bt.tree.visualItemRect(it).center())
        finally:
            QMenu.exec = orig
        return [a for a in got if a.text()]

    # ── ③ 기준 ──
    pick(find("A"))
    chk(bt.suggest_add_level(str(pdf))[0] == 1, "③ 파일 바로 아래 첫 책갈피는 단계 1", str(bt.suggest_add_level(str(pdf))))
    pick(find("A1a"))
    chk(bt.suggest_add_level(str(pdf))[0] == 3, "③ 그 아래 아래는 단계 3", str(bt.suggest_add_level(str(pdf))))

    # ── ①② 추가 창 ──
    def add_handler(dlg):
        cmb = dlg.findChild(QComboBox)
        texts = [cmb.itemText(i) for i in range(cmb.count())] if cmb else []
        cur = cmb.currentIndex() if cmb else -1
        if cmb:
            cmb.setCurrentIndex(cmb.findData(1))
        dlg.findChild(QLineEdit).setText("NEW")
        return texts, cur
    orig, seen = drive(add_handler)
    try:
        mw._prompt_add_bookmark(str(pdf), 5); spin(5)
    finally:
        QDialog.exec = orig
    texts, cur = seen.get("r", ([], -1))
    chk(texts == ["(단계 1) 상위 단계", "(단계 2) 상위 단계", "(단계 3) 윗 책갈피와 같은 단계", "(단계 4) 윗 책갈피의 하위"],
        "①② 추가 창 단계 — 상위 단계들이 '같은 단계' 위에, '(단계 N)' 이 이름 앞", str(texts))
    chk(cur == 2, "① 기본은 '윗 책갈피와 같은 단계'", str(cur))
    new = find("NEW")
    chk(new is not None and depth(new) == 1 and fn.indexOfChild(new) == fn.indexOfChild(find("A")) + 1,
        "① '(단계 1) 상위 단계' → 단계 1 조상 A 바로 뒤 형제", str(new and (depth(new), fn.indexOfChild(new))))

    # ── ④ 편집 창(실제 우클릭 '책갈피 수정') ──
    def edit_to(it, want):
        acts = menu_actions(it)
        a = next((x for x in acts if x.text().split("\t")[0] == "책갈피 수정"), None)
        info = {}

        def h(dlg):
            cmbs = dlg.findChildren(QComboBox)
            cmb = cmbs[0] if cmbs else None
            info["items"] = [cmb.itemText(i) for i in range(cmb.count())] if cmb else []
            if cmb:
                cmb.setCurrentIndex(cmb.findData(want))
            return info
        orig, _seen = drive(h)
        try:
            if a is not None:
                a.trigger(); spin(5)
        finally:
            QDialog.exec = orig
        return a is not None, info.get("items", [])

    c1 = find("C1")
    ok, items = edit_to(c1, 1)
    chk(ok and items == ["(단계 1)", "(단계 2)", "(단계 3)"], "④ 편집 창 단계 범위 = 1 ~ 위 줄(C2) 단계+1", str(items))
    c1 = find("C1")
    chk(c1 is not None and depth(c1) == 1 and fn.indexOfChild(c1) == fn.indexOfChild(find("C")) + 1,
        "④ 단계 1 로 → C 바로 뒤 형제", str(c1 and depth(c1)))
    a1 = find("A1")
    ok, items = edit_to(a1, 1)
    chk(items == ["(단계 1)", "(단계 2)"], "④ 첫 하위는 지금 단계까지(위 형제 없음)", str(items))
    a1 = find("A1")
    chk(a1 is not None and depth(a1) == 1 and find("A1a") is not None and find("A1a").parent() is a1,
        "④ 단계를 바꾸면 하위(A1a)도 함께", str(a1 and depth(a1)))

    # ── ⑤ 정렬 메뉴 ──
    acts = [a.text().split("\t")[0] for a in menu_actions(find("B"))]
    i_edit = acts.index("책갈피 수정") if "책갈피 수정" in acts else -9
    chk("페이지순 책갈피 정렬(선택 파일)" in acts and acts.index("페이지순 책갈피 정렬(선택 파일)") == i_edit + 1,
        "⑤ '페이지순 책갈피 정렬(선택 파일)' 이 '책갈피 수정' 바로 아래", str(acts[max(0, i_edit - 1):i_edit + 3]))
    chk(not any("페이지순 정렬" in t and t.startswith("선택 책갈피") for t in acts), "⑤ 옛 이름 없음")
    a = next((x for x in menu_actions(find("B")) if x.text().split("\t")[0] == "페이지순 책갈피 정렬(선택 파일)"), None)
    if a is not None:
        a.trigger(); spin(10)

    def pages(node):
        return [node.child(i).data(0, bt.DATA_PAGE) for i in range(node.childCount())]
    tops = [fn.child(i).text(0).split("  (p.")[0] for i in range(fn.childCount())]
    chk(tops == ["A", "A1", "NEW", "B", "C", "C1"], "⑤ 단계 1 은 같은 부모 안에서 쪽 순", str(tops))
    chk(find("A1a").parent() is find("A1") and find("C2").parent() is find("C"), "⑤ 하위는 부모 아래 그대로(단계 유지)")
    chk(all(pages(n) == sorted(pages(n)) for n in (fn, find("A1"), find("C"))), "⑤ 부모마다 쪽 오름차순")

    chk(not errs, "예외 없음", str(errs))
    bt._dirty = False
    mw.close(); spin(5)
finally:
    shutil.rmtree(root, ignore_errors=True)

print("FAILS:", len(fails))
sys.exit(1 if fails else 0)
