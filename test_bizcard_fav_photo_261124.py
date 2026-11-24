# -*- coding: utf-8 -*-
"""인물 사진 차례 바꾸기 뒤 목록 얼굴·즐겨찾기 선택 (명함 SOT §5.24.1 '목록 표 얼굴'·§5.24.2 '다시 채울 때', 261122-25) — 가짜 명함·합성 그림만.

사용자 보고: 즐겨찾기 썸네일은 사진이 바뀔 때 바로 바뀌는데 목록 썸네일은 처음 사진으로 고정 · 즐겨찾기 명단 중 한 명의 사진을
좌우로 옮기다 보면 갑자기 즐겨찾기 첫 명단으로 바뀜.

A 썸네일 줄에서 둘째 사진을 첫 자리에 놓으면(끌어 놓기 이벤트) 목록 표 얼굴도 새 첫 사진으로
B 그 뒤 즐겨찾기 칸은 보던 사람을 고른 채, 칸에 포커스가 돌아와도(창 전환) 보던 명함 그대로
C 보던 명함이 그 탭에 없을 때 포커스가 돌아와도 첫 사람으로 넘어가지 않음
D 즐겨찾기 칸에서 → 키로 옮기면 그 사람(종전 그대로)
"""
import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QMimeData, QPointF, QPoint
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QDropEvent, QDragEnterEvent, QDragMoveEvent
from PyQt6.QtTest import QTest
from pathlib import Path
from PIL import Image

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_favphoto_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_favphoto_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
WARN = []
QMessageBox.warning = staticmethod(lambda *a, **k: (WARN.append(1), QMessageBox.StandardButton.Ok)[1])
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
    """끌기 이벤트 — 끈 위젯(source)을 정해 둔다(가짜 끌기 이벤트는 source 가 비어 앱 안 끌기와 가를 수 없다)."""
    class E(cls):
        def __init__(self, src, *a):
            super().__init__(*a)
            self._src = src

        def source(self):
            return self._src
    return E


DropE, EnterE, MoveE = _with_source(QDropEvent), _with_source(QDragEnterEvent), _with_source(QDragMoveEvent)


