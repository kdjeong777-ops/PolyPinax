"""명함찾기 창의 Qt 없는 부분 (명함 SOT §5.9 P4) — 찾기, 인물 사진, 이름 바꾼 뒤 명함 DB 따라가기.

★ 명함 글·경로는 로그·예외 메시지에 싣지 않는다(§2.1).
"""
from __future__ import annotations

import json
import os
import re
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


# ── 인물 사진 ──
def people_dir(front) -> Path:
    return Path(front).parent.parent / PEOPLE_DIR


def person_photos(front) -> list:
    """정리본 이름과 같은(또는 ` (n)` 붙은) 인물 사진들 — 이름 차례."""
    if not front:
        return []
    d = people_dir(front)
    stem = Path(front).stem
    pat = re.compile(r"^%s( \(\d+\))?$" % re.escape(stem), re.I)
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return []
    return [str(d / n) for n in names
            if os.path.splitext(n)[1].lower() in R.IMG_EXTS and pat.match(os.path.splitext(n)[0])]


def next_photo_path(front) -> Path:
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
