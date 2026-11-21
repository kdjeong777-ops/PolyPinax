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


KINDS = ("all", "ko", "en", "card", "nocard", "photo", "nophoto", "kakao")   # kakao = 카톡 친구추가 방지(§5.29, 261121)   # 찾기 칸 앞 구분(명함 SOT §5.24.1, 사용자 지시 261119·261120-24)
KIND_GROUPS = (("all",), ("ko", "en"), ("card", "nocard"), ("photo", "nophoto"), ("kakao",))   # 콤보에서 묶음 사이 구분선(언어/명함/사진)


def photo_ids(cards, folder="") -> set:
    """인물 사진이 있는 명함 id — '인물' 폴더는 폴더마다 한 번만 읽는다(명함마다 파일을 찾지 않게, §5.24.1 '구분')."""
    listing, out = {}, set()
    for c in cards:
        pf = photo_front(c, folder)
        if not pf:
            continue
        d = people_dir(pf)
        if d not in listing:
            names = set()
            try:
                for n in os.listdir(d):
                    st, ext = os.path.splitext(n)
                    if ext.lower() in R.IMG_EXTS:
                        names.add(re.sub(r" \(\d+\)$", "", st).lower())
            except OSError:
                pass
            listing[d] = names
        if Path(pf).stem.lower() in listing[d]:
            out.add(c["id"])
    return out
_HANGUL = re.compile(r"[가-힣ㄱ-ㆎ]")
_LATIN = re.compile(r"[A-Za-z]")


def kind_ok(card: dict, kind: str, photos=None, blocked=None) -> bool:
    """구분 — 'ko' = 이름에 한글, 'en' = 이름이 영어(로마자, 한글 없음), 'card' = 명함 그림 있음, 'nocard' = 그림 없는 주소록 명함,
    'photo'·'nophoto' = 인물 사진 있음·없음(photos = `photo_ids` 결과)."""
    if kind == "kakao":                               # 카톡 친구추가 방지 표시(blocked = gsync.blocked_ids)
        return card.get("id") in (blocked or set())
    if kind in ("photo", "nophoto"):
        has = card.get("id") in (photos or set())
        return has if kind == "photo" else not has
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


def norm_kinds(kinds) -> list:
    """구분 여러 개(261120-49) — 글 하나(종전 meta)·목록 모두 받아 아는 값만, 비었거나 'all' 이 있으면 ['all']."""
    if isinstance(kinds, str):
        kinds = [kinds]
    out = [k for k in dict.fromkeys(kinds or []) if k in KINDS]
    return ["all"] if not out or "all" in out else out


def kinds_ok(card: dict, kinds, photos=None, blocked=None) -> bool:
    """구분 여러 개 — 같은 묶음(`KIND_GROUPS`) 안은 또는, 묶음끼리는 그리고(사용자 결정 261121, §5.24.1 '구분')."""
    ks = norm_kinds(kinds)
    if ks == ["all"]:
        return True
    for grp in KIND_GROUPS:
        mine = [k for k in ks if k in grp]
        if mine and not any(kind_ok(card, k, photos, blocked) for k in mine):
            return False
    return True


def _tagkey(t) -> str:
    return re.sub(r"\s+", "", str(t or "")).lstrip("#").lower()