def drop_on(view, src, pos):
    md = QMimeData()
    md.setData("application/x-qabstractitemmodeldatalist", b"")
    vp = view.viewport()
    p = QPointF(pos)
    QApplication.sendEvent(vp, EnterE(src, pos, Qt.DropAction.MoveAction, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    QApplication.sendEvent(vp, MoveE(src, pos, Qt.DropAction.MoveAction, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    QApplication.sendEvent(vp, DropE(src, p, Qt.DropAction.MoveAction, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))


def mid_color(pm):
    im = pm.toImage()
    return im.pixelColor(im.width() // 2, im.height() // 2)


try:
    from viewer.bizcard import people as P, store as S, face_thumb as FT
    FT.faces = lambda img: []                       # 얼굴 찾기 없이(합성 단색 그림 — 중요 부분 = 가운데)
    FOLD = TMP / "cards"
    (FOLD / "정리").mkdir(parents=True)
    db = TMP / "local" / "bizcard.db"
    st = S.BizcardStore(db)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    ids = [P._insert_contact(st, {"name": nm, "company": "가짜사", "phones": [("cell", "010-0000-000%d" % i)]}, ["명함"])
           for i, nm in enumerate(("가짜갑", "가짜을", "가짜병"))]
    out = P._insert_contact(st, {"name": "가짜정", "company": "다른사", "phones": [("cell", "010-0000-0009")]}, ["명함"])
    st.con.commit()
    for cid in ids:
        pf = P.photo_front(P.card_by_id(st, cid), str(FOLD))
        for col in ("red", "blue"):
            src = TMP / ("s_%s.png" % col)
            Image.new("RGB", (300, 300), col).save(src)
            P.save_person_photo(str(src), P.next_photo_path(pf))
    P.fav_init(st, "즐겨찾기")
    gid = P.fav_add_group(st, "가짜모음")
    P.fav_add(st, gid, ids)
    st.meta_set("fav_tab", gid)
    st.close()
    settings_store.set_picture_prefs({"bizcard_folder": str(FOLD)})

    from viewer.widgets import bizcard_find_dialog as FD
    fd = FD.BizcardFindDialog(None, db=db)
    fd._bz_folder = str(FOLD)
    fd.resize(1300, 850)
    fd.show()
    fd.activateWindow()
    pump(lambda: fd.table.rowCount() == 4 and fd.fav.count() == 3)
    m = fd.table.model()
    pump(lambda: all(c in m.face_px for c in ids), timeout=10)

    print("=== A 차례 바꾸기 → 목록 얼굴 ===")
    it = fd.fav.item(1)
    QTest.mouseClick(fd.fav.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, fd.fav.visualItemRect(it).center())
    pump(lambda: fd._card is not None and fd._card["id"] == ids[1], timeout=3)
    cid = ids[1]
    pump(lambda: cid in m.face_px, timeout=5)
    c0 = mid_color(m.face_px[cid])
    chk(c0.red() > 200 and c0.blue() < 60, "A 처음 목록 얼굴 = 첫 사진(빨강)", c0.name())
    r1 = fd.photos.visualItemRect(fd.photos.item(1))
    QTest.mouseClick(fd.photos.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, r1.center())
    pump(timeout=0.2)
    r0 = fd.photos.visualItemRect(fd.photos.item(0))
    drop_on(fd.photos, fd.photos, QPoint(r0.left() + 4, r0.center().y()))   # 첫 칸 왼쪽 절반 = 맨 앞
    pump(lambda: cid in m.face_px and mid_color(m.face_px[cid]).blue() > 200, timeout=8)
    first = P.person_photos(P.photo_front(P.card_by_id(fd._store(), cid), str(FOLD)))[0]
    with Image.open(first) as im:
        moved = im.convert("RGB").getpixel((10, 10))[2] > 200
    c1 = mid_color(m.face_px[cid]) if cid in m.face_px else None
    chk(moved, "A 준비 — 첫 사진 파일이 파랑으로 바뀜(이름은 그대로)")
    chk(c1 is not None and c1.blue() > 200 and c1.red() < 60, "A 목록 얼굴도 새 첫 사진(파랑)", c1.name() if c1 else "없음")

    print("\n=== B 다시 채운 뒤 즐겨찾기 선택 ===")
    cur = fd.fav.currentItem()
    chk(cur is not None and cur.data(FD.ROLE) == cid, "B 보던 사람이 지금 칸(선택은 바꾸지 않음)",
        repr(cur.data(FD.ROLE) if cur else None))
    fd.fav.clearFocus()
    fd.fav.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
    pump(timeout=FD.FAV_KEY_MS / 1000.0 + 0.6)
    chk(fd._card is not None and fd._card["id"] == cid, "B 포커스가 돌아와도 보던 명함 그대로", fd._card and fd._card["name"])

    print("\n=== C 보던 명함이 탭에 없을 때 ===")
    fd.table.setCurrentCell(fd.row_of_id(out), 0)
    pump(lambda: fd._card is not None and fd._card["id"] == out, timeout=3)
    fd._fav_fill()                                     # 다시 채움(사진 넣기·저장 등과 같은 길)
    fd.fav.clearFocus()
    fd.fav.setFocus(Qt.FocusReason.TabFocusReason)
    pump(timeout=FD.FAV_KEY_MS / 1000.0 + 0.6)
    chk(fd._card is not None and fd._card["id"] == out, "C 첫 사람으로 넘어가지 않음", fd._card and fd._card["name"])

    print("\n=== D 키보드로 옮김 ===")
    QTest.mouseClick(fd.fav.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     fd.fav.visualItemRect(fd.fav.item(0)).center())
    pump(lambda: fd._card is not None and fd._card["id"] == ids[0], timeout=3)
    QTest.keyClick(fd.fav, Qt.Key.Key_Right)
    pump(lambda: fd._card is not None and fd._card["id"] == ids[1], timeout=FD.FAV_KEY_MS / 1000.0 + 2)
    chk(fd._card is not None and fd._card["id"] == ids[1], "D → 키로 다음 사람", fd._card and fd._card["name"])
    chk(not WARN, "경고 없음", str(WARN))
    fd.close()
except Exception as e:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외", repr(e))
finish()
