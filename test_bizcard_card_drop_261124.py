# -*- coding: utf-8 -*-
"""명함 사진창 놓는 자리 둘 (명함 SOT §5.24.3 '끌어 놓기'·'붙여넣기'·'명함 그림 넣기', 261122-22) — 가짜 명함·임시 폴더만.

A 그림 파일을 끌어 위 명함 칸에 올리면 두 칸 틀이 뜨고 위 칸만 진하게(올린 칸), 아래로 옮기면 아래 칸만
B 그림 없는 명함의 위 칸에 실제 놓기 → 앞면 정리본(그림 명함이 됨, 같은 id)·인물 사진은 새 정리본 이름으로 따라감
C 앞면만 있는 명함 — 마우스를 위 칸에 두고 Ctrl+V → 뒷면 `_뒷면.jpg` 로 더함
D 앞·뒷면 다 있는 명함 — 위 명함 그림 우클릭 '붙여넣기' → 바꿀 면을 물음('앞면') → 옛 앞면은 휴지통, 같은 이름에 새 그림
E 아래 칸에 놓기·마우스가 위 칸 밖일 때 Ctrl+V 는 인물 사진(명함 그림은 그대로)
"""
import os, sys, tempfile, time, shutil
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QMimeData, QUrl, QPointF, QPoint
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox, QMenu
from PyQt6.QtGui import QImage, QColor, QCursor, QDragEnterEvent, QDragMoveEvent, QDropEvent
from PyQt6.QtTest import QTest
from pathlib import Path
from PIL import Image

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_carddrop_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_carddrop_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
WARN = []
QMessageBox.warning = staticmethod(lambda *a, **k: (WARN.append(a[2] if len(a) > 2 else ""), QMessageBox.StandardButton.Ok)[1])
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
MENUS = []
QMenu.exec = lambda self, *a, **k: MENUS.append(self)
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


def size_of(p):
    with Image.open(p) as im:
        return im.size