def auto_retag(tags, old_cards, name: str, company: str):
    """앱이 붙인 해시태그(§5.5 — #명함·#회사·언어 하나)를 새 이름·회사로 다시 맞춘다(261120-53 — 회사명이 바뀌는 모든 길이 이것 하나).
    old_cards = 그 값을 갖던 명함들(합치기면 여럿) — 그 회사들의 태그(법인 꼴을 뗀 것·원래 글, 공백·대소문자 무시)와 언어 태그를 걷는다.
    반환 (새 태그 목록, 걷은 옛 자동 태그 집합 — 정리본 파일 태그 맞춤 `_retag` 용). 사람이 붙인 태그는 그대로."""
    from viewer.bizcard.apply import tags_for, LANG_TAGS
    from viewer.bizcard.recognize import strip_corp
    tags = [t for t in (tags or []) if str(t).strip()]
    langs = [t for t in tags if t in LANG_TAGS]
    new_auto = tags_for({"name": name or "", "company": company or "", "langs": langs, "langs_ordered": False})
    old_keys, old_forms = {_tagkey(t) for t in LANG_TAGS}, set()
    for c in old_cards or []:
        co = str(c.get("company") or "")
        if co.strip():
            old_forms |= {co.strip(), strip_corp(co)}
    old_keys |= {_tagkey(f) for f in old_forms if f}
    new_keys = {_tagkey(t) for t in new_auto}
    old_auto = {t for t in tags if _tagkey(t) in old_keys and _tagkey(t) not in new_keys}
    old_auto |= {f for f in old_forms if f and _tagkey(f) not in new_keys}   # 정리본 파일에만 남은 옛 꼴도 걷게
    old_auto |= set(LANG_TAGS) - set(new_auto)
    out = list(dict.fromkeys(list(new_auto) + [t for t in tags if t not in old_auto and _tagkey(t) not in new_keys]))
    return out, old_auto


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
    if "phones" in fields:                              # 번호 종류 바로잡기 — 전화를 쓰는 모든 길이 여기(§5.11, 261120-55)
        fields = fix_phone_fields(fields, row.get("memo") or "")
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


def fix_phone_fields(fields: dict, memo: str = "") -> dict:
    """fields 의 phones 를 `phone.fix_kinds` 로 — 빠진 옛 휴대폰은 메모(fields 의 memo, 없으면 지금 메모) 끝 줄로."""
    from viewer.bizcard import phone as PH
    ph, old = PH.fix_kinds(fields.get("phones") or [])
    out = dict(fields, phones=ph)
    if old:
        out["memo"] = PH.memo_with_old(fields.get("memo", memo), old)
    return out


KINDS_FIXED_KEY = "phone_kinds_fixed"


def fix_kinds_all(store, backup_path: str = "") -> int:
    """이미 있는 명함 DB 의 번호 종류를 한 번 바로잡는다(§5.11 '번호 종류 바로잡기', 261120-55 — 배경에서, 자기 연결로).
    바꿀 것이 있으면 먼저 backup_path 로 DB 백업(SQLite 온라인 백업). 반환 = 바꾼 명함 수. 끝나면 meta 에 표시."""
    from viewer.bizcard import phone as PH
    todo = []
    for r in store.con.execute("SELECT * FROM cards").fetchall():
        c = store._row(r)
        ph, old = PH.fix_kinds(c.get("phones") or [])
        if old or [tuple(x) for x in ph] != [tuple(x) for x in c.get("phones") or []]:
            todo.append(c)
    if todo and backup_path:
        import sqlite3 as _sq
        dst = _sq.connect(backup_path)
        try:
            store.con.backup(dst)
        finally:
            dst.close()
    for c in todo:
        update_card(store, c["id"], {"phones": c.get("phones") or []}, commit=False)   # 고친 시각이 새로 — 구글 싱크가 구글로
    store.meta_set(KINDS_FIXED_KEY, time.time())
    store.con.commit()
    return len(todo)


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
    notes_init(store)                                  # 할 일 기록(§5.24.10, 261120-34) — 옛 할 일 내용은 첫 기록으로
    store.con.commit()


# ── 할 일 기록 (§5.24.10 '기록'·'줄', 261120-34·-39) — 할 일 탭마다 여러 기록, 기록 = 줄 목록·해시태그, 고치면 새 기록 ──
NOTE_COLS = (("items", "TEXT DEFAULT ''"),)          # 줄 목록 [{done, due, text}] JSON(261120-39) — 옛 기록은 비어 있음


def notes_table(store) -> None:
    store.con.execute("CREATE TABLE IF NOT EXISTS todo_notes(id INTEGER PRIMARY KEY, group_id INTEGER, made TEXT, body TEXT, "
                      "done INTEGER DEFAULT 0, n_start TEXT DEFAULT '', n_end TEXT DEFAULT '', tags TEXT DEFAULT '[]', "
                      "ts REAL DEFAULT 0)")
    have = {r[1] for r in store.con.execute("PRAGMA table_info(todo_notes)")}
    for col, typ in NOTE_COLS:
        if col not in have:
            store.con.execute("ALTER TABLE todo_notes ADD COLUMN %s %s" % (col, typ))


