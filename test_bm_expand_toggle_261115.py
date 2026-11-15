# -*- coding: utf-8 -*-
"""261115-8: 책갈피 모두 펼치기·접기 — 켜진 상태에서 다시 누르면 해제, 단축키 Ctrl+Shift+] / Ctrl+Shift+[ 도 같은 토글
(책갈피창·저장 SOT §4.7.3 '다시 누르면 해제' · 입력 SOT §3.2.4).

사용자 지시: "책갈피창의 책갈피 모두 펼치기 또는 모두 접기가 선택된 상태에서 1번 더 누르면 해제되도록 해. 단축키로 모두 펼치기는
Ctrl Shift + 이고, 모두 접기는 Ctrl Shift - 로 설정해. 단축키도 똑같이 누를 때마다 기존이 해제된 상태면 적용, 그렇지 않으면 해제 하도록해"

키는 사용자 결정(261115-8, 지휘 경유 '둘 다 다른 키로')으로 펼치기 Ctrl+Shift+] · 접기 Ctrl+Shift+[ — Ctrl+Shift++ 는 확대(Ctrl++)와 같은 누름이라.
A. 우클릭 '책갈피 모두 접기' 두 번 → 해제(체크 풀림, 줄 펼침은 그대로) · '모두 펼치기' 두 번 → 해제
B. 실제 키 Ctrl+Shift+[ / Ctrl+Shift+] 두 번 → 켜고 해제 · 메뉴 오른쪽 칸에 그 키 · 회전(Ctrl+[ / Ctrl+])은 일어나지 않는다
C. 배타 — 펼치기 켜진 채 접기 → 접기로 바뀜(해제가 아니다)
D. 해제 뒤 종전 동작 — 접기 해제 뒤 ↓ 는 파일을 펼친다 · 펼치기 해제 뒤 ↻ 는 저절로 펼치지 않는다
E. 아래 책갈피창에 포커스면 아래 창 · 사진 모드면 아무 일도 하지 않는다
수정 전 코드: 두 번 눌러도 켜진 채, 키는 아무 일도 하지 않는다.
"""
import os, sys, time, tempfile, shutil, faulthandler
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(240, exit=True)
from pathlib import Path

import fitz
from PyQt6.QtCore import Qt, QStandardPaths, QCoreApplication
from PyQt6.QtWidgets import QApplication, QMenu
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
QStandardPaths.setTestModeEnabled(True)               # 검사 작성 SOT §14.7.2 의 3
QCoreApplication.setApplicationName("polypdf_bm_toggle_%d" % os.getpid())
import modal_guard
modal_guard.install(label=lambda: "모두 펼치기·접기 토글", echo=False)   # §14.7.2 의 6
fails = []
CS = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def spin(ms=300):
    t = time.perf_counter()
    while (time.perf_counter() - t) * 1000 < ms:
        app.processEvents(); QTest.qWait(10)


