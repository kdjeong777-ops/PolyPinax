# -*- coding: utf-8 -*-
"""경로 꼴로 망가진 그림 없는 명함 열쇠 바로잡기 (명함찾기 SOT §5.24.5 '열쇠', 261122-24) — 가짜 명함·임시 폴더만.

1.1.0-beta.19 이전 [저장](update_card 가 `contact:<번호>` 를 경로로 바꿈 — 261120-10 에 막음)이 남긴 `<작업 폴더>\\contact:<번호>` 행은
'파일 잃은 그림 명함' 으로 보여, 인물 사진·명함 그림을 작업 폴더 옆 엉뚱한 자리(NTFS 대체 스트림)에 쓰려다 실패했다(사용자 보고 261122-23).

A 명함찾기를 열면 망가진 열쇠가 `contact:<번호>` 로 — 먼저 DB 백업(bizcard.db.keys_bak), 알림 한 번, 변경 기록엔 남기지 않음
B 바로잡은 명함에 png 를 아래 칸에 실제로 놓으면 명함 폴더 `인물\\` 에 인물 사진(작업 폴더에 아무것도 생기지 않음)
C update_card 에 망가진 열쇠가 와도 `contact:<번호>` 로 저장
D 옛 변경 기록(망가진 열쇠)을 되살려도 `contact:<번호>`
"""
import os, sys, tempfile, time, json
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QMimeData, QUrl, QPointF, QPoint
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from pathlib import Path
from PIL import Image

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_ckey_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_ckey_"))
WORK = TMP / "작업폴더"                               # 옛 [저장] 때의 작업 폴더 자리 — 여기에 아무것도 생기면 안 된다
WORK.mkdir()
os.chdir(WORK)
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
WARN, INFO = [], []
QMessageBox.warning = staticmethod(lambda *a, **k: (WARN.append(1), QMessageBox.StandardButton.Ok)[1])
QMessageBox.information = staticmethod(lambda *a, **k: (INFO.append(a[2] if len(a) > 2 else ""), QMessageBox.StandardButton.Ok)[1])
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


def bad_key(k):
    return os.path.normcase(os.path.abspath(k))       # 옛 update_card 의 _nk 와 같은 꼴


try:
    from viewer.bizcard import people as P, store as S, vcard as V, history as H
    FOLD = TMP / "cards"
    (FOLD / "정리").mkdir(parents=True)
    db = TMP / "local" / "bizcard.db"
    st = S.BizcardStore(db)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    a = P._insert_contact(st, {"name": "가짜갑", "company": "가짜사", "phones": [("cell", "010-0000-1111")]}, [])
    b = P._insert_contact(st, {"name": "가짜을", "company": "가짜사", "phones": [("cell", "010-0000-2222")]}, [])
    st.con.commit()
    ka = P.card_by_id(st, a)["front"]
    st.con.execute("UPDATE cards SET front=? WHERE id=?", (bad_key(ka), a))   # 옛 판 [저장]이 남긴 모습
    st.con.commit()
    n_hist0 = st.con.execute("SELECT COUNT(*) FROM card_history").fetchone()[0]
    chk(not V.is_contact(P.card_by_id(st, a)), "준비 — 망가진 열쇠는 그림 없는 명함으로 보이지 않음(재현)")
    st.close()
    settings_store.set_picture_prefs({"bizcard_folder": str(FOLD)})
    png = TMP / "받은" / "스크린샷.png"
    png.parent.mkdir()
    Image.new("RGB", (500, 300), "blue").save(png)

    print("=== A 열 때 바로잡기 ===")
    from viewer.widgets import bizcard_find_dialog as FD
    fd = FD.BizcardFindDialog(None, db=db)
    fd._bz_folder = str(FOLD)
    fd.resize(1200, 800)
    fd.show()
    pump(lambda: fd.table.rowCount() == 2 and fd._card is not None)
    pump(lambda: P.card_by_id(fd._store(), a)["front"] == ka, timeout=10)
    pump(timeout=0.3)
    ca = P.card_by_id(fd._store(), a)
    chk(ca["front"] == ka and V.is_contact(ca), "A 열쇠가 contact:<번호> 로", ca["front"])
    chk((TMP / "local" / "bizcard.db.keys_bak").exists(), "A 바꾸기 전 DB 백업(bizcard.db.keys_bak)")
    chk(len(INFO) == 1 and "1" in INFO[0], "A 알림 한 번", str(INFO))
    n_hist = fd._store().con.execute("SELECT COUNT(*) FROM card_history").fetchone()[0]
    chk(n_hist == n_hist0, "A 변경 기록엔 남기지 않음", "%d → %d" % (n_hist0, n_hist))

    print("\n=== B 바로잡은 명함에 인물 사진 ===")
    fd.table.setCurrentCell(fd.row_of_id(a), 0)
    pump(lambda: fd._card is not None and fd._card["id"] == a, timeout=3)
    w = fd.photo_split.widget(1)
    pos = QPointF(w.mapTo(fd, QPoint(w.width() // 2, w.height() // 2)))
    m = QMimeData()
    m.setUrls([QUrl.fromLocalFile(str(png))])
    QApplication.sendEvent(fd, QDragEnterEvent(pos.toPoint(), Qt.DropAction.CopyAction, m, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    QApplication.sendEvent(fd, QDropEvent(pos, Qt.DropAction.CopyAction, m, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    pump(lambda: not fd.photo_busy and (FOLD / "인물" / "가짜갑_가짜사.jpg").exists(), timeout=10)
    chk((FOLD / "인물" / "가짜갑_가짜사.jpg").exists() and not WARN, "B 명함 폴더 인물\\ 에 인물 사진", str(WARN))
    chk(not os.listdir(WORK) and not (TMP / "인물").exists(), "B 작업 폴더 옆엔 아무것도 생기지 않음", str(os.listdir(WORK)))

    print("\n=== C update_card ===")
    st2 = fd._store()
    kb = P.card_by_id(st2, b)["front"]
    P.update_card(st2, b, {"front": bad_key(kb), "memo": "가짜 메모"})
    chk(P.card_by_id(st2, b)["front"] == kb, "C 망가진 열쇠가 와도 contact:<번호> 로 저장", P.card_by_id(st2, b)["front"])

    print("\n=== D 옛 기록 되살리기 ===")
    row = dict(P.card_by_id(st2, b))
    raw = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v) for k, v in row.items()}
    raw["front"] = bad_key(kb)
    raw["memo"] = "옛 메모"
    H.restore(st2, [{"card_id": b, "row": raw}])
    st2.con.commit()
    chk(P.card_by_id(st2, b)["front"] == kb and P.card_by_id(st2, b)["memo"] == "옛 메모",
        "D 되살려도 contact:<번호>", P.card_by_id(st2, b)["front"])
except Exception as e:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외", repr(e))
finish()
