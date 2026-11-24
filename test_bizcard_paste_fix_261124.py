# -*- coding: utf-8 -*-
"""명함 사진창 넣기 결함 (명함 SOT §5.24.3 '붙여넣기'·'넣은 뒤 목록', 261122-23, 사용자 보고) — 가짜 명함·임시 폴더만.

사용자 보고 '명함과 사진이 없는 창에 스크린샷한 사진을 넣으려니 안되 · png 를 끌어 떨어뜨리는 것도 안되'
(덧붙인 답: 끌면 점선 틀은 보임 · Ctrl+V 전에 세부 칸·찾기 칸에 커서).

A '명함 없음' 으로 거른 목록 — 위 칸에 놓아 명함 그림을 넣으면 그 명함이 목록에서 빠져 다른 명함으로 넘어갔다(넣은 게 안 보임)
  → 넣은 명함을 그대로 보이고 목록에 남김
B '사진 없음' 으로 거른 목록 — 아래 칸에 인물 사진을 넣고 목록을 다시 채워도 보던 명함 그대로
C 다른 명함을 고르면 남겨 둔 명함은 구분대로 빠짐
D 글 칸(찾기 칸)에 커서 + 클립보드에 그림만(스크린샷) → Ctrl+V 는 그림 붙여넣기(마우스 자리), 찾기 칸 글은 그대로
E 글 칸 + 클립보드에 글 → Ctrl+V 는 글 붙여넣기(그림 넣지 않음)
"""
import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QMimeData, QUrl, QPointF, QPoint
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QImage, QColor, QCursor, QDragEnterEvent, QDropEvent
from PyQt6.QtTest import QTest
from pathlib import Path
from PIL import Image

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_pastefix_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_pastefix_"))
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


def pump(cond=lambda: False, timeout=10.0):
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


try:
    from viewer.bizcard import people as P, store as S, vcard as V
    FOLD = TMP / "cards"
    (FOLD / "정리").mkdir(parents=True)
    db = TMP / "local" / "bizcard.db"
    st = S.BizcardStore(db)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    a = P._insert_contact(st, {"name": "가짜갑", "company": "가짜사", "phones": [("cell", "010-0000-1111")]}, [])
    b = P._insert_contact(st, {"name": "가짜을", "company": "가짜사", "phones": [("cell", "010-0000-2222")]}, [])
    c = P._insert_contact(st, {"name": "가짜병", "company": "가짜사", "phones": [("cell", "010-0000-3333")]}, [])
    st.con.commit()
    st.close()
    settings_store.set_picture_prefs({"bizcard_folder": str(FOLD)})
    png = TMP / "받은" / "스크린샷.png"
    png.parent.mkdir()
    Image.new("RGB", (500, 300), "blue").save(png)

    from viewer.widgets import bizcard_find_dialog as FD
    fd = FD.BizcardFindDialog(None, db=db)
    fd._bz_folder = str(FOLD)
    fd.resize(1200, 800)
    fd.show()
    pump(lambda: fd.table.rowCount() == 3 and fd._card is not None)
    pump(timeout=0.3)

    def pick(cid):
        fd.table.setCurrentCell(fd.row_of_id(cid), 0)
        pump(lambda: fd._card is not None and fd._card["id"] == cid, timeout=3)

    def kind(k):
        fd.cb_kind.set_keys(k)
        fd._on_kind()
        pump(timeout=0.3)

    def drop(zone):
        w = fd.photo_split.widget(0 if zone == "card" else 1)
        pos = QPointF(w.mapTo(fd, QPoint(w.width() // 2, w.height() // 2)))
        m = QMimeData()
        m.setUrls([QUrl.fromLocalFile(str(png))])
        QApplication.sendEvent(fd, QDragEnterEvent(pos.toPoint(), Qt.DropAction.CopyAction, m, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        QApplication.sendEvent(fd, QDropEvent(pos, Qt.DropAction.CopyAction, m, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))

    def photos(cid):
        return P.person_photos(P.photo_front(P.card_by_id(fd._store(), cid), str(FOLD)))

    print("=== A '명함 없음' 목록 — 위 칸에 명함 그림 ===")
    kind("nocard")
    pick(a)
    drop("card")
    pump(lambda: not fd.photo_busy and not V.is_contact(P.card_by_id(fd._store(), a)), timeout=10)
    pump(timeout=0.3)
    chk(not V.is_contact(P.card_by_id(fd._store(), a)), "A 명함 그림이 들어감")
    chk(fd._card is not None and fd._card["id"] == a and fd.row_of_id(a) >= 0,
        "A 넣은 명함이 그대로 보이고 목록에 남음(다른 명함으로 넘어가지 않음)", "%s" % (fd._card and fd._card["name"]))

    print("\n=== B '사진 없음' 목록 — 아래 칸에 인물 사진 ===")
    kind("nophoto")
    pick(b)
    drop("photo")
    pump(lambda: not fd.photo_busy and len(photos(b)) == 1, timeout=10)
    fd.refresh()
    pump(timeout=0.3)
    chk(len(photos(b)) == 1 and fd._card is not None and fd._card["id"] == b and fd.row_of_id(b) >= 0,
        "B 인물 사진을 넣고 목록을 다시 채워도 보던 명함 그대로", "%s %s" % (photos(b), fd._card and fd._card["name"]))

    print("\n=== C 다른 명함을 고르면 구분대로 ===")
    pick(c)
    fd.refresh()
    pump(timeout=0.3)
    chk(fd.row_of_id(b) < 0 and fd._card is not None and fd._card["id"] == c, "C 다른 명함을 고른 뒤엔 사진 있는 명함은 빠짐",
        "row_b=%s" % fd.row_of_id(b))

    print("\n=== D 글 칸 + 그림만 → 그림 붙여넣기 ===")
    kind("all")
    pick(c)
    fd.ed_find.setText("")
    im = QImage(320, 200, QImage.Format.Format_RGB32)
    im.fill(QColor("red"))
    QApplication.clipboard().setImage(im)
    bottom = fd.photo_split.widget(1)
    QCursor.setPos(bottom.mapToGlobal(QPoint(bottom.width() // 2, bottom.height() // 2)))
    fd.activateWindow()
    fd.ed_find.setFocus()
    pump(timeout=0.05)
    QTest.keyClick(fd.ed_find, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    pump(lambda: not fd.photo_busy and len(photos(c)) == 1, timeout=10)
    chk(len(photos(c)) == 1 and fd.ed_find.text() == "", "D 찾기 칸에 커서여도 스크린샷은 인물 사진으로(찾기 칸 글 그대로)",
        "%s %r" % (photos(c), fd.ed_find.text()))

    print("\n=== E 글 칸 + 글 → 글 붙여넣기 ===")
    QApplication.clipboard().setText("가짜글")
    fd.ed_find.setFocus()
    QTest.keyClick(fd.ed_find, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    pump(timeout=0.8)
    chk(len(photos(c)) == 1 and "가짜글" in fd.ed_find.text(), "E 클립보드가 글이면 찾기 칸에 글", "%r" % fd.ed_find.text())
    chk(not WARN, "경고 없음")
except Exception as e:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외", repr(e))
finish()
