# -*- coding: utf-8 -*-
"""명함 자료 옮기기 zip (명함 SOT §5.31, 261120-73) — 가짜 명함·임시 폴더 둘(옛 PC·새 PC)만, 실제 설정·DB 를 쓰지 않는다.

A 내보낸 zip — DB·정리본·인물 사진, 원본 스캔·클라이언트 보안 비밀·사진 대기열 없음
B 바꾸기 — 지금 것을 먼저 백업 zip, 경로가 새 폴더로, 인물 사진을 찾음, 구글 짝 기록 남음
C 합치기 — 지금 DB 에 없는 명함만, 구글 짝 기록은 가져오지 않음
D 판이 크면 거부(아무것도 바꾸지 않음)
E 창 — ≡ 주소록 메뉴 항목, 배경(메인 최장 정지 < 1초)
"""
import os, sys, tempfile, time, json, zipfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, QTimer
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox
from pathlib import Path
from PIL import Image

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_archive_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_archive_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
from viewer.bizcard import people as P, store as S, gsync as G
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


def scan(st, folder, name, cell, photo=True):
    fold = Path(folder) / "정리"
    fold.mkdir(parents=True, exist_ok=True)
    orig = Path(folder) / ("%s_scan.jpg" % name)
    Image.new("RGB", (300, 200), "white").save(orig)
    f, b = fold / ("%s_가짜사.jpg" % name), fold / ("%s_가짜사_뒷면.jpg" % name)
    Image.new("RGB", (300, 200), "white").save(f)
    Image.new("RGB", (300, 200), "gray").save(b)
    cid = st.upsert({"front": str(f), "back": str(b), "src_key": str(orig), "name": name, "company": "가짜사", "phones": [("cell", cell)]})
    if photo:
        src = TMP / "face.jpg"
        Image.new("RGB", (120, 160), "red").save(src)
        P.save_person_photo(str(src), P.next_photo_path(P.photo_front(P.card_by_id(st, cid), folder)))
    return cid