def notes_init(store) -> None:
    notes_table(store)
    rows = store.con.execute("SELECT g.id, g.t_memo, g.t_start, g.t_end FROM fav_groups g WHERE g.todo=1 "
                             "AND IFNULL(g.t_memo, '') != '' AND NOT EXISTS (SELECT 1 FROM todo_notes n WHERE n.group_id = g.id)"
                             ).fetchall()
    for r in rows:                                     # 옛 할 일 — 내용을 첫 기록으로(한 번만)
        store.con.execute("INSERT INTO todo_notes(group_id, made, body, n_start, n_end, ts) VALUES(?,?,?,?,?,?)",
                          (r["id"], r["t_start"] or "", r["t_memo"], r["t_start"] or "", r["t_end"] or "", 0))


ITEM_MARK = {True: "☑", False: "☐"}
_ITEM_RE = re.compile(r"^\s*([☐☑])\s*(\d{4}-\d{2}-\d{2})\s*(.*)$")


def items_text(items) -> str:
    """줄 목록 → 글(탭 '내용'·엑셀·할 일 고치기 창) — 줄마다 '☐ 2026-11-21 글'."""
    return "\n".join("%s %s %s" % (ITEM_MARK[bool(i.get("done"))], i.get("due") or "", i.get("text") or "")
                     for i in items or [] if (i.get("text") or "").strip())


def items_from_text(text: str, default_due: str, done: bool = False) -> list:
    """글 → 줄 목록 — '☐/☑ 날짜 글' 꼴이면 그대로 읽고, 아니면 한 줄이 한 항목(체크 done·날짜 default_due). 빈 줄 버림."""
    out = []
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        m = _ITEM_RE.match(line)
        if m:
            out.append({"done": m.group(1) == "☑", "due": m.group(2), "text": m.group(3).strip()})
        else:
            out.append({"done": bool(done), "due": default_due, "text": line.strip()})
    return out


def todo_notes(store, gid: int) -> list:
    """그 할 일의 기록 — 최신이 처음. [{id, made, body, items, tags}]. 줄 목록이 없는 옛 기록(-34 꼴)은 내용의 줄마다 한 항목
    (체크 = 옛 '했음', 날짜 = 옛 끝 날짜·없으면 시작·수정일 — §5.24.10 '옛 할 일')."""
    notes_table(store)
    out = []
    for r in store.con.execute("SELECT * FROM todo_notes WHERE group_id=? ORDER BY ts DESC, id DESC", (gid,)).fetchall():
        try:
            tags = json.loads(r["tags"] or "[]")
        except ValueError:
            tags = []
        try:
            items = json.loads(r["items"]) if r["items"] else None
        except ValueError:
            items = None
        if items is None:
            items = items_from_text(r["body"] or "", r["n_end"] or r["n_start"] or r["made"] or "", bool(r["done"]))
        out.append({"id": r["id"], "made": r["made"] or "", "body": r["body"] or "", "items": items, "tags": list(tags)})
    return out


def _sync_memo(store, gid: int) -> None:
    """탭 '내용'(t_memo) = 최신 기록의 내용(할 일 고치기 창·엑셀이 본다)."""
    r = store.con.execute("SELECT body FROM todo_notes WHERE group_id=? ORDER BY ts DESC, id DESC LIMIT 1", (gid,)).fetchone()
    store.con.execute("UPDATE fav_groups SET t_memo=? WHERE id=?", (r["body"] if r else "", gid))


def note_add(store, gid: int, note: dict, today: str) -> int:
    """새 기록(맨 앞) — 고친 기록은 그대로 둔다. note = {items, tags}(또는 옛 꼴 body). 내용 글은 줄 목록에서. 반환 = 새 id."""
    notes_table(store)
    items = note.get("items")
    if items is None:
        items = items_from_text(note.get("body") or "", today)
    items = [{"done": bool(i.get("done")), "due": i.get("due") or today, "text": (i.get("text") or "").strip()}
             for i in items if (i.get("text") or "").strip()]
    nid = store.con.execute(
        "INSERT INTO todo_notes(group_id, made, body, items, tags, ts) VALUES(?,?,?,?,?,?)",
        (gid, today, items_text(items), json.dumps(items, ensure_ascii=False),
         json.dumps(list(note.get("tags") or []), ensure_ascii=False), time.time())).lastrowid
    _sync_memo(store, gid)
    store.con.commit()
    return nid


