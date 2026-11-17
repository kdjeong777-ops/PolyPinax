"""명함 DB `bizcard.db` (명함 SOT §5.7·§5.10, P2).

- 위치: 이 PC 의 도구 자료 폴더 `settings_store.local_data_dir()`(D4 — 클라우드 동기 폴더가 아니다).
- `cards`: 한 사람 한 행(정리본 앞면 경로가 열쇠). `cards_fts`: 이름·회사·직함·메모·영문 칸 찾기(FTS5).
- `recog`: 원천 열쇠(앞면 원천 경로) → 지문·인식 결과·확인 표 고침. 다시 열면 이어서 한다.
- ★ 명함 글은 로그·예외 메시지에 싣지 않는다(명함 SOT §2.1).
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

from viewer import dbutil

DB_NAME = "bizcard.db"
SCHEMA_VER = 1
_TEXT_COLS = ("name", "company", "title", "address", "memo", "scanned")


def db_path() -> Path:
    from viewer.settings_store import local_data_dir
    return local_data_dir() / DB_NAME


def source_sig(paths) -> str:
    """원천 지문 — 경로마다 크기·수정 시각. 원천이 바뀌면 다시 읽는다."""
    out = []
    for p in paths:
        if not p:
            continue
        try:
            st = os.stat(p)
            out.append("%s|%d|%d" % (os.path.normcase(str(p)), st.st_size, st.st_mtime_ns))
        except OSError:
            out.append("%s|-" % os.path.normcase(str(p)))
    return ";".join(out)


def _key(p) -> str:
    return os.path.normcase(os.path.abspath(str(p)))


class BizcardStore:
    """한 연결. 워커는 자기 것을 열고(BUSY_MS_BG), 메인은 읽기만 짧게(BUSY_MS_UI)."""

    def __init__(self, path=None, ui: bool = False):
        self.path = Path(path) if path else db_path()
        self.con = dbutil.connect(self.path, dbutil.BUSY_MS_UI if ui else dbutil.BUSY_MS_BG)
        self._init()

    def close(self):
        try:
            self.con.close()
        except Exception:
            pass

    def _init(self):
        c = self.con
        c.executescript("""
        CREATE TABLE IF NOT EXISTS cards(
            id INTEGER PRIMARY KEY, front TEXT UNIQUE NOT NULL, back TEXT, src_key TEXT, src_pdf TEXT,
            name TEXT, company TEXT, title TEXT, phones TEXT, emails TEXT, urls TEXT, address TEXT,
            en TEXT, memo TEXT, tags TEXT, scanned TEXT, top1 INTEGER, created REAL, updated REAL);
        CREATE INDEX IF NOT EXISTS cards_src ON cards(src_key);
        CREATE VIRTUAL TABLE IF NOT EXISTS cards_fts USING fts5(body, tokenize='unicode61');
        CREATE TABLE IF NOT EXISTS recog(src_key TEXT PRIMARY KEY, sig TEXT, result TEXT, edit TEXT, updated REAL);
        CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
        """)
        c.execute("INSERT OR IGNORE INTO meta(k, v) VALUES('schema', ?)", (str(SCHEMA_VER),))
        c.commit()

    # ── 인식 캐시 ──
    def recog_get(self, src, sig: str) -> Optional[dict]:
        r = self.con.execute("SELECT sig, result, edit FROM recog WHERE src_key=?", (_key(src),)).fetchone()
        if r is None or r["sig"] != sig:
            return None
        return {"result": json.loads(r["result"] or "{}"), "edit": json.loads(r["edit"] or "{}")}

    def recog_put(self, src, sig: str, result: dict):
        self.con.execute("INSERT INTO recog(src_key, sig, result, edit, updated) VALUES(?,?,?,?,?) "
                         "ON CONFLICT(src_key) DO UPDATE SET sig=excluded.sig, result=excluded.result, "
                         "edit=CASE WHEN recog.sig=excluded.sig THEN recog.edit ELSE NULL END, updated=excluded.updated",
                         (_key(src), sig, json.dumps(result, ensure_ascii=False), None, time.time()))
        self.con.commit()

    def edit_put(self, src, edit: dict):
        self.con.execute("UPDATE recog SET edit=?, updated=? WHERE src_key=?",
                         (json.dumps(edit, ensure_ascii=False), time.time(), _key(src)))
        self.con.commit()

    # ── 사람 ──
    @staticmethod
    def _body(d: dict) -> str:
        en = d.get("en") or {}
        parts = [d.get("name"), d.get("company"), d.get("title"), d.get("memo"), d.get("address"),
                 " ".join(d.get("emails") or []), " ".join(n for _, n in (d.get("phones") or [])),
                 " ".join(str(v) for v in en.values()), " ".join(d.get("tags") or [])]
        return " ".join(str(x) for x in parts if x)

    def card_by_src(self, src) -> Optional[dict]:
        r = self.con.execute("SELECT * FROM cards WHERE src_key=?", (_key(src),)).fetchone()
        return self._row(r)

    def card_by_front(self, front) -> Optional[dict]:
        r = self.con.execute("SELECT * FROM cards WHERE front=?", (_key(front),)).fetchone()
        return self._row(r)

    @staticmethod
    def _row(r) -> Optional[dict]:
        if r is None:
            return None
        d = dict(r)
        for k in ("phones", "emails", "urls", "tags"):
            d[k] = json.loads(d.get(k) or "[]")
        d["en"] = json.loads(d.get("en") or "{}")
        d["phones"] = [tuple(x) for x in d["phones"]]
        return d

    def upsert(self, d: dict) -> int:
        """`front`(정리본 앞면) 열쇠로 넣거나 고친다. 반환 = id."""
        now = time.time()
        vals = {k: d.get(k) or "" for k in _TEXT_COLS}
        js = {k: json.dumps(list(d.get(k) or []), ensure_ascii=False) for k in ("phones", "emails", "urls", "tags")}
        en = json.dumps(d.get("en") or {}, ensure_ascii=False)
        front = _key(d["front"])
        old = self.con.execute("SELECT id FROM cards WHERE front=?", (front,)).fetchone()
        args = (d.get("back") and _key(d["back"]) or "", d.get("src_key") and _key(d["src_key"]) or "",
                d.get("src_pdf") or "", vals["name"], vals["company"], vals["title"], js["phones"], js["emails"],
                js["urls"], vals["address"], en, vals["memo"], js["tags"], vals["scanned"],
                None if d.get("top1") is None else int(bool(d.get("top1"))))
        if old:
            cid = old["id"]
            self.con.execute("UPDATE cards SET back=?, src_key=?, src_pdf=?, name=?, company=?, title=?, phones=?, "
                             "emails=?, urls=?, address=?, en=?, memo=?, tags=?, scanned=?, top1=?, updated=? WHERE id=?",
                             args + (now, cid))
            self.con.execute("DELETE FROM cards_fts WHERE rowid=?", (cid,))
        else:
            cur = self.con.execute("INSERT INTO cards(front, back, src_key, src_pdf, name, company, title, phones, "
                                   "emails, urls, address, en, memo, tags, scanned, top1, created, updated) "
                                   "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (front,) + args + (now, now))
            cid = cur.lastrowid
        self.con.execute("INSERT INTO cards_fts(rowid, body) VALUES(?,?)", (cid, self._body(d)))
        self.con.commit()
        return cid

    def count(self) -> int:
        return self.con.execute("SELECT COUNT(*) FROM cards").fetchone()[0]

    def top1_ratio(self) -> tuple:
        """(인식 1위가 확정 이름이었던 수, 기록된 수) — 이름 정확도 판정용(명함 SOT §6 P1), 값은 남기지 않는다."""
        r = self.con.execute("SELECT SUM(top1), COUNT(top1) FROM cards WHERE top1 IS NOT NULL").fetchone()
        return int(r[0] or 0), int(r[1] or 0)

    def search(self, text: str = "", since: str = "", until: str = "", limit: int = 500) -> list:
        """이름·회사·메모 등 한 칸 찾기 + 스캔일 범위(YYYY-MM-DD). 명함찾기 창(P4)이 쓴다."""
        q = "SELECT cards.* FROM cards"
        args = []
        where = []
        toks = [t for t in (text or "").replace('"', " ").split() if t]
        if toks:
            q += " JOIN cards_fts ON cards_fts.rowid = cards.id"
            where.append("cards_fts MATCH ?")
            args.append(" ".join('"%s"*' % t for t in toks))
        if since:
            where.append("scanned >= ?"); args.append(since)
        if until:
            where.append("scanned <= ?"); args.append(until)
        if where:
            q += " WHERE " + " AND ".join(where)
        q += " ORDER BY scanned DESC, id DESC LIMIT %d" % int(limit)
        return [self._row(r) for r in self.con.execute(q, args).fetchall()]
