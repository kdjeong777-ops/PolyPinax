# -*- coding: utf-8 -*-
"""명함찾기 인물 사진 끌어 놓기 (명함 SOT §5.24.3 '끌어 놓기') — 가짜 그림·가짜 이름만(명함 SOT §2.1).

오프스크린, 실제 설정·데이터 폴더를 쓰지 않는다(검사 작성 SOT §14.7.2). 끌기 이벤트는 실제 자식 칸(큰 사진 칸·썸네일 줄·
목록 표)에 보내 Qt 가 부모로 넘기는 길 그대로 탄다.
A. 사진창 안(큰 사진 칸) — 들어오기·**움직이기**를 받는다(종전엔 움직이기를 받지 않아 Windows 에서 놓을 수 없었다), 놓으면 사진이 들어감
B. 놓을 자리 표시 — 끄는 동안 사진창 위 점선 틀(안에 올리면 바탕까지), 놓거나 떠나면 사라짐
C. 사진창 밖(목록 표) — 움직이기를 받지 않음(놓을 수 없음 커서), 틀은 보이되 바탕은 칠하지 않음
D. 썸네일 줄 위 — 그 줄이 받아 넣고 틀도 같게, 그림 아닌 파일은 받지 않음
"""
import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QMimeData, QUrl, QPointF
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent, QDragLeaveEvent, QDropEvent
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_drop_%d" % os.getpid())
fails = []
TMP = Path(tempfile.mkdtemp(prefix="bizcard_drop_"))
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


ACT = Qt.DropAction.CopyAction | Qt.DropAction.MoveAction | Qt.DropAction.LinkAction


def mime(path):
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(str(path))])
    return md


def enter_move(w, md):
    p = QPointF(w.width() / 2, w.height() / 2).toPoint()
    en = QDragEnterEvent(p, ACT, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(w, en)
    mv = QDragMoveEvent(p, ACT, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(w, mv)
    return en.isAccepted(), mv.isAccepted()


def drop(w, md):
    dr = QDropEvent(QPointF(w.width() / 2, w.height() / 2), ACT, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(w, dr)
    return dr.isAccepted()


try:
    from PIL import Image
    from viewer.bizcard import importer as I, apply as AP
    F = TMP / "cards"
    F.mkdir()
    Image.new("RGB", (339, 186), "white").save(F / "a_1.jpg", quality=90)
    items = {it.base: it for it in I.scan_folder(F)}
    db = TMP / "local" / "bizcard.db"
    AP.apply_cards([{"key": items["a"].key, "front": items["a"].front, "back": "", "pdf": "", "keep_back": False,
                     "name": "홍길동", "company": "가나다", "langs": ["한글"], "phones": [("cell", "010-0000-0001")]}],
                   F / "정리", db)
    PIC = TMP / "사진.png"
    Image.new("RGB", (60, 80), "pink").save(PIC)
    TXT = TMP / "메모.txt"
    TXT.write_text("x", encoding="utf-8")

    from viewer.widgets import bizcard_find_dialog as FD
    dlg = FD.BizcardFindDialog(None, db=db)
    dlg._bz_folder = str(F)
    dlg.resize(1400, 900)
    dlg.show()
    pump(lambda: dlg.table.rowCount() >= 1)
    dlg.table.setCurrentCell(0, 0)
    pump(lambda: dlg._card is not None, timeout=3)
    zone = lambda: getattr(dlg, "drop_zone", None)
    shown = lambda: zone() is not None and zone().isVisible()
    hot = lambda: shown() and FD.DROP_TINT_HOT in zone().styleSheet() if hasattr(FD, "DROP_TINT_HOT") else False

    print("=== A·B. 사진창 안(큰 사진 칸) ===")
    md = mime(PIC)
    en, mv = enter_move(dlg.photo_view, md)
    chk(en and mv, "A 큰 사진 칸 위 — 들어오기·움직이기 모두 받음(놓을 수 있음)", "enter=%s move=%s" % (en, mv))
    chk(shown() and hot(), "B 끄는 동안 사진창 위 점선 틀, 안에 올리면 바탕까지")
    if shown():
        z, ps = zone(), dlg.photo_split
        chk(z.geometry() == ps.geometry().translated(ps.parentWidget().mapTo(dlg, ps.pos()) - ps.pos()) or
            z.geometry().size() == ps.size(), "B 틀 = 사진창 자리·크기", "%s %s" % (z.geometry(), ps.size()))
    ok = drop(dlg.photo_view, md)
    pump(lambda: not dlg.photo_busy and dlg.photos.count() == 1, timeout=10)
    chk(ok and dlg.photos.count() == 1 and (F / "인물" / "홍길동_가나다.jpg").exists(), "A 놓으면 인물 사진으로 들어감",
        str(dlg.photo_paths()))
    chk(not shown(), "B 놓으면 틀이 사라짐")

    print("\n=== C. 사진창 밖(목록 표) ===")
    en, mv = enter_move(dlg.table.viewport(), md)
    chk(not mv, "C 목록 표 위 — 움직이기를 받지 않음(놓을 수 없음)", "enter=%s move=%s" % (en, mv))
    chk(shown() and not hot(), "C 틀은 보이되(어디에 놓을지 알림) 바탕은 칠하지 않음")
    QApplication.sendEvent(dlg, QDragLeaveEvent())
    chk(not shown(), "C 창을 떠나면 틀이 사라짐")
    n0 = dlg.photos.count()
    drop(dlg.table.viewport(), md)
    pump(None)
    chk(dlg.photos.count() == n0, "C 사진창 밖에 놓으면 넣지 않음")

    print("\n=== D. 썸네일 줄 위 ===")
    en, mv = enter_move(dlg.photos.viewport(), md)
    chk(en and mv and hot(), "D 썸네일 줄 위 — 받고 틀도 같게", "enter=%s move=%s" % (en, mv))
    drop(dlg.photos.viewport(), md)
    pump(lambda: not dlg.photo_busy and dlg.photos.count() == n0 + 1, timeout=10)
    chk(dlg.photos.count() == n0 + 1 and not shown(), "D 놓으면 넣고 틀이 사라짐", str(dlg.photo_paths()))
    en, mv = enter_move(dlg.photo_view, mime(TXT))
    chk(not mv and not shown(), "D 그림 아닌 파일은 받지 않고 틀도 없음", "enter=%s move=%s" % (en, mv))
    dlg.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "예외 없이 끝남")
finish()