def note_delete(store, nid: int) -> None:
    r = store.con.execute("SELECT group_id FROM todo_notes WHERE id=?", (nid,)).fetchone()
    if r is None:
        return
    store.con.execute("DELETE FROM todo_notes WHERE id=?", (nid,))
    _sync_memo(store, r["group_id"])
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


# ── 수정일·메모 기록 (§5.24.1 '수정일'·§5.9 '메모 기록', 261120-25·-26·-27) ──
EDIT_KEYS = ("name", "company", "dept", "title", "address", "phones", "emails", "urls")   # 수정일을 바꾸는 칸(메모 아님)
MEMO_LOG_KEY = "memo_log"            # meta — 메모에 고친 날짜·칸 기록(처음 켬)
MEMO_DATE_KEY = "memo_date"          # meta — 메모를 쓰기 시작하면 오늘 날짜(처음 켬)


def edited_init(store) -> None:
    """cards 에 `edited`(사람이 칸을 고친 날 YYYY-MM-DD) 열 — 옛 DB 에는 더한다(옛 판은 모른다). 빈 값 = 고친 적 없음(스캔일)."""
    have = {r[1] for r in store.con.execute("PRAGMA table_info(cards)")}
    if "edited" not in have:
        store.con.execute("ALTER TABLE cards ADD COLUMN edited TEXT DEFAULT ''")
        store.con.commit()


def shown_date(card) -> str:
    """목록 '수정일' 칸 — 고친 날, 없으면 스캔일."""
    return (card.get("edited") or card.get("scanned") or "")


def memo_opt(store, key: str) -> bool:
    v = store.meta_get(key) if store is not None else None
    return True if v is None else bool(v)


def set_memo_opt(store, key: str, on: bool) -> None:
    store.meta_set(key, bool(on))


def changed_keys(old: dict, new: dict) -> list:
    """메모 밖 칸 중 바뀐 것 — 전화는 종류(cell·work·fax)마다 따로. 차례는 세부 칸 차례."""
    out = []
    for k in EDIT_KEYS:
        if k == "phones":
            o = {kind: [n for kk, n in (old.get("phones") or []) if kk == kind] for kind in ("cell", "work", "fax")}
            n = {kind: [x for kk, x in (new.get("phones") or []) if kk == kind] for kind in ("cell", "work", "fax")}
            out += [kind for kind in ("cell", "work", "fax") if o[kind] != n[kind]]
        elif k in ("emails", "urls"):
            if list(old.get(k) or []) != list(new.get(k) or []):
                out.append("email" if k == "emails" else "url")
        elif (old.get(k) or "") != (new.get(k) or ""):
            out.append(k)
    return out


def memo_with_log(memo: str, today: str, labels: list, word: str) -> str:
    """메모 맨 위에 `[오늘 수정] 칸·칸` — 같은 날 줄이 맨 위에 있으면 그 줄에 칸을 더한다(겹치지 않게). 옛 값은 남기지 않는다(§2.1)."""
    memo = memo or ""
    lines = memo.split("\n")
    m = re.match(r"^\[(\d{4}-\d{2}-\d{2}) %s\] (.*)$" % re.escape(word), lines[0]) if lines else None
    if m and m.group(1) == today:
        have = [x for x in m.group(2).split("·") if x]
        lines[0] = "[%s %s] %s" % (today, word, "·".join(have + [x for x in labels if x not in have]))
        return "\n".join(lines)
    head = "[%s %s] %s" % (today, word, "·".join(labels))
    return head + ("\n" + memo if memo.strip() else "")


TODO_STATES = ("live", "soon", "past", "closed")   # 기간 안 · 시작 전 · 기간 지남 · 마감(D28)


def _latest_note(store, gid: int):
    """최신 할 일 기록(§5.24.10) — 없거나 기록 표를 못 읽으면 None."""
    try:
        notes = todo_notes(store, gid)
    except sqlite3.OperationalError:
        return None
    return notes[0] if notes else None


def _todo_state(r, today: str) -> str:
    if r["closed"]:
        return "closed"
    if (r["t_start"] or "") > today:
        return "soon"
    if r["t_end"] and today > r["t_end"]:
        return "past"
    return "live"


