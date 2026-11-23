# -*- coding: utf-8 -*-
"""명함 변경 기록·되살리기 (명함 SOT §5.30, 261120-64) — Qt 없음.

명함 행이 고쳐지거나 지워지면 SQLite 트리거가 **바뀌기 전 한 장 통째**(JSON)를 `card_history` 에 쓴다 — 고치기·합치기·싱크·
지우기 어느 길이든 한 곳. 트리거·출처 표는 연결마다 TEMP 로 만든다(연결마다 출처가 섞이지 않게, 스키마를 열 때마다 쓰지 않게).
"""
from __future__ import annotations

import contextlib
import json
import time
import uuid

KEEP_DAYS = 180                                   # 보존(사용자 결정 261121)
PRUNE_KEY = "history_pruned"
SOURCES = ("edit", "sync", "merge", "kinds", "split", "restore")   # split = 명단 나누기(§5.32, 261122-1)
_IGNORE = ("updated", "edited", "created", "top1")   # 이것만 바뀐 것은 남기지 않는다
NOTE = "note"                                     # 지운 할 일 기록(§5.30 '할 일 기록', 261120-69) — card_id 칸 = 기록 id


def _cols(con) -> list:
    return [r[1] for r in con.execute("PRAGMA main.table_info(cards)")]


def init(store) -> None:
    """기록 표(영구)와 이 연결의 TEMP 트리거·출처 표. BizcardStore 를 열 때 부른다."""
    con = store.con
    con.execute("CREATE TABLE IF NOT EXISTS card_history(id INTEGER PRIMARY KEY, card_id INTEGER, at REAL, kind TEXT, "
                "src TEXT, row TEXT)")
    con.execute("CREATE INDEX IF NOT EXISTS card_history_at ON card_history(at)")
    con.execute("CREATE INDEX IF NOT EXISTS card_history_card ON card_history(card_id, at)")
    con.execute("CREATE TEMP TABLE IF NOT EXISTS hist_ctx(k INTEGER PRIMARY KEY, src TEXT)")
    con.execute("INSERT OR IGNORE INTO temp.hist_ctx(k, src) VALUES(1, 'edit')")
    cols = _cols(con)
    obj = "json_object(%s)" % ", ".join("'%s', OLD.\"%s\"" % (c, c) for c in cols)
    changed = " OR ".join('OLD."%s" IS NOT NEW."%s"' % (c, c) for c in cols if c not in _IGNORE) or "0"
    src = "COALESCE((SELECT src FROM temp.hist_ctx WHERE k = 1), 'edit')"
    con.execute("DROP TRIGGER IF EXISTS temp.card_hist_upd")
    con.execute("DROP TRIGGER IF EXISTS temp.card_hist_del")
    con.execute("CREATE TEMP TRIGGER card_hist_upd AFTER UPDATE ON main.cards WHEN %s BEGIN "
                "INSERT INTO card_history(card_id, at, kind, src, row) VALUES(OLD.id, ((julianday('now') - 2440587.5) * 86400.0), 'edit', %s, %s); END"
                % (changed, src, obj))
    con.execute("CREATE TEMP TRIGGER card_hist_del AFTER DELETE ON main.cards BEGIN "
                "INSERT INTO card_history(card_id, at, kind, src, row) VALUES(OLD.id, ((julianday('now') - 2440587.5) * 86400.0), 'delete', %s, %s); END"
                % (src, obj))
    con.commit()


def note_deleted(store, row: dict) -> None:
    """할 일 기록 [삭제] 직전 — 그 기록 행(+ `_group` 탭 이름)을 변경 기록에 남긴다(되살릴 수 있게, 261120-69). 커밋은 부른 쪽."""
    src = store.con.execute("SELECT src FROM temp.hist_ctx WHERE k = 1").fetchone()
    store.con.execute("INSERT INTO card_history(card_id, at, kind, src, row) VALUES(?,?,?,?,?)",
                      (int(row["id"]), time.time(), NOTE, (src[0] if src else "edit") or "edit", json.dumps(row, ensure_ascii=False)))


@contextlib.contextmanager
def source(store, src: str):
    """이 블록에서 바뀐 명함은 출처 src 로 적는다(§5.30 '출처') — 끝나면 'edit'."""
    store.con.execute("UPDATE temp.hist_ctx SET src=? WHERE k=1", (src,))
    try:
        yield
    finally:
        store.con.execute("UPDATE temp.hist_ctx SET src='edit' WHERE k=1")


