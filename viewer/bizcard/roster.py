# -*- coding: utf-8 -*-
"""명단 관리 계산 (명함 SOT §5.32, 261122-1·-2) — Qt 없음.

010 둘 이상 명단(잘못 합쳐졌을 수 있음)과 사용자가 고른 vcf 와의 비교. vcf 는 읽기만 한다(명함 폴더에 복사하지 않음, 완전 오프라인).
"""
from __future__ import annotations

from viewer.bizcard import people as P

MERGED = "merged"            # vcf 사람의 010 을 가진 명단 — 010 둘 이상(잘못 합쳐짐?)
RENAMED = "renamed"          # 그 010 하나뿐(이름 바뀜?)
NEW = "new"                  # 지금 명단에 그 010 이 없음(새 사람 — 체크를 켰을 때만)
SAME_NAME = "same_name"      # 같은 이름 명단인데 010 번호가 vcf 와 다름(사용자 덧붙임 261122)


def all_cards(store) -> list:
    return [store._row(r) for r in store.con.execute("SELECT * FROM cards ORDER BY name, id").fetchall()]


def multi_mobile(cards) -> list:
    """010 번호가 둘 이상인 명단만(같은 번호는 한 번)."""
    return [c for c in cards if len(P.mobiles_010(c)) >= 2]


MANY_MIN = 3                 # '명함 3장 이상'(§5.32, 261122-14)


def card_images(cards, folder: str = "") -> dict:
    """명단 하나에 붙은 실제 그림 수 {id: 장 수} — 명단 관리 오른쪽 그림 줄과 같은 것: 정리본 앞면·뒷면(파일이 있는 것) +
    인물 폴더의 `<정리본 이름>.jpg`·` (n)` 들(`people.person_photos` 꼴). 폴더마다 한 번만 읽는다(명함마다 파일을 찾지 않게)."""
    import os
    import re
    from pathlib import Path
    from viewer.bizcard.vcard import is_contact
    from viewer.bizcard.recognize import IMG_EXTS
    lists = {}

    def names(d):
        d = os.path.normcase(os.path.abspath(str(d)))
        if d not in lists:
            try:
                lists[d] = [n for n in os.listdir(d)]
            except OSError:
                lists[d] = []
        return lists[d]
    out = {}
    for c in cards:
        n = 0
        if not is_contact(c):
            for f in (c.get("front"), c.get("back")):
                if f and os.path.normcase(os.path.basename(str(f))) in {os.path.normcase(x) for x in names(os.path.dirname(os.path.abspath(str(f))))}:
                    n += 1
        pf = P.photo_front(c, folder)
        if pf:
            pat = re.compile(r"^%s( \(\d+\))?$" % re.escape(Path(pf).stem), re.I)
            n += sum(1 for x in names(P.people_dir(pf)) if os.path.splitext(x)[1].lower() in IMG_EXTS and pat.match(os.path.splitext(x)[0]))
        out[c["id"]] = n
    return out


def many_cards(cards, folder: str = "", least: int = MANY_MIN) -> list:
    """한 명단에 실제 그림(앞·뒷면 + 인물 사진)이 least 장 이상 붙은 것만(§5.32 '명함 3장 이상', 261122-14 — 앞·뒤로 최대 2장인데
    잘못 붙은 것을 찾으려고. 종전 261122-5 는 이름·010 이 같은 명단 수를 셌다 — 뜻이 달랐다). 반환 [(명단, 장 수)] — 많은 차례, 같으면 이름."""
    cnt = card_images(cards, folder)
    hits = [(c, cnt.get(c["id"], 0)) for c in cards if cnt.get(c["id"], 0) >= least]
    return sorted(hits, key=lambda x: (-x[1], str(x[0].get("name") or ""), x[0]["id"]))

def text_match(card: dict, text: str) -> bool:
    """찾기 칸 — 이름·회사·번호(숫자만으로도)·메일 글자."""
    t = (text or "").strip().lower()
    if not t:
        return True
    hay = " ".join([card.get("name") or "", card.get("company") or ""]
                   + [str(x[-1] if isinstance(x, (list, tuple)) else x) for x in card.get("phones") or []]
                   + [str(e) for e in card.get("emails") or []]).lower()
    if t in hay:
        return True
    d = "".join(ch for ch in t if ch.isdigit())
    if len(d) < 3:
        return False
    return any(d in "".join(ch for ch in str(x[-1] if isinstance(x, (list, tuple)) else x) if ch.isdigit())
               for x in card.get("phones") or [])