def tab_export(store, gid: int, today: str):
    """탭 하나 내보낼 자료(§5.24.2 '할 일 내보내기', 261120-42) — {name, todo, members[명함 행]} + 할 일 탭이면
    {start, end, state, tags(최신 기록), notes[{made, items}] 최신 먼저}. 없는 탭은 None."""
    r = store.con.execute("SELECT * FROM fav_groups WHERE id=?", (gid,)).fetchone()
    if r is None:
        return None
    out = {"name": r["name"] or "", "todo": bool(r["todo"]), "members": fav_members(store, gid)}
    if not r["todo"]:
        return out
    try:
        notes = todo_notes(store, gid)
    except sqlite3.OperationalError:
        notes = []
    if not notes and (r["t_memo"] or "").strip():      # 기록 표가 생기기 전 옛 할 일 — 내용을 한 기록으로
        notes = [{"made": r["t_start"] or "", "items": items_from_text(r["t_memo"], r["t_end"] or r["t_start"] or today),
                  "tags": []}]
    out.update({"start": r["t_start"] or "", "end": r["t_end"] or "", "state": _todo_state(r, today),
                "tags": list(notes[0]["tags"]) if notes else [],
                "notes": [{"made": n["made"], "items": list(n["items"])} for n in notes]})
    return out


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
    if info.get("memo"):                               # 처음 내용 = 첫 기록(§5.24.10)
        try:
            notes_table(store)                         # 표만 — 옛 할 일 옮기기(notes_init)는 이 할 일을 두 번 넣는다
            import datetime
            note_add(store, gid, {"body": info["memo"], "start": info.get("start") or "", "end": info.get("end") or ""},
                     datetime.date.today().isoformat())
        except sqlite3.OperationalError:
            pass
    fav_add(store, gid, card_ids, ongoing=ongoing)
    return gid


def todo_update(store, gid: int, info: dict) -> None:
    """할 일 고치기 — 제목(탭 이름)·내용·기간. 메모는 다시 쓰지 않는다. 내용이 바뀌면 새 기록(§5.24.10 — 내용 = 최신 기록)."""
    old = todo_info(store, gid)
    store.con.execute("UPDATE fav_groups SET name=?, t_memo=?, t_start=?, t_end=? WHERE id=? AND todo=1",
                      (info["title"], info.get("memo") or "", info.get("start") or "", info.get("end") or "", gid))
    store.con.commit()
    if old is not None and (info.get("memo") or "") != (old.get("memo") or ""):
        import datetime
        last = (todo_notes(store, gid) or [{}])[0]
        today = datetime.date.today().isoformat()
        note_add(store, gid, {"items": items_from_text(info.get("memo") or "", today), "tags": last.get("tags") or []}, today)


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
    try:
        store.con.execute("DELETE FROM todo_notes WHERE group_id=?", (gid,))   # 할 일 기록도(§5.24.10)
    except sqlite3.OperationalError:
        pass
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
    recent_prune(store, commit=False)              # 항목 제한(§5.24.2 '최근 탭', 261120-18)
    store.con.commit()


# 항목 제한 — 명함 DB meta `recent_limit` = {mode: count|days, n}. 넘는 기록은 지운다(명함은 그대로)
RECENT_LIMIT_KEY = "recent_limit"
RECENT_LIMIT_DEFAULT = {"mode": "count", "n": 20}


def recent_limit(store) -> dict:
    v = store.meta_get(RECENT_LIMIT_KEY, None)
    if isinstance(v, dict) and v.get("mode") in ("count", "days"):
        try:
            n = int(v.get("n"))
        except (TypeError, ValueError):
            n = 0
        if n > 0:
            return {"mode": v["mode"], "n": n}
    return dict(RECENT_LIMIT_DEFAULT)


def set_recent_limit(store, mode: str, n: int) -> int:
    """제한을 정하고 곧바로 넘는 기록을 지운다 — 지운 수."""
    store.meta_set(RECENT_LIMIT_KEY, {"mode": mode if mode in ("count", "days") else "count", "n": max(1, int(n))})
    return recent_prune(store)


def _has_recent(store) -> bool:
    return store.con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='recent'").fetchone() is not None


