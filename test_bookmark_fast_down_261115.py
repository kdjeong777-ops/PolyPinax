# -*- coding: utf-8 -*-
"""책갈피창에서 아래 파일로 빠르게 내리기 — 속도·정지·고른 파일 (261115-11, 응답성 SOT §7.6·§8, 책갈피창·저장 SOT §4.7.3).

사용자 지시(2026-11-15): "책갈피창에서 아래 파일로 빠르게 내리면서 속도 등에 문제없는지 체크해. 향후 테스트에 항상 포함시켜."
→ 이 검사(전체 검사 `checks` 에 늘 들어간다)와 부하 시험(`scripts/load_test.py` '책갈피창 ↓ …' — 큰 실제 폴더·색인 중, 릴리스마다).

파일 40개(각 30쪽·목차 3개) 폴더, 단일(파일) 목록·트리 둘 다:
A. 펼친 상태에서 ↓ 연타(30ms × 39, 책갈피 줄도 지나간다) — 가장 긴 멈춤 < 1초, 끝에 본문 = 고른 파일(지나가는 파일을 하나씩 여는 것은 설계 — 수만 적는다)
B. ↓ 꾹 누르기(자동 반복 키 이벤트 20ms × 39) — 같은 판정
C. 모두 접기 상태에서 ↓ 연타 — 같은 판정, 연 파일 ≤ 3
D. 맨 끝에서 ↑ 연타로 되돌아오기 — 같은 판정
E. 내린 뒤 1.5초 안에 본문·썸네일·텍스트 창이 고른 파일로 따라온다(멈춘 뒤 뒤처리가 끝난다)
"""
import os, sys, time, tempfile, shutil, faulthandler
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.pop("POLYPDF_FAKE_POWER_SAVING", None)
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(400, exit=True)
from pathlib import Path

import fitz
from PyQt6.QtCore import Qt, QStandardPaths, QCoreApplication, QTimer, QElapsedTimer, QEvent
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QMenu
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
QStandardPaths.setTestModeEnabled(True)               # 검사 작성 SOT §14.7.2 의 3
QCoreApplication.setApplicationName("polypdf_fast_down_%d" % os.getpid())
import modal_guard
modal_guard.install(label=lambda: "빠른 내림", echo=False)   # §14.7.2 의 6
N_FILES = 40
STALL_LIMIT_MS = 1000                                  # 응답성 SOT §5
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def spin(ms=300):
    t = time.perf_counter()
    while (time.perf_counter() - t) * 1000 < ms:
        app.processEvents(); QTest.qWait(5)


