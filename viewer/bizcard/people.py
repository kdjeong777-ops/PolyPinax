"""명함찾기 창의 Qt 없는 부분 (명함 SOT §5.9 P4) — 찾기, 인물 사진, 이름 바꾼 뒤 명함 DB 따라가기.

★ 명함 글·경로는 로그·예외 메시지에 싣지 않는다(§2.1).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from pathlib import Path

from viewer.bizcard import recognize as R

PEOPLE_DIR = "인물"            # 인물 사진 폴더 — 정리 폴더 옆(D16 '폴더 통째' 와 같은 자리)
_COLS = ("name", "company", "dept", "title", "memo", "address", "emails", "phones", "urls", "en")


def _nk(p) -> str:
    return os.path.normcase(os.path.abspath(str(p))) if p else ""


# ── 찾기 ──
def find(store, text: str = "", since: str = "", until: str = "", limit=None) -> list:
    """검색 연산자(검색창 SOT §4.2 — 띄어쓰기 AND·`|` OR·`-` NOT·괄호·"구절") — 단위는 명함 하나, 낱말은 모든 칸 글자 **일부**로
    (대소문자·빈칸·하이픈 무시). `#낱말` 은 해시태그(앞부분 일치). 스캔일 범위 YYYY-MM-DD.
    반환 = 명함 DB 행(dict), 스캔일 최근 먼저, 찾은 것 전부(명함 SOT §5.9 '결과' — 종전 500장 상한은 '전체 목록이 일부만' 이라 없앰).
    limit 을 주면 그 장 수까지만.
    261117-30: 칸을 이어 붙인 글을 식으로 보려고 날짜로만 SQL 에서 거르고 낱말은 파이썬에서 본다(명함 수천 장 — 수 ms)."""
    from viewer.query import parse, flat_text
    pq = parse(text or "")
    if not pq.empty and not pq.ok:
        return []                                   # '-' 낱말뿐 — 찾을 낱말이 없다(SOT §4.2)
    where, args = [], []
    if since:
        where.append("IFNULL(scanned,'') >= ?"); args.append(since)
    if until:
        where.append("IFNULL(scanned,'') <= ?"); args.append(until + "￿")
    q = "SELECT * FROM cards" + (" WHERE " + " AND ".join(where) if where else "")
    q += " ORDER BY IFNULL(scanned,'') DESC, id DESC"
    if pq.empty:
        if limit is not None:
            q += " LIMIT %d" % int(limit)
        return [store._row(r) for r in store.con.execute(q, args).fetchall()]
    out = []
    for r in store.con.execute(q, args):
        hay = flat_text(" ".join(str(r[c] or "") for c in _COLS if c in r.keys())).lower()
        try:
            tags = [str(t).lower() for t in json.loads(r["tags"] or "[]")]
        except (ValueError, TypeError):
            tags = []

        def has(w, hay=hay, tags=tags):
            if w.startswith("#") and len(w) > 1:
                t = w[1:].lower()
                return any(x.startswith(t) for x in tags)
            return flat_text(w).lower() in hay
        if pq.test(has):
            out.append(store._row(r))
            if limit is not None and len(out) >= int(limit):
                break
    return out


KINDS = ("all", "ko", "en", "card", "nocard")     # 찾기 칸 앞 구분(명함 SOT §5.24.1, 사용자 지시 261119)
_HANGUL = re.compile(r"[가-힣ㄱ-ㆎ]")
_LATIN = re.compile(r"[A-Za-z]")


def kind_ok(card: dict, kind: str) -> bool:
    """구분 — 'ko' = 이름에 한글, 'en' = 이름이 영어(로마자, 한글 없음), 'card' = 명함 그림 있음, 'nocard' = 그림 없는 주소록 명함."""
    if kind in ("ko", "en"):
        name = str(card.get("name") or "")
        if _HANGUL.search(name):
            return kind == "ko"
        return kind == "en" and bool(_LATIN.search(name))
    if kind in ("card", "nocard"):
        from viewer.bizcard.vcard import is_contact
        has = bool(card.get("front")) and not is_contact(card)      # 그림 없는 주소록 명함(D22)은 '명함 없음'
        return has if kind == "card" else not has
    return True


def _like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def since_for(period: str, today=None) -> str:
    """'all'·'1m'·'3m'·'1y' → 시작 날짜(YYYY-MM-DD) 또는 ''."""
    import datetime as dt
    d = today or dt.date.today()
    days = {"1m": 31, "3m": 92, "1y": 366}.get(period)
    return (d - dt.timedelta(days=days)).isoformat() if days else ""


def card_for_path(path, db=None):
    """텍스트 창 명함 메모 칸(텍스트 창 SOT §2.2) — 이 그림이 정리본(앞면·뒷면)인 명함 행, 없으면 None.
    명함 DB 를 **읽기 전용**으로 잠깐 연다(사진을 바꿀 때마다 부르므로 스키마 만들기·쓰기 없음, UI 대기 상한)."""
    import sqlite3
    from viewer import dbutil
    from viewer.bizcard.store import db_path, BizcardStore
    p = Path(db) if db else db_path()
    if not path or not p.exists():
        return None
    k = _nk(path)
    try:
        con = dbutil.connect(p, dbutil.BUSY_MS_UI, readonly=True)   # 응답성 SOT §4 ⑤ — UI 대기 상한
    except sqlite3.Error:
        return None
    try:
        r = con.execute("SELECT * FROM cards WHERE front=? OR back=? LIMIT 1", (k, k)).fetchone()
        return BizcardStore._row(r)
    except sqlite3.Error:
        return None
    finally:
        con.close()


def set_memo(card_id: int, memo: str, db=None) -> None:
    """명함 메모만 고침(텍스트 창 SOT §2.2) — 명함찾기 창과 같은 칸."""
    from viewer.bizcard.store import BizcardStore
    st = BizcardStore(db, ui=True)
    try:
        update_card(st, card_id, {"memo": memo})
    finally:
        st.close()


# ── 인물 사진 ──
def people_dir(front) -> Path:
    return Path(front).parent.parent / PEOPLE_DIR


def person_photos(front) -> list:
    """정리본 이름과 같은(또는 ` (n)` 붙은) 인물 사진들 — 이름 차례."""
    if not front:
        return []
    d = people_dir(front)
    stem = Path(front).stem
    pat = re.compile(r"^%s( \((\d+)\))?$" % re.escape(stem), re.I)
    try:
        names = os.listdir(d)
    except OSError:
        return []
    got = []
    for n in names:
        m = pat.match(os.path.splitext(n)[0])
        if m and os.path.splitext(n)[1].lower() in R.IMG_EXTS:
            got.append((int(m.group(2) or 1), n))
    # 차례 = 번호(이름 없음 = 1, ` (2)` = 2 …) — 글자 차례로는 ' (2)' 가 '.jpg' 보다 앞에 온다(빈칸 < 마침표)
    return [str(d / n) for _k, n in sorted(got)]


CONTACT_PHOTO_SUFFIX = "_주소록"     # 같은 이름의 그림 명함과 인물 사진이 섞이지 않게(§5.24.3 '그림 없는 명함')


def contact_photo_front(name: str, company: str, folder) -> str:
    """그림 없는 주소록 명함의 인물 사진 기준 경로(가상) — `<명함 폴더>\\정리\\<성명_회사명>.jpg`.
    인물 사진은 그 `parent.parent\\인물` = 그림 명함과 같은 `<명함 폴더>\\인물` 에 `성명_회사명.jpg` 로 놓인다.
    같은 정리 폴더에 같은 이름의 그림 명함(정리본)이 있으면 `_주소록` 을 붙인다. 명함 폴더·이름이 없으면 ""."""
    if not folder or not (name or "").strip():
        return ""
    from viewer.bizcard.importer import OUT_DIR
    out = Path(folder) / OUT_DIR
    stem = Path(R.card_filename(name, company)).stem
    if any((out / (stem + e)).exists() for e in R.IMG_EXTS):
        stem += CONTACT_PHOTO_SUFFIX
    return str(out / (stem + ".jpg"))


def photo_front(card, folder=None) -> str:
    """인물 사진 기준 경로 — 그림 명함은 정리본 앞면, 그림 없는 주소록 명함은 `contact_photo_front`(folder = 명함 폴더)."""
    if not card:
        return ""
    from viewer.bizcard.vcard import is_contact
    if not is_contact(card):
        return card.get("front") or ""
    return contact_photo_front(card.get("name") or "", card.get("company") or "", folder)


def _real(front) -> str:
    """명함 DB 경로는 소문자 열쇠 — 새 이름을 지을 때는 실제 대소문자로."""
    return os.path.realpath(front) if front and os.path.exists(front) else str(front)


def next_photo_path(front) -> Path:
    front = _real(front)
    d = people_dir(front)
    stem = Path(front).stem
    p, k = d / (stem + ".jpg"), 2
    while p.exists():
        p, k = d / ("%s (%d).jpg" % (stem, k)), k + 1
    return p


def save_person_photo(src, dst) -> None:
    """그림 → JPG(화질 95). 방향(EXIF Orientation)은 그림에 반영하고 EXIF 는 통째로 뺀다(GPS 포함). 배경에서 부른다."""
    from PIL import Image, ImageOps
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        tmp = dst.with_name(dst.name + ".part")
        im.save(tmp, "JPEG", quality=95)          # exif= 를 주지 않으면 EXIF 없음
    os.replace(tmp, dst)


# ── 고치기 ──
def update_card(store, card_id: int, fields: dict, commit: bool = True) -> None:
    """id 로 칸 고침(앞면 경로가 바뀌어도 새 행을 만들지 않는다). fields: 칸 → 값(phones·emails·urls 는 목록)."""
    row = store._row(store.con.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone())
    if row is None:
        return
    row.update(fields)
    sets, args = [], []
    for k, v in fields.items():
        if k in ("phones", "emails", "urls", "tags"):
            v = json.dumps([list(x) if isinstance(x, tuple) else x for x in v], ensure_ascii=False)
        elif k == "en":
            v = json.dumps(v or {}, ensure_ascii=False)
        elif k in ("front", "back", "src_key"):
            from viewer.bizcard.vcard import CONTACT_PREFIX
            # 주소록 명함의 열쇠 `contact:…` 는 경로가 아니다 — 경로 열쇠로 바꾸면 [저장] 뒤 그림 없는 명함이 아니게 된다(§5.24.5)
            v = (v if str(v).startswith(CONTACT_PREFIX) else _nk(v)) if v else ""
        sets.append("%s=?" % k)
        args.append(v)
    sets.append("updated=?")
    args.append(time.time())
    store.con.execute("UPDATE cards SET %s WHERE id=?" % ", ".join(sets), args + [card_id])
    store.con.execute("DELETE FROM cards_fts WHERE rowid=?", (card_id,))
    store.con.execute("INSERT INTO cards_fts(rowid, body) VALUES(?,?)", (card_id, store._body(row)))
    if commit:
        store.con.commit()


def card_by_id(store, card_id: int):
    return store._row(store.con.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone())


# ── 체크한 칸 복사 (§5.24, D21 '항목: 값' 줄) ──
COPY_FIELDS = ("name", "company", "dept", "title", "cell", "work", "fax", "email", "address", "url", "memo")
COPY_DEFAULT = ("name", "company", "title", "cell", "email")


def field_values(card: dict) -> dict:
    """명함 행 → 칸 값(전화는 종류마다 모두, 메일·누리집도 모두 — 쉼표로)."""
    ph = card.get("phones") or []
    pick = lambda kind: ", ".join(n for k, n in ph if k == kind)
    return {"name": card.get("name") or "", "company": card.get("company") or "", "dept": card.get("dept") or "",
            "title": card.get("title") or "", "cell": pick("cell"), "work": pick("work"), "fax": pick("fax"),
            "email": ", ".join(card.get("emails") or []), "address": card.get("address") or "",
            "url": ", ".join(card.get("urls") or []), "memo": card.get("memo") or ""}


def copy_text(values_list, fields, labels: dict) -> str:
    """[{칸: 값}] → '항목: 값' 줄(값 있는 칸만), 명함 사이 빈 줄. 여러 줄 메모는 둘째 줄부터 들여 씀."""
    blocks = []
    for vals in values_list:
        lines = []
        for k in COPY_FIELDS:
            if k in fields and (vals.get(k) or "").strip():
                lines.append("%s: %s" % (labels.get(k, k), vals[k].strip().replace("\n", "\n  ")))
        if lines:
            blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


# ── 즐겨찾기 탭 (§5.24) — 이 PC 의 명함 DB 에만(D4) ──
def fav_init(store, default_name: str) -> None:
    store.con.executescript("""
    CREATE TABLE IF NOT EXISTS fav_groups(id INTEGER PRIMARY KEY, name TEXT, pos INTEGER);
    CREATE TABLE IF NOT EXISTS fav_members(group_id INTEGER, card_id INTEGER, pos INTEGER, PRIMARY KEY(group_id, card_id));
    """)
    store.con.execute("CREATE TABLE IF NOT EXISTS recent(card_id INTEGER PRIMARY KEY, seen TEXT)")   # '최근' 탭(D27)
    for table, cols in (("fav_groups", TODO_COLS), ("fav_members", MEMBER_COLS)):
        have = {r[1] for r in store.con.execute("PRAGMA table_info(%s)" % table)}
        for col, typ in cols:                          # 할 일(D26)·마감(D28)·메모 글(D29) — 옛 DB 에는 열을 더한다(옛 판은 이 열을 모른다)
            if col not in have:
                store.con.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, col, typ))
    if store.con.execute("SELECT COUNT(*) FROM fav_groups").fetchone()[0] == 0:
        store.con.execute("INSERT INTO fav_groups(name, pos) VALUES(?, 0)", (default_name,))
    store.con.commit()


TODO_COLS = (("todo", "INTEGER DEFAULT 0"), ("t_memo", "TEXT DEFAULT ''"), ("t_start", "TEXT DEFAULT ''"), ("t_end", "TEXT DEFAULT ''"),
             ("closed", "INTEGER DEFAULT 0"))
MEMBER_COLS = (("memo_entry", "TEXT DEFAULT ''"),)


def _todo_live(r, today: str) -> bool:
    """할 일 탭이 기간 안인가 — 시작일 ≤ 오늘 ≤ 종료일(종료일 없으면 계속)."""
    return (r["t_start"] or "") <= today and (not r["t_end"] or today <= r["t_end"])


def fav_groups(store, today: str = None) -> list:
    """탭 (id, 이름) 차례대로. today(YYYY-MM-DD)를 주면 마감한 탭·기간 밖 할 일 탭은 뺀다(D26·D28 — 숨김, 지우지 않음)."""
    rows = store.con.execute("SELECT * FROM fav_groups ORDER BY pos, id").fetchall()
    return [(r["id"], r["name"]) for r in rows
            if today is None or not (r["closed"] or (r["todo"] and not _todo_live(r, today)))]


def is_todo(store, gid) -> bool:
    r = store.con.execute("SELECT todo FROM fav_groups WHERE id=?", (gid,)).fetchone()
    return bool(r and r["todo"])


def closed_tabs(store, today: str) -> list:
    """'마감한 탭 ▸'(D28) — 마감한 탭과 기간 밖 할 일 (id, 이름, 할 일인가)."""
    rows = store.con.execute("SELECT * FROM fav_groups ORDER BY pos, id").fetchall()
    return [(r["id"], r["name"], bool(r["todo"])) for r in rows if r["closed"] or (r["todo"] and not _todo_live(r, today))]


def fav_close(store, gid: int, closed: bool = True) -> bool:
    """탭 마감 / 다시 열기(D28). 할 일이 아닌 마지막 열린 탭은 마감하지 않는다(False)."""
    if closed and not is_todo(store, gid) and store.con.execute(
            "SELECT COUNT(*) FROM fav_groups WHERE IFNULL(todo, 0)=0 AND IFNULL(closed, 0)=0").fetchone()[0] <= 1:
        return False
    store.con.execute("UPDATE fav_groups SET closed=? WHERE id=?", (1 if closed else 0, gid))
    store.con.commit()
    return True


def todo_info(store, gid: int):
    """할 일 탭이면 {title, memo, start, end}, 아니면 None."""
    r = store.con.execute("SELECT * FROM fav_groups WHERE id=?", (gid,)).fetchone()
    if r is None or not r["todo"]:
        return None
    return {"title": r["name"] or "", "memo": r["t_memo"] or "", "start": r["t_start"] or "", "end": r["t_end"] or ""}


def todo_hidden(store, today: str) -> list:
    """기간 밖 할 일 탭 (id, 제목) — '마감한 탭 ▸' 에 함께(closed_tabs)."""
    rows = store.con.execute("SELECT * FROM fav_groups WHERE todo=1 ORDER BY t_start, id").fetchall()
    return [(r["id"], r["name"]) for r in rows if not _todo_live(r, today)]


def todo_memo_entry(info: dict, ongoing: str) -> str:
    """인물 메모 맨 위에 넣는 글 — `[시작 ~ 끝|계속] 제목` + 내용."""
    head = "[%s ~ %s] %s" % (info.get("start") or "", info.get("end") or ongoing, info.get("title") or "")
    body = (info.get("memo") or "").strip()
    return head + ("\n" + body if body else "")


def _todo_memo(store, gid: int, card_ids, ongoing: str) -> None:
    info = todo_info(store, gid)
    if info is None:
        return
    entry = todo_memo_entry(info, ongoing)
    for cid in card_ids:
        r = store.con.execute("SELECT memo FROM cards WHERE id=?", (cid,)).fetchone()
        if r is None:
            continue
        old = (r["memo"] or "").strip()
        update_card(store, cid, {"memo": entry + ("\n\n" + old if old else "")}, commit=False)   # 최신이 맨 위
        store.con.execute("UPDATE fav_members SET memo_entry=? WHERE group_id=? AND card_id=?", (entry, gid, cid))   # D29


def remove_memo_entry(memo: str, entry: str) -> str:
    """메모에서 할 일 글 하나 빼기(D29) — 글이 그대로 있을 때만, 둘레의 빈 줄 하나도. 없으면 메모 그대로."""
    if not entry or entry not in (memo or ""):
        return memo
    for a in (entry + "\n\n", "\n\n" + entry, entry):
        if a in memo:
            return memo.replace(a, "", 1).strip("\n")
    return memo


def todo_add(store, info: dict, card_ids, ongoing: str) -> int:
    """할 일 탭을 만들고(이름 = 제목) 사람들을 넣는다 — 그 사람들 메모 맨 위에 할 일 글. 반환 = 탭 id."""
    pos = store.con.execute("SELECT IFNULL(MAX(pos), -1) + 1 FROM fav_groups").fetchone()[0]
    gid = store.con.execute("INSERT INTO fav_groups(name, pos, todo, t_memo, t_start, t_end) VALUES(?,?,1,?,?,?)",
                            (info["title"], pos, info.get("memo") or "", info.get("start") or "", info.get("end") or "")).lastrowid
    store.con.commit()
    fav_add(store, gid, card_ids, ongoing=ongoing)
    return gid


def todo_update(store, gid: int, info: dict) -> None:
    """할 일 고치기 — 제목(탭 이름)·내용·기간. 메모는 다시 쓰지 않는다."""
    store.con.execute("UPDATE fav_groups SET name=?, t_memo=?, t_start=?, t_end=? WHERE id=? AND todo=1",
                      (info["title"], info.get("memo") or "", info.get("start") or "", info.get("end") or "", gid))
    store.con.commit()


def fav_add_group(store, name: str) -> int:
    pos = store.con.execute("SELECT IFNULL(MAX(pos), -1) + 1 FROM fav_groups").fetchone()[0]
    gid = store.con.execute("INSERT INTO fav_groups(name, pos) VALUES(?, ?)", (name, pos)).lastrowid
    store.con.commit()
    return gid


def fav_rename_group(store, gid: int, name: str) -> None:
    store.con.execute("UPDATE fav_groups SET name=? WHERE id=?", (name, gid))
    store.con.commit()


def fav_delete_group(store, gid: int, ongoing: str = "") -> bool:
    """탭 삭제 — 할 일이 아닌 마지막 탭은 지우지 않는다(False). 명함은 그대로, 할 일로 메모에 적은 글은 빼낸다(D29)."""
    r = store.con.execute("SELECT todo FROM fav_groups WHERE id=?", (gid,)).fetchone()
    if r is None:
        return False
    if not r["todo"] and store.con.execute("SELECT COUNT(*) FROM fav_groups WHERE IFNULL(todo, 0)=0").fetchone()[0] <= 1:
        return False
    info = todo_info(store, gid)
    guess = todo_memo_entry(info, ongoing or "…") if info else ""      # 글을 기억하지 않던 옛 할 일
    for m in store.con.execute("SELECT m.card_id, m.memo_entry, c.memo FROM fav_members m JOIN cards c ON c.id = m.card_id "
                               "WHERE m.group_id=?", (gid,)).fetchall():
        new = remove_memo_entry(m["memo"] or "", m["memo_entry"] or guess)
        if new != (m["memo"] or ""):
            update_card(store, m["card_id"], {"memo": new}, commit=False)
    store.con.execute("DELETE FROM fav_members WHERE group_id=?", (gid,))
    store.con.execute("DELETE FROM fav_groups WHERE id=?", (gid,))
    store.con.commit()
    return True


def fav_order_groups(store, gids) -> None:
    for i, g in enumerate(gids):
        store.con.execute("UPDATE fav_groups SET pos=? WHERE id=?", (i, g))
    store.con.commit()


def fav_members(store, gid: int) -> list:
    """탭의 명함들(차례대로) — 명함 행이 없어진 칸은 빼고 보인다."""
    q = ("SELECT c.* FROM fav_members m JOIN cards c ON c.id = m.card_id WHERE m.group_id=? ORDER BY m.pos, m.rowid")
    return [store._row(r) for r in store.con.execute(q, (gid,)).fetchall()]


def fav_add(store, gid: int, card_ids, ongoing: str = "") -> int:
    """지금 탭 끝에 — 이미 있으면 건너뜀. 할 일 탭이면 새로 든 사람 메모 맨 위에 할 일 글(D26). 반환 = 더한 수."""
    pos = store.con.execute("SELECT IFNULL(MAX(pos), -1) + 1 FROM fav_members WHERE group_id=?", (gid,)).fetchone()[0]
    n = 0
    new = []
    for cid in card_ids:
        cur = store.con.execute("INSERT OR IGNORE INTO fav_members(group_id, card_id, pos) VALUES(?,?,?)", (gid, cid, pos + n))
        n += cur.rowcount
        if cur.rowcount:
            new.append(cid)
    if new:
        _todo_memo(store, gid, new, ongoing or "…")
    store.con.commit()
    return n


def fav_remove(store, gid: int, card_ids) -> None:
    store.con.executemany("DELETE FROM fav_members WHERE group_id=? AND card_id=?", [(gid, c) for c in card_ids])
    store.con.commit()


def fav_order(store, gid: int, card_ids) -> None:
    for i, c in enumerate(card_ids):
        store.con.execute("UPDATE fav_members SET pos=? WHERE group_id=? AND card_id=?", (i, gid, c))
    store.con.commit()


def fav_forget_cards(store, card_ids) -> None:
    """명함을 지울 때 — 모든 탭·최근에서 그 칸을 뺀다."""
    store.con.executemany("DELETE FROM fav_members WHERE card_id=?", [(c,) for c in card_ids])
    store.con.executemany("DELETE FROM recent WHERE card_id=?", [(c,) for c in card_ids])
    store.con.commit()


# ── '최근' 탭 (D27) — 세부 칸에 RECENT_MS 이상 본 명함, 사람이 넣지 않는다 ──
def recent_add(store, card_id: int, when: str = "") -> None:
    import datetime
    when = when or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    store.con.execute("INSERT INTO recent(card_id, seen) VALUES(?, ?) ON CONFLICT(card_id) DO UPDATE SET seen=excluded.seen",
                      (card_id, when))
    store.con.commit()


def recent_list(store, since: str = "", until: str = "") -> list:
    """기간(YYYY-MM-DD, 끝 날짜 포함) 안에 본 명함 — 최근에 본 차례."""
    q = "SELECT c.* FROM recent r JOIN cards c ON c.id = r.card_id WHERE 1=1"
    args = []
    if since:
        q += " AND substr(r.seen, 1, 10) >= ?"
        args.append(since)
    if until:
        q += " AND substr(r.seen, 1, 10) <= ?"
        args.append(until)
    return [store._row(r) for r in store.con.execute(q + " ORDER BY r.seen DESC, r.rowid DESC", args).fetchall()]


def recent_remove(store, card_ids) -> None:
    store.con.executemany("DELETE FROM recent WHERE card_id=?", [(c,) for c in card_ids])
    store.con.commit()


# ── 이메일 복사 (§5.24.1) — 받는 사람 칸에 붙여 쓰기 ──
def email_list(cards) -> tuple:
    """고른 명함들의 메일 주소(여럿이면 모두, 같은 주소 한 번) + 메일 없는 명함 수 (명함 SOT §5.24.1 '이메일 복사')."""
    out, seen, missing = [], set(), 0
    for c in cards:
        got = False
        for e in c.get("emails") or []:
            e = str(e[-1] if isinstance(e, (list, tuple)) else e).strip()
            if not e:
                continue
            got = True
            if e.lower() not in seen:
                seen.add(e.lower())
                out.append(e)
        if not got:
            missing += 1
    return out, missing


def emails_text(cards) -> str:
    return ", ".join(email_list(cards)[0])


# ── Gmail 보내기 (명함 SOT §5.24.1 'Gmail 보내기', 사용자 결정 261120) — 브라우저 쓰기 창 주소만, 네트워크 없음(§2.1) ──
GMAIL_COMPOSE = "https://mail.google.com/mail/?view=cm&fs=1"
GMAIL_URL_MAX = 2000                # 주소 한 개 최대 길이 — 넘으면 쓰기 창을 나눠 연다


def gmail_urls(emails, field: str = "to", account: str = "", limit: int = GMAIL_URL_MAX) -> list:
    """Gmail 쓰기 창 주소들 — field('to'·'bcc') 칸에 주소를 넣고, 한 주소가 limit 를 넘지 않게 차례대로 나눈다.
    account(보낼 구글 계정)가 있으면 authuser 로. 주소가 하나도 없으면 []."""
    from urllib.parse import quote
    base = GMAIL_COMPOSE + ("&authuser=" + quote(account.strip(), safe="@") if (account or "").strip() else "")
    head = "%s&%s=" % (base, field)
    urls, cur = [], ""
    for e in emails:
        q = quote(e, safe="@")
        if cur and len(head) + len(cur) + 1 + len(q) > limit:
            urls.append(head + cur)
            cur = ""
        cur = (cur + "," + q) if cur else q
    if cur:
        urls.append(head + cur)
    return urls


# ── 인물 사진 차례 (§5.24, D20 — 파일 이름을 차례대로) ──
def photo_name(front, i: int, ext: str = ".jpg") -> str:
    stem = Path(front).stem
    return (stem if i == 0 else "%s (%d)" % (stem, i + 1)) + ext


def photo_renames(front, ordered) -> list:
    """원하는 차례의 사진 경로들 → 이름 바꾸기 [(원래, 임시, 최종)] — 바꿀 것만. 임시를 거쳐 서로 겹치지 않게."""
    out = []
    front = _real(front)
    d = people_dir(front)
    for i, p in enumerate(ordered):
        final = str(d / photo_name(front, i, os.path.splitext(p)[1].lower() or ".jpg"))
        if os.path.normcase(final) != os.path.normcase(p):
            tmp = str(d / ("~%s.%d.tmp%s" % (Path(front).stem, i, os.path.splitext(p)[1])))
            out.append((p, tmp, final))
    return out


# ── 지울 파일 (§5.24 D18 — 명함 관리 [삭제] 와 같은 것 + 인물 사진) ──
def card_files(card: dict, folder=None) -> tuple:
    """(원본 [앞·뒤·PDF], 정리본 [앞·뒤], 인물 사진) — 있는 파일만, 실제 경로. 원본은 원천 폴더를 다시 훑어 찾는다.
    folder = 명함 폴더(그림 없는 주소록 명함의 인물 사진 자리 — `photo_front`)."""
    from viewer.bizcard.importer import scan_folder, PDF_DIR
    from viewer.bizcard.vcard import is_contact
    if is_contact(card):                        # 주소록에서 가져온 명함 — 그림 파일 없음, 인물 사진만
        pf = photo_front(card, folder)
        return [], [], person_photos(pf) if pf else []
    src = card.get("src_key") or ""
    orig = []
    if src:
        folder = Path(src).parent
        if folder.name.lower() == PDF_DIR.lower():
            folder = folder.parent
        k = _nk(src)
        for it in scan_folder(folder) if folder.is_dir() else []:
            if _nk(it.key) == k:
                orig = [p for p in (it.front, it.back, it.pdf) if p]
                break
        if not orig and os.path.exists(src):
            orig = [src]
    outs = [os.path.realpath(p) for p in (card.get("front"), card.get("back")) if p and os.path.exists(p)]
    photos = person_photos(os.path.realpath(card["front"])) if card.get("front") else []
    return [p for p in orig if os.path.exists(p)], outs, photos


# ── 주소록 가져오기 (§5.24 D22 — 모두 그림 없는 명함으로 넣고, 같은 사람은 [중복 검토] 창에서 고른다 §5.24.8) ──
_SCALARS = ("name", "company", "dept", "title", "address", "memo")


def _phone_key(num: str) -> str:
    from viewer.bizcard.vcard import digits
    d = digits(num)
    return d if len(d) >= 9 else ""


# 주소록 출처(§5.24 D24) — 칸마다 어느 주소록에서 왔나. 중복 검토의 출처(리멤버·구글)와 손으로 고친 칸을 가린다(§5.24.8).
SOURCE_RANK = {"google": 1, "remember": 2}


def src_init(store) -> None:
    store.con.execute("CREATE TABLE IF NOT EXISTS contact_src(card_id INTEGER, field TEXT, src TEXT, PRIMARY KEY(card_id, field))")
    store.con.commit()


def field_srcs(store, card_id: int) -> dict:
    try:
        return {r["field"]: r["src"] for r in store.con.execute("SELECT field, src FROM contact_src WHERE card_id=?", (card_id,))}
    except sqlite3.OperationalError:
        return {}


def _set_srcs(store, card_id: int, fields, src: str) -> None:
    store.con.executemany("INSERT INTO contact_src(card_id, field, src) VALUES(?,?,?) ON CONFLICT(card_id, field) "
                          "DO UPDATE SET src=excluded.src", [(card_id, f, src) for f in fields])


def forget_srcs(store, card_id: int, fields=None) -> None:
    """손으로 고친 칸(명함찾기 [저장])은 출처를 지운다 — 다음 가져오기가 덮어쓰지 않게."""
    try:
        if fields is None:
            store.con.execute("DELETE FROM contact_src WHERE card_id=?", (card_id,))
        else:
            store.con.executemany("DELETE FROM contact_src WHERE card_id=? AND field=?", [(card_id, f) for f in fields])
        store.con.commit()
    except sqlite3.OperationalError:
        pass


def apply_import(store, persons, tag: str = "", src: str = "") -> int:
    """가져오기 — 연락처마다 그림 없는 명함(front `contact:<번호>`)을 더한다. 반환 = 더한 수.
    같은 사람이 이미 있어도 합치지 않는다 — 부르는 쪽이 곧바로 [중복 검토] 창을 띄운다(§5.24.8, 사용자 지시 261119).
    src = 'remember'·'google' — 칸마다 출처를 적어 둔다(중복 검토의 출처·손으로 고친 칸 가리기)."""
    src_init(store)
    added = 0
    for p in persons:
        nid = _insert_contact(store, p, [t for t in ("명함", tag) if t])
        if src:
            _set_srcs(store, nid, [k for k in _SCALARS if (p.get(k) or "").strip()], src)
        added += 1
    store.con.commit()
    return added


def _insert_contact(store, p: dict, tags) -> int:
    """그림 없는 명함 한 장(front `contact:<번호>`)을 넣고 찾기 색인까지 — 새 id. 커밋은 부르는 쪽이."""
    import uuid
    from viewer.bizcard.vcard import CONTACT_PREFIX
    front = CONTACT_PREFIX + uuid.uuid4().hex
    now = time.time()
    cur = store.con.execute(
        "INSERT INTO cards(front, back, src_key, src_pdf, name, company, title, phones, emails, urls, address, en, "
        "memo, tags, scanned, created, updated, dept) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (front, "", "", "", p.get("name") or "", p.get("company") or "", p.get("title") or "",
         json.dumps([list(x) for x in p.get("phones") or []], ensure_ascii=False),
         json.dumps(list(p.get("emails") or []), ensure_ascii=False),
         json.dumps(list(p.get("urls") or []), ensure_ascii=False), p.get("address") or "", "{}",
         p.get("memo") or "", json.dumps(tags, ensure_ascii=False), time.strftime("%Y-%m-%d"), now, now,
         p.get("dept") or ""))
    nid = cur.lastrowid
    row = card_by_id(store, nid)
    store.con.execute("INSERT INTO cards_fts(rowid, body) VALUES(?,?)", (nid, store._body(row)))
    return nid


# ── 새 명함 입력 (§5.24.1 '새 명함 입력', 261120-15) — 창(Qt)은 widgets/bizcard_new_dialog.py, 여기는 저장만(배경에서) ──
MANUAL_TAG = "직접입력"


def add_new_card(store, fields: dict, folder: str = "", front_img: str = "", back_img: str = "", photos=()) -> tuple:
    """손으로 넣은 명함 한 장 — 반환 (새 id, 인물 사진 실패 수).
    앞면 그림이 없으면 그림 없는 명함(`contact:`), 있으면 명함 관리 [적용]과 같은 길(`apply_cards`)로 `<folder>\\정리\\성명_회사명.jpg`.
    fields = {name, company, dept, title, address, phones, emails, urls, memo}. 인물 사진은 `photo_front` 자리에 JPG(EXIF 뺌)."""
    from viewer.bizcard import apply as AP
    tags = list(dict.fromkeys(AP.tags_for({"name": fields.get("name") or "", "company": fields.get("company") or "",
                                            "langs": []}) + [MANUAL_TAG]))
    if front_img:
        if not folder:
            raise ValueError("no folder")
        import uuid
        from viewer.bizcard.importer import OUT_DIR
        key = "manual:" + uuid.uuid4().hex
        row = dict(fields, key=key, front=front_img, back=back_img or "", pdf="", keep_back=bool(back_img), langs=[],
                   scanned=time.strftime("%Y-%m-%d"), en={})
        AP.apply_cards([row], Path(folder) / OUT_DIR, db=store.path)
        c = store.card_by_src(key)
        if not c:
            raise OSError("apply failed")
        nid = c["id"]
        update_card(store, nid, {"memo": fields.get("memo") or "", "dept": fields.get("dept") or "", "tags": tags})
    else:
        nid = _insert_contact(store, dict(fields, tags=tags), tags)
        store.con.commit()
    bad = 0
    pf = photo_front(card_by_id(store, nid), folder) if photos else ""
    for s in photos or ():
        try:
            if not pf:
                raise ValueError("no folder")
            save_person_photo(s, next_photo_path(pf))
        except Exception:
            bad += 1
    return nid, bad


def same_person_ids(store, card_id: int) -> list:
    """같은 사람일 수 있는 다른 명함 — 휴대폰 번호나 메일 주소가 같은 것(§5.24.1 '새 명함 입력' 저장 뒤 물음)."""
    c = card_by_id(store, card_id)
    if not c:
        return []
    mob = set(_mobile_keys(c))
    mails = {str(e[-1] if isinstance(e, (list, tuple)) else e).strip().lower() for e in c.get("emails") or [] if e}
    mails.discard("")
    if not mob and not mails:
        return []
    out = []
    for r in store.con.execute("SELECT id FROM cards WHERE id<>?", (card_id,)).fetchall():
        o = card_by_id(store, r[0])
        if not o:
            continue
        om = {str(e[-1] if isinstance(e, (list, tuple)) else e).strip().lower() for e in o.get("emails") or [] if e}
        if mob & set(_mobile_keys(o)) or mails & om:
            out.append(o["id"])
    return out


# ── 중복 검토 (§5.24.8 D30) — 묶기·출처·차례·합친 값은 여기(Qt 없음), 파일 옮기기·적용은 창이 ──
DUPE_SOURCES = ("card", "remember", "google", "contact")   # 명함(그림) · 리멤버 · 구글 · 출처 모름 주소록
DUPE_ORDER_KEY = "dupe_order"
HOLD_DIR = "병합 보관"            # 합쳐 지운 그림 명함 파일 — 정리 폴더 옆(인물 폴더와 같은 자리), 다음 합치기 때 휴지통
WHY_SURE = ("phone", "mail")
_WHY_RANK = {"phone": 0, "mail": 1, "typo": 2, "namecomp": 3}
_ONE = ("name", "company", "dept", "title", "address")


def _nname(s) -> str:
    return re.sub(r"\s+", "", str(s or "")).lower()


def _keys_of(card) -> list:
    out = []
    for x in card.get("phones") or []:
        k = _phone_key(x[-1] if isinstance(x, (list, tuple)) else x)
        if k:
            out.append(k)
    return out


MOBILE_PREFIX = ("010", "011", "016", "017", "018", "019")


def _mobile_keys(card) -> list:
    """휴대폰 번호만(종류가 휴대폰이거나 01x 로 시작) — 회사 대표 번호·팩스는 여럿이 같이 쓴다(사용자 보고 261119)."""
    out = []
    for x in card.get("phones") or []:
        kind, num = (x[0], x[-1]) if isinstance(x, (list, tuple)) and len(x) >= 2 else ("", x)
        k = _phone_key(num)
        if k and kind != "fax" and (kind == "cell" or k.startswith(MOBILE_PREFIX)):
            out.append(k)
    return out


def _same_person_name(a, b) -> bool:
    """이름이 같거나 한쪽이 비었으면 True — 이름이 다르면 같은 휴대폰일 때만 같은 사람으로 본다."""
    na, nb = _nname(a.get("name")), _nname(b.get("name"))
    return not na or not nb or na == nb


def one_off(a: str, b: str) -> bool:
    """숫자 수가 같고 한 자리만 다른 번호(오타 의심)."""
    return len(a) == len(b) and a != b and sum(x != y for x, y in zip(a, b)) == 1


def dupe_order(store) -> list:
    got = [s for s in (store.meta_get(DUPE_ORDER_KEY) or []) if s in DUPE_SOURCES]
    return list(dict.fromkeys(got + [s for s in DUPE_SOURCES if s not in got]))


def card_source(store, card) -> str:
    from viewer.bizcard.vcard import is_contact
    if not is_contact(card):
        return "card"
    vals = [v for v in field_srcs(store, card["id"]).values() if v in SOURCE_RANK]
    if not vals:
        return "contact"
    return max(sorted(set(vals)), key=lambda v: (vals.count(v), SOURCE_RANK[v]))


def order_cards(cards, src_of: dict, order) -> list:
    """출처 순서, 같은 출처는 스캔일·고친 날 최근 먼저."""
    rank = {s: i for i, s in enumerate(order)}
    out = sorted(cards, key=lambda c: (str(c.get("scanned") or ""), float(c.get("updated") or 0)), reverse=True)
    return sorted(out, key=lambda c: rank.get(src_of.get(c["id"]), len(rank)))


def manual_fields(store, cards) -> set:
    """손으로 고친 칸 {(id, 칸)} — 주소록 명함인데 값이 있고 출처 기록이 없는 칸([저장] 이 출처를 지움, D24).
    중복 검토에서 출처 순서보다 먼저 쓴다(손으로 고친 값은 주소록이 덮지 않는다)."""
    from viewer.bizcard.vcard import is_contact
    out = set()
    for c in cards:
        if is_contact(c):
            srcs = field_srcs(store, c["id"])
            out |= {(c["id"], k) for k in _ONE if (c.get(k) or "").strip() and k not in srcs}
    return out


def dupe_groups(store, order=None) -> list:
    """[{cards: [차례대로], why: {id: 이유}, sure_root: {id: 확실한 묶음 열쇠}, src: {id: 출처}}] — 두 장 이상 묶음만.
    이유 = 'phone'·'mail'(확실) · 'typo'(이름 같고 번호 한 자리 다름) · 'namecomp'(이름+회사 같음)."""
    order = order or dupe_order(store)
    cards = [store._row(r) for r in store.con.execute("SELECT * FROM cards").fetchall()]
    byid = {c["id"]: c for c in cards}
    par, spar, edges = {}, {}, {}

    def find(p, x):
        while p.setdefault(x, x) != x:
            p[x] = p[p[x]]
            x = p[x]
        return x

    def link(a, b, why):
        if a == b:
            return
        par[find(par, a)] = find(par, b)
        if why in WHY_SURE:
            spar[find(spar, a)] = find(spar, b)
        for x, y in ((a, b), (b, a)):
            old = edges.get(x, {}).get(y)
            if old is None or _WHY_RANK[why] < _WHY_RANK[old]:
                edges.setdefault(x, {})[y] = why

    # 같은 휴대폰 = 같은 사람(이름이 달라도 — 이름을 잘못 읽었을 수 있다). 회사 번호·팩스·메일은 여럿이 같이 쓰므로
    # 이름이 같을(또는 한쪽이 빈) 때만(사용자 보고 261119 '첫번째 전화번호가 다르고 이름도 다른데 유사하다고 판단하면 안 됨')
    bucket = {}
    for c in cards:
        mob = set(_mobile_keys(c))
        for k in mob:
            bucket.setdefault(("c", k), []).append(c)
        for k in set(_keys_of(c)) - mob:
            bucket.setdefault(("t", k), []).append(c)
        for e in {str(e).strip().lower() for e in c.get("emails") or [] if str(e).strip()}:
            bucket.setdefault(("m", e), []).append(c)
    for (t, _k), same in bucket.items():
        for i, a in enumerate(same):
            for b in same[i + 1:]:
                if t == "c" or _same_person_name(a, b):
                    link(a["id"], b["id"], "mail" if t == "m" else "phone")
    by_name, by_nc = {}, {}
    for c in cards:
        n = _nname(c.get("name"))
        if not n:
            continue
        by_name.setdefault(n, []).append(c)
        co = _nname(c.get("company"))
        if co:
            by_nc.setdefault((n, co), []).append(c)
    for same in by_name.values():
        for i, a in enumerate(same):
            ka = _mobile_keys(a)
            for b in same[i + 1:]:
                if any(one_off(x, y) for x in ka for y in _mobile_keys(b)):
                    link(a["id"], b["id"], "typo")
    for same in by_nc.values():
        for b in same[1:]:
            link(same[0]["id"], b["id"], "namecomp")
    comp = {}
    for cid in par:
        comp.setdefault(find(par, cid), []).append(cid)
    out = []
    for ids in comp.values():
        if len(ids) < 2:
            continue
        src = {i: card_source(store, byid[i]) for i in ids}
        ordered = order_cards([byid[i] for i in ids], src, order)
        why = {i: min(edges.get(i, {}).values(), key=lambda w: _WHY_RANK[w]) for i in ids}
        out.append({"cards": ordered, "why": why, "src": src, "sure_root": {i: find(spar, i) for i in ids},
                    "manual": manual_fields(store, [byid[i] for i in ids])})
    out.sort(key=lambda g: _nname(g["cards"][0].get("name")))
    return out


OLD_MOBILE = ("011", "016", "017", "018", "019")   # 예전 휴대폰 앞자리 — 010 번호가 있으면 뺀다(사용자 지시 261119)


def merge_plan(cards, manual=None) -> dict:
    """차례대로 놓인 명함들(첫째 = 대표) → {keeper, fields, frm, drop, photo_from}.
    한 칸은 손으로 고친 칸(manual = {(id, 칸)})이 먼저, 없으면 차례대로 처음 비지 않은 값.
    전화·메일·누리집은 모두(휴대폰을 바꿨을 수 있다 — 한 자리만 다른 번호는 오타로 빼고, 010 이 있으면 011·016~019 는 뺌),
    태그 모두, 메모는 대표 위 + 없는 글 아래."""
    from viewer.bizcard.vcard import is_contact
    rep = cards[0]
    manual = manual or set()
    fields, frm = {}, {}
    for k in _ONE:
        hand = [c for c in cards if (c["id"], k) in manual and (c.get(k) or "").strip()]
        for c in hand + cards:
            v = (c.get(k) or "").strip()
            if v:
                fields[k], frm[k] = v, c["id"]
                break
        else:
            fields[k] = ""
    en = {}
    for c in cards:
        for k, v in (c.get("en") or {}).items():
            if v and not en.get(k):
                en[k] = v
    fields["en"] = en
    memo = (rep.get("memo") or "").strip()
    for c in cards[1:]:
        m = (c.get("memo") or "").strip()
        if m and m not in memo:
            memo = (memo + "\n\n" + m) if memo else m
    fields["memo"] = memo
    phones, keys, mobs = [], [], []
    for c in cards:
        for kind, num in c.get("phones") or []:
            k = _phone_key(num) or re.sub(r"\D", "", num or "")
            mob = bool(_mobile_keys({"phones": [(kind, num)]}))
            if not k or k in keys or (mob and any(one_off(k, x) for x in mobs)):   # 휴대폰끼리만 오타로 봄(회사 직통은 한 자리 차이가 흔함)
                continue
            keys.append(k)
            phones.append((kind, num))
            if mob:
                mobs.append(k)
    if any(k.startswith("010") for k in keys):
        phones = [(kind, num) for (kind, num), k in zip(phones, keys) if not k.startswith(OLD_MOBILE)]
    fields["phones"] = phones
    for k in ("emails", "urls"):
        seen, vals = set(), []
        for c in cards:
            for x in c.get(k) or []:
                if str(x).strip() and str(x).lower() not in seen:
                    seen.add(str(x).lower())
                    vals.append(x)
        fields[k] = vals
    fields["tags"] = list(dict.fromkeys(t for c in cards for t in c.get("tags") or []))
    keeper = rep if not is_contact(rep) else next((c for c in cards if not is_contact(c)), rep)
    photo_from = None
    if not is_contact(keeper) and not person_photos(keeper.get("front")):
        photo_from = next((c["id"] for c in cards if c is not keeper and not is_contact(c) and person_photos(c.get("front"))), None)
    return {"keeper": keeper["id"], "fields": fields, "frm": frm,
            "drop": [c["id"] for c in cards if c["id"] != keeper["id"]], "photo_from": photo_from}


def merge_db(store, plan, extra: dict = None) -> None:
    """합친 값을 남길 행에, 지울 행의 즐겨찾기·할 일·최근 칸은 남길 행으로, 주소록 출처는 칸마다 값을 준 명함의 것.
    extra = 창이 정한 front·back(이름을 바꾼 뒤). 그 뒤 지울 행을 지운다(파일은 창이 먼저 옮김)."""
    kid = plan["keeper"]
    srcs = {cid: field_srcs(store, cid) for cid in set(plan["frm"].values())}
    update_card(store, kid, dict(plan["fields"], **(extra or {})), commit=False)
    for cid in plan["drop"]:
        for sql in ("INSERT OR IGNORE INTO fav_members(group_id, card_id, pos, memo_entry) "
                    "SELECT group_id, ?, pos, memo_entry FROM fav_members WHERE card_id=?",
                    "INSERT INTO recent(card_id, seen) SELECT ?, seen FROM recent WHERE card_id=? AND 1 "
                    "ON CONFLICT(card_id) DO UPDATE SET seen=MAX(recent.seen, excluded.seen)"):
            try:
                store.con.execute(sql, (kid, cid))
            except sqlite3.OperationalError:
                pass
    try:
        store.con.execute("DELETE FROM contact_src WHERE card_id=?", (kid,))
        store.con.executemany("INSERT INTO contact_src(card_id, field, src) VALUES(?,?,?)",
                              [(kid, f, srcs[c][f]) for f, c in plan["frm"].items() if srcs.get(c, {}).get(f)])
    except sqlite3.OperationalError:
        pass
    store.con.commit()
    for cid in plan["drop"]:
        r = store.con.execute("SELECT src_key FROM cards WHERE id=?", (cid,)).fetchone()
        if r is None:
            continue
        if r["src_key"]:
            store.delete_src(r["src_key"])
        else:
            store.delete_card(cid)


def hold_dir(front) -> Path:
    return Path(front).parent.parent / HOLD_DIR


# ── 해시태그 (§5.24) — 명함 DB 태그 칸, 정리본 파일 태그는 부르는 쪽이 앱 태그 저장소로 ──
def common_tags(cards) -> list:
    sets = [list(c.get("tags") or []) for c in cards]
    if not sets:
        return []
    first = sets[0]
    return [t for t in first if all(t in s for s in sets[1:])]


def retag_cards(store, cards, added, removed) -> None:
    for c in cards:
        cur = [t for t in (c.get("tags") or []) if t not in removed]
        update_card(store, c["id"], {"tags": list(dict.fromkeys(cur + list(added)))})


LANG_FIX_KEY = "lang_tag_one"


def fix_lang_tags(store, tags=None) -> int:
    """종전 규칙으로 `#한글`·`#영어` 둘 다 붙은 명함을 하나로(D25·§5.5) — 명함 DB 태그 칸과 정리본 앞뒷면 파일 태그.
    한 번만(meta `lang_tag_one`). tags = 앱의 태그 저장소(없으면 DB 만). 반환 = 고친 명함 수."""
    if store.meta_get(LANG_FIX_KEY):
        return 0
    import contextlib
    from viewer.bizcard.apply import lang_tag, LANG_TAGS
    from viewer.bizcard.vcard import is_contact
    ids =[r["id"] for r in store.con.execute("SELECT id FROM cards WHERE tags LIKE ? AND tags LIKE ?",
                                               ("%한글%", "%영어%")).fetchall()]
    n = 0
    ctx = tags.bulk() if tags is not None and hasattr(tags, "bulk") else contextlib.nullcontext()
    with ctx:
        for cid in ids:
            c = card_by_id(store, cid)
            cur = list(c.get("tags") or [])
            langs = [t for t in cur if t in LANG_TAGS]
            if len(set(langs)) < 2:
                continue
            keep = lang_tag(c.get("name") or "", c.get("company") or "", langs, ordered=False)
            drop = [t for t in LANG_TAGS if t != keep]
            update_card(store, cid, {"tags": [t for t in cur if t not in drop]}, commit=False)
            if tags is not None:
                for p in (c.get("front"), c.get("back")):
                    if p and not is_contact(c) and os.path.exists(p):
                        rp = os.path.realpath(p)
                        man = list(tags.get_manual(rp) or [])
                        if any(t in drop for t in man):
                            tags.set(rp, [t for t in man if t not in drop])     # 사람이 붙인 다른 태그는 그대로
            n += 1
    store.con.commit()
    store.meta_set(LANG_FIX_KEY, 1)
    return n


def relocate_cards(store, pairs) -> int:
    """앱의 이름 바꾸기·옮기기(`filesRelocated`) 뒤 — 명함 DB 의 경로를 새 경로로(§5.7). 명함 DB 에 없는 경로는 건너뛴다.
    반환 = 고친 짝 수."""
    from viewer.bizcard.relocate import relocate_db
    paths = set()
    for r in store.con.execute("SELECT front, back, src_key FROM cards").fetchall():
        paths.update(x for x in (r["front"], r["back"], r["src_key"]) if x)
    n = 0
    for old, new in pairs:
        if not old or not new:
            continue
        o = _nk(old)
        if o in paths or any(p.startswith(o + os.sep) for p in paths):
            relocate_db(store, old, new)
            n += 1
    return n
