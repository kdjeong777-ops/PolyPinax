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
import weakref
from pathlib import Path
from typing import Optional

from viewer import dbutil

DB_NAME = "bizcard.db"
SCHEMA_VER = 1
_TEXT_COLS = ("name", "company", "dept", "title", "address", "memo", "scanned")


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


def sig_tail(sig: str) -> str:
    """지문에서 폴더를 뗀 꼴 — 폴더를 통째 옮겨도(§5.12) 같은 파일이면 같은 지문(이름·크기·수정 시각)."""
    out = []
    for part in (sig or "").split(";"):
        bits = part.split("|")
        bits[0] = os.path.basename(bits[0])
        out.append("|".join(bits))
    return ";".join(out)


def _key(p) -> str:
    return os.path.normcase(os.path.abspath(str(p)))


_OPEN = weakref.WeakSet()                         # 열린 연결 — 앱이 `os._exit` 로 끝나기 전에 `close_all`(main.py)


def close_all() -> int:
    """열린 명함 DB 연결을 모두 닫는다(WAL 정리 포함) — 메인 스레드에서, 앱이 끝나기 직전. 반환 = 닫은 수."""
    n = 0
    for st in list(_OPEN):
        st.close()
        n += 1
    return n


class BizcardStore:
    """한 연결. 워커는 자기 것을 열고(BUSY_MS_BG), 메인은 읽기만 짧게(BUSY_MS_UI)."""

    def __init__(self, path=None, ui: bool = False):
        self.path = Path(path) if path else db_path()
        self.con = dbutil.connect(self.path, dbutil.BUSY_MS_UI if ui else dbutil.BUSY_MS_BG)
        _OPEN.add(self)
        self._init()

    def close(self):
        """닫기 전에 WAL 을 본 파일에 옮기고 비운다(`wal_checkpoint(TRUNCATE)`) — 묵은 -wal 이 남지 않게(261122-1 덧붙임,
        명함 DB 손상 261123: 보조 파일이 두 벌로 갈라졌을 때 남은 묵은 WAL 이 다음 실행에 다시 얹혔다). 다른 연결이 쓰는 중이면 건너뜀."""
        _OPEN.discard(self)
        try:
            self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass
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
        CREATE TABLE IF NOT EXISTS layouts(key TEXT, field TEXT, x0 REAL, y0 REAL, x1 REAL, y1 REAL, n INTEGER,
            manual INTEGER, updated REAL, PRIMARY KEY(key, field));
        CREATE TABLE IF NOT EXISTS domain_org(domain TEXT PRIMARY KEY, org TEXT, n INTEGER, updated REAL);
        CREATE TABLE IF NOT EXISTS samples(src_key TEXT PRIMARY KEY, data TEXT, updated REAL);
        CREATE TABLE IF NOT EXISTS corrections(field TEXT, wrong TEXT, right TEXT, n INTEGER, updated REAL,
            PRIMARY KEY(field, wrong));
        """)
        cols = {r[1] for r in c.execute("PRAGMA table_info(cards)")}
        if "dept" not in cols:                       # 261117-11: 부서 칸(옛 DB 는 열만 더한다)
            c.execute("ALTER TABLE cards ADD COLUMN dept TEXT")
        c.execute("INSERT OR IGNORE INTO meta(k, v) VALUES('schema', ?)", (str(SCHEMA_VER),))
        c.commit()
        from viewer.bizcard import history                # 변경 기록 트리거(연결마다 TEMP — 명함 SOT §5.30, 261120-64)
        history.init(self)

    # ── 인식 캐시 ──
    def recog_get(self, src, sig: str) -> Optional[dict]:
        r = self.con.execute("SELECT sig, result, edit, updated FROM recog WHERE src_key=?", (_key(src),)).fetchone()
        if r is None or sig_tail(r["sig"]) != sig_tail(sig):
            return None
        return {"result": json.loads(r["result"] or "{}"), "edit": json.loads(r["edit"] or "{}"), "updated": r["updated"] or 0}

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
        parts = [d.get("name"), d.get("company"), d.get("dept"), d.get("title"), d.get("memo"), d.get("address"),
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
        """`front`(정리본 앞면) 열쇠로 넣거나 고친다. 반환 = id. 전화는 번호 종류 바로잡기를 거친다(명함 SOT §5.11, 261120-55)."""
        from viewer.bizcard import phone as PH
        ph, old = PH.fix_kinds(d.get("phones") or [])
        d = dict(d, phones=ph, memo=PH.memo_with_old(d.get("memo") or "", old) if old else d.get("memo"))
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
                             "emails=?, urls=?, address=?, en=?, memo=?, tags=?, scanned=?, top1=?, updated=?, dept=? WHERE id=?",
                             args + (now, vals["dept"], cid))
            self.con.execute("DELETE FROM cards_fts WHERE rowid=?", (cid,))
        else:
            cur = self.con.execute("INSERT INTO cards(front, back, src_key, src_pdf, name, company, title, phones, "
                                   "emails, urls, address, en, memo, tags, scanned, top1, created, updated, dept) "
                                   "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (front,) + args + (now, now, vals["dept"]))
            cid = cur.lastrowid
        self.con.execute("INSERT INTO cards_fts(rowid, body) VALUES(?,?)", (cid, self._body(d)))
        self.con.commit()
        return cid

    # ── 배운 것(§5.11) — 모두 이 PC 의 bizcard.db 에만 ──
    def meta_get(self, k: str, default=None):
        r = self.con.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return json.loads(r["v"]) if r else default

    def meta_set(self, k: str, v):
        self.con.execute("INSERT INTO meta(k, v) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                         (k, json.dumps(v, ensure_ascii=False)))
        self.con.commit()

    def layout_put(self, key: str, field: str, box, manual: bool = False):
        """양식 위치 — 사용자가 그린 상자(manual)는 그대로 덮고, 자동은 평균에 섞는다."""
        if not key or not box:
            return
        x0, y0, x1, y1 = [float(v) for v in box]
        r = self.con.execute("SELECT * FROM layouts WHERE key=? AND field=?", (key, field)).fetchone()
        if r is None or manual:
            n = 1 if r is None else int(r["n"]) + 1
            self.con.execute("INSERT INTO layouts(key, field, x0, y0, x1, y1, n, manual, updated) VALUES(?,?,?,?,?,?,?,?,?) "
                             "ON CONFLICT(key, field) DO UPDATE SET x0=excluded.x0, y0=excluded.y0, x1=excluded.x1, "
                             "y1=excluded.y1, n=excluded.n, manual=MAX(layouts.manual, excluded.manual), updated=excluded.updated",
                             (key, field, x0, y0, x1, y1, n, int(manual), time.time()))
        elif not r["manual"]:
            n = int(r["n"])
            m = lambda a, b: (a * n + b) / (n + 1)
            self.con.execute("UPDATE layouts SET x0=?, y0=?, x1=?, y1=?, n=?, updated=? WHERE key=? AND field=?",
                             (m(r["x0"], x0), m(r["y0"], y0), m(r["x1"], x1), m(r["y1"], y1), n + 1, time.time(), key, field))
        self.con.commit()

    def layouts(self, min_auto: int = 2) -> dict:
        """{열쇠: {칸: (x0, y0, x1, y1)}} — 자동으로 배운 것은 `min_auto` 번 넘게 맞았을 때만 쓴다."""
        out = {}
        for r in self.con.execute("SELECT * FROM layouts"):
            if r["manual"] or int(r["n"]) >= min_auto:
                out.setdefault(r["key"], {})[r["field"]] = (r["x0"], r["y0"], r["x1"], r["y1"])
        return out

    def domain_put(self, domain: str, org: str):
        if not domain or not org:
            return
        self.con.execute("INSERT INTO domain_org(domain, org, n, updated) VALUES(?,?,1,?) ON CONFLICT(domain) DO UPDATE "
                         "SET n=CASE WHEN domain_org.org=excluded.org THEN domain_org.n+1 ELSE 1 END, org=excluded.org, "
                         "updated=excluded.updated", (domain, org, time.time()))
        self.con.commit()

    def domain_map(self) -> dict:
        return {r["domain"]: r["org"] for r in self.con.execute("SELECT domain, org FROM domain_org")}

    def sample_put(self, src, data: dict):
        """이름 점수 학습 표본 — 후보 특징과 '확정한 것인가' 만(이름 글자는 남기지 않는다)."""
        self.con.execute("INSERT INTO samples(src_key, data, updated) VALUES(?,?,?) ON CONFLICT(src_key) DO UPDATE "
                         "SET data=excluded.data, updated=excluded.updated",
                         (_key(src), json.dumps(data, ensure_ascii=False), time.time()))
        self.con.commit()

    def correction_put(self, field: str, wrong: str, right: str):
        """교정(§5.15) — 위치 지정에서 읽은 글(wrong)을 사람이 고친 글(right). 같은 오인식은 다음부터 고친 글로."""
        if not field or not wrong or not right or wrong == right:
            return
        self.con.execute("INSERT INTO corrections(field, wrong, right, n, updated) VALUES(?,?,?,1,?) "
                         "ON CONFLICT(field, wrong) DO UPDATE SET n=CASE WHEN corrections.right=excluded.right "
                         "THEN corrections.n+1 ELSE 1 END, right=excluded.right, updated=excluded.updated",
                         (field, wrong, right, time.time()))
        self.con.commit()

    def corrections(self) -> dict:
        out = {}
        for r in self.con.execute("SELECT field, wrong, right FROM corrections"):
            out.setdefault(r["field"], {})[r["wrong"]] = r["right"]
        return out

    def samples(self) -> list:
        return [json.loads(r["data"]) for r in self.con.execute("SELECT data FROM samples")]

    def delete_src(self, src) -> list:
        """명함 하나 지우기(261117-19) — 그 원천의 인식 기록·학습 표본·사람 행. 반환 = 지운 사람 행의 정리본 [앞, 뒤]."""
        k = _key(src)
        outs = []
        for r in self.con.execute("SELECT id, front, back FROM cards WHERE src_key=?", (k,)).fetchall():
            outs += [x for x in (r["front"], r["back"]) if x]
            self.con.execute("DELETE FROM cards_fts WHERE rowid=?", (r["id"],))
            self._forget_fav(r["id"])
        self.con.execute("DELETE FROM cards WHERE src_key=?", (k,))
        self.con.execute("DELETE FROM recog WHERE src_key=?", (k,))
        self.con.execute("DELETE FROM samples WHERE src_key=?", (k,))
        self.con.commit()
        return outs

    def _forget_fav(self, card_id: int):
        """즐겨찾기 칸도 지운다(§5.24) — id 는 다시 쓰일 수 있어 남겨 두면 새 명함이 옛 칸을 물려받는다. 표가 없으면(옛 DB) 그만."""
        for t in ("fav_members", "contact_src", "recent"):   # 즐겨찾기 칸·주소록 출처·최근(§5.24)
            try:
                self.con.execute("DELETE FROM %s WHERE card_id=?" % t, (card_id,))
            except sqlite3.OperationalError:
                pass

    def delete_card(self, card_id: int):
        """원천이 없는 명함 행 하나 지우기(§5.24) — 원천이 있으면 `delete_src`."""
        self.con.execute("DELETE FROM cards_fts WHERE rowid=?", (card_id,))
        self.con.execute("DELETE FROM cards WHERE id=?", (card_id,))
        self._forget_fav(card_id)
        self.con.commit()

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
