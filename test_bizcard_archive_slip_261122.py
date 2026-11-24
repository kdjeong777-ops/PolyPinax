# -*- coding: utf-8 -*-
"""명함 자료 zip — 폴더 밖으로 쓰는 zip 거부(zip slip, 명함찾기 SOT §5.31 '판 확인', 261120-78 ①). 가짜 명함·임시 폴더만.

A manifest 파일 지도에 '..' 가 든 이름 → 거부(ArchiveError format), 명함 폴더 밖에 아무것도 쓰지 않음, DB 그대로
B 절대 경로 이름 → 거부
C 지도에 없는 zip 안 이름이라도 '..' 면 거부(지도 값만 믿지 않음)
"""
import os, sys, tempfile, json, zipfile, sqlite3
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication
from pathlib import Path
from PIL import Image

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_slip_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_slip_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
from viewer.bizcard import people as P, store as S, archive as AR
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


def evil_zip(name, arc):
    src = TMP / "src.db"
    st = S.BizcardStore(src)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    P._insert_contact(st, {"name": "가짜일", "phones": [("cell", "010-0000-0001")]}, ["명함"])
    st.con.commit()
    st.close()
    z = TMP / name
    jpg = TMP / "x.jpg"
    Image.new("RGB", (20, 20), "red").save(jpg)
    man = {"format": AR.FORMAT, "version": AR.VERSION, "schema": 1, "folder": "", "cards": 1, "map": {"c:\\old\\x.jpg": arc}}
    with zipfile.ZipFile(z, "w") as w:
        w.writestr("manifest.json", json.dumps(man))
        w.write(src, "bizcard.db")
        w.write(jpg, arc)
    return z


try:
    NEW = TMP / "새PC" / "명함"
    NEW.mkdir(parents=True)
    db = TMP / "새PC" / "bizcard.db"
    st = S.BizcardStore(db)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    P._insert_contact(st, {"name": "지금사람", "phones": [("cell", "010-0000-0009")]}, ["명함"])
    st.con.commit()
    st.close()
    for tag, arc, outside in (("A", "files/../../밖.jpg", TMP / "밖.jpg"),
                              ("B", "files/" + str(TMP / "절대밖.jpg").replace("\\", "/"), TMP / "절대밖.jpg")):
        z = evil_zip("evil_%s.zip" % tag, arc)
        for mode in ("replace", "merge"):
            try:
                AR.import_zip(z, db, str(NEW), mode=mode, backup_dir=TMP / "bak")
                got = ""
            except AR.ArchiveError as e:
                got = e.what
            except Exception as e:
                got = "other:" + type(e).__name__
            con = sqlite3.connect(str(db))
            names = sorted(r[0] for r in con.execute("SELECT name FROM cards"))
            con.close()
            chk(got == "format" and not outside.exists() and names == ["지금사람"],
                "%s(%s) 폴더 밖으로 쓰는 이름은 거부·밖에 안 씀·DB 그대로" % (tag, mode), str((got, outside.exists(), names)))
    # C — read_manifest 단계에서 거름(파일을 하나도 풀기 전)
    z = evil_zip("evil_C.zip", "files/../../밖C.jpg")
    try:
        AR.read_manifest(z)
        got = ""
    except AR.ArchiveError as e:
        got = e.what
    chk(got == "format", "C 판 확인 단계에서 거름", got)
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외")
print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
