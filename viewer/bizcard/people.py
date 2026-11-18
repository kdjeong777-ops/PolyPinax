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
SEARCH_LIMIT = 500
_COLS = ("name", "company", "dept", "title", "memo", "address", "emails", "phones", "urls", "en")


def _nk(p) -> str:
    return os.path.normcase(os.path.abspath(str(p))) if p else ""


# ── 찾기 ──
def find(store, text: str = "", since: str = "", until: str = "", limit: int = SEARCH_LIMIT) -> list:
    """낱말 여럿(모두 들어 있어야) — 칸 글자 **일부**로(LIKE). `#낱말` 은 해시태그. 스캔일 범위 YYYY-MM-DD.
    반환 = 명함 DB 행(dict), 스캔일 최근 먼저, limit+1 장까지(넘쳤는지 부르는 쪽이 안다)."""
    hay = " || ' ' || ".join("IFNULL(%s,'')" % c for c in _COLS)
    where, args = [], []
    for t in (text or "").split():
        if t.startswith("#") and len(t) > 1:
            where.append("IFNULL(tags,'') LIKE ? ESCAPE '\\'")
            args.append('%"' + _like(t[1:]) + '%')
        else:
            where.append("(%s) LIKE ? ESCAPE '\\'" % hay)
            args.append("%" + _like(t) + "%")
    if since:
        where.append("IFNULL(scanned,'') >= ?"); args.append(since)
    if until:
        where.append("IFNULL(scanned,'') <= ?"); args.append(until + "￿")
    q = "SELECT * FROM cards" + (" WHERE " + " AND ".join(where) if where else "")
    q += " ORDER BY IFNULL(scanned,'') DESC, id DESC LIMIT %d" % (int(limit) + 1)
    return [store._row(r) for r in store.con.execute(q, args).fetchall()]


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
def update_card(store, card_id: int, fields: dict) -> None:
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
            v = _nk(v) if v else ""
        sets.append("%s=?" % k)
        args.append(v)
    sets.append("updated=?")
    args.append(time.time())
    store.con.execute("UPDATE cards SET %s WHERE id=?" % ", ".join(sets), args + [card_id])
    store.con.execute("DELETE FROM cards_fts WHERE rowid=?", (card_id,))
    store.con.execute("INSERT INTO cards_fts(rowid, body) VALUES(?,?)", (card_id, store._body(row)))
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
    if store.con.execute("SELECT COUNT(*) FROM fav_groups").fetchone()[0] == 0:
        store.con.execute("INSERT INTO fav_groups(name, pos) VALUES(?, 0)", (default_name,))
    store.con.commit()


def fav_groups(store) -> list:
    return [(r["id"], r["name"]) for r in store.con.execute("SELECT id, name FROM fav_groups ORDER BY pos, id")]


def fav_add_group(store, name: str) -> int:
    pos = store.con.execute("SELECT IFNULL(MAX(pos), -1) + 1 FROM fav_groups").fetchone()[0]
    gid = store.con.execute("INSERT INTO fav_groups(name, pos) VALUES(?, ?)", (name, pos)).lastrowid
    store.con.commit()
    return gid


def fav_rename_group(store, gid: int, name: str) -> None:
    store.con.execute("UPDATE fav_groups SET name=? WHERE id=?", (name, gid))
    store.con.commit()


def fav_delete_group(store, gid: int) -> bool:
    """탭 지우기 — 마지막 하나는 지우지 않는다(False). 명함은 그대로."""
    if store.con.execute("SELECT COUNT(*) FROM fav_groups").fetchone()[0] <= 1:
        return False
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


def fav_add(store, gid: int, card_ids) -> int:
    """지금 탭 끝에 — 이미 있으면 건너뜀. 반환 = 더한 수."""
    pos = store.con.execute("SELECT IFNULL(MAX(pos), -1) + 1 FROM fav_members WHERE group_id=?", (gid,)).fetchone()[0]
    n = 0
    for cid in card_ids:
        cur = store.con.execute("INSERT OR IGNORE INTO fav_members(group_id, card_id, pos) VALUES(?,?,?)", (gid, cid, pos + n))
        n += cur.rowcount
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
    """명함을 지울 때 — 모든 탭에서 그 칸을 뺀다."""
    store.con.executemany("DELETE FROM fav_members WHERE card_id=?", [(c,) for c in card_ids])
    store.con.commit()


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
def card_files(card: dict) -> tuple:
    """(원본 [앞·뒤·PDF], 정리본 [앞·뒤], 인물 사진) — 있는 파일만, 실제 경로. 원본은 원천 폴더를 다시 훑어 찾는다."""
    from viewer.bizcard.importer import scan_folder, PDF_DIR
    from viewer.bizcard.vcard import is_contact
    if is_contact(card):                        # 주소록에서 가져온 명함 — 파일 없음
        return [], [], []
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


# ── 주소록 가져오기 (§5.24 D22 — 같은 사람은 빈 칸만 채우고, 없는 사람은 그림 없는 명함으로) ──
_SCALARS = ("name", "company", "dept", "title", "address", "memo")