def recent_prune(store, today=None, commit: bool = True) -> int:
    """제한을 넘는 '최근' 기록을 지운다 — 개수면 최근에 본 n 개만, 기간이면 오늘부터 n 일 안(오늘 포함)만. 지운 수."""
    import datetime
    if not _has_recent(store):                      # 즐겨찾기 표(fav_init) 전의 새 DB — 지울 것이 없다
        return 0
    lim = recent_limit(store)
    if lim["mode"] == "days":
        today = today or datetime.date.today()
        since = (today - datetime.timedelta(days=lim["n"] - 1)).isoformat()
        cur = store.con.execute("DELETE FROM recent WHERE substr(seen, 1, 10) < ?", (since,))
    else:
        cur = store.con.execute(
            "DELETE FROM recent WHERE rowid NOT IN (SELECT rowid FROM recent ORDER BY seen DESC, rowid DESC LIMIT ?)",
            (lim["n"],))
    if commit:
        store.con.commit()
    return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0


def recent_clear(store) -> int:
    """'최근' 기록을 모두 지운다(명함은 그대로, §5.24.2 '모두 삭제', 261120-19) — 지운 수."""
    if not _has_recent(store):
        return 0
    cur = store.con.execute("DELETE FROM recent")
    store.con.commit()
    return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0


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
def email_list(cards, first_only: bool = True) -> tuple:
    """고른 명함들의 메일 주소(같은 주소 한 번) + 메일 없는 명함 수 (명함 SOT §5.24.1 '이메일 복사').
    first_only = 사람마다 첫 메일 하나만(261120-32, 사용자 결정 '보내기·복사 모두'), False 면 여럿이면 모두."""
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
            if first_only:
                break
        if not got:
            missing += 1
    return out, missing


def emails_text(cards) -> str:
    return ", ".join(email_list(cards)[0])


MAIL_FIELD_KEY = "mail_field"        # 메일 보내기 받는 칸 'to'·'bcc' — 명함 환경설정에서 고르고 기억(§5.24.9, 261120-33)


# ── Gmail 보내기 (명함 SOT §5.24.1 'Gmail 보내기', 사용자 결정 261120) — 브라우저 쓰기 창 주소만, 네트워크 없음(§2.1) ──
GMAIL_COMPOSE = "https://mail.google.com/mail/?view=cm&fs=1"
GMAIL_URL_MAX = 2000                # 주소 한 개 최대 길이 — 넘으면 쓰기 창을 나눠 연다


def gmail_urls(emails, field: str = "to", account: str = "", limit: int = GMAIL_URL_MAX) -> list:
    """Gmail 쓰기 창 주소들 — field('to'·'bcc') 칸에 주소를 넣고, 한 주소가 limit 를 넘지 않게 차례대로 나눈다.
    account(보낼 구글 계정)가 있으면 authuser 로. 주소가 하나도 없으면 []."""
    from urllib.parse import quote
    base = GMAIL_COMPOSE + ("&authuser=" + quote(account.strip(), safe="@") if (account or "").strip() else "")
    return _chunk_urls("%s&%s=" % (base, field), emails, limit)


# 기본 메일 앱(mailto, RFC 6068) — PC 에 정한 메일 프로그램이 연다(§5.24.1 '메일 보내기', 261120-23)
NAVER_MAIL = "https://mail.naver.com/"      # 네이버는 받는 사람을 채운 쓰기 창 주소를 공개하지 않는다 — 주소 복사 + 메일 화면만


def mailto_urls(emails, field: str = "to", limit: int = GMAIL_URL_MAX) -> list:
    """mailto 주소들 — 받는 사람은 `mailto:a,b`, 숨은 참조는 `mailto:?bcc=a,b`. 길면 차례대로 나눈다."""
    return _chunk_urls("mailto:" if field == "to" else "mailto:?bcc=", emails, limit)


def _chunk_urls(head: str, emails, limit: int) -> list:
    """head 뒤에 주소를 쉼표로 잇되 한 주소가 limit 를 넘지 않게 나눈다(빈 목록 = [])."""
    from urllib.parse import quote
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
        if src:   # 전화 칸 출처도 — 이름 등을 손으로 고쳐도(그 칸 출처만 지움) 어느 주소록에서 왔는지 남는다(구글 싱크 §5.29 '새 사람', 261120-46)
            _set_srcs(store, nid, [k for k in _SCALARS if (p.get(k) or "").strip()] + (["phones"] if p.get("phones") else []), src)
        added += 1
    store.con.commit()
    return added