try:
    from viewer.bizcard import people as P, store as S, vcard as V
    FOLD = TMP / "cards"
    OUT = FOLD / "정리"
    OUT.mkdir(parents=True)
    db = TMP / "local" / "bizcard.db"
    st = S.BizcardStore(db)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    # 같은 이름의 그림 명함 — 그림 없는 명함의 인물 사진은 '_주소록' 자리, 앞면을 넣으면 ' (2)' 정리본으로
    twin = OUT / "가짜갑_가짜사.jpg"
    Image.new("RGB", (300, 180), "white").save(twin)
    st.upsert({"front": str(twin), "name": "가짜갑", "company": "가짜사", "phones": [("cell", "010-0000-1999")]})
    a = P._insert_contact(st, {"name": "가짜갑", "company": "가짜사", "phones": [("cell", "010-0000-1111")]}, [])
    fb = OUT / "가짜을_가짜사.jpg"
    Image.new("RGB", (300, 180), "white").save(fb)
    b = st.upsert({"front": str(fb), "name": "가짜을", "company": "가짜사", "phones": [("cell", "010-0000-2222")]})
    fc, bc = OUT / "가짜병_가짜사.jpg", OUT / "가짜병_가짜사_뒷면.jpg"
    Image.new("RGB", (300, 180), "white").save(fc)
    Image.new("RGB", (300, 180), "gray").save(bc)
    c = st.upsert({"front": str(fc), "back": str(bc), "name": "가짜병", "company": "가짜사", "phones": [("cell", "010-0000-3333")]})
    st.con.commit()
    pa_old = P.photo_front(P.card_by_id(st, a), str(FOLD))
    st.close()
    chk(pa_old.endswith("가짜갑_가짜사_주소록.jpg"), "준비 — 그림 없는 명함 인물 사진 자리 '_주소록'", pa_old)
    ph = P.next_photo_path(pa_old)
    ph.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 50), "green").save(ph)
    settings_store.set_picture_prefs({"bizcard_folder": str(FOLD)})
    src = TMP / "받은" / "새 명함.png"
    src.parent.mkdir()
    Image.new("RGB", (350, 200), "blue").save(src)
    TRASH = TMP / "휴지통"
    TRASH.mkdir()

    from viewer.widgets import bizcard_find_dialog as FD
    fd = FD.BizcardFindDialog(None, db=db)
    fd._bz_folder = str(FOLD)

    def fake_trash(paths):
        for p_ in paths:
            if os.path.exists(p_):
                shutil.move(p_, str(TRASH / ("%d_%s" % (len(os.listdir(TRASH)), os.path.basename(p_)))))
        return []
    fd._trash = fake_trash
    fd.resize(1200, 800)
    fd.show()
    pump(lambda: fd.table.rowCount() == 4 and fd._card is not None)
    pump(timeout=0.3)

    def pick(cid):
        fd.table.setCurrentCell(fd.row_of_id(cid), 0)
        pump(lambda: fd._card is not None and fd._card["id"] == cid, timeout=3)
        pump(timeout=0.2)

    def card():
        return P.card_by_id(fd._store(), fd._card["id"])

    def mid(w):
        return QPointF(w.mapTo(fd, QPoint(w.width() // 2, w.height() // 2)))

    top = fd.photo_split.widget(0)
    bottom = fd.photo_split.widget(1)

    def md_file(p_):
        m = QMimeData()
        m.setUrls([QUrl.fromLocalFile(str(p_))])
        return m

    print("=== A 끄는 동안 두 틀 ===")
    pick(a)
    m = md_file(src)
    en = QDragEnterEvent(mid(top).toPoint(), Qt.DropAction.CopyAction, m, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(fd, en)
    cz, pz = getattr(fd, "card_drop_zone", None), getattr(fd, "drop_zone", None)
    chk(en.isAccepted() and cz is not None and cz.isVisible() and pz is not None and pz.isVisible()
        and getattr(fd, "drop_hot", None) == "card", "A 위 칸에 올림 — 두 틀, 위 칸만 진하게",
        "%s %s %s" % (en.isAccepted(), cz, getattr(fd, "drop_hot", None)))
    mv = QDragMoveEvent(mid(bottom).toPoint(), Qt.DropAction.CopyAction, m, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(fd, mv)
    chk(mv.isAccepted() and getattr(fd, "drop_hot", None) == "photo", "A 아래 칸으로 — 아래 칸만 진하게", str(getattr(fd, "drop_hot", None)))

    print("\n=== B 그림 없는 명함 위 칸에 놓기 ===")
    mv = QDragMoveEvent(mid(top).toPoint(), Qt.DropAction.CopyAction, m, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(fd, mv)
    dr = QDropEvent(mid(top), Qt.DropAction.CopyAction, m, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(fd, dr)
    pump(lambda: not fd.photo_busy and not V.is_contact(card()), timeout=10)
    ca = card()
    newf = P._real(ca["front"]) if ca else ""
    chk(ca and ca["id"] == a and not V.is_contact(ca) and os.path.exists(newf)
        and os.path.basename(newf) == "가짜갑_가짜사 (2).jpg" and size_of(newf) == (350, 200),
        "B 앞면 정리본 ' (2)' (그림 명함이 됨, 같은 id, 350×200)", "%s %s" % (ca and ca["front"], WARN))
    phs = P.person_photos(P.photo_front(ca, str(FOLD))) if ca else []
    chk(len(phs) == 1 and not os.path.exists(str(ph)) and os.path.basename(phs[0]).startswith("가짜갑_가짜사 (2)"),
        "B 인물 사진이 새 정리본 이름으로 따라감", str(phs))
    chk(src.exists() and twin.exists(), "B 원본·같은 이름 그림 명함은 그대로")

    print("\n=== C 앞면만 — 마우스 위 칸 + Ctrl+V → 뒷면 ===")
    pick(b)
    im = QImage(320, 190, QImage.Format.Format_RGB32)
    im.fill(QColor("red"))
    QApplication.clipboard().setImage(im)
    QCursor.setPos(top.mapToGlobal(QPoint(top.width() // 2, top.height() // 2)))
    fd.activateWindow()
    fd.table.setFocus()
    pump(timeout=0.05)
    QTest.keyClick(fd.table, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    pump(lambda: not fd.photo_busy and bool(card().get("back")), timeout=10)
    cb_ = card()
    bk = P._real(cb_.get("back") or "")
    chk(bk and os.path.exists(bk) and os.path.basename(bk) == "가짜을_가짜사_뒷면.jpg" and size_of(bk) == (320, 190),
        "C 뒷면 '_뒷면.jpg' 로 더함(320×190)", "%s %s" % (cb_.get("back"), WARN))
    chk(not P.person_photos(P.photo_front(cb_, str(FOLD))), "C 인물 사진은 넣지 않음")

    print("\n=== D 앞·뒷면 다 있음 — 우클릭 '붙여넣기' → 물음 → 앞면 바꾸기 ===")
    pick(c)
    ASKED = []
    fd._ask_card_side = lambda: (ASKED.append(1), "front")[1]
    MENUS.clear()
    fd.pv.customContextMenuRequested.emit(QPoint(5, 5))
    acts = [x for x in MENUS[-1].actions() if x.text() == "붙여넣기"] if MENUS else []
    chk(bool(acts) and acts[0].isEnabled(), "D 위 명함 그림 우클릭 '붙여넣기' 켜짐", str([x.text() for x in MENUS[-1].actions()] if MENUS else None))
    if acts:
        acts[0].trigger()
    pump(lambda: not fd.photo_busy and os.path.exists(str(fc)) and size_of(fc) == (320, 190), timeout=10)
    cc = card()
    chk(ASKED == [1], "D 바꿀 면을 물음", str(ASKED))
    chk(os.path.exists(str(fc)) and size_of(fc) == (320, 190) and os.path.normcase(P._real(cc["front"])) == os.path.normcase(str(fc))
        and size_of(bc) == (300, 180), "D 같은 이름 앞면에 새 그림, 뒷면 그대로", "%s" % (cc["front"],))
    chk(len(os.listdir(TRASH)) == 1, "D 옛 앞면은 휴지통", str(os.listdir(TRASH)))

    print("\n=== E 아래 칸·위 칸 밖은 인물 사진 ===")
    QCursor.setPos(bottom.mapToGlobal(QPoint(bottom.width() // 2, bottom.height() // 2)))
    fd.activateWindow()
    fd.table.setFocus()
    pump(timeout=0.05)
    QTest.keyClick(fd.table, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    pump(lambda: not fd.photo_busy and len(P.person_photos(P.photo_front(card(), str(FOLD)))) >= 1, timeout=10)
    chk(len(P.person_photos(P.photo_front(card(), str(FOLD)))) == 1 and size_of(fc) == (320, 190),
        "E 마우스가 아래 칸 — Ctrl+V 는 인물 사진", str(P.person_photos(P.photo_front(card(), str(FOLD)))))
    m2 = md_file(src)
    QApplication.sendEvent(fd, QDragEnterEvent(mid(bottom).toPoint(), Qt.DropAction.CopyAction, m2, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    QApplication.sendEvent(fd, QDropEvent(mid(bottom), Qt.DropAction.CopyAction, m2, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    pump(lambda: not fd.photo_busy and len(P.person_photos(P.photo_front(card(), str(FOLD)))) >= 2, timeout=10)
    chk(len(P.person_photos(P.photo_front(card(), str(FOLD)))) == 2 and size_of(fc) == (320, 190) and len(os.listdir(TRASH)) == 1,
        "E 아래 칸에 놓기 — 인물 사진(명함 그림 그대로)")
    chk(not WARN, "경고 없음", str(WARN))
except Exception as e:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외", repr(e))
finish()
