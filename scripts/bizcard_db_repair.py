# -*- coding: utf-8 -*-
"""손상된 명함 DB 를 새 파일로 살려 만들기 — 원래 파일은 바꾸지 않는다. 명함 글은 찍지 않고 개수만.

  --make  : 명함 DB 옆에 `bizcard.rescued.db` 를 만든다.
            명함 = 지금 DB 에서 id 하나씩(찾기 색인의 id) — 못 읽으면 백업(`bizcard.db.dupe_bak`, 없으면 `kinds_bak`)의 같은 id,
            다른 표 = 지금 DB 에서 읽히면 그것, 못 읽으면 백업 것, 찾기 색인은 새로 만든다. 끝에 무결성 검사.
  --swap  : (명함찾기·PolyCardex·뷰어를 모두 닫고) `bizcard.db` 를 `bizcard.db.손상_날짜-시각` 으로 비켜 두고
            `bizcard.rescued.db` 를 `bizcard.db` 로. -wal·-shm 도 같은 이름으로 비켜 둔다.
  경로를 주면 그 DB 로(검사):  bizcard_db_repair.py --make <bizcard.db>
"""
import os
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

SKIP = ("sqlite_",)
FTS = "cards_fts"


def ro(path):
    return sqlite3.connect("file:%s?mode=ro" % str(path).replace("\\", "/"), uri=True)


def schema(con) -> dict:
    """{이름: (종류, sql, 표)} — 읽히는 만큼."""
    out = {}
    try:
        for t, name, tbl, sql in con.execute("SELECT type, name, tbl_name, sql FROM sqlite_master"):
            if sql and not name.startswith(SKIP):
                out[name] = (t, sql, tbl)
    except sqlite3.Error:
        pass
    return out


def cols(con, t) -> list:
    return [r[1] for r in con.execute('PRAGMA table_info("%s")' % t)]


def db_of(arg):
    if arg:
        return Path(arg)
    from viewer.bizcard.store import db_path
    return Path(db_path())


