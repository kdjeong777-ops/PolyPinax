# -*- coding: utf-8 -*-
"""명함 얼굴 썸네일 (명함찾기 SOT §5.24.2 '즐겨찾기 줄'·§5.24.1 '목록 표 얼굴', 261120-76) — 가짜 명함·합성 그림만.

A 얼굴이 있으면 그 얼굴만(얼굴 찾기 결과 상자 둘레 정사각) — 얼굴 찾기는 합성 상자로 바꿔 끼움
B 얼굴이 없으면 중요 부분(테두리 많은 곳)
C 인물 사진이 없으면 명함 앞면 가운데 정사각
D 캐시 — 두 번째는 다시 계산하지 않음
E 윈도우 얼굴 찾기를 실제로 불러도 예외 없음(합성 그림 — 얼굴 0개여도 됨)
F 목록 표 — 줄 높이 LIST_ROW_H, 이름 칸 앞 원형 얼굴(배경에서), 풍선은 큰 얼굴, 계산은 배경(메인 최장 정지 < 1초)
G 즐겨찾기 칸 그림도 얼굴 썸네일(배경)
"""
import os, sys, tempfile, time, threading
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QTimer
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication
from pathlib import Path
from PIL import Image, ImageDraw

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_face_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_face_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
MAIN = threading.main_thread()
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


