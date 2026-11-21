# -*- coding: utf-8 -*-
"""구글 주소록 싱크 — 짝 맞추기·계획·반영 (명함 SOT §5.29, 261120-36).

`plan(store, people, opts)` 는 네트워크 없이 계획만(구글 목록은 부르는 쪽이 받아 넘긴다) — 미리보기 창이 보이고 사람이 고른 것만
`apply(...)` 가 반영한다. 둘 다 배경 일꾼에서 부른다(응답성 SOT §4). 명함 값은 구글로만 오가고 로그·오류 글에 싣지 않는다(§2.1).
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime

from viewer.bizcard import people as P
from viewer.bizcard import phone as PH

SRC = "google"                                  # contact_src 출처·태그
TAG = "구글"
OPT_PHOTOS, OPT_DRIVE, OPT_FOLDER = "gsync_photos", "gsync_drive", "gsync_drive_folder"   # 명함 DB meta
DRIVE_FOLDER_DEFAULT = "PolyCardex 명함"
DEFAULT_PHOTO = "default"                       # 구글 사진의 기본 실루엣 표시(photos[].default)

# 계획 줄 갈래
NEW_CARD, NEW_GOOGLE, TO_CARD, TO_GOOGLE, GONE_GOOGLE, GONE_CARD, PHOTO_UP, PHOTO_DOWN, DRIVE_UP = (
    "new_card", "new_google", "to_card", "to_google", "gone_google", "gone_card", "photo_up", "photo_down", "drive_up")
KAKAO_UP, KAKAO_DOWN = "kakao_up", "kakao_down"     # 카톡 친구추가 방지(구글 이름 앞 '#') 바꿈 → 구글 · 구글 이름대로 표시 맞춤
MERGED_GOOGLE = "merged_google"                 # 명함 합치기로 남지 못한 짝의 구글 연락처 — 지울까요(§5.29 '명함 합치기와 짝', 261120-46)
LABELS, LABEL_GONE = "labels", "label_gone"     # 고른 해시태그 ↔ 구글 라벨 맞춤 · 고른 목록에서 뺀 라벨 — 지울까요(§5.29 '라벨', 261120-61)
KINDS = (NEW_CARD, NEW_GOOGLE, TO_CARD, TO_GOOGLE, GONE_GOOGLE, GONE_CARD, MERGED_GOOGLE, PHOTO_UP, PHOTO_DOWN, DRIVE_UP,
         KAKAO_UP, KAKAO_DOWN, LABELS, LABEL_GONE)
OPT_LABELS = "gsync_label_tags"                  # meta — 구글 라벨로 올릴 해시태그(명함 환경설정)
OPT_LABELS_OFF = "gsync_label_off"               # meta — 환경설정에서 끈 것(구글 라벨이어도 다시 넣지 않음)
META_LABEL_GROUPS = "gsync_label_groups"         # meta — 앱이 쓴 라벨 {이름: contactGroups/…}
OPT_KAKAO_NEW = "gsync_kakao_new"               # meta — 구글에 새로 보낼 때 친구추가 방지(처음 켬)
KAKAO_MARK = "#"
DEFAULT_ON = {k: k not in (GONE_GOOGLE, GONE_CARD, LABEL_GONE) for k in KINDS}    # 지워짐은 기본 '남김'(§5.29 '지운 것'), 합쳐져 남음은 켬(사용자 결정 261121)
GOOGLE_WRITES = (NEW_GOOGLE, TO_GOOGLE, GONE_CARD, MERGED_GOOGLE, KAKAO_UP, PHOTO_UP, DRIVE_UP, LABELS, LABEL_GONE)   # 구글 쪽을 바꾸는 갈래 — 미리보기의 백업 권함


def row_default(r: dict) -> bool:
    """미리보기 처음 체크 — 출처가 구글인 명함의 '구글로 보냄' 은 끔(구글에 이미 있을 수 있음, 사용자 결정 261121)."""
    return False if r.get("maybe_dup") else DEFAULT_ON.get(r["kind"], True)

_G2C = {"mobile": "cell", "workFax": "fax", "homeFax": "fax", "otherFax": "fax"}
_C2G = {"cell": "mobile", "fax": "workFax", "work": "work"}


def init(store) -> None:
    store.con.execute("CREATE TABLE IF NOT EXISTS kakao_block(card_id INTEGER PRIMARY KEY, block INTEGER, set_at REAL)")
    store.con.execute("CREATE TRIGGER IF NOT EXISTS kakao_block_del AFTER DELETE ON cards "
                      "BEGIN DELETE FROM kakao_block WHERE card_id = OLD.id; END")
    store.con.execute("CREATE TABLE IF NOT EXISTS google_link(card_id INTEGER PRIMARY KEY, resource_name TEXT UNIQUE, "
                      "etag TEXT, synced REAL, photo_sig TEXT DEFAULT '', drive TEXT DEFAULT '')")
    if "front" not in {r[1] for r in store.con.execute("PRAGMA table_info(google_link)")}:
        store.con.execute("ALTER TABLE google_link ADD COLUMN front TEXT DEFAULT ''")   # 짝지은 명함의 열쇠 — 같은 id 를 다시 받은 새 명함과 가름
    if "merged" not in {r[1] for r in store.con.execute("PRAGMA table_info(google_link)")}:
        store.con.execute("ALTER TABLE google_link ADD COLUMN merged INTEGER DEFAULT 0")   # 합치기로 남지 못한 짝 — 남은 명함 id
    if "labels" not in {r[1] for r in store.con.execute("PRAGMA table_info(google_link)")}:
        store.con.execute("ALTER TABLE google_link ADD COLUMN labels TEXT DEFAULT '[]'")   # 지난 싱크 때 고른 라벨(261120-61)
    # 명함 파일 이름이 바뀌면(이름 바꾸기·옮기기·합치기) 짝의 열쇠도 따라감 — 어느 길이든 한 곳(261120-46)
    store.con.execute("CREATE TRIGGER IF NOT EXISTS google_link_front AFTER UPDATE OF front ON cards WHEN OLD.front IS NOT NEW.front "
                      "BEGIN UPDATE google_link SET front = NEW.front WHERE card_id = NEW.id AND front = OLD.front; END")
    store.con.commit()


def links(store) -> dict:
    init(store)
    return {r[0]: {"rn": r[1], "etag": r[2], "synced": r[3] or 0.0, "photo_sig": r[4] or "", "drive": json.loads(r[5] or "{}"),
                   "front": r[6] or "", "merged": r[7] or 0, "labels": json.loads(r[8] or "[]")}
            for r in store.con.execute("SELECT card_id, resource_name, etag, synced, photo_sig, drive, front, merged, labels FROM google_link")}


def _link_put(store, cid: int, rn: str, etag: str, **kw) -> None:
    old = links(store).get(cid) or {}
    row = store.con.execute("SELECT front FROM cards WHERE id=?", (cid,)).fetchone()
    keep_labels = old.get("labels", []) if old.get("rn") == rn else []
    store.con.execute("INSERT INTO google_link(card_id, resource_name, etag, synced, photo_sig, drive, front, labels) VALUES(?,?,?,?,?,?,?,?) "
                      "ON CONFLICT(card_id) DO UPDATE SET resource_name=excluded.resource_name, etag=excluded.etag, "
                      "synced=excluded.synced, photo_sig=excluded.photo_sig, drive=excluded.drive, front=excluded.front, labels=excluded.labels",
                      (cid, rn, etag or old.get("etag") or "", kw.get("synced", time.time()), kw.get("photo_sig", old.get("photo_sig", "")),
                       json.dumps(kw.get("drive", old.get("drive", {}))), (row[0] if row else "") or "",
                       json.dumps(list(kw.get("labels", keep_labels)), ensure_ascii=False)))


# ── 카톡 친구추가 방지(§5.29 '카톡 친구추가 방지') — 명함 이름에는 '#' 를 두지 않고 사람마다 표시만 ──
def kakao_rows(store) -> dict:
    init(store)
    return {r[0]: (bool(r[1]), r[2] or 0.0) for r in store.con.execute("SELECT card_id, block, set_at FROM kakao_block")}


def blocked_ids(store) -> set:
    return {cid for cid, (b, _t) in kakao_rows(store).items() if b}


def kakao_set(store, card_ids, on: bool, set_at=None) -> int:
    """표시 바꾸기 — set_at 이 지난 싱크보다 나중이면 다음 싱크가 구글 이름에 반영(§5.29). 사람이 바꾼 것은 지금 시각."""
    init(store)
    t = time.time() if set_at is None else set_at
    store.con.executemany("INSERT INTO kakao_block(card_id, block, set_at) VALUES(?,?,?) ON CONFLICT(card_id) "
                          "DO UPDATE SET block=excluded.block, set_at=excluded.set_at", [(int(c), int(bool(on)), t) for c in card_ids])
    store.con.commit()
    return len(list(card_ids))


def kakao_new_default(store) -> bool:
    v = store.meta_get(OPT_KAKAO_NEW, None)
    return True if v is None else bool(v)


def bare_name(n: str) -> str:
    return str(n or "").lstrip().lstrip(KAKAO_MARK).lstrip()


def merge_links(store, keeper: int, drops) -> None:
    """명함 합치기(`people.merge_db`) — 지워질 명함의 구글 짝·카톡 표시를 남는 명함으로(§5.29 '명함 합치기와 짝', 261120-46).
    남는 명함에 짝이 있으면 그것을, 없으면 drops 차례(대표 먼저)로 첫 짝을 옮긴다. 남지 못한 짝은 merged = keeper —
    다음 싱크에 '합쳐져 남은 구글 연락처' 로 보인다. 커밋은 부르는 쪽이."""
    init(store)
    lk, kb = links(store), kakao_rows(store)
    drops = [d for d in drops if d != keeper]
    moved = None
    if keeper not in lk:
        moved = next((d for d in drops if d in lk), None)
        if moved is not None:
            store.con.execute("UPDATE google_link SET card_id=?, merged=0 WHERE card_id=?", (keeper, moved))
    for d in drops:
        if d in lk and d != moved:
            store.con.execute("UPDATE google_link SET merged=? WHERE card_id=?", (keeper, d))
    store.con.execute("UPDATE google_link SET front=(SELECT front FROM cards WHERE id=?) WHERE card_id=?", (keeper, keeper))
    if keeper not in kb:
        k_src = moved if moved in kb else next((d for d in drops if d in kb), None)
        if k_src is not None:
            b, t = kb[k_src]
            store.con.execute("INSERT INTO kakao_block(card_id, block, set_at) VALUES(?,?,?)", (keeper, int(b), t))


def unlink(store, cid=None) -> None:
    init(store)
    if cid is None:
        store.con.execute("DELETE FROM google_link")
    else:
        store.con.execute("DELETE FROM google_link WHERE card_id=?", (cid,))
    store.con.commit()


# ── 바꾸기: 구글 사람 ↔ 명함 값 ──
def _ts(s: str) -> float:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def person_time(p: dict) -> float:
    return max([_ts(x.get("updateTime", "")) for x in (p.get("metadata") or {}).get("sources") or []] or [0.0])


def person_values(p: dict) -> dict:
    nm = (p.get("names") or [{}])[0]
    name = nm.get("unstructuredName") or nm.get("displayName") or (
        (nm.get("familyName") or "") + (nm.get("givenName") or "") if re.search(r"[가-힣]", (nm.get("familyName") or "") + (nm.get("givenName") or ""))
        else " ".join(x for x in (nm.get("givenName"), nm.get("familyName")) if x))
    org = (p.get("organizations") or [{}])[0]
    phones = []
    for ph in p.get("phoneNumbers") or []:
        v = ph.get("value") or ""
        if v:
            phones.append((_G2C.get(ph.get("type") or "", "work"), PH.normalize(v)))
    kakao = str(name or "").lstrip().startswith(KAKAO_MARK)
    name = bare_name(name)
    return {"name": name or "", "kakao": kakao, "company": org.get("name") or "", "dept": org.get("department") or "",
            "title": org.get("title") or "", "phones": phones,
            "emails": [e.get("value") for e in p.get("emailAddresses") or [] if e.get("value")],
            "address": ((p.get("addresses") or [{}])[0].get("formattedValue") or ""),
            "urls": [u.get("value") for u in p.get("urls") or [] if u.get("value")],
            "memo": ((p.get("biographies") or [{}])[0].get("value") or "")}


def card_person(c: dict, etag: str = "", kakao: bool = False) -> dict:
    """명함 → 구글 사람(우리가 고치는 칸만). kakao = 이름 앞 '#'(카톡 친구추가 방지)."""
    nm = bare_name(c.get("name") or "")
    p = {"names": [{"unstructuredName": (KAKAO_MARK + nm) if (kakao and nm) else nm}],
         "organizations": [{"name": c.get("company") or "", "department": c.get("dept") or "", "title": c.get("title") or ""}],
         "phoneNumbers": [{"value": n, "type": _C2G.get(k, "work")} for k, n in c.get("phones") or [] if n],
         "emailAddresses": [{"value": e} for e in c.get("emails") or [] if e],
         "addresses": [{"formattedValue": c.get("address") or ""}] if c.get("address") else [],
         "urls": [{"value": u} for u in c.get("urls") or [] if u],
         "biographies": [{"value": c.get("memo") or "", "contentType": "TEXT_PLAIN"}] if c.get("memo") else []}
    if etag:
        p["etag"] = etag
    return p


def _nz(s) -> str:
    return re.sub(r"\s+", "", str(s or "")).lower()


def _norm(v: dict) -> dict:
    return {"name": _nz(bare_name(v.get("name"))), "company": _nz(v.get("company")), "dept": _nz(v.get("dept")),
            "title": _nz(v.get("title")), "address": _nz(v.get("address")), "memo": (v.get("memo") or "").strip(),
            "phones": sorted({(k, PH.digits(n)) for k, n in v.get("phones") or [] if PH.digits(n)}),
            "emails": sorted({_nz(e) for e in v.get("emails") or [] if e}),
            "urls": sorted({(u or "").strip() for u in v.get("urls") or [] if u})}


def diff_fields(card: dict, pv: dict) -> list:
    a, b = _norm(card), _norm(pv)
    return [k for k in a if a[k] != b[k]]


# ── 짝 맞추기 ──
def _name_co(v: dict) -> str:
    from viewer.bizcard.recognize import strip_corp
    n = _nz(v.get("name"))
    return (n + "|" + _nz(strip_corp(v.get("company") or ""))) if n else ""


def _cell_keys(phones) -> set:
    """휴대폰 열쇠(끝 8자리) — 중복 검토와 같은 휴대폰 꼴(`people._mobile_keys` 한 곳 — 종류가 휴대폰이거나 01x, +82 꼴도, 팩스 빼고).
    구글 연락처·구글 vCard 는 종류 없는 번호를 '전화' 로 들인다(261120-46·-48)."""
    return {k[-8:] for k in P._mobile_keys({"phones": list(phones or [])})}


def match(cards: list, people: list) -> dict:
    """짝 없는 명함·사람 사이 — 메일 → 휴대폰 → 이름+회사 차례, 한 사람에 짝 하나. 반환 {card_id: resourceName}."""
    out, used = {}, set()
    pv = [(p["resourceName"], person_values(p)) for p in people]
    gcell = {rn: _cell_keys(v["phones"]) for rn, v in pv}
    ccell = {c["id"]: _cell_keys(c.get("phones")) for c in cards}
    for step in ("email", "cell", "name"):
        for c in cards:
            if c["id"] in out:
                continue
            for rn, v in pv:
                if rn in used:
                    continue
                if step == "email":
                    ok = bool({_nz(e) for e in c.get("emails") or [] if e} & {_nz(e) for e in v["emails"]})
                elif step == "cell":
                    ok = bool(ccell[c["id"]] & gcell[rn])
                else:
                    ok = bool(_name_co(c)) and _name_co(c) == _name_co(v)
                if ok:
                    out[c["id"]] = rn
                    used.add(rn)
                    break
    return out


def _google_src_ids(store) -> set:
    """출처가 구글인 칸이 있는 명함(구글 주소록 vCard 로 가져온 것 — `contact_src`, §5.24 D24)."""
    try:
        return {r[0] for r in store.con.execute("SELECT DISTINCT card_id FROM contact_src WHERE src=?", (SRC,))}
    except Exception:
        return set()


def show(v: dict, f: str) -> str:
    """미리보기 '옛 값 → 새 값' 의 한 칸 글(화면에만 — 로그에 싣지 않는다, §2.1 의 3)."""
    x = v.get(f)
    if f == "phones":
        x = ", ".join(n for _k, n in x or [] if n)
    elif isinstance(x, (list, tuple)):
        x = ", ".join(str(i) for i in x if i)
    x = " / ".join(t.strip() for t in str(x or "").splitlines() if t.strip())
    return x if len(x) <= 80 else x[:79] + "…"


# ── 사진 ──
def g_photo(p: dict) -> str:
    """구글 연락처 사진 주소 — 기본 실루엣이면 ''."""
    for ph in p.get("photos") or []:
        if not ph.get(DEFAULT_PHOTO) and ph.get("url"):
            return ph["url"]
    return ""


def _sig(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()[:16]
    except OSError:
        return ""


def first_photo(card: dict, folder: str) -> str:
    pf = P.photo_front(card, folder)
    ps = P.person_photos(pf) if pf else []
    return ps[0] if ps else ""


# ── 계획 ──
def all_cards(store) -> list:
    return [store._row(r) for r in store.con.execute("SELECT * FROM cards ORDER BY id")]


def label_tags(store) -> list:
    """구글 라벨로 올릴 해시태그(명함 환경설정, §5.29 '라벨')."""
    return [t for t in (store.meta_get(OPT_LABELS, []) or []) if str(t).strip()]


def label_off(store) -> set:
    return {P._tagkey(t) for t in (store.meta_get(OPT_LABELS_OFF, []) or [])}


def add_label_tags(store, names) -> None:
    """가져온 구글 라벨을 '구글 라벨로 올릴 해시태그' 에(끈 것 빼고) — 양방향(사용자 지시 261121)."""
    off, cur = label_off(store), label_tags(store)
    have = {P._tagkey(t) for t in cur}
    new = [n for n in dict.fromkeys(names or []) if P._tagkey(n) and P._tagkey(n) not in have and P._tagkey(n) not in off]
    if new:
        store.meta_set(OPT_LABELS, cur + new)


def _user_groups(groups) -> dict:
    """사람이 만든 라벨만 {contactGroups/…: 이름} — 시스템 라벨(myContacts·starred …)은 뺀다."""
    return {g["resourceName"]: g.get("name") or "" for g in groups or [] if g.get("groupType", "USER_CONTACT_GROUP") == "USER_CONTACT_GROUP"}


def person_labels(p: dict, gmap: dict) -> list:
    return [gmap[m["contactGroupMembership"]["contactGroupResourceName"]] for m in p.get("memberships") or []
            if (m.get("contactGroupMembership") or {}).get("contactGroupResourceName") in gmap]


def plan(store, people: list, folder: str = "", photos: bool = False, drive: bool = False, card_first: bool = False,
         groups=None) -> list:
    """계획 줄 [{kind, card_id, rn, name, fields, ...}] — 네트워크 없이. 반영 전에는 아무것도 바꾸지 않는다.
    card_first = '명함 기준으로 올리기'(§5.29, 261120-59) — 명함 값이 이김: 구글에서 지워진 짝은 새 연락처로 다시, 구글 → 명함 줄 없음."""
    init(store)
    lk = links(store)
    kb = kakao_rows(store)
    new_k = kakao_new_default(store)
    cards = all_cards(store)
    by_id = {c["id"]: c for c in cards}
    by_rn = {p["resourceName"]: p for p in people}
    rn_linked = {v["rn"] for v in lk.values()}
    rows = []
    pairs = []
    regone = []                                            # card_first — 구글에서 지워진 짝의 명함(새 연락처로 다시)
    known = set(lk) | _google_src_ids(store)               # 예전 구글에 있던 명함(§5.29 '카톡' — 새로 보낼 때 # 없이, 261120-59)
    for cid, l in list(lk.items()):
        c, p = by_id.get(cid), by_rn.get(l["rn"])
        if c is not None and l.get("front") and l["front"] != (c.get("front") or ""):
            c = None                                       # 짝지은 명함은 지워졌고 같은 id 를 새 명함이 받음 — 새 명함은 짝 없는 쪽으로
            lk.pop(cid)
            lk[-cid] = l
        if c is None and p is not None:
            rows.append({"kind": MERGED_GOOGLE if l.get("merged") else GONE_CARD, "card_id": cid, "rn": l["rn"],
                         "name": person_values(p)["name"]})
        elif p is None and c is not None:
            if card_first:
                regone.append(c)
            else:
                rows.append({"kind": GONE_GOOGLE, "card_id": cid, "rn": l["rn"], "name": c.get("name") or ""})
        elif c is not None:
            pairs.append((c, p, l))
    free_cards = [c for c in cards if c["id"] not in lk] + regone
    from_google = _google_src_ids(store)
    known_mob = {k for c in cards if c["id"] in known for k in P._mobile_keys(c)}

    def new_kakao(c):
        if c["id"] in kb:
            return kb[c["id"]][0]                          # 사람마다 표시가 먼저
        if c["id"] in known or set(P._mobile_keys(c)) & known_mob:
            return False                                   # 예전 구글에 있던 사람은 # 없이(사용자 결정 261121)
        return new_k
    free_people = [p for p in people if p["resourceName"] not in rn_linked]
    m = match(free_cards, free_people)
    use_labels = groups is not None
    gmap = _user_groups(groups) if use_labels else {}
    ch = {}
    if use_labels:                                         # 고른 해시태그 + 구글 라벨(끈 것 빼고, 사용자 지시 261121 '구글의 라벨을 해시태그로')
        off = label_off(store)
        for t in label_tags(store) + sorted(gmap.values()):
            k = P._tagkey(t)
            if k and k not in off:
                ch.setdefault(k, t)

    def _keys(names):
        return [k for k in dict.fromkeys(P._tagkey(t) for t in names or []) if k in ch]
    for c in free_cards:
        if c["id"] in m:
            pairs.append((c, by_rn[m[c["id"]]], {"rn": m[c["id"]], "synced": 0.0, "photo_sig": "", "drive": {}, "new": True}))
        else:
            rows.append({"kind": NEW_GOOGLE, "card_id": c["id"], "rn": "", "name": c.get("name") or "",
                         "kakao": new_kakao(c),                                     # 새로 보낼 때는 기본 친구추가 방지
                         "maybe_dup": c["id"] in from_google and not card_first,    # 구글 vCard 로 가져온 명함 — 구글에 이미 있을 수 있음
                         "labels": [ch[k] for k in _keys(c.get("tags"))]})
    for p in free_people:
        if p["resourceName"] not in m.values() and not card_first:
            rows.append({"kind": NEW_CARD, "card_id": 0, "rn": p["resourceName"], "name": person_values(p)["name"],
                         "tags_add": [ch[k] for k in _keys(person_labels(p, gmap))]})
    for c, p, l in pairs:
        pv = person_values(p)
        d = diff_fields(c, pv)
        pt, ct, syn = person_time(p), float(c.get("updated") or 0), float(l.get("synced") or 0)
        g_k = pv["kakao"]
        row = kb.get(c["id"])
        c_k = g_k if row is None else row[0]                 # 표시가 없으면 구글 이름대로(이미 있는 연락처는 그대로)
        if row is None and g_k:
            if not card_first:
                rows.append({"kind": KAKAO_DOWN, "card_id": c["id"], "rn": p["resourceName"], "name": c.get("name") or "", "kakao": True})
        elif row is not None and row[0] != g_k:
            up = row[1] > syn or card_first                    # 표시를 바꾼 뒤면 구글로, 아니면 구글 이름대로(명함 기준이면 늘 구글로)
            rows.append({"kind": KAKAO_UP if up else KAKAO_DOWN, "card_id": c["id"], "rn": p["resourceName"],
                         "name": c.get("name") or "", "kakao": row[0] if up else g_k, "etag": p.get("etag") or ""})
            c_k = row[0] if up else g_k
        if d:
            g_new, c_new = pt > syn, ct > syn
            to_card = not card_first and ((g_new and not c_new) or (g_new == c_new and pt > ct))   # 한쪽만 바뀌었으면 그쪽, 둘 다면 나중 것
            rows.append({"kind": TO_CARD if to_card else TO_GOOGLE, "card_id": c["id"], "rn": p["resourceName"],
                         "name": c.get("name") or pv["name"], "fields": d, "etag": p.get("etag") or "", "link": bool(l.get("new")),
                         "kakao": c_k,
                         "changes": [(f,) + ((show(c, f), show(pv, f)) if to_card else (show(pv, f), show(c, f))) for f in d]})
        elif l.get("new"):                                   # 처음 짝 — 값이 같으면 짝만 적는다
            rows.append({"kind": "link", "card_id": c["id"], "rn": p["resourceName"], "name": c.get("name") or "",
                         "etag": p.get("etag") or "", "labels": [ch[k] for k in set(_keys(c.get("tags"))) & set(_keys(person_labels(p, gmap)))]})
        if ch:                                               # 고른 해시태그 ↔ 구글 라벨(§5.29 '라벨', 261120-61)
            C, Gs = set(_keys(c.get("tags"))), set(_keys(person_labels(p, gmap)))
            L = (C & Gs) if l.get("new") else set(_keys(l.get("labels")))
            if card_first:
                add_g, rm_g, add_t, rm_t = C - Gs, Gs - C, set(), set()
            else:
                add_g, rm_g = (C - L) - Gs, (L - C) & Gs
                add_t, rm_t = (Gs - L) - C, (L - Gs) & C
            if add_g or rm_g or add_t or rm_t:
                nm = lambda ks: sorted(ch[k] for k in ks)
                txt = " ".join(["+" + x for x in nm(add_g)] + ["−" + x for x in nm(rm_g)])
                tt = " ".join(["+" + x for x in nm(add_t)] + ["−" + x for x in nm(rm_t)])
                rows.append({"kind": LABELS, "card_id": c["id"], "rn": p["resourceName"], "name": c.get("name") or "",
                             "add_g": nm(add_g), "rm_g": nm(rm_g), "add_t": nm(add_t), "rm_t": nm(rm_t),
                             "labels": nm((C | add_t) - rm_t),
                             "txt": "  ".join(x for x in (("구글 " + txt) if txt else "", ("해시태그 " + tt) if tt else "") if x)})
        if photos:
            mine = first_photo(c, folder)
            gp = g_photo(p)
            if mine and not gp:
                rows.append({"kind": PHOTO_UP, "card_id": c["id"], "rn": p["resourceName"], "name": c.get("name") or "",
                             "path": mine})
            elif gp and not mine and not card_first:
                rows.append({"kind": PHOTO_DOWN, "card_id": c["id"], "rn": p["resourceName"], "name": c.get("name") or "",
                             "url": gp})
        if drive and not str(c.get("front") or "").startswith("contact:"):
            have = l.get("drive") or {}
            for side in ("front", "back"):
                path = c.get(side) or ""
                if path and _sig(path) and have.get(side, {}).get("sig") != _sig(path):
                    rows.append({"kind": DRIVE_UP, "card_id": c["id"], "rn": p["resourceName"], "name": c.get("name") or "",
                                 "side": side, "path": path})
    if use_labels:                                           # 앱이 쓰던 라벨을 고른 목록에서 뺐으면 — 지울까요(기본 남김)
        used = store.meta_get(META_LABEL_GROUPS, {}) or {}
        for name, grn in sorted(used.items()):
            if P._tagkey(name) not in ch and grn in gmap:
                rows.append({"kind": LABEL_GONE, "card_id": 0, "rn": grn, "name": name})
    order = {k: i for i, k in enumerate(KINDS + ("link",))}
    rows.sort(key=lambda r: (order.get(r["kind"], 99), r.get("name") or ""))
    return rows


def counts(rows: list) -> dict:
    out = {}
    for r in rows:
        out[r["kind"]] = out.get(r["kind"], 0) + 1
    return out


# ── 반영 ──
def apply(store, api, rows: list, folder: str = "", drive_folder: str = DRIVE_FOLDER_DEFAULT, progress=None,
          people=None) -> dict:
    """고른 줄만 반영(배경). 반환 {'done': n, 'failed': n, 'delete_cards': [id]} — 명함 지우기는 부르는 쪽이 휴지통 길로(§5.20)."""
    init(store)
    P.src_init(store)
    done = failed = 0
    delete_cards = []
    by_rn = {p["resourceName"]: p for p in people or []}     # 계획 때 받은 목록(없으면 처음 필요할 때 한 번 받는다)
    folder_id = ""
    n = len(rows)
    gcache = {}                                             # 라벨 이름(열쇠) → contactGroups/… — 처음 필요할 때 한 번 받는다

    def group_of(name, make=True):
        if not gcache:
            for g in api.list_groups():
                if g.get("groupType", "USER_CONTACT_GROUP") == "USER_CONTACT_GROUP":
                    gcache[P._tagkey(g.get("name"))] = g["resourceName"]
            gcache[""] = ""
        rn = gcache.get(P._tagkey(name))
        if not rn and make:
            rn = api.create_group(name)["resourceName"]
            gcache[P._tagkey(name)] = rn
        if rn:
            used = dict(store.meta_get(META_LABEL_GROUPS, {}) or {})
            if used.get(name) != rn:
                used[name] = rn
                store.meta_set(META_LABEL_GROUPS, used)
        return rn
    for i, r in enumerate(rows):
        k = r["kind"]
        try:
            if k == NEW_CARD:
                p = r.get("person") or by_rn.get(r["rn"])
                if p is None:
                    p = _fetch(api, r["rn"], by_rn)
                v = person_values(p)
                cid = P._insert_contact(store, v, ["명함", TAG])
                kakao_set(store, [cid], v.get("kakao", False), set_at=0.0)
                P._set_srcs(store, cid, [x for x in P._SCALARS if (v.get(x) or "").strip()], SRC)
                if r.get("tags_add"):                         # 고른 라벨만 해시태그로(§5.29 '라벨')
                    cc = P.card_by_id(store, cid)
                    P.update_card(store, cid, {"tags": list(dict.fromkeys(list(cc.get("tags") or []) + list(r["tags_add"])))}, commit=False)
                _link_put(store, cid, r["rn"], p.get("etag") or "", labels=list(r.get("tags_add") or []))
            elif k == NEW_GOOGLE:
                c = P.card_by_id(store, r["card_id"])
                p = api.create(card_person(c, kakao=bool(r.get("kakao"))))
                kakao_set(store, [c["id"]], bool(r.get("kakao")), set_at=0.0)
                for name in r.get("labels") or []:               # 새 연락처도 고른 해시태그의 라벨을(§5.29 '라벨')
                    api.modify_members(group_of(name), add=[p["resourceName"]])
                _link_put(store, c["id"], p["resourceName"], p.get("etag") or "", labels=list(r.get("labels") or []))
            elif k == TO_CARD:
                p = _fetch(api, r["rn"], by_rn)
                v = person_values(p)
                ch = {f: v[f] for f in r["fields"] if f in v}
                if "name" in ch or "company" in ch:           # 회사·이름이 바뀌면 자동 해시태그도(§5.5, 261120-53)
                    old = P.card_by_id(store, r["card_id"])
                    ch["tags"] = P.auto_retag(old.get("tags") or [], [old], ch.get("name", old.get("name")),
                                              ch.get("company", old.get("company")))[0]
                P.update_card(store, r["card_id"], ch, commit=False)
                P._set_srcs(store, r["card_id"], [f for f in r["fields"] if f in P._SCALARS], SRC)
                _link_put(store, r["card_id"], r["rn"], p.get("etag") or "")
            elif k == TO_GOOGLE:
                c = P.card_by_id(store, r["card_id"])
                p = api.update(r["rn"], card_person(c, r.get("etag") or "", kakao=bool(r.get("kakao"))))
                _link_put(store, c["id"], r["rn"], p.get("etag") or "")
            elif k == KAKAO_UP:
                c = P.card_by_id(store, r["card_id"])
                p = _fetch(api, r["rn"], by_rn)
                p2 = api.update(r["rn"], card_person(c, p.get("etag") or "", kakao=bool(r.get("kakao"))))
                by_rn[r["rn"]] = p2
                kakao_set(store, [c["id"]], bool(r.get("kakao")), set_at=0.0)
                _link_put(store, c["id"], r["rn"], p2.get("etag") or "")
            elif k == KAKAO_DOWN:
                kakao_set(store, [r["card_id"]], bool(r.get("kakao")), set_at=0.0)
            elif k == "link":
                _link_put(store, r["card_id"], r["rn"], r.get("etag") or "", labels=list(r.get("labels") or []))
            elif k == LABELS:                                    # 고른 해시태그 ↔ 구글 라벨(§5.29 '라벨', 261120-61)
                for name in r.get("add_g") or []:
                    api.modify_members(group_of(name), add=[r["rn"]])
                for name in r.get("rm_g") or []:
                    g = group_of(name, make=False)
                    if g:
                        api.modify_members(g, remove=[r["rn"]])
                if r.get("add_t") or r.get("rm_t"):
                    cc = P.card_by_id(store, r["card_id"])
                    gone = {P._tagkey(t) for t in r.get("rm_t") or []}
                    tags = [t for t in cc.get("tags") or [] if P._tagkey(t) not in gone] + list(r.get("add_t") or [])
                    P.update_card(store, r["card_id"], {"tags": list(dict.fromkeys(tags))}, commit=False)
                _link_put(store, r["card_id"], r["rn"], "", labels=list(r.get("labels") or []))
            elif k == LABEL_GONE:                                # 라벨만 지움 — 연락처는 그대로
                api.delete_group(r["rn"])
                used = dict(store.meta_get(META_LABEL_GROUPS, {}) or {})
                used.pop(r["name"], None)
                store.meta_set(META_LABEL_GROUPS, used)
            elif k == GONE_GOOGLE:
                delete_cards.append(r["card_id"])
                store.con.execute("DELETE FROM google_link WHERE card_id=?", (r["card_id"],))
            elif k in (GONE_CARD, MERGED_GOOGLE):
                api.delete(r["rn"])
                store.con.execute("DELETE FROM google_link WHERE card_id=?", (r["card_id"],))
            elif k == PHOTO_UP:
                with open(r["path"], "rb") as f:
                    api.update_photo(r["rn"], f.read())
                _link_put(store, r["card_id"], r["rn"], "", photo_sig=_sig(r["path"]))
            elif k == PHOTO_DOWN:
                c = P.card_by_id(store, r["card_id"])
                pf = P.photo_front(c, folder)
                if not pf:
                    raise ValueError("no folder")
                import os
                import tempfile
                data = api.get_bytes(r["url"])
                fd, tmp = tempfile.mkstemp(suffix=".jpg")
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
                try:
                    dst = P.next_photo_path(pf)
                    P.save_person_photo(tmp, dst)
                finally:
                    os.unlink(tmp)
                _link_put(store, r["card_id"], r["rn"], "", photo_sig=_sig(str(dst)))
            elif k == DRIVE_UP:
                if not folder_id:
                    folder_id = api.ensure_folder(drive_folder or DRIVE_FOLDER_DEFAULT)
                lk = links(store).get(r["card_id"]) or {}
                dr = dict(lk.get("drive") or {})
                import os
                fid = api.upload(r["path"], os.path.basename(r["path"]), folder_id, (dr.get(r["side"]) or {}).get("id", ""))
                dr[r["side"]] = {"id": fid, "sig": _sig(r["path"])}
                from viewer.bizcard.gsync_api import drive_link
                c = P.card_by_id(store, r["card_id"])
                link = drive_link(fid)
                if link not in (c.get("urls") or []):                 # 연락처 누리집 칸에 링크(§5.29 '드라이브')
                    urls = list(c.get("urls") or []) + [link]
                    P.update_card(store, c["id"], {"urls": urls}, commit=False)
                    c = P.card_by_id(store, c["id"])
                    p = _fetch(api, r["rn"], by_rn)
                    p2 = api.update(r["rn"], card_person(c, p.get("etag") or "", kakao=c["id"] in blocked_ids(store)))
                    by_rn[r["rn"]] = p2
                _link_put(store, r["card_id"], r["rn"], "", drive=dr)
            done += 1
        except Exception:                                     # 값·토큰은 싣지 않는다 — 개수만
            failed += 1
        store.con.commit()
        if progress is not None:
            progress(i + 1, n)
    add_label_tags(store, [n for r in rows for n in (r.get("tags_add") or []) + (r.get("add_t") or [])])   # 가져온 라벨도 목록에
    store.con.commit()
    return {"done": done, "failed": failed, "delete_cards": delete_cards}


def _fetch(api, rn: str, cache: dict) -> dict:
    if rn not in cache:
        for p in api.list_people():
            cache[p["resourceName"]] = p
    return cache[rn]
