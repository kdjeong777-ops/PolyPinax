# -*- coding: utf-8 -*-
"""명함찾기 구분 거르기 손보기 (명함찾기 SOT §5.24.1 '구분'·'이름 앞 # 빼기', 261122-10) — 가짜 명함·임시 폴더만.

A 탭 명단 보기(즐겨찾기 탭을 누름, 찾기 칸 빈 채)에도 구분이 걸림 — 한글·명함 있음·사진 있음 = 셋 다 맞는 사람만
B 탭 명단 보기에서 체크를 바꾸면 그 명단을 곧바로 다시 거름(찾기 결과로 빠지지 않음)
C 구분 '이름 # 있음'·'이름 # 없음'
D 고른 줄 '이름 앞 # 빼기' — 이름·정리본 파일 이름이 바뀌고 변경 기록 출처 '# 빼기', '#' 없는 줄은 그대로
"""
import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox
from pathlib import Path
from PIL import Image

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_kindf_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_kindf_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


def pump(t=0.4):
    e = time.monotonic() + t
    while time.monotonic() < e:
        app.processEvents()
        time.sleep(0.01)


try:
    from viewer.bizcard import people as P, store as S, history as H
    FOLD = TMP / "cards"
    OUT = FOLD / "정리"
    OUT.mkdir(parents=True)
    db = TMP / "local" / "bizcard.db"
    st = S.BizcardStore(db)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    ids = {}
    for nm, card, photo in (("가짜갑", 1, 1), ("가짜을", 1, 0), ("가짜병", 0, 1), ("Fake Jung", 1, 1), ("#가짜무", 1, 1)):
        if card:
            f = OUT / ("%s_가짜사.jpg" % nm.lstrip("#"))
            Image.new("RGB", (300, 180), "white").save(f)
            cid = st.upsert({"front": str(f), "name": nm, "company": "가짜사"})
        else:
            cid = P._insert_contact(st, {"name": nm, "company": "가짜사"}, ["명함"])
        ids[nm] = cid
        if photo:
            pp = P.next_photo_path(P.photo_front(P.card_by_id(st, cid), str(FOLD)))
            pp.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (60, 80), "red").save(pp)
    st.con.commit()
    P.fav_init(st, "즐겨찾기")
    gid = P.fav_groups(st)[0][0]
    P.fav_add(st, gid, list(ids.values()))
    st.con.commit()
    st.close()
    settings_store.set_picture_prefs({"bizcard_folder": str(FOLD)})

    from viewer.bizcard import face_thumb as FT
    FT._no_detector = True                                       # 즐겨찾기 사람 칸 얼굴 찾기(winrt)는 이 검사와 상관없음 — 끔
    from viewer.widgets import bizcard_find_dialog as FD
    fd = FD.BizcardFindDialog(None, db=db)
    fd._bz_folder = str(FOLD)
    fd.show()
    pump(1.0)
    names = lambda: sorted(c["name"] for c in fd._rows)          # noqa: E731

    print("=== A 탭 명단 보기에도 거름 ===")
    fd.cb_kind.set_keys(["ko", "card", "photo"], emit=True)
    pump()
    ti = next(i for i in range(fd.fav_tabs.count()) if fd.fav_tabs.tabData(i) == gid)
    fd.fav_tabs.setCurrentIndex(ti)
    fd._tab_clicked(ti)                                          # 탭을 누름(찾기 칸은 빈 채)
    pump()
    chk(fd._table_tab == gid and not fd.ed_find.text(), "(전제) 탭 명단 보기·찾기 칸 빔")
    chk(names() == ["#가짜무", "가짜갑"], "A 한글·명함 있음·사진 있음 셋 다 맞는 사람만", str(names()))

    print("\n=== B 탭 명단에서 체크를 바꾸면 곧바로 ===")
    fd.cb_kind.toggle("photo")                                   # 사진 있음 끔 → 한글·명함 있음
    pump()
    chk(fd._table_tab == gid and names() == ["#가짜무", "가짜갑", "가짜을"], "B 탭 명단 그대로 다시 거름", "%s %s" % (fd._table_tab, names()))

    print("\n=== C 이름 # ===")
    chk([fd.cb_kind.itemData(i) for i in range(fd.cb_kind.count()) if fd.cb_kind.itemData(i)]
        == ["all", "ko", "en", "card", "nocard", "photo", "nophoto", "hash", "nohash", "kakao"], "C 구분에 '이름 # 있음·없음'")
    fd.cb_kind.set_keys(["hash"], emit=True)
    pump()
    chk(names() == ["#가짜무"], "C 이름 # 있음", str(names()))
    fd.cb_kind.set_keys(["nohash"], emit=True)
    pump()
    chk("#가짜무" not in names() and len(names()) == 4, "C 이름 # 없음", str(names()))

    print("\n=== D 고른 줄 이름 앞 # 빼기 ===")
    fd.cb_kind.set_keys(["all"], emit=True)
    pump()
    picks = [c for c in fd._rows if c["id"] in (ids["#가짜무"], ids["가짜갑"])]
    t0 = time.time() - 1
    n = fd.unhash(picks, ask=False)
    pump()
    mu = P.card_by_id(fd._store(), ids["#가짜무"])
    gab = P.card_by_id(fd._store(), ids["가짜갑"])
    chk(n == 1 and mu["name"] == "가짜무" and gab["name"] == "가짜갑", "D '#' 있는 줄만 이름에서 뗌", "%s %s" % (n, mu["name"]))
    chk(os.path.basename(P._real(mu["front"])) == "가짜무_가짜사 (2).jpg" or os.path.basename(P._real(mu["front"])).startswith("가짜무_가짜사"),
        "D 정리본 파일 이름도 '성명_회사명'", os.path.basename(P._real(mu["front"])))
    ent = H.entries(fd._store(), t0, time.time() + 1, srcs=["unhash"])
    chk([e["card_id"] for e in ent] == [ids["#가짜무"]] and ent[0]["row"].get("name") == "#가짜무",
        "D 변경 기록 출처 '# 빼기' — 옛 이름으로 되살릴 수 있음", str([(e["card_id"], e["row"].get("name")) for e in ent]))
except Exception as e:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외", repr(e))
print("FAILURES: %d" % len(fails))
for f in fails:
    print("  -", f)
sys.stdout.flush()
os._exit(1 if fails else 0)
