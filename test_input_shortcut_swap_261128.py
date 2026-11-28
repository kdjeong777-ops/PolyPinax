# -*- coding: utf-8 -*-
"""단축키 맞바꿈 — 보기 탭 Ctrl+1~9, 꾸미기 선 1~5 Ctrl+Shift+1~5 (입력 SOT §3.2.1, 261128-14).

A 기본값 — 보기 9개 Ctrl+숫자, 선 5개 Ctrl+Shift+숫자, 발표 펜 기본도 Ctrl+Shift, 둘이 겹치지 않는다
B 실제 키(편집 모드) — Ctrl+Shift+1·3 → 선 1·3, Ctrl+2 → 2단·선은 그대로, Ctrl+1 → 1단
C 발표 창 — Windows 가 보내는 Shift+숫자(`!`, 가상 키 0x31)도 Ctrl+Shift+1 로 맞춘다
D 설정 판 15 — 옛 기본값만 옮기고, 사용자가 바꾼 키·다른 id 에 둔 키는 그대로
수정 전 코드는 A·B·C·D 모두 실패한다.
"""
import os, sys, tempfile, time, shutil
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pathlib import Path
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QEvent
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtTest import QTest
app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_keys_swap_%d" % os.getpid())
import modal_guard
modal_guard.install(label=lambda: "단축키 맞바꿈", echo=False)
fails = []
C, CS = Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


def pump(cond=None, timeout=8.0):
    t = time.monotonic()
    while time.monotonic() - t < timeout:
        app.processEvents()
        if cond is not None and cond():
            return True
        if cond is None and time.monotonic() - t > 0.3:
            return True
        time.sleep(0.01)
    return False


import fitz
root = Path(tempfile.mkdtemp(prefix="polypdf_keys_"))
try:
    folder = root / "docs"; folder.mkdir()
    pdf = folder / "a.pdf"
    d = fitz.open()
    for i in range(3):
        d.new_page().insert_text((72, 100), "page %d" % (i + 1))
    d.save(str(pdf)); d.close()

    from viewer.app import MainWindow
    mw = MainWindow(); mw._skip_save_on_close = True
    mw.resize(1300, 850); mw.show(); pump()
    # ── A ──
    defs = mw._sc_defs
    views = ("view_single", "toggle_split", "view_text", "view_study", "view_search", "view_shot", "view_law", "view_kipo", "view_kcsc")
    chk([defs[s][1] for s in views] == ["Ctrl+%d" % i for i in range(1, 10)], "A1 보기 탭 기본 = Ctrl+1~9",
        str([defs[s][1] for s in views]))
    chk([defs["draw_pen_%d" % i][1] for i in range(1, 6)] == ["Ctrl+Shift+%d" % i for i in range(1, 6)],
        "A2 선 1~5 기본 = Ctrl+Shift+1~5")
    from viewer.widgets import presentation
    chk(presentation.DEFAULT_PEN_KEYS[0] == "Ctrl+Shift+1", "A3 발표 펜 기본도 Ctrl+Shift", str(presentation.DEFAULT_PEN_KEYS))
    keys = [v[1].replace(" ", "").lower() for v in defs.values() if v[1]]
    chk(len(keys) == len(set(keys)), "A4 기본 단축키끼리 겹치지 않는다", str(sorted(k for k in keys if keys.count(k) > 1)))

    # ── B 실제 키 ──
    bt = mw.bookmark_tree
    mw.open_folder(folder); pump(lambda: sum(1 for _ in bt._iter_file_nodes()) == 1)
    mw.open_pdf(pdf); pump()
    bt.btn_edit.setChecked(True); pump()
    mv = mw.main_view
    tgt = mv.view
    mv.view.setFocus(); pump()
    QTest.keyClick(tgt, Qt.Key.Key_1, CS); pump()
    chk(mv._pen_idx == 0, "B1 Ctrl+Shift+1 → 선 1", str(mv._pen_idx))
    QTest.keyClick(tgt, Qt.Key.Key_3, CS); pump()
    chk(mv._pen_idx == 2, "B2 Ctrl+Shift+3 → 선 3", str(mv._pen_idx))
    QTest.keyClick(tgt, Qt.Key.Key_2, C); pump()
    chk(mw.act_split.isChecked() and mv._pen_idx == 2, "B3 Ctrl+2 → 2단, 선은 그대로", str((mw.act_split.isChecked(), mv._pen_idx)))
    mw.main_view.view.setFocus(); pump()
    QTest.keyClick(mw.main_view.view, Qt.Key.Key_1, C); pump()
    chk(not mw.act_split.isChecked(), "B4 Ctrl+1 → 1단")

    # ── C 발표 창의 Shift+숫자 ──
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Exclam, CS, 0, 0x31, 0, "!")
    names = presentation._pressed_names(ev)
    chk("ctrl+shift+1" in names, "C1 Windows 의 Ctrl+Shift+! (가상 키 '1')도 Ctrl+Shift+1 로 맞춘다", str(names))
    ev2 = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_2, CS)
    chk("ctrl+shift+2" in presentation._pressed_names(ev2), "C2 Qt 가 숫자로 보내도(오프스크린) 맞춘다")
    mw.close()

    # ── D 설정 판 15 ──
    from viewer import settings_store as ss
    dct = {"schema_version": 14, "preferences": {"shortcuts": {
        "view_single": "Ctrl+Shift+1", "toggle_split": "Ctrl+Shift+2", "view_text": "F9",      # 바꾼 키는 그대로
        "draw_pen_1": "Ctrl+1", "draw_pen_2": "Ctrl+2", "draw_pen_3": "Alt+3",
        "view_search": "Ctrl+Shift+5", "print": "Ctrl+5"}}}                                     # Ctrl+5 를 사용자가 다른 일에
    out = ss._migrate(dct)["preferences"]["shortcuts"]
    chk(out["view_single"] == "Ctrl+1" and out["toggle_split"] == "Ctrl+2" and out["view_text"] == "F9",
        "D1 보기 — 옛 기본값만 Ctrl+숫자로, 바꾼 키는 그대로", str(out))
    chk(out["draw_pen_1"] == "Ctrl+Shift+1" and out["draw_pen_2"] == "Ctrl+Shift+2" and out["draw_pen_3"] == "Alt+3",
        "D2 선 — 옛 기본값만 Ctrl+Shift+숫자로", str(out))
    chk(out["view_search"] == "Ctrl+Shift+5", "D3 새 키가 사용자가 다른 일에 둔 키면 옛 값 그대로(빼앗지 않는다)", str(out))
    chk(ss._migrate(dict(dct))["schema_version"] == ss.CURRENT_SCHEMA == 15, "D4 판 15·다시 돌려도 같다")
finally:
    shutil.rmtree(root, ignore_errors=True)

print("ALL PASS" if not fails else f"{len(fails)} FAIL")
sys.stdout.flush()
os._exit(1 if fails else 0)