def _phone_key(num: str) -> str:
    from viewer.bizcard.vcard import digits
    d = digits(num)
    return d if len(d) >= 9 else ""


def import_plan(store, persons) -> list:
    """[(사람, 맞는 명함 id 또는 None)] — 휴대폰·전화 번호(숫자 9자리 이상) 또는 메일이 같으면 같은 사람.
    가져오는 파일 안에서 같은 사람이 또 나오면 앞의 것에 합친다(같은 '새 명함')."""
    by_phone, by_mail = {}, {}
    for r in store.con.execute("SELECT id, phones, emails FROM cards").fetchall():
        for x in json.loads(r["phones"] or "[]"):
            k = _phone_key(x[-1] if isinstance(x, list) else x)
            if k:
                by_phone.setdefault(k, r["id"])
        for e in json.loads(r["emails"] or "[]"):
            by_mail.setdefault(str(e).strip().lower(), r["id"])
    plan, new_of = [], {}
    for i, p in enumerate(persons):
        keys = [("t", _phone_key(n)) for _k, n in p.get("phones") or []] + [("m", e.strip().lower()) for e in p.get("emails") or []]
        keys = [k for k in keys if k[1]]
        cid = next((by_phone.get(v) if t == "t" else by_mail.get(v) for t, v in keys
                    if (by_phone.get(v) if t == "t" else by_mail.get(v))), None)
        if cid is None:
            cid = next((new_of[k] for k in keys if k in new_of), None)
        if cid is None:
            new_of.update({k: ("new", i) for k in keys})
        plan.append((p, cid))
    return plan


def import_counts(plan) -> tuple:
    """(합칠 사람 수, 새로 더할 사람 수)."""
    merged = sum(1 for _p, c in plan if isinstance(c, int))
    added = sum(1 for _p, c in plan if c is None)
    return merged, added


# 주소록 우선순위(§5.24 D24, 사용자 지시 '리멤버, 구글 주소록 순서로 우선') — 큰 수가 이긴다.
#   명함을 읽은 값·손으로 고친 값은 출처 없음(=None) — 주소록이 덮어쓰지 않고 빈 칸만 채운다.
SOURCE_RANK = {"google": 1, "remember": 2}
_OVERRIDE = ("name", "company", "dept", "title", "address")      # 메모는 덮어쓰지 않는다(빈 칸만)


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


def _merge_into(row: dict, p: dict, srcs: dict = None, src: str = "") -> tuple:
    """빈 칸은 채우고, 값이 다른 칸은 **앞 출처가 주소록이고 이번 주소록이 더 높을 때만** 바꾼다(리멤버 > 구글).
    번호·메일·누리집은 없는 것만 더함. 반환 = (바꿀 칸, 이번 출처로 적을 칸)."""
    srcs, rank = srcs or {}, SOURCE_RANK.get(src, 0)
    ch, mine = {}, []
    for k in _SCALARS:
        new = (p.get(k) or "").strip()
        old = (row.get(k) or "").strip()
        if not new or new == old:
            continue
        if not old:
            ch[k] = new
            mine.append(k)
        elif k in _OVERRIDE and srcs.get(k) in SOURCE_RANK and rank > SOURCE_RANK[srcs[k]]:
            ch[k] = new
            mine.append(k)
    have = {_phone_key(n) or n for _k, n in row.get("phones") or []}
    add = [(k, n) for k, n in p.get("phones") or [] if (_phone_key(n) or n) not in have]
    if add:
        ch["phones"] = list(row.get("phones") or []) + add
    for k in ("emails", "urls"):
        low = {x.lower() for x in row.get(k) or []}
        more = [x for x in p.get(k) or [] if x.lower() not in low]
        if more:
            ch[k] = list(row.get(k) or []) + more
    return ch, mine


def apply_import(store, plan, tag: str = "", src: str = "") -> tuple:
    """가져오기 적용 — (합친 명함 수, 더한 명함 수). 더하는 명함은 front 가 `contact:<번호>`(그림 없음).
    src = 'remember'·'google' — 칸마다 출처를 적어 두어 다음 가져오기의 우선순위를 가린다(D24)."""
    import uuid
    from viewer.bizcard.vcard import CONTACT_PREFIX
    src_init(store)
    merged, added = 0, 0
    made = {}                                       # 같은 파일 안 '새 사람' 의 첫 행 → id
    for i, (p, cid) in enumerate(plan):
        if isinstance(cid, tuple):                  # ("new", j) — 앞에서 더한 새 명함에 합침
            cid = made.get(cid[1])
        if cid is None:
            front = CONTACT_PREFIX + uuid.uuid4().hex
            now = time.time()
            tags = [t for t in ("명함", tag) if t]
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
            if src:
                _set_srcs(store, nid, [k for k in _SCALARS if (p.get(k) or "").strip()], src)
            store.con.commit()
            made[i] = nid
            added += 1
            continue
        row = card_by_id(store, cid)
        if row is None:
            continue
        ch, mine = _merge_into(row, p, field_srcs(store, cid), src)
        if ch:
            update_card(store, cid, ch)
        if src and mine:
            _set_srcs(store, cid, mine, src)
            store.con.commit()
        merged += 1
    return merged, added


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