def vcf_compare(cards, persons, show_new: bool = False) -> list:
    """vcf(예전 구글 백업 — 바른 기준) 사람마다 — 010 번호(종류 무관)가 있고, 그 이름이 지금 명단에 없거나 **있어도 그 이름 명단의
    010 번호가 vcf 와 다르면** 한 묶음(사용자 덧붙임 261122). 이름 비교는 `_pname`(빈칸·앞 #·괄호 직함 무시).
    [{person, keys: [010 열쇠], kind: 'match'|NEW, subs: [{card, kind: SAME_NAME|MERGED|RENAMED, key}]}] — 아래 명단이 없으면 NEW(show_new 일 때만)."""
    by_name, by_key = {}, {}
    for c in cards:
        pn = P._pname(c.get("name"))
        if pn:
            by_name.setdefault(pn, []).append(c)
        for k in P.mobiles_010(c):
            by_key.setdefault(k, []).append(c)
    out = []
    for p in persons:
        keys = P.mobiles_010({"phones": p.get("phones") or []})
        pn = P._pname(p.get("name"))
        if not keys or not pn:
            continue
        same = by_name.get(pn, [])
        diff = [c for c in same if set(P.mobiles_010(c)) != set(keys)]
        if same and not diff:
            continue                                        # 이름·번호 모두 vcf 와 같음
        subs = [{"card": c, "key": "", "kind": SAME_NAME} for c in diff]
        seen = {c["id"] for c in same}
        for k in keys:
            for c in by_key.get(k, []):
                if c["id"] in seen:
                    continue
                seen.add(c["id"])
                subs.append({"card": c, "key": k, "kind": MERGED if len(P.mobiles_010(c)) >= 2 else RENAMED})
        if not subs and not show_new:
            continue
        out.append({"person": p, "keys": keys, "kind": "match" if subs else NEW, "subs": subs})
    out.sort(key=lambda g: (g["kind"] == NEW, P._nname(g["person"].get("name"))))
    return out


META_KEY = "roster_vcf"      # 명함 DB meta — vcf 경로·고정한 작업 목록·사람이 정한 체크(261122-4)
_PERSON_KEYS = ("name", "company", "dept", "title", "phones", "emails")


def freeze(groups) -> list:
    """`vcf_compare` 결과 → 고정한 작업 목록(JSON 으로 남김) — 하위는 명함 id·종류·겹친 번호·그때 이름만."""
    return [{"person": {k: g["person"].get(k) for k in _PERSON_KEYS}, "keys": list(g["keys"]), "kind": g["kind"],
             "subs": [{"id": s["card"]["id"], "kind": s["kind"], "key": s["key"], "name": s["card"].get("name") or ""}
                      for s in g["subs"]]} for g in groups]


def person_resolved(g, cards) -> bool:
    """대표 줄 해결 — 그 이름이고 그 010 번호를 모두 가진 명단이 있음."""
    pn, keys = P._pname(g["person"].get("name")), set(g["keys"])
    return any(P._pname(c.get("name")) == pn and keys <= set(P.mobiles_010(c)) for c in cards)


def sub_resolved(g, sub, card) -> bool:
    """하위 줄 해결 — 지운 명단이거나, 종류마다: 잘못 합쳐짐? = vcf 번호가 빠짐, 이름 바뀜? = 이름이 vcf 이름이 되거나 번호가 빠짐,
    같은 이름·번호 다름 = 010 번호가 vcf 와 같아짐."""
    if card is None:
        return True
    keys, m = set(g["keys"]), set(P.mobiles_010(card))
    if sub["kind"] == SAME_NAME:
        return m == keys
    if sub["kind"] == RENAMED and P._pname(card.get("name")) == P._pname(g["person"].get("name")):
        return True
    return not (keys & m)


def read_vcf(path: str) -> list:
    """vcf 파일 → 사람들(읽기만). 글자판은 UTF-8, 안 되면 cp949."""
    from viewer.bizcard.vcard import people_from_vcf
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return people_from_vcf(raw.decode(enc))
        except UnicodeDecodeError:
            continue
    return people_from_vcf(raw.decode("utf-8", "replace"))
