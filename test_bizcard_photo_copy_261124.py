# -*- coding: utf-8 -*-
"""인물 사진 다른 명함으로 복사·다른 이름으로 저장 (명함찾기 SOT §5.24.3, 261122-25) — 가짜 명함·합성 그림·임시 폴더만.

A 썸네일 우클릭 메뉴에 '다른 명함으로 복사'·'다른 이름으로 저장', 위 명함 칸은 '다른 이름으로 저장' 만
B '다른 명함으로 복사' → 명함 고르기 창(지금 명함은 빠짐)에서 고르면 그 명함 인물 사진에 더함(원래 명함은 그대로)·알림·목록 얼굴
C 썸네일을 목록 표의 줄에 놓으면 그 명함으로 복사, 지금 명함 줄 위는 받지 않음, 썸네일 줄은 그대로
D 썸네일을 즐겨찾기 사람 칸에 놓으면 그 사람으로 복사
E '다른 이름으로 저장' 한 장 = 저장 창, 바이트 그대로 · 여러 장 = 폴더, 겹치면 ' (2)' · 지난 폴더 기억
"""
import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QMimeData, QPointF, QPoint
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox, QMenu, QFileDialog
from PyQt6.QtGui import QDropEvent, QDragEnterEvent, QDragMoveEvent
from PyQt6.QtTest import QTest
from pathlib import Path
from PIL import Image

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_photocopy_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_photocopy_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
WARN = []
QMessageBox.warning = staticmethod(lambda *a, **k: (WARN.append(1), QMessageBox.StandardButton.Ok)[1])
MENUS = []
QMenu.exec = lambda self, *a, **k: MENUS.append(self)
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


def pump(cond=lambda: False, timeout=5.0):
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


def _with_source(cls):
    class E(cls):                                   # 끈 위젯을 정해 둔 끌기 이벤트(가짜 이벤트는 source 가 빔)
        def __init__(self, src, *a):
            super().__init__(*a)
            self._src = src

        def source(self):
            return self._src
    return E


DropE, EnterE, MoveE = _with_source(QDropEvent), _with_source(QDragEnterEvent), _with_source(QDragMoveEvent)
ACTS = Qt.DropAction.MoveAction | Qt.DropAction.CopyAction   # 썸네일 줄 끌기가 허용하는 동작(QListWidget 기본 — 복사·이동)


