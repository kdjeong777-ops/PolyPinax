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