root = Path(tempfile.mkdtemp(prefix="polypdf_fast_down_"))
try:
    for i in range(N_FILES):
        d = fitz.open()
        for k in range(30):
            pg = d.new_page()
            pg.insert_text((60, 90), f"file{i:02d} page{k} fast down text body", fontsize=12)
            pg.insert_text((60, 130), "lorem ipsum " * 8, fontsize=9)
        d.set_toc([[1, f"f{i:02d} 장1", 1], [1, f"f{i:02d} 장2", 10], [1, f"f{i:02d} 장3", 20]])
        d.save(str(root / f"f{i:02d}.pdf")); d.close()

    from viewer.app import MainWindow
    mw = MainWindow(); mw._skip_save_on_close = True
    mw.resize(1300, 850); mw.show(); app.processEvents()
    bt = mw.bookmark_tree; mv = mw.main_view
    loads = []
    _orig_ld = mv.load_document

    def _spy_ld(path, *a, **k):
        loads.append(Path(str(path)).stem)
        return _orig_ld(path, *a, **k)
    mv.load_document = _spy_ld

    def cur_file():
        f = mv.current_file()
        return Path(f).stem if f else None

    def sel_file():
        it = bt.tree.currentItem()
        while it is not None and not it.data(0, bt.DATA_FILE):
            it = it.parent()
        return Path(it.data(0, bt.DATA_FILE)).stem if it is not None else None

    def wait_follow(ms=4000):
        t = time.perf_counter()
        while cur_file() != sel_file() and (time.perf_counter() - t) * 1000 < ms:
            app.processEvents(); QTest.qWait(5)
        return cur_file() == sel_file()

    def menu_action(text, it):
        got = {}
        orig = QMenu.exec

        def fake_exec(menu, *a, **k):
            for x in menu.actions():
                if x.text().split("\t")[0] == text:
                    got["a"] = x
            return None
        QMenu.exec = fake_exec
        try:
            bt._on_tree_context_menu(bt.tree.visualItemRect(it).center())
        finally:
            QMenu.exec = orig
        return got.get("a")

    beat = QElapsedTimer(); beat.start(); worst = [0]

    def tick():
        worst[0] = max(worst[0], beat.restart())
    hb = QTimer(); hb.setInterval(10); hb.timeout.connect(tick); hb.start()

    def run(label, key, n, gap_ms, autorep=False):
        """`key` 를 n 번(gap_ms 간격) — 그 동안과 뒤따라오기까지의 가장 긴 멈춤·연 파일."""
        spin(300)
        n0 = len(loads)
        worst[0] = 0; beat.restart()
        bt.tree.setFocus()
        t0 = time.perf_counter()
        for _ in range(n):
            if autorep:
                QApplication.sendEvent(bt.tree, QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, "", True))
            else:
                QTest.keyClick(bt.tree, key)
            app.processEvents(); QTest.qWait(gap_ms)
        if autorep:
            QApplication.sendEvent(bt.tree, QKeyEvent(QEvent.Type.KeyRelease, key, Qt.KeyboardModifier.NoModifier, "", False))
        keys_s = time.perf_counter() - t0
        ok = wait_follow()
        follow_s = time.perf_counter() - t0 - keys_s
        spin(1500)                                     # 멈춘 뒤 뒤처리(썸네일·텍스트 창)까지
        opened = loads[n0:]
        print(f"  [{label}] 키 {n}번 {keys_s:.2f}s · 따라오기 {follow_s:.2f}s · 가장 긴 멈춤 {worst[0]}ms · 연 파일 {len(opened)}개 {opened[:6]}")
        return ok, worst[0], opened, follow_s

    bt.load_folder(root); spin(1200)
    for tree_mode in (False, True):
        mode = "트리" if tree_mode else "단일"
        try:
            bt.set_tree_view(tree_mode); bt.set_sort_mode(bt.SORT_NAME)
        except Exception:
            pass
        bt.btn_edit.setChecked(False); spin(400)
        row = {Path(n.data(0, bt.DATA_FILE)).stem: n for n in bt._iter_file_nodes()}
        chk(len(row) == N_FILES, f"{mode} 준비 — 파일 {N_FILES}개", str(len(row)))
        bt.tree.setFocus(); bt.tree.setCurrentItem(row["f00"]); wait_follow(); spin(900)

        # A 펼친 상태 연타 — 펼친 책갈피 줄도 지나간다
        ok, w, opened, fs = run(f"{mode} A 연타", Qt.Key.Key_Down, N_FILES - 1, 30)
        chk(ok, f"{mode} A ↓ 연타 뒤 본문 = 고른 파일", f"본문 {cur_file()} · 고름 {sel_file()}")
        chk(w < STALL_LIMIT_MS, f"{mode} A ↓ 연타 내내 가장 긴 멈춤 < 1초", f"{w}ms")
        # 펼친 상태는 지나가는 파일을 하나씩 연다 — 설계(261114-5 사용자 결정: '멈춘 파일만' 은 모두 접기·가벼운 넘김일 때). 수만 적는다
        chk(fs < 1.5, f"{mode} E 키를 멈춘 뒤 1.5초 안에 본문이 고른 파일로", f"{fs:.2f}s")

        # B 꾹 누르기(자동 반복)
        bt.tree.setCurrentItem(row["f00"]); wait_follow(); spin(900)
        ok, w, opened, fs = run(f"{mode} B 꾹", Qt.Key.Key_Down, N_FILES - 1, 20, autorep=True)
        chk(ok, f"{mode} B ↓ 꾹 누르기 뒤 본문 = 고른 파일", f"본문 {cur_file()} · 고름 {sel_file()}")
        chk(w < STALL_LIMIT_MS, f"{mode} B ↓ 꾹 누르기 내내 가장 긴 멈춤 < 1초", f"{w}ms")

        # D 맨 끝에서 ↑ 로 되돌아오기
        ok, w, opened, fs = run(f"{mode} D 되돌아오기", Qt.Key.Key_Up, N_FILES - 1, 30)
        chk(ok and w < STALL_LIMIT_MS, f"{mode} D ↑ 연타로 되돌아와도 고른 파일·멈춤 < 1초", f"{w}ms 본문 {cur_file()} 고름 {sel_file()}")

        # C 모두 접기 상태
        a = menu_action("책갈피 모두 접기", row["f00"])
        if a is not None:
            a.trigger(); spin(300)
            bt.tree.setCurrentItem(row["f00"]); wait_follow(); spin(900)
            ok, w, opened, fs = run(f"{mode} C 접기 연타", Qt.Key.Key_Down, N_FILES - 1, 30)
            chk(ok and sel_file() == f"f{N_FILES - 1:02d}", f"{mode} C 모두 접기 ↓ 연타 — 맨 끝 파일까지·본문 = 고른 파일", f"고름 {sel_file()} 본문 {cur_file()}")
            chk(w < STALL_LIMIT_MS, f"{mode} C 모두 접기 ↓ 연타 내내 가장 긴 멈춤 < 1초", f"{w}ms")
            chk(len(set(opened)) <= 3, f"{mode} C 모두 접기 — 연 파일 ≤ 3(멈춘 파일만)", str(opened))
            b = menu_action("책갈피 모두 펼치기", row["f00"])
            if b is not None:
                b.trigger(); spin(600)
        else:
            chk(False, f"{mode} C 준비 — '책갈피 모두 접기' 메뉴")
    hb.stop()
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
