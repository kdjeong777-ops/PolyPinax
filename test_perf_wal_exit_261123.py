# -*- coding: utf-8 -*-
"""끝낼 때 모든 SQLite WAL 비우기 (응답성 SOT §4 ⑤ '끝낼 때 WAL 을 비운다', 261122-3) — 임시 폴더·가짜 DB 만.

앱은 `os._exit` 로 끝나 연결을 닫지 않는다 — index.db·study.db·dict.db·photo_index.db 의 -wal 이 남아 다음 실행·다른 프로세스에 얹혔다
(명함 DB 손상 261123 은 WAL 이 두 벌로 갈라진 탓, 묵은 WAL 이 피해를 키움).
A. 자식 프로세스가 실제 색인(PdfIndex)·사전(DictStore)·명함(BizcardStore)을 연 채 main._close_dbs() → os._exit — 남은 -wal 이 모두 0바이트
B. 다른 연결이 읽기를 쥔 DB 는 대기 상한 뒤 건너뛰고 전체 시간 상한 안에 끝남
"""
import os, sys, tempfile, time, subprocess, sqlite3
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


CHILD = r'''
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, sys.argv[1])
d = sys.argv[2]
from viewer.indexer import PdfIndex
from viewer.study.dict_store import DictStore
from viewer.bizcard.store import BizcardStore
from viewer.bizcard import people as P
idx = PdfIndex(os.path.join(d, "index.db"))
idx.conn.execute("CREATE TABLE IF NOT EXISTS t_fill(x TEXT)")
idx.conn.executemany("INSERT INTO t_fill VALUES(?)", [("가짜" * 50,)] * 500)
idx.conn.commit()
ds = DictStore(os.path.join(d, "dict.db"))
bz = BizcardStore(os.path.join(d, "bizcard.db"))
P._insert_contact(bz, {"name": "가짜", "phones": [("cell", "010-0000-1111")]}, ["명함"])
bz.con.commit()
print("before", {f: os.path.getsize(os.path.join(d, f)) for f in os.listdir(d) if f.endswith("-wal")}, flush=True)
import main
main._close_dbs()
sys.stdout.flush()
os._exit(0)
'''

try:
    d = tempfile.mkdtemp(prefix="wal_exit_")
    script = os.path.join(d, "child.py")
    open(script, "w", encoding="utf-8").write(CHILD)
    env = dict(os.environ, POLYPDF_PROFILE="test_wal_%d" % os.getpid(), QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, script, HERE, d], env=env, capture_output=True, text=True, encoding="utf-8", timeout=120)
    print(r.stdout.strip()[-400:])
    if r.returncode != 0:
        print(r.stderr[-1500:])
    wals = {f: os.path.getsize(os.path.join(d, f)) for f in os.listdir(d) if f.endswith("-wal")}
    before_ok = "index.db-wal" in r.stdout and "bizcard.db-wal" in r.stdout
    chk(r.returncode == 0 and before_ok and wals and all(v == 0 for v in wals.values()),
        "A 끝내기 직전 색인·사전·명함 DB 의 -wal 이 모두 비워짐(os._exit 로 끝나도)", str(wals))

    print("\n=== B 읽기를 쥔 DB ===")
    from viewer import dbutil
    db2 = os.path.join(d, "busy.db")
    c = dbutil.connect(db2)
    c.execute("CREATE TABLE t(x)")
    c.executemany("INSERT INTO t VALUES(?)", [(i,) for i in range(2000)])
    c.commit()
    reader = sqlite3.connect(db2)
    reader.execute("BEGIN")
    reader.execute("SELECT count(*) FROM t").fetchone()          # 읽기 트랜잭션을 쥔 채
    t0 = time.monotonic()
    dbutil.checkpoint_all(budget_s=3.0, busy_ms=300)
    el = time.monotonic() - t0
    reader.rollback()
    reader.close()
    chk(el < 3.5, "B 읽기를 쥔 DB 가 있어도 시간 상한 안에 끝남", "%.2fs" % el)
    c.close()

    print("\n=== D 명함 연결 닫기는 기다리지 않음(261122-9) ===")
    from viewer.bizcard.store import BizcardStore
    db3 = os.path.join(d, "bz_busy.db")
    bg = BizcardStore(db3)                                        # 배경 일꾼의 연결(대기 30초)
    bg.meta_set("x", "가짜")                                      # WAL 에 쓴 것이 있게
    holder = sqlite3.connect(db3)
    holder.execute("BEGIN")
    holder.execute("SELECT count(*) FROM meta").fetchone()       # 다른 연결이 읽기를 쥔 채(TRUNCATE 는 이것이 끝나길 기다린다)
    t0 = time.monotonic()
    bg.close()
    el = time.monotonic() - t0
    holder.rollback()
    holder.close()
    chk(el < 1.0, "D 다른 연결이 읽기를 쥐고 있으면 WAL 비우기를 건너뛰고 바로 닫음(종전엔 대기 30초를 다 채움)", "%.2fs" % el)

    print("\n=== C 시작 막기가 보는 폴더 = DB 가 있는 폴더 ===")
    from PyQt6.QtCore import QCoreApplication, QStandardPaths
    from viewer import pkg_guard as G, branding as B
    QCoreApplication.setApplicationName(B.APP_ID)
    QCoreApplication.setOrganizationName("LocalTools")          # main._set_app_names 와 같은 이름(만들지 않고 경로만)
    QStandardPaths.setTestModeEnabled(False)                    # 경로 이름만 읽는다(만들지·쓰지 않음) — 검사 묶음이 켠 시험 모드를 잠깐 끔
    app_data = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    QStandardPaths.setTestModeEnabled(True)
    local = os.path.join(os.environ.get("LOCALAPPDATA", ""), B.APP_ID)   # settings_store.local_data_dir 규칙
    dd = [os.path.normcase(os.path.abspath(x)) for x in G.data_dirs(B.APP_ID)]
    chk(os.path.normcase(os.path.abspath(app_data)) in dd and os.path.normcase(os.path.abspath(local)) in dd,
        "C pkg_guard 가 설정 폴더(index.db·study.db·dict.db·photo_index.db)·도구 자료 폴더(bizcard.db)를 본다", str((app_data, dd)))
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외")
print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
