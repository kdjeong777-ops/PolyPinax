# -*- coding: utf-8 -*-
"""261117-64: 스크린샷 스트립 한도(`screenshot_max`)를 넘으면 **가장 오래된 컷**부터 빠진다 (스크린샷 SOT §4).

종전 결함: 캡처 길은 모두 끝에 붙이는데(`prepend=False`) 한도를 넘으면 끝(= 방금 넣은 컷)부터 빼서,
한도가 찬 뒤로는 새 컷이 들어오자마자 사라졌다.

A. 실제 '클립보드 가져오기' 단추로 그림 파일 5장 → 한도 3: 마지막 3장이 들어온 차례대로 남는다, 개수 '(3/3)'
B. 한 장 더(그림 데이터) → 가장 오래된 것이 빠지고 새 컷이 맨 끝에, 빠진 컷의 PNG 는 임시 폴더에 그대로
C. 한도를 2 로 줄이면(`set_max_items`) 오래된 쪽부터 빠지고 새 컷 둘이 남는다, 번호도 1·2 로 다시
D. 앞에 붙이는 쓰임(`prepend=True`)에서는 끝(가장 오래된 쪽)부터 빠진다
"""
import os, sys, tempfile, shutil, faulthandler
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(180, exit=True)
from pathlib import Path

from PyQt6.QtCore import QStandardPaths, QMimeData, QUrl
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QImage, QColor
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
from PyQt6.QtCore import QCoreApplication
QCoreApplication.setApplicationName("polypdf_shotlimit_%d" % os.getpid())   # 검사 작성 SOT §14.7.2 의 3
import modal_guard
modal_guard.install(label=lambda: "스크린샷 한도", echo=False)
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def spin(n=10, ms=20):
    for _ in range(n):
        app.processEvents(); QTest.qWait(ms)


root = Path(tempfile.mkdtemp(prefix="polypdf_shotlimit_"))
try:
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    from viewer.app import MainWindow
    mw = MainWindow(); mw.resize(1300, 850); mw.show(); app.processEvents()
    strip = mw.shot_strip
    strip.clear()
    strip.set_max_items(3)

    def widths():
        return [QImage(p).width() for p in strip.all_paths()]

    # ── A ────────────────────────────────────────────────────────────
    files = []
    for i in range(5):
        f = root / f"컷{i}.png"
        im = QImage(50 + i, 30, QImage.Format.Format_RGB32); im.fill(QColor(20 * i, 80, 160)); im.save(str(f))
        files.append(f)
    cb = QApplication.clipboard()
    md = QMimeData(); md.setUrls([QUrl.fromLocalFile(str(f)) for f in files])
    cb.setMimeData(md); spin(2)
    mw.btn_clip_in.click(); spin(3)
    chk(widths() == [52, 53, 54], "A 한도 3 에 5장 → 마지막 3장이 차례대로 남는다", str(widths()))
    chk(strip.count_label.text() == "(3/3)", "A 개수 표시 (3/3)", strip.count_label.text())

    # ── B ────────────────────────────────────────────────────────────
    oldest = strip.all_paths()[0]
    img = QImage(99, 30, QImage.Format.Format_RGB32); img.fill(QColor(200, 30, 30))
    cb.setImage(img); spin(2)
    mw.btn_clip_in.click(); spin(3)
    chk(widths() == [53, 54, 99], "B 한 장 더 → 가장 오래된 컷이 빠지고 새 컷이 맨 끝", str(widths()))
    chk(Path(oldest).is_file(), "B 빠진 컷의 PNG 는 임시 폴더에 남는다(카드만 빠짐)", oldest)

    # ── C ────────────────────────────────────────────────────────────
    strip.set_max_items(2); spin(2)
    chk(widths() == [54, 99], "C 한도를 2 로 줄이면 오래된 쪽부터 빠진다", str(widths()))
    nums = [strip.list.item(i).text() for i in range(strip.list.count())]
    chk(nums == ["1", "2"], "C 번호도 다시 1·2", str(nums))

    # ── D ────────────────────────────────────────────────────────────
    from viewer.widgets.strip import MiniStrip
    st = MiniStrip("스크린샷", max_items=2)
    ps = []
    for i in range(3):
        f = root / f"앞{i}.png"
        im = QImage(70 + i, 30, QImage.Format.Format_RGB32); im.fill(QColor(0, 0, 0)); im.save(str(f))
        ps.append(str(f))
        st.add_item(str(f), kind="image", prepend=True)
    chk(st.all_paths() == [ps[2], ps[1]], "D 앞에 붙이면 끝(가장 오래된 쪽)부터 빠진다",
        str([Path(p).name for p in st.all_paths()]))
    st.deleteLater()
    cb.clear(); spin(2)
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
os._exit(1 if fails else 0)     # MainWindow 정리 중 종료 충돌을 피한다(다른 MainWindow 검사와 같음)
