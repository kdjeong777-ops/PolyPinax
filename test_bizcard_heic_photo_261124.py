# -*- coding: utf-8 -*-
"""HEIC 를 명함 인물 사진에 끌어 놓기 (명함찾기 SOT §5.24.3 '끌어 놓기', 261122-16) — 합성 HEIC·가짜 명함·임시 폴더만.

HEIC 표본은 `test_photo_heic_261104.py` 의 합성 HEIC(64×48, EXIF 방향 6 — 업무 사진 아님)를 그대로 읽어 쓴다.
HEIC 해독기(pi-heif)가 없으면 명시적 SKIP.

A 사진창에 HEIC 를 실제 놓기 이벤트로 놓으면 받는다(종전: 확장자 목록에 없어 끌기를 받지 않음 — 사진 모드 책갈피창에서 끌 때)
B 인물 사진은 JPG 로(방향 반영 48×64), 원본 HEIC 는 그대로(종전: 받고도 걸러 붙지 않음·Pillow 가 HEIC 를 못 읽음 — 탐색기에서 끌 때)
C 아이폰이 내보낸 .JPG 이름의 HEIC 도 붙음
"""
import os, sys, re, base64, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QMimeData, QUrl, QPointF, QPoint
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QDropEvent, QDragEnterEvent
from pathlib import Path
from PIL import Image

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_heic_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_heic_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
WARN = []
QMessageBox.warning = staticmethod(lambda *a, **k: (WARN.append(1), QMessageBox.StandardButton.Ok)[1])
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


def pump(cond, timeout=10.0):
    t = time.monotonic()
    while time.monotonic() - t < timeout:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


def finish():
    print("FAILURES: %d" % len(fails))
    for f in fails:
        print("  -", f)
    sys.stdout.flush()
    os._exit(1 if fails else 0)


from viewer import photo_io
if not photo_io.heif_ready():
    print("SKIP - HEIC 해독기(pi-heif)가 없음")
    sys.stdout.flush()
    os._exit(0)
src_txt = open(os.path.join(HERE, "test_photo_heic_261104.py"), encoding="utf-8").read()
HEIC = base64.b64decode(re.search(r'HEIC_B64 = "([^"]+)"', src_txt).group(1))

try:
    from viewer.bizcard import people as P, store as S
    FOLD = TMP / "cards"
    OUT = FOLD / "정리"
    OUT.mkdir(parents=True)
    db = TMP / "local" / "bizcard.db"
    st = S.BizcardStore(db)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    f = OUT / "가짜갑_가짜사.jpg"
    Image.new("RGB", (300, 180), "white").save(f)
    a = st.upsert({"front": str(f), "name": "가짜갑", "company": "가짜사", "phones": [("cell", "010-0000-1111")]})
    st.con.commit()
    st.close()
    settings_store.set_picture_prefs({"bizcard_folder": str(FOLD)})
    h1 = TMP / "받은" / "가짜 사진.heic"
    h1.parent.mkdir()
    h1.write_bytes(HEIC)
    h2 = TMP / "받은" / "IMG_0001.JPG"                    # .JPG 이름의 HEIC
    h2.write_bytes(HEIC)

    from viewer.widgets import bizcard_find_dialog as FD
    fd = FD.BizcardFindDialog(None, db=db)
    fd._bz_folder = str(FOLD)
    fd.resize(1200, 800)
    fd.show()
    pump(lambda: fd.table.rowCount() == 1 and fd._card is not None)
    pump(lambda: False, timeout=0.3)
    z = fd.photo_split.widget(1)                         # 아래 인물 사진 칸(261122-22 — 위 칸은 명함 그림 자리)
    pos = QPointF(z.mapTo(fd, QPoint(z.width() // 2, z.height() // 2)))

    def drop(path):
        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(str(path))])
        en = QDragEnterEvent(pos.toPoint(), Qt.DropAction.CopyAction, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(fd, en)
        ok = en.isAccepted()
        ev = QDropEvent(pos, Qt.DropAction.CopyAction, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(fd, ev)
        return ok

    print("=== A·B HEIC 놓기 ===")
    raw0 = h1.read_bytes()
    acc = drop(h1)
    chk(acc, "A HEIC 끌기를 받음(사진창)")
    pump(lambda: not fd.photo_busy and fd.photos.count() >= 1, timeout=10)
    phs = P.person_photos(P.photo_front(P.card_by_id(fd._store(), a), str(FOLD)))
    ok_b = len(phs) == 1 and not WARN
    if ok_b:
        with Image.open(phs[0]) as im:
            ok_b = im.format == "JPEG" and im.size == (48, 64) and phs[0].lower().endswith(".jpg")
    chk(ok_b, "B 인물 사진은 JPG(방향 반영 48×64)로 붙음", "%s %s" % (phs, WARN))
    chk(h1.read_bytes() == raw0, "B 원본 HEIC 는 그대로")

    print("\n=== C .JPG 이름의 HEIC ===")
    drop(h2)
    pump(lambda: not fd.photo_busy and fd.photos.count() >= 2, timeout=10)
    phs = P.person_photos(P.photo_front(P.card_by_id(fd._store(), a), str(FOLD)))
    chk(len(phs) == 2 and not WARN, "C .JPG 이름의 HEIC 도 붙음", "%s %s" % (phs, WARN))
except Exception as e:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외", repr(e))
finish()