def make(db: Path) -> int:
    out = db.with_name("bizcard.rescued.db")
    bak = next((p for p in (db.with_name(db.name + ".dupe_bak"), db.with_name(db.name + ".kinds_bak")) if p.is_file()), None)
    if out.exists():
        out.unlink()
    cur = ro(db)
    old = ro(bak) if bak else None
    sc, sb = schema(cur), (schema(old) if old else {})
    new = sqlite3.connect(str(out))
    new.execute("PRAGMA journal_mode = WAL")
    # 표·가상 표 먼저(찾기 색인 그림자 표는 가상 표가 만든다), 그다음 색인·트리거
    names = dict(sb)
    names.update(sc)                                     # 지금 DB 의 꼴이 이긴다(열이 더 많을 수 있음)
    shadow = {n for n in names if n.startswith(FTS + "_")}
    for kind in ("table", "index", "trigger", "view"):
        for n, (t, sql, _tbl) in sorted(names.items()):
            if t != kind or n in shadow:
                continue
            try:
                new.execute(sql)
            except sqlite3.Error as e:
                print("  만들기 실패 %s %s: %s" % (t, n, e))
    new.commit()
    print("새 파일:", out)
    print("백업:", bak.name if bak else "(없음)")
    # 명함
    known = set()                                        # 지금 DB 에 있다고 알 수 있는 명함 id — 찾기 색인(지울 때 함께 지움),
    for sql in ("SELECT rowid FROM %s" % FTS, "SELECT DISTINCT card_id FROM contact_src"):   # 못 읽으면 칸 출처
        try:
            known = {r[0] for r in cur.execute(sql)}
            break
        except sqlite3.Error:
            continue
    bak_ids = set()
    if old is not None:
        try:
            bak_ids = {r[0] for r in old.execute("SELECT id FROM cards")}
        except sqlite3.Error:
            pass
    top = max(known | bak_ids | {0})
    ids = sorted(known | set(range(1, top + 200)))       # 색인이 깨져도 id 범위를 한 장씩
    cc = cols(new, "cards")
    cur_c = [c for c in cols(cur, "cards") if c in cc]
    bak_c = [c for c in cols(old, "cards") if c in cc] if old else []
    got = {"지금": 0, "백업": 0, "잃음": 0}
    for i in ids:
        row, src = None, ""
        failed = False
        try:
            row = cur.execute('SELECT %s FROM cards WHERE id=?' % ", ".join('"%s"' % c for c in cur_c), (i,)).fetchone()
            src, use = "지금", cur_c
        except sqlite3.Error:
            row, failed = None, True
        if row is None and not failed:
            continue                                     # 지금 DB 에 없는 id(합치기 등으로 지운 것) — 백업에서 되살리지 않음
        if row is None and old is not None:
            try:
                row = old.execute('SELECT %s FROM cards WHERE id=?' % ", ".join('"%s"' % c for c in bak_c), (i,)).fetchone()
                src, use = "백업", bak_c
            except sqlite3.Error:
                row = None
        if row is None:
            got["잃음"] += 1
            continue
        try:
            new.execute('INSERT INTO cards(%s) VALUES(%s)' % (", ".join('"%s"' % c for c in use), ",".join("?" * len(use))), list(row))
            got[src] += 1
        except sqlite3.Error as e:
            got["잃음"] += 1
            print("  명함 넣기 실패(id 만): %d %s" % (i, type(e).__name__))
    print("명함: 지금 DB 에서 %(지금)d장 · 백업에서 %(백업)d장 · 잃음 %(잃음)d장" % got)
    # 다른 표
    for n, (t, _sql, _tbl) in sorted(names.items()):
        if t != "table" or n == "cards" or n == FTS or n in shadow:
            continue
        tc = cols(new, n)
        done = False
        for label, con in (("지금", cur), ("백업", old)):
            if con is None:
                continue
            try:
                have = [c for c in cols(con, n) if c in tc]
                if not have:
                    continue
                rows = con.execute('SELECT %s FROM "%s"' % (", ".join('"%s"' % c for c in have), n)).fetchall()
            except sqlite3.Error:
                continue
            new.executemany('INSERT OR IGNORE INTO "%s"(%s) VALUES(%s)' % (n, ", ".join('"%s"' % c for c in have), ",".join("?" * len(have))), rows)
            print("표 %-18s %s에서 %d줄" % (n, label, len(rows)))
            done = True
            break
        if not done:
            print("표 %-18s 못 옮김(빈 표)" % n)
    new.commit()
    # 찾기 색인 새로
    if FTS in names:
        from viewer.bizcard.store import BizcardStore
        new.row_factory = sqlite3.Row
        n = 0
        for r in new.execute("SELECT * FROM cards").fetchall():
            d = BizcardStore._row(r)
            new.execute("INSERT INTO %s(rowid, body) VALUES(?,?)" % FTS, (d["id"], BizcardStore._body(d)))
            n += 1
        new.commit()
        print("찾기 색인 새로 %d줄" % n)
    qc = [r[0] for r in new.execute("PRAGMA integrity_check")]
    print("새 파일 무결성:", "ok" if qc == ["ok"] else qc[:5])
    new.close()
    cur.close()
    if old is not None:
        old.close()
    return 0 if qc == ["ok"] else 1


def swap(db: Path) -> int:
    new = db.with_name("bizcard.rescued.db")
    if not new.is_file():
        print("먼저 --make 를 돌리세요.")
        return 1
    c = ro(new)
    ok = [r[0] for r in c.execute("PRAGMA integrity_check")] == ["ok"]
    c.close()
    if not ok:
        print("새 파일이 성하지 않아 바꾸지 않습니다.")
        return 1
    tag = time.strftime("%y%m%d-%H%M%S")
    moved = []
    try:
        for suf in ("", "-wal", "-shm"):
            p = Path(str(db) + suf)
            if p.exists():
                to = Path(str(db) + ".손상_" + tag + suf)
                os.replace(p, to)
                moved.append((p, to))
        os.replace(new, db)
        for suf in ("-wal", "-shm"):
            p = Path(str(new) + suf)
            if p.exists():
                p.unlink()
    except OSError as e:
        print("바꾸지 못했습니다(%s) — 명함찾기·PolyCardex·뷰어가 열려 있는지 확인하세요. 되돌리는 중…" % type(e).__name__)
        for a, b in reversed(moved):
            if b.exists() and not a.exists():
                os.replace(b, a)
        return 1
    print("바꿈: 옛 파일은 %s" % (Path(str(db) + ".손상_" + tag)).name)
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    db = db_of(args[0] if args else "")
    if "--swap" in sys.argv:
        sys.exit(swap(db))
    sys.exit(make(db))
