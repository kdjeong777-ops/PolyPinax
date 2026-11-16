# -*- coding: utf-8 -*-
"""261116-22: 발표 중 글자·숫자 키는 수식 없음(Shift·키패드만 허용)일 때만 — 발표 SOT §3.

실제 키 이벤트(QTest.keyClick)로:
A. Ctrl+S 는 상하 2분할을, Ctrl+D 는 좌우 2쪽을 바꾸지 않는다 — 수식 없는 S·D 는 바꾼다
B. Ctrl+6 은 쪽 번호 입력이 아니다 — 수식 없는 6·키패드 6 은 쪽 번호 입력
C. Backspace 는 한 글자 지우기, ESC 는 숫자 입력 중이면 입력만 비우고 창은 그대로
수정 전 코드: Ctrl+S·Ctrl+D·Ctrl+6 이 수식을 무시해 A·B 실패.
"""
import os, sys, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_preskeys261116_%d" % os.getpid())
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def spin(sec=0.2):
    t0 = time.time()
    while time.time() - t0 < sec:
        app.processEvents(); time.sleep(0.01)


try:
    from test_fixtures import text_pdf
    from viewer.widgets.presentation import PresentationWindow
    w = PresentationWindow(str(text_pdf()), 0, None)
    w.resize(1280, 720); w.show(); spin(0.3)
    CTRL, NONE = Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.NoModifier

    # A
    s0, d0 = w._split_mode, w._dual_mode
    QTest.keyClick(w, Qt.Key.Key_S, CTRL); spin(0.1)
    chk(w._split_mode == s0, "A1 Ctrl+S 는 상하 2분할을 바꾸지 않는다", str((s0, w._split_mode)))
    QTest.keyClick(w, Qt.Key.Key_D, CTRL); spin(0.1)
    chk(w._dual_mode == d0, "A2 Ctrl+D 는 좌우 2쪽을 바꾸지 않는다", str((d0, w._dual_mode)))
    QTest.keyClick(w, Qt.Key.Key_S, NONE); spin(0.1)
    chk(w._split_mode != s0, "A3 수식 없는 S 는 상하 2분할 토글")
    QTest.keyClick(w, Qt.Key.Key_S, NONE); spin(0.1)
    QTest.keyClick(w, Qt.Key.Key_D, NONE); spin(0.1)
    chk(w._dual_mode != d0, "A4 수식 없는 D 는 좌우 2쪽 토글")
    QTest.keyClick(w, Qt.Key.Key_D, NONE); spin(0.1)

    # B
    w._numbuf = ""
    QTest.keyClick(w, Qt.Key.Key_6, CTRL); spin(0.1)
    chk(w._numbuf == "", "B1 Ctrl+6 은 쪽 번호 입력이 아니다", repr(w._numbuf))
    QTest.keyClick(w, Qt.Key.Key_6, NONE); spin(0.1)
    QTest.keyClick(w, Qt.Key.Key_2, Qt.KeyboardModifier.KeypadModifier); spin(0.1)
    chk(w._numbuf == "62", "B2 수식 없는 6·키패드 2 는 쪽 번호 입력", repr(w._numbuf))

    # C
    QTest.keyClick(w, Qt.Key.Key_Backspace, NONE); spin(0.1)
    chk(w._numbuf == "6", "C1 Backspace 는 한 글자 지우기", repr(w._numbuf))
    QTest.keyClick(w, Qt.Key.Key_Escape, NONE); spin(0.1)
    chk(w._numbuf == "" and w.isVisible(), "C2 숫자 입력 중 ESC 는 입력만 비우고 창은 그대로", repr(w._numbuf))
    w.close(); spin(0.1)
except Exception:
    import traceback
    traceback.print_exc()
    fails.append("예외")

print("\n=== " + ("ALL PASS" if not fails else "FAILURE (%d)" % len(fails)) + " ===")
for m in fails:
    print(" -", m)
sys.stdout.flush()
os._exit(1 if fails else 0)