try:
    from viewer.bizcard import archive as AR
    OLD, NEW = TMP / "옛PC" / "명함", TMP / "새PC" / "내 명함"
    OLD.mkdir(parents=True)
    NEW.mkdir(parents=True)
    old_db = TMP / "옛PC" / "bizcard.db"
    st = S.BizcardStore(old_db)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    a = scan(st, str(OLD), "가짜일", "010-0000-0001")
    b = scan(st, str(OLD), "가짜이", "010-0000-0002", photo=False)
    c = P._insert_contact(st, {"name": "가짜삼", "company": "가짜상사", "phones": [("cell", "010-0000-0003")]}, ["명함"])
    st.con.commit()
    src = TMP / "face2.jpg"
    Image.new("RGB", (120, 160), "blue").save(src)
    P.save_person_photo(str(src), P.next_photo_path(P.photo_front(P.card_by_id(st, c), str(OLD))))
    G._link_put(st, a, "people/g1", "e1")
    st.meta_set("gsync_client_secret", "가짜잠금값")
    st.meta_set(G.QUEUE_KEY, [{"kind": "photo_up", "card_id": a, "side": "", "path": "x"}])
    st.con.commit()
    st.close()

    # ── A ──
    print("=== A. 내보내기 ===")
    out = TMP / "옮김.zip"
    res = AR.export_zip(old_db, str(OLD), out)
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        man = json.loads(z.read("manifest.json"))
        z.extract("bizcard.db", TMP / "peek")
    chk(res["cards"] == 3 and "bizcard.db" in names and any(n.endswith("가짜일_가짜사.jpg") for n in names)
        and any(n.endswith("가짜일_가짜사_뒷면.jpg") for n in names) and sum("/인물/" in n for n in names) == 2,
        "A DB·정리본 앞뒷면·인물 사진(그림 없는 명함 것 포함)", str(names))
    chk(not any("_scan" in n for n in names), "A 원본 스캔은 담지 않음")
    pk = S.BizcardStore(TMP / "peek" / "bizcard.db")
    chk(not pk.meta_get("gsync_client_secret", "") and not pk.meta_get(G.QUEUE_KEY, []) and G.links(pk).get(a),
        "A 비밀값·사진 대기열은 지우고 구글 짝 기록은 담음")
    pk.close()

    # ── D ──
    print("\n=== D. 판 확인 ===")
    bad = TMP / "새판.zip"
    with zipfile.ZipFile(out) as z, zipfile.ZipFile(bad, "w") as w:
        for n in z.namelist():
            data = z.read(n)
            if n == "manifest.json":
                m2 = json.loads(data)
                m2["version"] = AR.VERSION + 1
                data = json.dumps(m2).encode()
            w.writestr(n, data)
    new_db = TMP / "새PC" / "bizcard.db"
    st2 = S.BizcardStore(new_db)
    st2.meta_set(P.KINDS_FIXED_KEY, 1.0)
    keep = scan(st2, str(NEW), "가짜일", "010-0000-0001")              # 새 PC 에도 같은 사람(합치기에서 건너뜀)
    st2.con.commit()
    st2.close()
    try:
        AR.import_zip(bad, new_db, str(NEW), mode="replace")
        got = ""
    except AR.ArchiveError as e:
        got = e.what
    st2 = S.BizcardStore(new_db)
    chk(got == "version" and st2.con.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 1, "D 판이 크면 거부·그대로", got)
    st2.close()

    # ── C ──
    print("\n=== C. 합치기 ===")
    r = AR.import_zip(out, new_db, str(NEW), mode="merge")
    st2 = S.BizcardStore(new_db)
    names2 = sorted(x[0] for x in st2.con.execute("SELECT name FROM cards"))
    chk(r["cards"] == 2 and names2 == sorted(["가짜일", "가짜이", "가짜삼"]) and not G.links(st2),
        "C 없는 명함만 더함·구글 짝은 안 가져옴", str((r, names2)))
    st2.close()

    # ── B ──
    print("\n=== B. 바꾸기 ===")
    r = AR.import_zip(out, new_db, str(NEW), mode="replace", backup_dir=TMP / "새PC")
    st2 = S.BizcardStore(new_db)
    ca = next(x for x in (st2._row(y) for y in st2.con.execute("SELECT * FROM cards")) if x["name"] == "가짜일")
    cc = next(x for x in (st2._row(y) for y in st2.con.execute("SELECT * FROM cards")) if x["name"] == "가짜삼")
    nfront = os.path.normcase(ca["front"])
    chk(r["backup"] and Path(r["backup"]).exists() and zipfile.is_zipfile(r["backup"]), "B 바꾸기 전 지금 것을 백업 zip", str(r))
    chk(nfront.startswith(os.path.normcase(str(NEW))) and os.path.exists(ca["front"]) and os.path.exists(ca["back"]),
        "B 경로가 새 폴더로·파일 있음", ca["front"])
    chk(len(P.person_photos(P.photo_front(ca, str(NEW)))) == 1 and len(P.person_photos(P.photo_front(cc, str(NEW)))) == 1,
        "B 인물 사진을 찾음(그림 없는 명함 것도)")
    chk(G.links(st2).get(ca["id"], {}).get("rn") == "people/g1" and st2.con.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 3,
        "B 구글 짝 기록 남음·명함 3장")
    st2.close()

    # ── E ──
    print("\n=== E. 창 ===")
    settings_store.set_picture_prefs({"bizcard_folder": str(OLD)})
    from viewer.widgets import bizcard_find_dialog as FD
    fd = FD.BizcardFindDialog(None, db=old_db)
    fd.show()
    pump(lambda: fd.table.rowCount() == 3)
    acts = [x.text() for x in fd.vcard_menu.actions()]
    chk("명함 자료 내보내기(zip)" in acts and "명함 자료 불러오기(zip)" in acts, "E ≡ 주소록 메뉴 항목", str(acts))
    gap, last = [0.0], [time.monotonic()]

    def tick():
        now = time.monotonic()
        gap[0] = max(gap[0], now - last[0])
        last[0] = now
    tm = QTimer()
    tm.timeout.connect(tick)
    tm.start(20)
    out2 = TMP / "창.zip"
    fd.export_archive(path=str(out2))
    pump(lambda: not getattr(fd, "archive_busy", False) and out2.exists(), timeout=15)
    fd.import_archive(path=str(out2), mode="replace")
    pump(lambda: not getattr(fd, "archive_busy", False), timeout=15)
    pump(lambda: fd.table.rowCount() == 3, timeout=5)
    tm.stop()
    chk(out2.exists() and (fd.archive_result or {}).get("cards") == 3 and fd.table.rowCount() == 3, "E 창에서 내보내기·바꾸기 — 끝나면 목록 다시",
        str(getattr(fd, "archive_result", None)))
    chk(gap[0] < 1.0, "E 메인 최장 정지 < 1초", "%.3f" % gap[0])
    fd.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외")
print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
