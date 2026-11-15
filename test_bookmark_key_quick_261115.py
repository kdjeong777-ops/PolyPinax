# -*- coding: utf-8 -*-
"""261115-12: 책갈피창 — 키로 다른 파일로 옮기면 상태와 상관없이 '표지 먼저' (응답성 SOT §4.7 ⑤, 책갈피창·저장 SOT §4.7.3).

사용자 결정(2026-11-15): "키보드 이동엔 항상" — 종전 261114-5 의 '모두 접기 상태 + 느린 PC' 를 넓혔다.
종전: 펼친(평소) 상태에서 ↓ 연타는 지나가는 파일을 하나하나 통째로 열어 큰 폴더(3,061개)에서 최장 1.2~2.0초 섰다.

A. 평소 상태(모두 접기·가벼운 넘김 아님)에서 실제 ↓ 5번 연타(30ms) — 연 파일은 2개 이하(첫 것·멈춘 것), 멈추면 본문 = 고른 파일
B. 그 멈춘 파일은 표지 먼저로 열렸다 — 연 직후 썸네일을 붙들고, 조금 뒤 푼다
C. 천천히(400ms) 누르면 지나가는 파일도 하나씩 연다
D. 마우스 누름은 종전대로 — 바로 다 연다(붙들지 않는다)
E. Home·End 도 키라 표지 먼저
"""
import os, sys, time, tempfile, shutil, faulthandler
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.pop("POLYPDF_FAKE_POWER_SAVING", None)
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(300, exit=True)
from pathlib import Path

import fitz
from PyQt6.QtCore import Qt, QStandardPaths, QCoreApplication
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
QStandardPaths.setTestModeEnabled(True)               # 검사 작성 SOT §14.7.2 의 3
QCoreApplication.setApplicationName("polypdf_key_quick_%d" % os.getpid())
import modal_guard
modal_guard.install(label=lambda: "키 옮김 표지 먼저", echo=False)   # §14.7.2 의 6
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def spin(ms=300):
    t = time.perf_counter()
    while (time.perf_counter() - t) * 1000 < ms:
        app.processEvents(); QTest.qWait(5)


root = Path(tempfile.mkdtemp(prefix="polypdf_key_quick_"))
try:
    for i in range(8):
        d = fitz.open()
        for k in range(20):
            d.new_page().insert_text((60, 90), f"file{i} page{k} key quick", fontsize=14)
        d.save(str(root / f"f{i}.pdf")); d.close()            # 책갈피 없음 — 파일 줄만(↓ 가 파일에서 파일로)

    from viewer.app import MainWindow
    from viewer import perf_mode
    mw = MainWindow(); mw.resize(1300, 850); mw.show(); app.processEvents()
    bt = mw.bookmark_tree; mv = mw.main_view; pt = mw.page_thumbs
    _held = lambda: bool(getattr(pt, "is_render_held", lambda: False)())
    loads = []
    _orig_ld = mv.load_document

    def _spy_ld(path, *a, **k):
        loads.append(Path(str(path)).stem)
        return _orig_ld(path, *a, **k)
    mv.load_document = _spy_ld

    bt.load_folder(root); spin(800)
    try:
        bt.set_tree_view(False); bt.set_sort_mode(bt.SORT_NAME)
    except Exception:
        pass
    bt.btn_edit.setChecked(False); spin(200)
    row = {Path(n.data(0, bt.DATA_FILE)).stem: n for n in bt._iter_file_nodes()}
    chk(len(row) == 8, "준비 — 파일 8개", str(len(row)))
    chk(not bt.is_collapse_all_mode() and not bt.is_expand_all_mode() and not perf_mode.is_lite(),
        "준비 — 평소 상태(모두 접기·모두 펼치기·가벼운 넘김 아님)")

    def cur_file():
        f = mv.current_file()
        return Path(f).stem if f else None

    def wait_file(stem, ms=4000):
        t = time.perf_counter()
        while cur_file() != stem and (time.perf_counter() - t) * 1000 < ms:
            app.processEvents(); QTest.qWait(3)
        return cur_file() == stem

    bt.tree.setFocus(); bt.tree.setCurrentItem(row["f0"]); wait_file("f0"); spin(900)

    # ── A·B 연타 ──
    n0 = len(loads)
    for _ in range(5):
        QTest.keyClick(bt.tree, Qt.Key.Key_Down); spin(30)
    ok = wait_file("f5")
    held = _held()
    opened = loads[n0:]
    chk(ok and len(opened) <= 2, "A ★ 평소 상태 ↓ 연타 — 지나간 파일은 열지 않는다(첫 것·멈춘 것만)", str(opened))
    chk(held, "B ★ 멈춘 파일은 표지 먼저 — 연 직후 썸네일을 붙든다")
    spin(getattr(mw, "QUICK_REST_MS", 450) + 400)
    chk(not _held(), "B 조금 뒤 썸네일을 그린다(붙듦 풂)")

    # ── C 천천히 ──
    n0 = len(loads)
    for _ in range(2):
        QTest.keyClick(bt.tree, Qt.Key.Key_Down); spin(400)
    wait_file("f7"); spin(300)
    chk(loads[n0:] == ["f6", "f7"], "C 천천히 누르면 하나씩 연다", str(loads[n0:]))
    spin(800)

    # ── D 마우스 누름 ──
    n0 = len(loads)
    bt.tree.scrollToItem(row["f2"]); spin(100)
    r = bt.tree.visualItemRect(row["f2"])
    QTest.mouseClick(bt.tree.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, r.center())
    ok = wait_file("f2")
    chk(ok and not _held(), "D 마우스 누름은 종전대로 바로 다 연다(붙들지 않는다)", f"{cur_file()} held={_held()}")
    spin(800)

    # ── E Home ──
    bt.tree.setFocus()
    QTest.keyClick(bt.tree, Qt.Key.Key_Home)
    ok = wait_file("f0")
    chk(ok and _held(), "E Home 도 키라 표지 먼저", f"{cur_file()} held={_held()}")
    spin(900)
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
