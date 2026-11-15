# -*- coding: utf-8 -*-
"""261115-10: '책갈피 모두 접기' 상태에서 ↑↓ 가 건너뛰거나 거꾸로 가지 않는다 (책갈피창·저장 SOT §4.7.3).

사용자 보고: "책갈피창이 접기 상태에서 위아래로 이동시 2번이상 내리기를 해야 내려갈 때가 있고, 아래로 내려가다 올라갈 때도 있어.
아마 접힌상태에도 내부 책갈피항목을 인식하는거 같아"

원인: 처음 보는 PDF 는 배경에서 데운 뒤 연다(응답성 SOT §4.9). 빠르게 ↓ 하면 지나온 파일이 그 사이 데우기를 마치고 열려,
그 쪽 알림(`_sync_bookmark_to_active` → `select_for_page`)이 이미 앞에 가 있는 고른 줄을 지나온 파일로 되돌렸다.
검사는 데우기를 느리게(백신 검사처럼) 하고 늘 '처음 보는 파일' 로 둔다.

A. 실제 ↓↑ 를 300·150·80·40ms 간격으로 — 누를 때마다 보이는 다음(이전) 줄로 한 칸, 간격이 지나도 그 줄 그대로
B. 멈추면 본문 = 고른 줄의 파일, 펼친 파일 없음
C. 데우는 중(새 열기 대기)에 앞 파일의 쪽 알림이 와도 고른 줄을 되돌리지 않는다 · 데우기가 끝나면 본문이 그 파일
D. 펼친 파일 안의 접힌 책갈피 쪽으로 본문이 가면 보이는 조상(접힌 책갈피 줄)을 고르고 펼치지 않는다
E. 상태가 없으면 종전대로 — 접힌 책갈피 안 쪽은 그 책갈피를 고른다(펼쳐 보인다)
"""
import os, sys, time, tempfile, shutil, faulthandler
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(300, exit=True)
from pathlib import Path

import fitz
from PyQt6.QtCore import Qt, QStandardPaths, QCoreApplication
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
import modal_guard
modal_guard.install(label=lambda: "모두 접기 ↑↓ 되돌림", echo=False)   # 검사 작성 SOT §14.7.2 의 6
QStandardPaths.setTestModeEnabled(True)                                # 검사 작성 SOT §14.7.2 의 3
QCoreApplication.setApplicationName("polypdf_collapse_stale_%d" % os.getpid())
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def spin(ms):
    t = time.perf_counter()
    while (time.perf_counter() - t) * 1000 < ms:
        app.processEvents(); QTest.qWait(5)


# 데우기를 느리게, 늘 처음 보는 파일로 — 백신이 막 보게 된 파일을 검사하는 동안(응답성 SOT §4.9)
import viewer.workers as W
W.is_warm = lambda p: False
_orun = W.WarmReadWorker.run
WARM_S = [0.35]


def _slow_run(self):
    time.sleep(WARM_S[0])
    _orun(self)


W.WarmReadWorker.run = _slow_run

