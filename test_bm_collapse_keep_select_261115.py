# -*- coding: utf-8 -*-
"""261115-15: 책갈피창 접기·펼치기 뒤에도 고른 줄과 그 화면 위치는 그대로 (책갈피창·저장 SOT §4.7.3).

사용자 보고: "책갈피 창에서 접기 등을 한 후, 책갈피 선택 위치가 상단으로 바뀌고 있어. 원래 선택되었던 위치에서 바뀌지 않도록 수정해"

원인 ① 파일 안 책갈피를 고른 채 접으면(모두 접기·▾ 누름) 숨은 책갈피가 고른 줄로 남아, 다음 ↓ 가 목록 맨 위로 갔다.
원인 ② 모두 펼치기가 위쪽 파일들을 펼치며 고른 줄을 화면 밖으로 밀어냈다.

A. 책갈피를 고른 채 모두 접기 → 파일 줄을 고름 · 본문 그대로 · 화면 높이 그대로 · 실제 ↓ 는 바로 아래 파일
B. 책갈피를 고른 채 부모 파일 줄 ▾ 실제 누름 → 파일 줄을 고름 · 본문 그대로 · 실제 ↓ 는 바로 아래 파일
C. 모두 펼치기 → 고른 줄(파일·책갈피) 화면 높이 그대로
D. 위쪽 파일들이 펼쳐진 채 모두 접기 → 고른 줄 화면 높이 그대로
E. 고른 줄이 창 밖이었으면 맞추지 않는다(스크롤 그대로)
"""
import os, sys, time, tempfile, shutil, faulthandler
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(300, exit=True)
from pathlib import Path

import fitz
from PyQt6.QtCore import Qt, QStandardPaths, QCoreApplication, QPoint
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
import modal_guard
modal_guard.install(label=lambda: "접기 뒤 고른 줄 유지", echo=False)   # 검사 작성 SOT §14.7.2 의 6
QStandardPaths.setTestModeEnabled(True)                                # 검사 작성 SOT §14.7.2 의 3
QCoreApplication.setApplicationName("polypdf_collapse_keep_sel_%d" % os.getpid())
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def spin(ms):
    t = time.perf_counter()
    while (time.perf_counter() - t) * 1000 < ms:
        app.processEvents(); QTest.qWait(5)