def entries(store, since: float, until: float, kinds=None, srcs=None) -> list:
    """기간 [since, until](유닉스 초)에 바뀐 명함마다 한 줄 — {card_id, kind('delete'|'edit' — 지금 없으면 delete), at, srcs,
    row(되살릴 값 = 기간 안 첫 기록 = 그 기간이 시작되기 전 모습), name, later(그 뒤 또 바뀜), now(지금 행 또는 None)}."""
    con = store.con
    rows = con.execute("SELECT id, card_id, at, kind, src, row FROM card_history WHERE at BETWEEN ? AND ? ORDER BY id",
                       (since, until)).fetchall()       # 기록 시각 = 유닉스 초(트리거가 julianday 를 초로 바꿔 쓴다)
    by = {}
    notes = []
    for r in rows:
        if r[3] == NOTE:                                  # 지운 할 일 기록 — 한 줄씩(명함과 따로)
            notes.append({"card_id": None, "note_id": r[1], "note": True, "row": json.loads(r[5] or "{}"), "srcs": {r[4] or "edit"},
                          "at": r[2], "kind": "delete", "later": False, "now": None,
                          "name": str(json.loads(r[5] or "{}").get("_group") or "")})
            continue
        e = by.setdefault(r[1], {"card_id": r[1], "row": json.loads(r[5] or "{}"), "srcs": set(), "at": 0.0})
        e["srcs"].add(r[4] or "edit")
        e["at"] = r[2]
    out = []
    for e in notes:
        if (kinds and "delete" not in kinds) or (srcs and not (e["srcs"] & set(srcs))):
            continue
        out.append(e)
    for cid, e in by.items():
        cur = con.execute("SELECT * FROM cards WHERE id=?", (cid,)).fetchone()
        e["now"] = store._row(cur) if cur is not None else None
        e["kind"] = "edit" if cur is not None else "delete"
        e["name"] = (e["row"].get("name") or "")
        e["later"] = con.execute("SELECT 1 FROM card_history WHERE card_id=? AND kind <> 'note' AND at > ? LIMIT 1", (cid, until)).fetchone() is not None
        if kinds and e["kind"] not in kinds:
            continue
        if srcs and not (e["srcs"] & set(srcs)):
            continue
        out.append(e)
    out.sort(key=lambda e: (-e["at"], e["name"]))
    return out


def restore(store, items) -> int:
    """고른 줄을 되살린다(§5.30 '되살린 뒤') — 지운 명함은 같은 id 로(비었으면) 다시, 고친 명함은 옛 칸 값으로. 고친 시각은 지금
    (다음 구글 싱크 미리보기에 보인다). 되살리기도 기록에 남는다(출처 restore). 배경에서 부른다. 반환 = 되살린 수."""
    con = store.con
    cols = _cols(con)
    now = time.time()
    n = 0
    with source(store, "restore"):
        for e in items:
            if e.get("note"):                             # 지운 할 일 기록 — 그 탭이 남아 있을 때만(§5.30 '할 일 기록')
                n += _restore_note(store, e["row"])
                continue
            row = dict(e["row"])
            cid = e["card_id"]
            row["updated"] = now
            vals = {c: row[c] for c in cols if c != "id" and c in row}   # 기록에 있는 칸만 — 뒤 판에서 는 칸은 그대로(261120-68)
            if con.execute("SELECT 1 FROM cards WHERE id=?", (cid,)).fetchone():
                other = con.execute("SELECT 1 FROM cards WHERE front=? AND id<>?", (vals.get("front"), cid)).fetchone()
                if other:
                    vals["front"] = "contact:" + uuid.uuid4().hex
                con.execute("UPDATE cards SET %s WHERE id=?" % ", ".join('"%s"=?' % c for c in vals), list(vals.values()) + [cid])
                con.execute("DELETE FROM cards_fts WHERE rowid=?", (cid,))
                new_id = cid
            else:
                if con.execute("SELECT 1 FROM cards WHERE front=?", (vals.get("front"),)).fetchone():
                    vals["front"] = "contact:" + uuid.uuid4().hex
                keys = ["id"] + list(vals)
                cur = con.execute("INSERT INTO cards(%s) VALUES(%s)" % (", ".join('"%s"' % k for k in keys), ", ".join("?" * len(keys))),
                                  [cid] + list(vals.values()))
                new_id = cur.lastrowid
            fresh = store._row(con.execute("SELECT * FROM cards WHERE id=?", (new_id,)).fetchone())
            con.execute("INSERT INTO cards_fts(rowid, body) VALUES(?,?)", (new_id, store._body(fresh)))
            n += 1
        con.commit()
    return n


def _restore_note(store, row: dict) -> int:
    con = store.con
    gid = row.get("group_id")
    if gid is None or not con.execute("SELECT 1 FROM fav_groups WHERE id=?", (gid,)).fetchone():
        return 0                                          # 탭이 지워졌다 — 되살리지 않는다(못 한 수로)
    cols = [r[1] for r in con.execute("PRAGMA main.table_info(todo_notes)")]
    vals = {c: row[c] for c in cols if c in row and c != "id"}
    nid = row.get("id")
    if nid is not None and not con.execute("SELECT 1 FROM todo_notes WHERE id=?", (nid,)).fetchone():
        vals = dict(id=nid, **vals)
    con.execute("INSERT INTO todo_notes(%s) VALUES(%s)" % (", ".join('"%s"' % k for k in vals), ", ".join("?" * len(vals))),
                list(vals.values()))
    from viewer.bizcard import people as _P
    _P._sync_memo(store, gid)
    return 1


def prune(store, days: int = KEEP_DAYS) -> int:
    """보존 기간이 지난 기록을 지운다. 반환 = 지운 수."""
    cur = store.con.execute("DELETE FROM card_history WHERE at < ?", (time.time() - days * 86400,))
    store.con.commit()
    return cur.rowcount or 0


def maybe_prune(store) -> int:
    """하루 한 번만(명함찾기를 열 때)."""
    last = store.meta_get(PRUNE_KEY, 0) or 0
    if time.time() - float(last) < 86400:
        return 0
    n = prune(store)
    store.meta_set(PRUNE_KEY, time.time())
    return n
