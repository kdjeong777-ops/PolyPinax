# -*- coding: utf-8 -*-
"""테마를 바꾸는 중(app.setStyle) 앱이 죽지 않는다 — 파이썬 GC 를 멈추고 바꾼다 (261115-2 덧붙임, 화면 디자인 SOT §4.1 함정).

증상: test_merge_thread 가 `_apply_prefs → apply_theme → app.setStyle` 에서 0xC0000005 로 자주 죽었다(4개 동시 8번 중 4~7번).
원인: `QApplication::setStyle` 은 위젯 목록을 복사해 둔 채 위젯마다 unpolish·polish·StyleChange 를 보낸다. 그 사이 파이썬 코드
(앱 위젯의 event·changeEvent, 파이썬 앱 스타일)가 돌면서 GC 가 순환 참조로 남은 부모 없는 위젯을 지우면, 복사해 둔 목록에
지워진 위젯 포인터가 남아 Qt 가 그것을 만진다. 261115-2 이전 코드도 같은 조건에서 24번 중 4번 죽었다(덧그리기는 빈도만 올림).
고침: `MainWindow.apply_theme` 이 `gc.collect()` 뒤 GC 를 멈추고 setStyle, 끝나면 되돌린다.

부모 없는 위젯을 순환 참조로 남기고 GC 문턱을 1 로 낮춘 채 실제 `MainWindow.apply_theme` 을 되풀이한다 — 자식 프로세스로 돌려
죽으면 FAIL 로 적는다(검사 작성 SOT §14.7.2 — 실제 경로, 수정 전 코드로 실패 확인).
A. 테마를 다크·라이트로 여러 번 바꿔도 자식이 끝까지 간다(종료 코드 0, 'CHILD-OK')
B. apply_theme 뒤 GC 가 다시 켜져 있다
C. 다크로 바꾼 뒤 스크롤바 화살표 덧그리기(§2.5)는 그대로 — 세로 스크롤바 ▲ 가운데 밝기 ≥ 215
"""
import os, sys, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))


def child():
    import gc
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    sys.path.insert(0, HERE)
    from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
    QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2 의 3
    from PyQt6.QtWidgets import QApplication, QListWidget, QStyle, QStyleOptionSlider
    from PyQt6.QtTest import QTest
    app = QApplication.instance() or QApplication(sys.argv[:1])
    QCoreApplication.setApplicationName("polypdf_theme_gc_%d" % os.getpid())
    import modal_guard
    modal_guard.install(label=lambda: "테마 바꾸기 GC", echo=False)   # §14.7.2 의 6
    from viewer.app import MainWindow
    mw = MainWindow(); mw.resize(1100, 700); mw.show()
    for _ in range(10):
        app.processEvents(); QTest.qWait(15)
    gc.set_threshold(1, 1, 1)                           # 파이썬 객체 하나만 생겨도 GC — setStyle 중 GC 를 일부러 부른다
    for i in range(8):
        for k in range(60):                             # 부모 없는 위젯을 순환 참조로 남긴다(파이썬이 가진 위젯)
            w = QListWidget(); w.addItems(["항목 %d" % j for j in range(30)]); w.resize(120, 80)
            w._me = w
            w.ensurePolished()
        w = None
        mw.apply_theme("dark" if i % 2 == 0 else "light")
        print("GC-ON", i, gc.isenabled()); sys.stdout.flush()
        app.processEvents()
    gc.set_threshold(700, 10, 10)
    mw.apply_theme("dark")
    lw = QListWidget(); lw.addItems(["줄 %d" % j for j in range(200)]); lw.resize(200, 160); lw.show()
    for _ in range(5):
        app.processEvents(); QTest.qWait(15)
    sb = lw.verticalScrollBar()
    img = sb.grab().toImage()
    opt = QStyleOptionSlider(); sb.initStyleOption(opt)
    r = sb.style().subControlRect(QStyle.ComplexControl.CC_ScrollBar, opt, QStyle.SubControl.SC_ScrollBarSubLine, sb)
    c = r.center()
    lum = max(int(0.299 * q.red() + 0.587 * q.green() + 0.114 * q.blue())
              for q in (img.pixelColor(c.x() + dx, c.y() + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)))
    print("ARROW-LUM", lum)
    print("CHILD-OK"); sys.stdout.flush()
    os._exit(0)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    fails = []

    def chk(cond, msg, extra=""):
        print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
        if not cond:
            fails.append(msg)

    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    runs = []
    for n in range(2):
        try:
            r = subprocess.run([sys.executable, "-X", "faulthandler", os.path.abspath(__file__), "--child"],
                               cwd=HERE, env=env, capture_output=True, timeout=240)
            out = (r.stdout + r.stderr).decode("utf-8", "replace")
            runs.append((r.returncode & 0xFFFFFFFF, out))
        except subprocess.TimeoutExpired:
            runs.append((-1, "timeout"))
    for n, (rc, out) in enumerate(runs):
        tail = out[out.find("Windows fatal"):][:600] if "Windows fatal" in out else out[-600:]
        chk(rc == 0 and "CHILD-OK" in out, "A%d. 테마를 8번 바꿔도 죽지 않음" % (n + 1), "rc=%s\n%s" % (hex(rc) if rc >= 0 else rc, tail))
        gcs = [ln for ln in out.splitlines() if ln.startswith("GC-ON")]
        chk(len(gcs) == 8 and all(ln.endswith("True") for ln in gcs), "B%d. apply_theme 뒤 GC 다시 켜짐" % (n + 1), str(gcs))
        lums = [int(ln.split()[1]) for ln in out.splitlines() if ln.startswith("ARROW-LUM")]
        chk(lums and lums[0] >= 215, "C%d. 다크 스크롤바 ▲ 밝기 ≥ 215(§2.5 덧그리기 유지)" % (n + 1), str(lums))
    print()
    print("ALL PASS" if not fails else "%d FAIL: %s" % (len(fails), fails))
    sys.stdout.flush()
    os._exit(0 if not fails else 1)


if __name__ == "__main__":
    if "--child" in sys.argv:
        child()
    else:
        main()
