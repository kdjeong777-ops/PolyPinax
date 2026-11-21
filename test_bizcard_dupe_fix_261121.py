# -*- coding: utf-8 -*-
"""중복 검토 — 숨은 둘째 번호까지 고치기·고친 뒤 다시 묶기·잘못 붙은 명함 그림 떼기 (명함 SOT §5.24.8 '명함 고치기'·'그림 떼기').
가짜 명함·가짜 번호(010-0000-…)·임시 폴더만(§2.1).

A '명함 고치기' 창에 종류마다 둘째 번호·둘째 메일도 칸으로 — 비우면 지우고, 고친 뒤 다시 묶어 그 번호로 이어졌던 명함은 빠짐
B '명함 그림 떼기' — 정리본 앞·뒷면은 휴지통, 명함은 그림 없는 명함(연락처·메모 그대로), 인물 사진은 새 자리로, 원본 스캔은 그대로
"""
import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox, QMenu
from pathlib import Path
from PIL import Image

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_dupefix_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_dupefix_"))
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
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
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
    from viewer.bizcard import people as P, store as S, vcard as V
    db = TMP / "local" / "bizcard.db"
    st = S.BizcardStore(db)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    fold = TMP / "cards" / "정리"
    fold.mkdir(parents=True)
    orig = TMP / "cards" / "scan_1.jpg"
    Image.new("RGB", (340, 200), "white").save(orig)
    front, back = fold / "가짜대표_가짜사.jpg", fold / "가짜대표_가짜사_뒷면.jpg"
    Image.new("RGB", (340, 200), "white").save(front)
    Image.new("RGB", (340, 200), "gray").save(back)
    rep = st.upsert({"front": str(front), "back": str(back), "src_key": str(orig), "name": "가짜대표", "company": "가짜사",
                     "phones": [("cell", "010-0000-1000"), ("cell", "010-0000-2000")], "emails": ["a@example.com", "b@example.com"],
                     "memo": "가짜 메모"})
    pf = P.photo_front(P.card_by_id(st, rep), "")
    src = TMP / "face.jpg"
    Image.new("RGB", (120, 160), "red").save(src)
    P.save_person_photo(str(src), P.next_photo_path(pf))
    P.apply_import(st, [{"name": "가짜둘", "company": "", "phones": [("cell", "010-0000-2000")], "emails": [], "urls": []}],
                   "주소록", "google")
    st.close()

    from viewer.widgets import bizcard_find_dialog as FD
    from viewer.widgets import bizcard_dupe_dialog as DD
    fd = FD.BizcardFindDialog(None, db=db)
    fd._bz_folder = str(TMP / "cards")
    fd.show()
    pump(lambda: fd.table.rowCount() >= 2)
    dd = fd.open_dupes(exec_=False)
    pump(lambda: bool(dd.groups))
    chk(len(dd.groups) == 1, "(전제) 대표의 숨은 둘째 휴대폰으로 '같은 번호' 한 묶음", str(len(dd.groups)))

    # ── A ──
    print("=== A. 숨은 번호까지 고치기 ===")
    gi = 0
    rc = P.card_by_id(fd._store(), rep)
    ed = DD.CardEditDialog(rc, dd)
    texts = [(g, k, e.text()) for g, k, e in getattr(ed, "extra_eds", [])]
    chk(("phone", "cell", "010-0000-2000") in texts and ("email", "", "b@example.com") in texts,
        "A 둘째 휴대폰·둘째 메일도 칸으로 보임", str(texts))
    for g, k, e in getattr(ed, "extra_eds", []):
        if g == "phone":
            e.setText("")                                 # 비우면 지움
    dd.edit_card(gi, rep, dlg=ed)
    pump(lambda: not getattr(dd, "working", False))
    after = P.card_by_id(fd._store(), rep)
    chk([n for _k, n in after["phones"]] == ["010-0000-1000"] and after["emails"] == ["a@example.com", "b@example.com"],
        "A 비운 둘째 휴대폰만 지움(나머지 그대로)", str((after["phones"], after["emails"])))
    chk(dd.groups == [], "A 고친 뒤 다시 묶어 그 번호로 이어졌던 명함은 빠짐", str(len(dd.groups)))

    # ── B ──
    print("\n=== B. 명함 그림 떼기 ===")
    cc = P.card_by_id(fd._store(), rep)
    ok = dd.detach_image(rep, ask=False) if hasattr(dd, "detach_image") else False
    pump(lambda: not front.exists(), timeout=5)
    c2 = P.card_by_id(fd._store(), rep)
    chk(ok and V.is_contact(c2) and not front.exists() and not back.exists(), "B 정리본 앞·뒷면은 휴지통, 그림 없는 명함으로",
        str((ok, c2.get("front"), front.exists())))
    chk(c2["name"] == "가짜대표" and "가짜 메모" in c2["memo"] and orig.exists() and not c2.get("src_key"),
        "B 연락처·메모 그대로, 원본 스캔은 남고 인식 기록 열쇠는 뗌", str((c2.get("memo"), orig.exists(), c2.get("src_key"))))
    newpf = P.photo_front(c2, str(TMP / "cards"))
    chk(newpf and len(P.person_photos(newpf)) == 1, "B 인물 사진은 그림 없는 명함 자리로", str(newpf))
    m = []
    QMenu.exec = lambda self, *a, **k: m.append([x.text() for x in self.actions()])
    dd.reload()
    dd.close()
    fd.close()
    pump(lambda: False, timeout=1)
    import gc; gc.collect()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외")
print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