def _insert_contact(store, p: dict, tags) -> int:
    """그림 없는 명함 한 장(front `contact:<번호>`)을 넣고 찾기 색인까지 — 새 id. 커밋은 부르는 쪽이."""
    import uuid
    from viewer.bizcard.vcard import CONTACT_PREFIX
    p = fix_phone_fields(p, p.get("memo") or "")          # 번호 종류 바로잡기(261120-55)
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


MOBILE_PREFIX = ("010", "011", "016", "017", "018", "019")


def _mobile_keys(card) -> list:
    """휴대폰 번호만 — 회사 대표 번호·팩스는 여럿이 같이 쓴다(사용자 보고 261119). 국내는 **010 꼴만**(+82·앞 0 빠짐도 국내 꼴로 —
    종류 칸이 '휴대폰'으로 잘못 든 일반 번호·옛 011·016~019 는 뺀다, 261120-48 덧고침·-55), 외국은 + 로 시작하고 종류가 휴대폰일 때만.
    판정은 `phone.mobile_key` 한 곳(구글 싱크 짝 맞추기도)."""
    from viewer.bizcard import phone as PH
    out = []
    for x in card.get("phones") or []:
        kind, num = (x[0], x[-1]) if isinstance(x, (list, tuple)) and len(x) >= 2 else ("", x)
        k = PH.mobile_key(kind, num)
        if len(k) >= 9:
            out.append(k)
    return out


def _same_person_name(a, b) -> bool:
    """이름이 같거나 한쪽이 비었으면 True — 이름이 다르면 같은 휴대폰일 때만 같은 사람으로 본다."""
    na, nb = _nname(a.get("name")), _nname(b.get("name"))
    return not na or not nb or na == nb


def one_off(a: str, b: str) -> bool:
    """숫자 수가 같고 한 자리만 다른 번호(오타 의심)."""
    return len(a) == len(b) and a != b and sum(x != y for x, y in zip(a, b)) == 1


def mobile_typo(a: str, b: str) -> bool:
    """휴대폰 오타 거리 — 한 자리만 다름, 또는 이웃한 두 자리가 자리바뀜(§5.24.8 '묶기', 사용자 결정 261121, 261120-48)."""
    if one_off(a, b):
        return True
    if len(a) != len(b) or a == b:
        return False
    d = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    return len(d) == 2 and d[1] == d[0] + 1 and a[d[0]] == b[d[1]] and a[d[1]] == b[d[0]]


