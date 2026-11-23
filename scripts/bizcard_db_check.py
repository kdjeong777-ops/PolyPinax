# -*- coding: utf-8 -*-
"""명함 DB 손상 진단 — 읽기 전용(파일을 바꾸지 않는다). 명함 글은 찍지 않고 표·색인 이름·쪽 번호·개수만.

사용:  .venv\\Scripts\\python.exe scripts\\bizcard_db_check.py [bizcard.db 경로]
경로를 안 주면 앱이 쓰는 명함 DB(`store.db_path()`). 명함찾기·PolyCardex 는 닫고 돌린다.
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


def main():
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        from viewer.bizcard.store import db_path
        path = str(db_path())
    print("DB:", path, "· 크기 %d 바이트" % os.path.getsize(path))
    con = sqlite3.connect("file:%s?mode=ro" % path.replace("\\", "/"), uri=True)
    for name, sql in (("quick_check", "PRAGMA quick_check(30)"), ("integrity_check", "PRAGMA integrity_check(30)")):
        try:
            rows = [r[0] for r in con.execute(sql)]
            print("[%s]" % name, "ok" if rows == ["ok"] else "")
            for r in rows if rows != ["ok"] else []:
                print("   ", r)
        except sqlite3.Error as e:
            print("[%s] 실패: %s: %s" % (name, type(e).__name__, e))
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    for t in tables:
        try:
            n = con.execute('SELECT count(*) FROM "%s"' % t).fetchone()[0]
            print("표 %-24s %d 줄" % (t, n))
        except sqlite3.Error as e:
            print("표 %-24s 읽기 실패: %s: %s" % (t, type(e).__name__, e))
    for label, sql in (("명함 전부(차례 없이)", "SELECT * FROM cards"),
                       ("명함 전부(이름 차례 — 명단 관리 길)", "SELECT * FROM cards ORDER BY name, id"),
                       ("찾기 색인(cards_fts)", "SELECT rowid FROM cards_fts")):
        try:
            n = sum(1 for _ in con.execute(sql))
            print("%s: %d 줄 읽힘" % (label, n))
        except sqlite3.Error as e:
            print("%s: 실패 — %s: %s" % (label, type(e).__name__, e))
    bad, last = [], 0
    try:
        ids = [r[0] for r in con.execute("SELECT id FROM cards ORDER BY id")]
    except sqlite3.Error as e:
        ids = []
        print("명함 id 목록 실패:", type(e).__name__, e)
    for i in ids:
        try:
            con.execute("SELECT * FROM cards WHERE id=?", (i,)).fetchone()
        except sqlite3.Error:
            bad.append(i)
    print("한 장씩 읽기: %d 장 중 못 읽은 것 %d 장" % (len(ids), len(bad)))
    con.close()


if __name__ == "__main__":
    main()