root = Path(tempfile.mkdtemp(prefix="polypdf_collapse_stale_"))
try:
    names = [f"f{i:02d}" for i in range(12)]
    for n in names:
        d = fitz.open()
        for k in range(8):
            d.new_page().insert_text((50, 80), f"{n} p{k}")
        d.set_toc([[1, f"{n} A", 1], [2, f"{n} a", 3], [1, f"{n} B", 6]])
        d.save(str(root / f"{n}.pdf")); d.close()

    from viewer.app import MainWindow
    mw = MainWindow(); mw.resize(1200, 800); mw.show(); app.processEvents()
    bt = mw.bookmark_tree; mv = mw.main_view
    bt.load_folder(root); spin(800)
    try:
        bt.set_tree_view(False)
        bt.set_sort_mode(bt.SORT_NAME)
    except Exception:
        pass
    bt.btn_edit.setChecked(False); spin(200)
    files = list(bt._iter_file_nodes())
    row = {Path(n.data(0, bt.DATA_FILE)).stem: n for n in files}
    chk(len(files) == 12, "준비 — 파일 12개", str(len(files)))

    def name(it):
        if it is None:
            return None
        d = it.data(0, bt.DATA_FILE)
        return (Path(d).stem if d else "?") + ("" if bt._is_file_node(it) else ":" + it.text(0))

    def cur_file():
        f = mv.current_file()
        return Path(f).stem if f else None

    def wait_file(stem, ms=4000):
        t = time.perf_counter()
        while cur_file() != stem and (time.perf_counter() - t) * 1000 < ms:
            spin(20)
        return cur_file() == stem

    bt.tree.setFocus()
    bt.tree.setCurrentItem(row["f00"]); wait_file("f00"); spin(300)
    bt.toggle_expand_all(False); spin(300)                  # 모두 접기(메뉴와 같은 함수)
    chk(bt.is_collapse_all_mode() and not any(n.isExpanded() for n in files), "준비 — 모두 접기 상태, 펼친 파일 없음")
    bt.tree.setCurrentItem(row["f00"]); spin(600)

    # ── A·B ──
    for gap in (300, 150, 80, 40):
        bad = []
        bt.tree.setFocus()
        for k in [Qt.Key.Key_Down] * 7 + [Qt.Key.Key_Up] * 5:
            before = bt.tree.currentItem()
            exp = bt.tree.itemBelow(before) if k == Qt.Key.Key_Down else bt.tree.itemAbove(before)
            QTest.keyClick(bt.tree, k)
            now = bt.tree.currentItem()
            spin(gap)
            later = bt.tree.currentItem()
            if exp is not None and (now is not exp or later is not exp):
                bad.append(f"{name(before)}→기대 {name(exp)} · 누른 직후 {name(now)} · {gap}ms 뒤 {name(later)}")
        chk(not bad, f"A {gap}ms 간격 ↓↑ — 누를 때마다 보이는 다음(이전) 줄로 한 칸, 되돌아가지 않는다", "\n    " + "\n    ".join(bad[:5]))
        last = name(bt.tree.currentItem())
        ok = wait_file(last); spin(400)
        chk(ok and name(bt.tree.currentItem()) == last, f"B {gap}ms — 멈추면 본문 = 고른 줄의 파일", f"{cur_file()} / {name(bt.tree.currentItem())}")
        chk(not any(n.isExpanded() for n in files), f"B {gap}ms — 펼친 파일 없음",
            str([name(n) for n in files if n.isExpanded()]))

    # ── C 데우는 중 앞 파일 쪽 알림 ──
    WARM_S[0] = 1.2
    start = name(bt.tree.currentItem())
    spin(400)                                               # 모으기 시간(QUICK_HOLD_MS)이 지나 곧바로 내보낸다
    QTest.keyClick(bt.tree, Qt.Key.Key_Down)
    tgt = bt.tree.currentItem()
    spin(150)
    chk(mw._main_opening() and cur_file() == start, "C 준비 — 새 파일을 데우는 중, 본문은 아직 앞 파일",
        f"opening={mw._main_opening()} {cur_file()} {start}")
    mv.go_to_page(2)                                        # 앞 파일 쪽 알림(썸네일·이어 보기 멈춤 알림 등과 같은 신호)
    spin(100)
    chk(bt.tree.currentItem() is tgt, "C ★ 데우는 중 앞 파일 쪽 알림이 고른 줄을 되돌리지 않는다", name(bt.tree.currentItem()))
    ok = wait_file(name(tgt), 5000); spin(300)
    chk(ok and bt.tree.currentItem() is tgt, "C 데우기가 끝나면 본문 = 고른 줄의 파일", f"{cur_file()} {name(bt.tree.currentItem())}")
    WARM_S[0] = 0.35

    # ── D 접힌 책갈피 안 쪽 → 보이는 조상 ──
    f5 = row["f05"]
    bt.tree.setCurrentItem(f5); ok = wait_file("f05"); spin(300)
    bt.tree.setFocus()
    QTest.keyClick(bt.tree, Qt.Key.Key_Right); spin(800)    # → 로 펼친다(사용자 펼침)
    chk(ok and f5.isExpanded() and f5.childCount() >= 2, "D 준비 — → 로 f05 를 펼쳤다", f"{f5.isExpanded()} {f5.childCount()}")
    a_row = next((f5.child(i) for i in range(f5.childCount()) if f5.child(i).text(0) == "f05 A"), None)
    if a_row is not None:
        a_row.setExpanded(False); spin(100)
    mv.go_to_page(3); spin(300)                             # 'f05 a'(3쪽, A 아래)
    cur = bt.tree.currentItem()
    chk(a_row is not None and cur is a_row and not a_row.isExpanded(),
        "D ★ 모두 접기 상태 — 본문 쪽이 접힌 책갈피 안이면 보이는 조상(f05 A)을 고르고 펼치지 않는다",
        f"{name(cur)} A펼침={a_row.isExpanded() if a_row else None}")

    # ── E 상태 없음 → 종전대로 ──
    bt.toggle_expand_all(False); spin(200)                  # 다시 누르면 해제(261115-8)
    chk(not bt.is_collapse_all_mode(), "E 준비 — 모두 접기 해제")
    mv.go_to_page(0); spin(200)
    if a_row is not None:
        a_row.setExpanded(False); spin(100)
    mv.go_to_page(3); spin(300)
    cur = bt.tree.currentItem()
    chk(cur is not None and cur.text(0) == "f05 a", "E 상태가 없으면 종전대로 — 그 책갈피(f05 a)를 고른다", name(cur))
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