try:
    from viewer.bizcard import face_thumb as FT, people as P, store as S
    # 합성 사진 — 세로 600×900, 오른쪽 아래에 빨간 '얼굴' 상자, 왼쪽 위에 무늬(테두리 많음)
    ph = TMP / "photo.jpg"
    im = Image.new("RGB", (600, 900), (230, 230, 230))
    d = ImageDraw.Draw(im)
    d.rectangle((380, 600, 500, 740), fill=(220, 40, 40))
    for k in range(0, 260, 12):
        d.line((20 + k, 20, 20, 20 + k), fill=(0, 0, 0), width=3)
    im.save(ph)

    # ── A ──
    print("=== A. 얼굴 ===")
    _faces = FT.faces
    FT.faces = lambda img: [(380, 600, 120, 140)]
    a = FT.crop(str(ph))
    px = a.getpixel((FT.SIZE // 2, FT.SIZE // 2))
    chk(a.size == (FT.SIZE, FT.SIZE) and px[0] > 180 and px[1] < 90, "A 얼굴 상자 둘레 정사각(가운데가 얼굴)", str(px))

    # ── B ──
    print("\n=== B. 중요 부분 ===")
    FT.faces = lambda img: []
    box = FT.salient_box(Image.open(ph).convert("RGB"))
    chk(box[1] < 300 and box[2] - box[0] == 600, "B 얼굴이 없으면 테두리 많은 곳(위쪽 무늬) 정사각", str(box))

    # ── C ──
    print("\n=== C. 명함 앞면 ===")
    card = TMP / "card.jpg"
    Image.new("RGB", (400, 240), "white").save(card)
    c = FT.crop(str(card), from_card=True)
    chk(c.size == (FT.SIZE, FT.SIZE), "C 명함 앞면 가운데 정사각")

    # ── D ──
    print("\n=== D. 캐시 ===")
    n = [0]
    _crop = FT.crop

    def counted(*a_, **k_):
        n[0] += 1
        return _crop(*a_, **k_)
    FT.crop = counted
    t1 = FT.thumb(str(ph))
    t2 = FT.thumb(str(ph))
    FT.crop = _crop
    chk(t1 and t1 == t2 and n[0] == 1 and Path(t1).parent == FT.cache_dir() and FT.cached(str(ph)) == t1, "D 캐시 — 두 번째는 계산 없이", str(n))

    # ── E ──
    FT.faces = _faces
    FT._no_detector = False
    try:
        got = FT.faces(Image.open(ph))
        ok = isinstance(got, list)
    except Exception as e:
        ok = False
    chk(ok, "E 윈도우 얼굴 찾기를 불러도 예외 없음(합성 그림)")

    # ── F·G ──
    print("\n=== F·G. 목록 표·즐겨찾기 ===")
    where = []
    _thumb = FT.thumb

    def rec(*a_, **k_):
        where.append(threading.current_thread() is MAIN)
        return _thumb(*a_, **k_)
    FT.thumb = rec
    FT.faces = lambda img: [(380, 600, 120, 140)]
    db = TMP / "local" / "bizcard.db"
    st = S.BizcardStore(db)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    fold = TMP / "cards" / "정리"
    fold.mkdir(parents=True)
    fr = fold / "가짜일_가짜사.jpg"
    Image.new("RGB", (400, 240), "white").save(fr)
    a1 = st.upsert({"front": str(fr), "name": "가짜일", "company": "가짜사", "phones": [("cell", "010-0000-0001")]})
    P.save_person_photo(str(ph), P.next_photo_path(P.photo_front(P.card_by_id(st, a1), str(TMP / "cards"))))
    b1 = P._insert_contact(st, {"name": "가짜이", "phones": [("cell", "010-0000-0002")]}, ["명함"])
    st.con.commit()
    P.fav_init(st, "즐겨찾기")
    gid = P.fav_add_group(st, "가짜모음")
    P.fav_add(st, gid, [a1])
    st.meta_set("fav_tab", gid)
    st.close()
    settings_store.set_picture_prefs({"bizcard_folder": str(TMP / "cards")})
    from viewer.widgets import bizcard_find_dialog as FD
    fd = FD.BizcardFindDialog(None, db=db)
    fd._bz_folder = str(TMP / "cards")
    gap, last = [0.0], [time.monotonic()]

    def tick():
        now = time.monotonic()
        gap[0] = max(gap[0], now - last[0])
        last[0] = now
    tm = QTimer()
    tm.timeout.connect(tick)
    tm.start(20)
    fd.show()
    pump(lambda: fd.table.rowCount() == 2)
    m = fd.table.model()
    pump(lambda: len(m.face_px) >= 2, timeout=10)
    tm.stop()
    r = m.row_of_id(a1)
    deco = m.data(m.index(r, FD.C_NAME), Qt.ItemDataRole.DecorationRole)
    tip = m.data(m.index(r, FD.C_NAME), Qt.ItemDataRole.ToolTipRole) or ""
    chk(fd.table.verticalHeader().defaultSectionSize() == FD.LIST_ROW_H, "F 줄 높이 LIST_ROW_H")
    chk(deco is not None and not deco.isNull() and m.data(m.index(m.row_of_id(b1), FD.C_NAME), Qt.ItemDataRole.DecorationRole) is not None,
        "F 이름 칸 앞 원형 얼굴(사진 없는 명함은 첫 글자)")
    chk("<img" in tip and str(FD.FACE_TIP) in tip, "F 풍선은 큰 얼굴", tip[:80])
    chk(where and not any(where), "F 얼굴 계산은 배경", str(where[:5]))
    chk(gap[0] < 1.0, "F 메인 최장 정지 < 1초", "%.3f" % gap[0])
    # G — 즐겨찾기 칸
    where.clear()
    i = next(i for i in range(fd.fav_tabs.count()) if fd.fav_tabs.tabData(i) == gid)
    fd.fav_tabs.setCurrentIndex(i)
    fd._fav_fill()
    pump(lambda: getattr(fd, "fav_icons_pending", 1) == 0, timeout=10)
    got_icon = any(fd.fav.item(i).data(FD.ROLE + 1) for i in range(fd.fav.count()))
    chk(fd.fav.count() == 1 and got_icon and where and not any(where), "G 즐겨찾기 칸 그림도 얼굴 썸네일(배경)", str((fd.fav.count(), where)))
    FT.thumb = _thumb
    fd.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외")
print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