def drag_to(view, src, pos, drop=True):
    """반환 = 움직임 이벤트를 받았는가."""
    md = QMimeData()
    md.setData("application/x-qabstractitemmodeldatalist", b"")
    vp = view.viewport()
    QApplication.sendEvent(vp, EnterE(src, pos, ACTS, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    mv = MoveE(src, pos, ACTS, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(vp, mv)
    ok = mv.isAccepted()
    if drop:
        d = DropE(src, QPointF(pos), ACTS, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(vp, d)
        ok = ok and d.isAccepted() and d.dropAction() == Qt.DropAction.CopyAction
    return ok


try:
    from viewer.bizcard import people as P, store as S, face_thumb as FT
    FT.faces = lambda img: []
    FOLD = TMP / "cards"
    (FOLD / "정리").mkdir(parents=True)
    db = TMP / "local" / "bizcard.db"
    st = S.BizcardStore(db)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    a = P._insert_contact(st, {"name": "가짜갑", "company": "가짜사", "phones": [("cell", "010-0000-0001")]}, ["명함"])
    b = P._insert_contact(st, {"name": "가짜을", "company": "가짜사", "phones": [("cell", "010-0000-0002")]}, ["명함"])
    c = P._insert_contact(st, {"name": "가짜병", "company": "가짜사", "phones": [("cell", "010-0000-0003")]}, ["명함"])
    st.con.commit()
    pa = P.photo_front(P.card_by_id(st, a), str(FOLD))
    for col in ("red", "green"):
        src = TMP / ("s_%s.png" % col)
        Image.new("RGB", (200, 260), col).save(src)
        P.save_person_photo(str(src), P.next_photo_path(pa))
    P.fav_init(st, "즐겨찾기")
    gid = P.fav_add_group(st, "가짜모음")
    P.fav_add(st, gid, [a, c])
    st.meta_set("fav_tab", gid)
    st.close()
    settings_store.set_picture_prefs({"bizcard_folder": str(FOLD)})

    def photos_of(cid):
        return P.person_photos(P.photo_front(P.card_by_id(fd._store(), cid), str(FOLD)))

    from viewer.widgets import bizcard_find_dialog as FD
    fd = FD.BizcardFindDialog(None, db=db)
    fd._bz_folder = str(FOLD)
    fd.resize(1300, 850)
    fd.show()
    pump(lambda: fd.table.rowCount() == 3)
    fd.table.setCurrentCell(fd.row_of_id(a), 0)
    pump(lambda: fd._card is not None and fd._card["id"] == a and fd.photos.count() == 2, timeout=3)
    a_photos = photos_of(a)

    print("=== A 메뉴 ===")
    MENUS.clear()
    fd.photos.customContextMenuRequested.emit(fd.photos.visualItemRect(fd.photos.item(0)).center())
    names = [x.text() for x in MENUS[-1].actions()] if MENUS else []
    chk("다른 명함으로 복사" in names and "다른 이름으로 저장" in names, "A 썸네일 메뉴에 복사·저장", str(names))
    MENUS.clear()
    fd.pv.customContextMenuRequested.emit(QPoint(5, 5))
    names_pv = [x.text() for x in MENUS[-1].actions()] if MENUS else []
    chk("다른 명함으로 복사" not in names_pv and "다른 이름으로 저장" in names_pv, "A 위 명함 칸은 저장만", str(names_pv))

    print("\n=== B 명함 고르기 창으로 복사 ===")
    seen = {}

    def fake_exec(dlg):
        seen["ids"] = [dlg.lst.item(i).data(FD.ROLE) for i in range(dlg.lst.count())]
        dlg.ed.setText("가짜을")
        seen["after"] = [dlg.lst.item(i).data(FD.ROLE) for i in range(dlg.lst.count())]
        return 1
    FD._CardPickDialog.exec = fake_exec
    fd.photos.setCurrentRow(1)                         # 둘째(초록) 사진 하나
    fd.photos.item(1).setSelected(True)
    MENUS.clear()
    fd.photos.customContextMenuRequested.emit(fd.photos.visualItemRect(fd.photos.item(1)).center())
    act = next((x for x in MENUS[-1].actions() if x.text() == "다른 명함으로 복사"), None) if MENUS else None
    if act is not None:
        act.trigger()
    pump(lambda: not fd.photo_busy and len(photos_of(b)) == 1, timeout=8)
    pb = photos_of(b)
    green = False
    if pb:
        with Image.open(pb[0]) as im:
            px = im.convert("RGB").getpixel((5, 5))
            green = px[1] > 100 and px[0] < 80
    chk(a not in seen.get("ids", [a]) and b in seen.get("ids", []) and seen.get("after") == [b], "B 고르기 창 — 지금 명함은 빠지고 찾기로 거름",
        str(seen))
    chk(len(pb) == 1 and green, "B 고른 명함에 고른 사진(초록) 복사", str(pb))
    chk(photos_of(a) == a_photos and fd._card["id"] == a, "B 원래 명함 사진·보던 명함은 그대로")
    chk("가짜을" in (getattr(fd, "flash_text", "") or ""), "B 아래 줄 알림", getattr(fd, "flash_text", ""))
    m = fd.table.model()
    fd.table.scrollTo(m.index(fd.row_of_id(b), 0))
    fd.table.viewport().update()

    def face_green(cid):
        f = m.face_px.get(cid)
        if f is None:
            m.data(m.index(fd.row_of_id(cid), FD.C_NAME), Qt.ItemDataRole.DecorationRole)   # 보이는 줄 그리기와 같은 요청
            return False
        im = f.toImage()
        return im.pixelColor(im.width() // 2, im.height() // 2).green() > 100
    pump(lambda: face_green(b), timeout=5)
    fb = m.face_px.get(b)
    chk(fb is not None and fb.toImage().pixelColor(fb.toImage().width() // 2, fb.toImage().height() // 2).green() > 100,
        "B 받은 명함의 목록 얼굴도 그 사진", "")

    print("\n=== C 목록 줄에 놓기 ===")
    fd.photos.clearSelection()
    fd.photos.item(0).setSelected(True)                # 첫(빨강) 사진
    rc = fd.table.visualRect(fd.table.model().index(fd.row_of_id(c), 0)).center()
    ra = fd.table.visualRect(fd.table.model().index(fd.row_of_id(a), 0)).center()
    chk(not drag_to(fd.table, fd.photos, ra, drop=False), "C 지금 명함 줄 위는 받지 않음")
    chk(drag_to(fd.table, fd.photos, rc), "C 다른 명함 줄 위에 놓기 — 복사로 받음")
    pump(lambda: not fd.photo_busy and len(photos_of(c)) == 1, timeout=8)
    chk(len(photos_of(c)) == 1 and fd.photos.count() == 2 and photos_of(a) == a_photos, "C 그 명함에 복사, 썸네일 줄은 그대로",
        str((photos_of(c), fd.photos.count())))

    print("\n=== D 즐겨찾기 사람 칸에 놓기 ===")
    it_c = next(fd.fav.item(i) for i in range(fd.fav.count()) if fd.fav.item(i).data(FD.ROLE) == c)
    chk(drag_to(fd.fav, fd.photos, fd.fav.visualItemRect(it_c).center()), "D 즐겨찾기 사람 칸에 놓기 — 복사로 받음")
    pump(lambda: not fd.photo_busy and len(photos_of(c)) == 2, timeout=8)
    chk(len(photos_of(c)) == 2 and fd.photos.count() == 2, "D 그 사람에게 하나 더", str(photos_of(c)))

    print("\n=== E 다른 이름으로 저장 ===")
    dst1 = TMP / "내보냄" / "한장.jpg"
    dst1.parent.mkdir()
    QFileDialog.getSaveFileName = staticmethod(lambda *a_, **k_: (str(dst1.with_suffix("")), ""))   # 확장자 없이 적음 → 원본 꼴
    fd.photos.clearSelection()
    fd.photos.item(0).setSelected(True)
    fd.saved_photos = None
    MENUS.clear()
    fd.photos.customContextMenuRequested.emit(fd.photos.visualItemRect(fd.photos.item(0)).center())
    act = next((x for x in MENUS[-1].actions() if x.text() == "다른 이름으로 저장"), None) if MENUS else None
    if act is not None:
        act.trigger()
    pump(lambda: fd.saved_photos == 1, timeout=5)
    chk(dst1.exists() and dst1.read_bytes() == Path(a_photos[0]).read_bytes(), "E 한 장 — 저장 창 이름(+원본 확장자), 바이트 그대로")
    dir2 = TMP / "폴더"
    dir2.mkdir()
    (dir2 / os.path.basename(a_photos[0])).write_bytes(b"x")   # 같은 이름이 이미 있음
    QFileDialog.getExistingDirectory = staticmethod(lambda *a_, **k_: str(dir2))
    fd.saved_photos = None
    chk(fd.save_photos_as(a_photos), "E 여러 장 — 폴더 고르기")
    pump(lambda: fd.saved_photos == 2, timeout=5)
    got = sorted(os.listdir(dir2))
    stem, ext = os.path.splitext(os.path.basename(a_photos[0]))
    chk(len(got) == 3 and ("%s (2)%s" % (stem, ext)) in got, "E 원래 이름, 겹치면 ' (2)'", str(got))
    chk(str(fd._store().meta_get(FD.PHOTO_SAVE_DIR, "")) == str(dir2), "E 지난 폴더 기억")
    chk(not WARN, "경고 없음", str(WARN))
    fd.close()
except Exception as e:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외", repr(e))
finish()
