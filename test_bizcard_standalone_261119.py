# -*- coding: utf-8 -*-
"""명함 프로그램 — 본 화면 명함 아이콘·별도 프로세스 (명함 SOT §5.27, D32).

실제 MainWindow 로(오프스크린, 시험 모드·임시 데이터 — 검사 작성 SOT §14.7.2).
A. 아이콘 — 탭 줄 왼쪽 칸, PDF↔사진 모드 아이콘 바로 오른쪽 · 명함 폴더가 비면 숨김 · 설정을 바꾸면 곧바로
B. 도구 탭에 `명함 ▾` 없음
C. 누르면 `--bizcard` 를 따로 띄움(명령 꼴) · 경계 — 명함 모듈이 viewer.app 을 import 하지 않음
D. 실제 프로세스 — `main.py --bizcard`(시험 프로필)가 명함찾기 창을 띄우고 단일 실행 통로를 연다, 둘째 실행은 첫째를 앞으로 보내고 곧 끝남
"""
import os, sys, tempfile, time, subprocess
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtTest import QTest
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_standalone_%d" % os.getpid())
fails = []
TMP = Path(tempfile.mkdtemp(prefix="bizcard_alone_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def pump(cond=None, timeout=15.0):
    t = time.monotonic()
    while time.monotonic() - t < timeout:
        app.processEvents()
        if cond is not None and cond():
            return True
        if cond is None and time.monotonic() - t > 0.3:
            return True
        time.sleep(0.01)
    return False


def finish():
    print("FAILURES: %d" % len(fails))
    for f in fails:
        print("  -", f)
    sys.stdout.flush()
    os._exit(1 if fails else 0)


procs = []
try:
    from viewer.app import MainWindow
    import modal_guard
    modal_guard.install(label=lambda: "명함 프로그램", echo=False)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    mw = MainWindow(); mw._skip_save_on_close = True
    mw.resize(1200, 800)
    mw.show()
    pump(timeout=1.0)
    print("=== A. 아이콘 ===")
    b = getattr(mw, "_bizcard_btn", None)
    pb = getattr(mw, "_photo_btn", None)
    lay = mw._ribbon.left_fill.layout()
    chk(b is not None and pb is not None and lay.indexOf(b) == lay.indexOf(pb) + 1, "A 명함 아이콘은 모드 아이콘 바로 오른쪽(같은 칸)")
    pic = mw._prefs.setdefault("picture", {})
    pic.pop("bizcard_folder", None)
    mw._gate_api_dependent_ui(mw._prefs)
    chk(b is not None and not b.isVisible(), "A 명함 폴더가 비면 숨김")
    F = TMP / "cards"
    F.mkdir()
    pic["bizcard_folder"] = str(F)
    mw._gate_api_dependent_ui(mw._prefs)
    pump(timeout=0.1)
    chk(b is not None and b.isVisible() and not b.icon().isNull() and (not pb.isVisible() or b.x() > pb.x()),
        "A 폴더를 정하면 곧바로 보임(다시 켜지 않고)·그림 있음")

    print("\n=== B. 도구 탭 ===")
    from PyQt6.QtGui import QAction
    chk("tools.bizcard" not in (getattr(mw, "_cmds", None) or {})
        and not [a for a in mw.findChildren(QAction) if a.text() in ("명함", "명함찾기")],
        "B 도구 탭에 `명함 ▾` 없음")

    print("\n=== C. 띄우기·경계 ===")
    from viewer.bizcard import standalone as SA
    got = []
    _orig = SA.launch
    SA.launch = lambda popen=None: got.append(SA.main_cmd([SA.ARG])) or object()
    try:
        QTest.mouseClick(b, Qt.MouseButton.LeftButton)
    finally:
        SA.launch = _orig
    chk(got and got[0][-1] == "--bizcard" and got[0][-2].endswith("main.py"), "C 누르면 같은 실행 파일을 --bizcard 로 따로 띄움", str(got))
    import re
    bad = []
    for root in ("viewer/bizcard", ):
        for n in os.listdir(os.path.join(HERE, root)):
            if n.endswith(".py"):
                t = open(os.path.join(HERE, root, n), encoding="utf-8").read()
                if re.search(r"^\s*(from viewer\.app import|import viewer\.app)", t, re.M):
                    bad.append(n)
    for n in ("bizcard_find_dialog.py", "bizcard_import_dialog.py", "bizcard_dupe_dialog.py", "bizcard_multi_dialog.py"):
        t = open(os.path.join(HERE, "viewer", "widgets", n), encoding="utf-8").read()
        if re.search(r"^\s*(from viewer\.app import|import viewer\.app)", t, re.M):
            bad.append(n)
    chk(not bad, "C 경계 — 명함 코드는 viewer.app 을 import 하지 않음", str(bad))
    mw.close()
    pump(timeout=0.3)

    print("\n=== D. 실제 프로세스 ===")
    from PyQt6.QtNetwork import QLocalSocket
    from viewer.branding import APP_ID
    import getpass
    prof = "bzt%d" % (os.getpid() % 100000)
    env = dict(os.environ, POLYPDF_PROFILE=prof, QT_QPA_PLATFORM="offscreen")
    name = APP_ID + "-" + prof + SA.SERVER_SUFFIX + "-" + "".join(ch for ch in getpass.getuser() if ch.isalnum())
    cmd = [sys.executable, os.path.join(HERE, "main.py"), "--bizcard"]
    p1 = subprocess.Popen(cmd, env=env, cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    procs.append(p1)

    def up():
        s = QLocalSocket()
        s.connectToServer(name)
        ok = s.waitForConnected(200)
        s.abort()
        return ok
    chk(pump(up, timeout=40) and p1.poll() is None, "D --bizcard 프로세스가 떠서 단일 실행 통로를 엶(명함찾기 창)",
        (p1.stderr.read().decode("utf-8", "replace")[-600:] if p1.poll() is not None else ""))
    t0 = time.monotonic()
    p2 = subprocess.Popen(cmd, env=env, cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    procs.append(p2)
    try:
        rc2 = p2.wait(timeout=40)
    except subprocess.TimeoutExpired:
        rc2 = None
    chk(rc2 == 0 and p1.poll() is None, "D 둘째 실행은 첫째를 앞으로 보내고 곧 끝남(첫째는 그대로)", "%s %.1fs" % (rc2, time.monotonic() - t0))
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "예외 없이 끝남")
finally:
    for p in procs:
        if p.poll() is None:
            p.kill()
finish()