def _mobiles_near(A, B) -> bool:
    return any(x == y or mobile_typo(x, y) for x in A for y in B)


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
    이유 = 'phone'·'mail'(확실) · 'typo'(이름 같고 휴대폰 오타 거리) · 'namecomp'(이름+회사 같음).
    휴대폰만 사람을 가른다 — 일반 전화·팩스는 평가에서 빼고, 휴대폰이 서로 다른 묶음끼리는 잇지 않는다(261120-48)."""
    order = order or dupe_order(store)
    cards = [store._row(r) for r in store.con.execute("SELECT * FROM cards").fetchall()]
    byid = {c["id"]: c for c in cards}
    par, spar, edges = {}, {}, {}
    mob = {c["id"]: set(_mobile_keys(c)) for c in cards}
    cm = dict((k, set(v)) for k, v in mob.items())         # 묶음 뿌리 → 그 묶음의 휴대폰들

    def find(p, x):
        while p.setdefault(x, x) != x:
            p[x] = p[p[x]]
            x = p[x]
        return x

    mkey = {}                                               # 명함 → 묶인 휴대폰(이유 풍선 도움말, 261120-55)

    def link(a, b, why, key=""):
        if a == b:
            return
        ra, rb = find(par, a), find(par, b)
        if ra != rb and why != "phone" and cm.get(ra) and cm.get(rb) and not _mobiles_near(cm[ra], cm[rb]):
            return                                          # 휴대폰이 서로 다르면 다른 사람 — 이름·회사·메일이 같아도
        if ra != rb:
            par[ra] = rb
            cm[rb] = cm.get(rb, set()) | cm.pop(ra, set())
        if why in WHY_SURE:
            spar[find(spar, a)] = find(spar, b)
        for x, y in ((a, b), (b, a)):
            old = edges.get(x, {}).get(y)
            if old is None or _WHY_RANK[why] < _WHY_RANK[old]:
                edges.setdefault(x, {})[y] = why
            if key and (x not in mkey or why == "phone"):
                mkey[x] = key

    # ① 같은 휴대폰 = 같은 사람(이름이 달라도 — 이름을 잘못 읽었을 수 있다). 일반 전화·팩스는 여럿이 같이 써서 평가에서 뺀다
    # (사용자 지시 261121, 261120-48). 메일은 이름이 같을(또는 한쪽이 빈) 때만 — 아래 ③, 휴대폰이 다르면 link 가 막는다.
    bucket, mails = {}, {}
    for c in cards:
        for k in mob[c["id"]]:
            bucket.setdefault(k, []).append(c)
        for e in {str(e).strip().lower() for e in c.get("emails") or [] if str(e).strip()}:
            mails.setdefault(e, []).append(c)
    for k, same in bucket.items():
        for b in same[1:]:
            link(same[0]["id"], b["id"], "phone", k)
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
                hit = next((x for x in ka for y in _mobile_keys(b) if mobile_typo(x, y)), "")
                if hit:
                    link(a["id"], b["id"], "typo", hit)
    for same in mails.values():
        for i, a in enumerate(same):
            for b in same[i + 1:]:
                if _same_person_name(a, b):
                    link(a["id"], b["id"], "mail")
    for same in by_nc.values():
        for i, a in enumerate(same):                       # 휴대폰이 다른 명함이 끼어도 나머지끼리 이을 수 있게 모든 짝
            for b in same[i + 1:]:
                link(a["id"], b["id"], "namecomp")
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
                    "match": {i: mkey[i] for i in ids if i in mkey},
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
            if not k or k in keys or (mob and any(mobile_typo(k, x) for x in mobs)):   # 휴대폰끼리만 오타로 봄(회사 직통은 한 자리 차이가 흔함)
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
    fields["tags"] = auto_retag(list(dict.fromkeys(t for c in cards for t in c.get("tags") or [])), cards,
                                fields.get("name") or "", fields.get("company") or "")[0]   # 남지 않는 회사의 옛 태그는 걷음(261120-53)
    keeper = rep if not is_contact(rep) else next((c for c in cards if not is_contact(c)), rep)
    photo_from = None
    if not is_contact(keeper) and not person_photos(keeper.get("front")):
        photo_from = next((c["id"] for c in cards if c is not keeper and not is_contact(c) and person_photos(c.get("front"))), None)
    return {"keeper": keeper["id"], "fields": fields, "frm": frm,
            "drop": [c["id"] for c in cards if c["id"] != keeper["id"]], "photo_from": photo_from}


def merge_db(store, plan, extra: dict = None) -> None:
    """합친 값을 남길 행에, 지울 행의 즐겨찾기·할 일·최근 칸·구글 짝·카톡 표시는 남길 행으로, 주소록 출처는 칸마다 값을 준 명함의 것.
    extra = 창이 정한 front·back(이름을 바꾼 뒤). 그 뒤 지울 행을 지운다(파일은 창이 먼저 옮김)."""
    kid = plan["keeper"]
    srcs = {cid: field_srcs(store, cid) for cid in set(plan["frm"].values())}
    ph_src = next((s for s in (field_srcs(store, c).get("phones") for c in [kid] + list(plan["drop"])) if s), "")   # 전화는 모두 합침 — 첫 출처
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
                              [(kid, f, srcs[c][f]) for f, c in plan["frm"].items() if srcs.get(c, {}).get(f)]
                              + ([(kid, "phones", ph_src)] if ph_src else []))
    except sqlite3.OperationalError:
        pass
    from viewer.bizcard import gsync                        # 구글 짝·카톡 표시는 남는 명함으로(§5.29 '명함 합치기와 짝', 261120-46)
    gsync.merge_links(store, kid, plan["drop"])
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