root = Path(tempfile.mkdtemp(prefix="polypdf_collapse_keep_sel_"))
try:
    for i in range(40):
        n = f"f{i:02d}"
        d = fitz.open()
        for k in range(12):
            d.new_page().insert_text((50, 80), f"{n} p{k}")
        d.set_toc([[1, f"{n} A", 1], [2, f"{n} a1", 2], [2, f"{n} a2", 3], [1, f"{n} B", 5],
                   [2, f"{n} b1", 6], [2, f"{n} b2", 7], [1, f"{n} C", 9]])
        d.save(str(root / f"{n}.pdf")); d.close()

    from viewer.app import MainWindow
    mw = MainWindow(); mw.resize(1200, 700); mw.show(); app.processEvents()
    bt = mw.bookmark_tree; tree = bt.tree; mv = mw.main_view
    bt.load_folder(root); spin(800)
    try:
        bt.set_tree_view(False)
        bt.set_sort_mode(bt.SORT_NAME)
    except Exception:
        pass
    bt.btn_edit.setChecked(False); spin(200)
    row = {Path(n.data(0, bt.DATA_FILE)).stem: n for n in bt._iter_file_nodes()}
    chk(len(row) == 40, "준비 — 파일 40개", str(len(row)))

    def name(it):
        if it is None:
            return None
        d = it.data(0, bt.DATA_FILE)
        return (Path(d).stem if d else "?") + ("" if bt._is_file_node(it) else ":" + it.text(0))

    def ytop(it):
        r = tree.visualItemRect(it)
        return r.top() if r.height() > 0 else None

    def cur_file():
        f = mv.current_file()
        return Path(f).stem if f else None

    def wait_file(stem, ms=4000):
        t = time.perf_counter()
        while cur_file() != stem and (time.perf_counter() - t) * 1000 < ms:
            spin(20)
        return cur_file() == stem

    def reset():
        """두 상태를 끄고 모든 파일 줄을 접는다(시작 모양)."""
        if bt.is_expand_all_mode():
            bt.toggle_expand_all(True)
        if bt.is_collapse_all_mode():
            bt.toggle_expand_all(False)
        for n in row.values():
            n.setExpanded(False)
        spin(150)

    def pick(file, bm=None):
        """file(과 그 안 책갈피 bm)을 고르고 창 가운데쯤에 둔다."""
        f = row[file]
        tree.setFocus()
        tree.setCurrentItem(f); wait_file(file); spin(300)
        tgt = f
        if bm:
            f.setExpanded(True); spin(500)
            stack = [f]
            while stack:
                x = stack.pop()
                x.setExpanded(True)
                if x.text(0) == f"{file} {bm}":
                    tgt = x
                stack.extend(x.child(k) for k in range(x.childCount()))
            spin(200)
            tree.setCurrentItem(tgt); spin(500)
        tree.scrollToItem(tgt, tree.ScrollHint.PositionAtCenter); spin(200)
        return tgt

    def click_arrow(it):
        r = tree.visualItemRect(it)
        QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         QPoint(r.left() - tree.indentation() // 2, r.center().y()))

    # ── A 책갈피를 고른 채 모두 접기 ──
    reset()
    a2 = pick("f20", "a2")
    y0, page0 = ytop(a2), mv.current_page()
    chk(a2 is not None and a2.text(0) == "f20 a2" and page0 == 2, "A 준비 — f20 a2 고름, 본문 3쪽", f"{name(a2)} {page0}")
    bt.toggle_expand_all(False); spin(400)                       # 메뉴·단축키와 같은 함수
    cur = tree.currentItem()
    chk(cur is row["f20"], "A ★ 모두 접기 → 숨은 책갈피 대신 보이는 조상(f20 파일 줄)을 고른다", name(cur))
    chk(cur_file() == "f20" and mv.current_page() == page0, "A 본문은 옮기지 않는다", f"{cur_file()} {mv.current_page()}")
    chk(ytop(cur) == y0, "A ★ 고른 줄 화면 높이 그대로", f"{y0} → {ytop(cur)}")
    QTest.keyClick(tree, Qt.Key.Key_Down); spin(300)
    chk(tree.currentItem() is row["f21"], "A ★ 그 뒤 실제 ↓ 는 바로 아래 파일(맨 위로 가지 않는다)", name(tree.currentItem()))

    # ── B 책갈피를 고른 채 부모 ▾ 실제 누름 ──
    reset()
    a2 = pick("f20", "a2")
    page0 = mv.current_page()
    click_arrow(row["f20"]); spin(400)
    chk(not row["f20"].isExpanded(), "B 준비 — ▾ 누름으로 f20 이 접혔다")
    cur = tree.currentItem()
    chk(cur is row["f20"], "B ★ ▾ 누름 → 보이는 조상(f20)을 고른다", name(cur))
    chk(cur_file() == "f20" and mv.current_page() == page0, "B 본문은 옮기지 않는다", f"{cur_file()} {mv.current_page()}")
    QTest.keyClick(tree, Qt.Key.Key_Down); spin(300)
    chk(tree.currentItem() is row["f21"], "B ★ 그 뒤 실제 ↓ 는 바로 아래 파일", name(tree.currentItem()))

    # ── C 모두 펼치기 ──
    reset()
    f20 = pick("f20")
    y0 = ytop(f20)
    bt.toggle_expand_all(True); spin(1500)
    chk(row["f20"].isExpanded(), "C 준비 — 모두 펼치기로 f20 이 펼쳐졌다")
    chk(tree.currentItem() is f20 and ytop(f20) == y0, "C ★ 모두 펼치기 — 고른 파일 줄 화면 높이 그대로", f"{y0} → {ytop(f20)}")
    reset()
    b1 = pick("f20", "b1")
    y0 = ytop(b1)
    bt.toggle_expand_all(True); spin(1500)
    chk(tree.currentItem() is b1 and ytop(b1) == y0, "C ★ 모두 펼치기 — 고른 책갈피 줄 화면 높이 그대로", f"{y0} → {ytop(b1)}")

    # ── D 위쪽 파일들이 펼쳐진 채 모두 접기 ──
    reset()
    f20 = pick("f20")
    for k in range(14, 20):
        row[f"f{k:02d}"].setExpanded(True)
    spin(600)
    tree.setCurrentItem(f20); spin(300)
    tree.scrollToItem(f20, tree.ScrollHint.PositionAtCenter); spin(200)
    y0 = ytop(f20)
    bt.toggle_expand_all(False); spin(400)
    chk(tree.currentItem() is f20 and ytop(f20) == y0, "D ★ 위쪽이 펼쳐진 채 모두 접기 — 고른 줄 화면 높이 그대로", f"{y0} → {ytop(f20)}")

    # ── E 창 밖이었으면 맞추지 않는다 ──
    reset()
    f30 = pick("f30")
    tree.scrollToTop(); spin(200)
    chk(ytop(f30) is None or ytop(f30) > tree.viewport().height(), "E 준비 — 고른 줄이 창 밖")
    bt.toggle_expand_all(True); spin(1500)
    chk(tree.verticalScrollBar().value() == 0 and tree.currentItem() is f30,
        "E 창 밖이던 고른 줄로 스크롤하지 않는다", str(tree.verticalScrollBar().value()))
except Exception:
    import traceback
    traceback.print_exc()
    fails.append("예외")
finally:
    shutil.rmtree(root, ignore_errors=True)

print("\n=== " + ("ALL PASS" if not fails else f"FAILURE ({len(fails)})") + " ===")
for m in fails:
    print(" -", m)
sys.stdout.flush()
os._exit(1 if fails else 0)
