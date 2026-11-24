# -*- coding: utf-8 -*-
"""명함찾기 사진창 구분선 = 크기 조절 손잡이 (명함찾기 SOT §5.24.3 '인물 사진', 261120-22) — 가짜 명함만(명함 SOT §2.1).

오프스크린, 실제 설정·데이터 폴더를 쓰지 않는다(검사 작성 SOT §14.7.2).
A. 보이는 1px 구분선은 손잡이가 그린다(손잡이 가운데 = 카드 테 색, 그 위아래는 선이 아님), 손잡이는 집을 만큼 높다
B. 선을 실제 마우스로 집어 끌면 위 명함·아래 인물 사진 높이가 바뀐다
C. 가리키면 선이 강조색으로(집을 수 있음), 커서는 위아래 화살표
"""
import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QPoint, QPointF
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QEnterEvent
from PyQt6.QtTest import QTest
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_handle_%d" % os.getpid())
fails = []
TMP = Path(tempfile.mkdtemp(prefix="bizcard_handle_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def pump(cond=None, timeout=10.0):
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


try:
    from PIL import Image
    from viewer.bizcard import importer as I, apply as AP
    F = TMP / "cards"
    F.mkdir()
    Image.new("RGB", (339, 186), "white").save(F / "a_1.jpg", quality=90)
    items = {it.base: it for it in I.scan_folder(F)}
    db = TMP / "local" / "bizcard.db"
    AP.apply_cards([{"key": items["a"].key, "front": items["a"].front, "back": "", "pdf": "", "keep_back": False,
                     "name": "홍길동", "company": "가나다", "langs": ["한글"]}], F / "정리", db)
    from viewer.widgets import bizcard_find_dialog as FD
    dlg = FD.BizcardFindDialog(None, db=db)
    dlg.resize(1400, 900)
    dlg.show()
    pump(lambda: dlg.table.rowCount() >= 1)
    pump(None)
    sp = dlg.photo_split
    h = sp.handle(1)
    border = FD.DETAIL_BG["light"]["border"]

    print("=== A. 선 = 손잡이 ===")
    img = h.grab().toImage()
    mid = img.pixelColor(h.width() // 2, h.height() // 2).name()
    off = img.pixelColor(h.width() // 2, 0).name()
    chk(mid == border and off != border, "A 손잡이 가운데에 카드 테 색 1px 선(위끝은 선 아님)", "%s %s %s" % (mid, off, border))
    chk(h.height() >= 7, "A 손잡이는 집을 만큼 높다(7px 이상)", str(h.height()))
    chk(getattr(dlg, "photo_sep", None) is None, "A 인물 사진 칸 안의 따로 그린 선(photo_sep)은 없다")

    print("\n=== B. 실제 마우스로 끌기 ===")
    before = sp.sizes()
    c = QPoint(h.width() // 2, h.height() // 2)
    QTest.mousePress(h, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, c)
    for dy in (10, 25, 40, 60):
        QTest.mouseMove(h, QPoint(c.x(), c.y() + dy))
        app.processEvents()
    QTest.mouseRelease(h, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(c.x(), c.y() + 60))
    pump(None)
    after = sp.sizes()
    chk(after[0] > before[0] + 30 and after[1] < before[1] - 30, "B 선을 집어 아래로 끌면 위 명함이 커지고 아래 인물 사진이 줄어듦",
        "%s → %s" % (before, after))

    print("\n=== C. 가리킴 ===")
    QApplication.sendEvent(h, QEnterEvent(QPointF(c), QPointF(h.mapTo(dlg, c)), QPointF(h.mapToGlobal(c))))
    pump(None)
    hot = h.grab().toImage().pixelColor(h.width() // 2, h.height() // 2).name()
    hl = h.palette().color(h.palette().ColorRole.Highlight).name()
    chk(hot == hl, "C 가리키면 선이 강조색", "%s %s" % (hot, hl))
    chk(h.cursor().shape() == Qt.CursorShape.SplitVCursor, "C 커서는 위아래 화살표", str(h.cursor().shape()))
    dlg.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "예외 없이 끝남")
finish()