errs = []
sys.excepthook = lambda t, v, tb: errs.append(f"{t.__name__}: {v}")
root = Path(tempfile.mkdtemp(prefix="polypdf_bm_toggle_"))
mw = None
try:
    import test_fixtures as _TFX; _TFX.autotag_off()
    for i in range(5):
        d = fitz.open()
        for k in range(4):
            d.new_page().insert_text((50, 80), f"f{i} p{k}")
        d.set_toc([[1, f"f{i} 장1", 1], [2, f"f{i} 절", 2], [1, f"f{i} 장2", 3]])
        d.save(str(root / f"f{i}.pdf")); d.close()

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
    row = {Path(n.data(0, bt.DATA_FILE)).stem: n for n in bt._iter_file_nodes()}
    chk(len(row) == 5, "준비 — 파일 5개", str(len(row)))

    def menu_action(text, it=None):
        got = {}
        orig = QMenu.exec

        def fake_exec(menu, *a, **k):
            for x in menu.actions():
                if x.text().split("\t")[0] == text:
                    got["a"] = x
            return None
        QMenu.exec = fake_exec
        try:
            bt._on_tree_context_menu(bt.tree.visualItemRect(it or row["f0"]).center())
        finally:
            QMenu.exec = orig
        return got.get("a")

    def press(t, ms=300):
        menu_action(t).trigger(); spin(ms)

    def key(k, w=None, ms=300):
        w = w or bt.tree
        w.setFocus(); spin(30)
        QTest.keyClick(w, k, CS); spin(ms)

    def state(b=None):
        b = b or bt
        return (b.is_expand_all_mode(), b.is_collapse_all_mode())

    def expanded():
        return sorted(s for s, n in row.items() if n.isExpanded())

    bt.tree.setFocus(); bt.tree.setCurrentItem(row["f0"]); spin(600)

    # ── A 메뉴 두 번 ──
    press("책갈피 모두 접기")
    chk(state() == (False, True) and not expanded(), "A 준비 — 모두 접기 켬, 다 접힘", f"{state()} {expanded()}")
    QTest.keyClick(bt.tree, Qt.Key.Key_Right); spin(500)        # 사용자가 f0 을 펼친다
    exp_before = expanded()
    press("책갈피 모두 접기")
    a = menu_action("책갈피 모두 접기")
    chk(state() == (False, False) and a is not None and not a.isChecked(),
        "A ★ 켜진 '모두 접기' 를 다시 누르면 해제(체크 풀림)", f"{state()} checked={a.isChecked() if a else None}")
    chk(expanded() == exp_before, "A 해제는 줄 펼침을 그대로 둔다", f"{exp_before} → {expanded()}")
    press("책갈피 모두 펼치기", 900)
    chk(state() == (True, False) and len(expanded()) == 5, "A 준비 — 모두 펼치기 켬, 보이는 파일 다 펼침", f"{state()} {expanded()}")
    press("책갈피 모두 펼치기")
    a = menu_action("책갈피 모두 펼치기")
    chk(state() == (False, False) and a is not None and not a.isChecked(),
        "A ★ 켜진 '모두 펼치기' 를 다시 누르면 해제", f"{state()}")
    chk(len(expanded()) == 5, "A 해제는 펼친 줄을 접지 않는다", str(expanded()))

    # ── D-1 펼치기 해제 뒤 종전 — ↻ 로 다시 채워도 저절로 펼치지 않는다 ──
    press("책갈피 모두 접기"); press("책갈피 모두 접기")          # 다 접은 뒤 해제
    chk(state() == (False, False) and not expanded(), "D 준비 — 다 접힌 평소 상태", f"{state()} {expanded()}")
    bt.refresh(); spin(800)
    row = {Path(n.data(0, bt.DATA_FILE)).stem: n for n in bt._iter_file_nodes()}
    chk(not [s for s, n in row.items() if n.isExpanded() and s != "f0"],
        "D 펼치기 해제 뒤 ↻ 는 보이는 파일을 저절로 펼치지 않는다", str(expanded()))

    # ── B 실제 키 ──
    bt.tree.setCurrentItem(row["f0"]); spin(300)
    key(Qt.Key.Key_BracketLeft)
    chk(state() == (False, True), "B Ctrl+Shift+[ 로 모두 접기 켬", str(state()))
    key(Qt.Key.Key_BracketLeft)
    chk(state() == (False, False), "B ★ Ctrl+Shift+[ 를 한 번 더 누르면 해제", str(state()))
    key(Qt.Key.Key_BracketRight, ms=900)
    chk(state() == (True, False) and len(expanded()) == 5, "B Ctrl+Shift+] 로 모두 펼치기 켬", f"{state()} {expanded()}")
    key(Qt.Key.Key_BracketRight)
    chk(state() == (False, False), "B ★ Ctrl+Shift+] 를 한 번 더 누르면 해제", str(state()))
    rot = []
    _r = mw._sc_objs["rotate_right"][1], mw._sc_objs["rotate_left"][1]
    for _o in _r:
        _o.activated.connect(lambda: rot.append(1))
    key(Qt.Key.Key_BracketRight); key(Qt.Key.Key_BracketRight)
    key(Qt.Key.Key_BracketLeft); key(Qt.Key.Key_BracketLeft)
    chk(not rot and state() == (False, False), "B 회전 키(Ctrl+] / Ctrl+[)와 겹치지 않는다 — 회전은 일어나지 않는다", f"rot={len(rot)} {state()}")
    a1 = menu_action("책갈피 모두 펼치기"); a2 = menu_action("책갈피 모두 접기")
    t1 = a1.text().split("\t")[1] if a1 and "\t" in a1.text() else ""
    t2 = a2.text().split("\t")[1] if a2 and "\t" in a2.text() else ""
    chk(t1.replace(" ", "") == "Ctrl+Shift+]" and t2.replace(" ", "") == "Ctrl+Shift+[",
        "B 메뉴 오른쪽 칸에 지금 키", f"{t1!r} {t2!r}")

    # ── C 배타 ──
    key(Qt.Key.Key_BracketRight, ms=600)
    key(Qt.Key.Key_BracketLeft)
    chk(state() == (False, True) and not expanded(), "C 펼치기 켜진 채 접기 → 접기로 바뀐다(해제가 아니다)", f"{state()} {expanded()}")
    press("책갈피 모두 펼치기", 600)
    chk(state() == (True, False), "C 접기 켜진 채 펼치기 → 펼치기로 바뀐다", str(state()))

    # ── D-2 접기 해제 뒤 ↓ 는 종전대로 펼친다 ──
    key(Qt.Key.Key_BracketLeft); key(Qt.Key.Key_BracketLeft)
    chk(state() == (False, False) and not expanded(), "D 준비 — 접은 뒤 해제", f"{state()} {expanded()}")
    bt.refresh(); spin(800)                              # 책갈피를 아직 읽지 않은 줄로 — 모두 접기 상태면 ↓ 로 와도 펼치지 않는 경우
    row = {Path(n.data(0, bt.DATA_FILE)).stem: n for n in bt._iter_file_nodes()}
    bt.tree.setFocus(); bt.tree.setCurrentItem(row["f1"]); spin(500)
    QTest.keyClick(bt.tree, Qt.Key.Key_Down); spin(900)
    chk(mv.current_file() and Path(mv.current_file()).stem == "f2" and row["f2"].isExpanded(),
        "D 접기 해제 뒤 ↓ 로 옮긴 (읽지 않은) 파일은 종전대로 펼친다", f"{mv.current_file()} exp={row['f2'].isExpanded()}")

    # ── E 사진 모드 · 아래 창 ──
    s0 = state()
    _orig = bt._photo_on
    bt._photo_on = lambda: True
    try:
        key(Qt.Key.Key_BracketLeft)
    finally:
        bt._photo_on = _orig
    chk(state() == s0, "E 사진 모드면 키가 아무 일도 하지 않는다", f"{s0} → {state()}")
    br = mw.bookmark_tree_right
    br.show(); spin(300)                                # 아래 책갈피창(2단의 아래 창)을 보이게 — test_shortcuts_chrome 과 같은 방법
    if br.isVisible():
        key(Qt.Key.Key_BracketLeft, w=br.tree)
        chk(state(br) == (False, True) and state() == s0, "E 아래 책갈피창에 포커스면 아래 창만", f"아래 {state(br)} 위 {state()}")
        key(Qt.Key.Key_BracketLeft, w=br.tree)
        chk(state(br) == (False, False), "E 아래 창도 한 번 더 누르면 해제", str(state(br)))
    else:
        chk(False, "E 준비 — 2단 보기에서 아래 책갈피창이 보인다")

    chk(not errs, "예외 없음", str(errs[:3]))
except Exception as e:
    import traceback; traceback.print_exc()
    chk(False, "검사 중 예외", repr(e))
finally:
    try:
        mw.close()
    except Exception:
        pass
    shutil.rmtree(root, ignore_errors=True)

print("FAILS:", len(fails))
for f in fails:
    print("  -", f)
sys.stdout.flush()
os._exit(1 if fails else 0)
