# -*- coding: utf-8 -*-
"""명함 사진창 붙여넣기·주소록 메뉴 차례 (명함 SOT §5.24.3 '붙여넣기'·§5.24 '주소록 단추', 261122-21) — 가짜 명함·임시 폴더만.

A 클립보드의 그림 자체(화면 캡처처럼)를 실제 Ctrl+V(목록 표에 커서) → 인물 사진 JPG(크기 그대로)
B 탐색기에서 복사한 그림 파일(파일 목록)을 Ctrl+V → 인물 사진 하나 더
C 글 칸(찾기 칸)에 커서 + 클립보드가 글이면 Ctrl+V 는 글 칸 몫 — 인물 사진이 늘지 않음(그림뿐이면 그림 — 261122-23, test_bizcard_paste_fix_261124)
D 사진창 우클릭 '붙여넣기' — 클립보드에 그림이 있으면 켜짐·누르면 붙음, 그림이 없으면 흐림
E ≡ 주소록 메뉴 맨 위 = '구글 주소록과 싱크', 그 뒤 구분선
"""
import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QMimeData, QUrl, QPoint
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox, QMenu
from PyQt6.QtGui import QImage, QColor, QCursor
from PyQt6.QtTest import QTest
from pathlib import Path
from PIL import Image

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_paste_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_paste_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
WARN = []
QMessageBox.warning = staticmethod(lambda *a, **k: (WARN.append(1), QMessageBox.StandardButton.Ok)[1])
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
MENUS = []
QMenu.exec = lambda self, *a, **k: MENUS.append(self)  # 우클릭 메뉴는 띄우지 않고 잡아 둔다
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
    png = TMP / "받은" / "가짜 사진.png"
    png.parent.mkdir()
    Image.new("RGB", (90, 70), "blue").save(png)

    from viewer.widgets import bizcard_find_dialog as FD
    fd = FD.BizcardFindDialog(None, db=db)
    fd._bz_folder = str(FOLD)
    fd.resize(1200, 800)
    fd.show()
    pump(lambda: fd.table.rowCount() == 1 and fd._card is not None)
    pump(timeout=0.3)
    cb = QApplication.clipboard()

    def photos():
        return P.person_photos(P.photo_front(P.card_by_id(fd._store(), a), str(FOLD)))

    def ctrl_v(w):
        QCursor.setPos(-500, -500)                     # 마우스는 창 밖 — Ctrl+V 는 인물 사진(261122-22: 위 명함 칸 위면 명함 그림)
        fd.activateWindow()
        w.setFocus()
        pump(timeout=0.05)
        QTest.keyClick(w, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)

    print("=== A 그림 자체 Ctrl+V ===")
    im = QImage(120, 80, QImage.Format.Format_RGB32)
    im.fill(QColor("red"))
    cb.setImage(im)
    ctrl_v(fd.table)
    pump(lambda: not fd.photo_busy and len(photos()) >= 1, timeout=10)
    phs = photos()
    ok = len(phs) == 1 and not WARN
    if ok:
        with Image.open(phs[0]) as pim:
            ok = pim.format == "JPEG" and pim.size == (120, 80) and phs[0].lower().endswith(".jpg")
    chk(ok, "A 클립보드 그림 → 인물 사진 JPG(120×80)", "%s %s" % (phs, WARN))

    print("\n=== B 그림 파일 목록 Ctrl+V ===")
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(str(png))])
    cb.setMimeData(md)
    ctrl_v(fd.table)
    pump(lambda: not fd.photo_busy and len(photos()) >= 2, timeout=10)
    phs = photos()
    chk(len(phs) == 2 and not WARN, "B 복사한 그림 파일 → 인물 사진 하나 더", "%s %s" % (phs, WARN))
    chk(png.exists(), "B 원본 파일은 그대로")

    print("\n=== C 글 칸에서는 글 붙여넣기 ===")
    cb.setText("가짜글")
    ctrl_v(fd.ed_find)
    pump(timeout=0.8)
    chk(len(photos()) == 2 and not fd.photo_busy, "C 찾기 칸에 커서·클립보드 글 — 인물 사진이 늘지 않음", str(photos()))
    fd.ed_find.clear()                                 # 붙은 글이 목록을 거르지 않게
    fd.refresh()
    pump(lambda: fd._card is not None, timeout=3)

    print("\n=== D 사진창 우클릭 '붙여넣기' ===")

    def menu_on_view():
        MENUS.clear()
        fd.photo_view.customContextMenuRequested.emit(QPoint(5, 5))
        acts = [x for x in MENUS[-1].actions() if x.text() == "붙여넣기"] if MENUS else []
        return acts[0] if acts else None

    cb.setImage(im)
    act = menu_on_view()
    chk(act is not None and act.isEnabled(), "D 그림이 있으면 '붙여넣기' 켜짐", repr(act))
    if act is not None:
        act.trigger()
    pump(lambda: not fd.photo_busy and len(photos()) >= 3, timeout=10)
    chk(len(photos()) == 3, "D '붙여넣기' 를 누르면 붙음", str(photos()))
    md2 = QMimeData()
    md2.setText("글만")
    cb.setMimeData(md2)
    act = menu_on_view()
    chk(act is not None and not act.isEnabled(), "D 그림이 없으면 '붙여넣기' 흐림", repr(act))

    print("\n=== E 주소록 메뉴 차례 ===")
    acts = fd.vcard_menu.actions()
    chk(len(acts) > 1 and acts[0].text() == "구글 주소록과 싱크" and acts[1].isSeparator(),
        "E 주소록 메뉴 맨 위 = 구글 주소록과 싱크, 그 뒤 구분선", str([x.text() for x in acts[:3]]))
except Exception as e:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외", repr(e))
finish()
