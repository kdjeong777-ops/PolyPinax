"""명함 → vCard 3.0 내보내기·기존 vCard 에 합치기 (구글 싱크 SOT §5.8, P3 · R9·R10 · D5·D6).

Qt 없음 — 명함 읽기 창과 명함찾기 창(P4)이 함께 부른다. 파일 쓰기는 부르는 쪽이 `bg_write` 로(응답성 SOT §6).
★ 명함 글은 로그로 내보내지 않는다(§2.1) — 돌려주는 통계는 숫자만.
"""
from __future__ import annotations

import os
import re
import urllib.parse

from viewer.bizcard import phone as _phone
from viewer.bizcard.recognize import COMPOUND_SURNAMES
from viewer.i18n import tr

DRIVE_SEARCH = "https://drive.google.com/drive/search?q="
TEL_TYPE = {"cell": "CELL", "work": "WORK", "fax": "FAX"}
FOLD = 75                  # vCard 3.0(RFC 2425) 줄 길이 — 바이트


def _hangul(s: str) -> bool:
    return any("가" <= ch <= "힣" for ch in s or "")


def esc(s: str) -> str:
    return (str(s or "").replace("\\", "\\\\").replace("\r\n", "\n").replace("\n", "\\n")
            .replace(",", "\\,").replace(";", "\\;"))


def unesc(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s):
            nx = s[i + 1]
            out.append("\n" if nx in "nN" else nx)
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def fold(line: str) -> str:
    """75 바이트마다 CRLF + 빈칸 — UTF-8 글자 중간은 자르지 않는다."""
    b = line.encode("utf-8")
    if len(b) <= FOLD:
        return line
    parts, cur, lim = [], "", FOLD
    for ch in line:
        if len((cur + ch).encode("utf-8")) > lim:
            parts.append(cur)
            cur, lim = ch, FOLD - 1          # 이어지는 줄은 앞 빈칸 한 바이트
        else:
            cur += ch
    parts.append(cur)
    return "\r\n ".join(parts)


def split_name(name: str):
    """(성, 이름) — 한글은 앞 1~2자가 성, 로마자는 마지막 낱말이 성."""
    name = (name or "").strip()
    if not name:
        return "", ""
    if _hangul(name):
        n = name.replace(" ", "")
        if len(n) >= 3 and n[:2] in COMPOUND_SURNAMES:
            return n[:2], n[2:]
        return n[:1], n[1:]
    w = name.split()
    if len(w) == 1:
        return w[0], ""
    return w[-1], " ".join(w[:-1])


CONTACT_PREFIX = "contact:"          # 주소록에서 가져온 '그림 없는 명함' 의 front 열쇠(§5.24 D22)


def is_contact(card) -> bool:
    return str((card or {}).get("front") or "").startswith(CONTACT_PREFIX)


def _note_lines(card: dict, drive_folder: str, other_lang_line: str, card_word: str) -> list:
    lines = [ln for ln in (card.get("memo") or "").splitlines() if ln.strip()]
    fname = "" if is_contact(card) else os.path.basename(card.get("front") or "")
    if drive_folder and fname:
        lines.append("%s: %s/%s" % (card_word, drive_folder.strip().strip("/\\"), fname))
        lines.append(DRIVE_SEARCH + urllib.parse.quote(fname))
    if other_lang_line:
        lines.append(other_lang_line)
    return lines


def card_to_vcard(card: dict, drive_folder: str = "", lang: str = "ko", card_word: str = "", style: str = "google") -> str:
    """명함 DB 한 행 → vCard 3.0 한 장(CRLF). card_word = NOTE 의 '명함' 낱말(결과물 언어, 비우면 tr).
    style='remember' — 리멤버 명함첩 꼴(§5.24 D23): 이름 통째로 N 둘째 칸, TEL TYPE=work,cell·work·work,fax, EMAIL·ADR TYPE=work,
    주소는 ADR 둘째 칸, NOTE 에 드라이브 줄 없음(메모만)."""
    if style == "remember":
        return _remember_vcard(card, lang)
    if not card_word:
        card_word = tr("명함")
    en = card.get("en") or {}
    ko = {k: card.get(k) or "" for k in ("name", "company", "dept", "title", "address")}
    if lang.startswith("en") and en.get("name"):
        main = {k: en.get(k) or ko[k] for k in ko}
        other = ko if any(_hangul(v) for v in ko.values()) else {}
        tag = "Korean"
    else:
        main, other, tag = ko, en, "English"
    other_line = ""
    vals = [other.get(k) for k in ("name", "title", "dept", "company", "address") if other.get(k)]
    if vals and vals != [main.get(k) for k in ("name", "title", "dept", "company", "address") if other.get(k)]:
        other_line = "%s: %s" % (tag, " · ".join(vals))
    fam, giv = split_name(main["name"])
    out = ["BEGIN:VCARD", "VERSION:3.0",
           "N:%s;%s;;;" % (esc(fam), esc(giv)),
           "FN:%s" % esc(main["name"].replace(" ", "") if _hangul(main["name"]) else main["name"])]
    if main["company"] or main["dept"]:
        out.append("ORG:%s;%s" % (esc(main["company"]), esc(main["dept"])) if main["dept"] else "ORG:%s" % esc(main["company"]))
    if main["title"]:
        out.append("TITLE:%s" % esc(main["title"]))
    for kind, num in card.get("phones") or []:
        if num:
            out.append("TEL;TYPE=%s:%s" % (TEL_TYPE.get(kind, "VOICE"), esc(_phone.normalize(num))))
    for e in card.get("emails") or []:
        if e:
            out.append("EMAIL;TYPE=INTERNET:%s" % esc(e))
    if main["address"]:
        out.append("ADR;TYPE=WORK:;;%s;;;;" % esc(main["address"]))
    for u in card.get("urls") or []:
        if u:
            out.append("URL:%s" % esc(u))
    note = _note_lines(card, drive_folder, other_line, card_word)
    if note:
        out.append("NOTE:%s" % esc("\n".join(note)))
    out.append("END:VCARD")
    return "".join(fold(x) + "\r\n" for x in out)


def _remember_vcard(card: dict, lang: str = "ko") -> str:
    en = card.get("en") or {}
    main = {k: card.get(k) or "" for k in ("name", "company", "dept", "title", "address")}
    if lang.startswith("en") and en.get("name"):
        main = {k: en.get(k) or main[k] for k in main}
    name = main["name"].replace(" ", "") if _hangul(main["name"]) else main["name"]
    out = ["BEGIN:VCARD", "VERSION:3.0", "N:;%s;;;" % esc(name), "FN:%s" % esc(name)]
    kinds = {"cell": "work,cell", "work": "work", "fax": "work,fax"}
    for kind, num in card.get("phones") or []:
        if num:
            out.append("TEL;TYPE=%s:%s" % (kinds.get(kind, "work"), esc(_phone.normalize(num))))
    if main["company"] or main["dept"]:
        out.append("ORG:%s;%s" % (esc(main["company"]), esc(main["dept"])))
    if main["title"]:
        out.append("TITLE:%s" % esc(main["title"]))
    for e in card.get("emails") or []:
        if e:
            out.append("EMAIL;TYPE=work:%s" % esc(e))
    if main["address"]:
        out.append("ADR;TYPE=work:;%s;;;;;" % esc(main["address"]))
    for u in card.get("urls") or []:
        if u:
            out.append("URL:%s" % esc(u))
    memo = "\n".join(ln for ln in (card.get("memo") or "").splitlines() if ln.strip())
    if memo:
        out.append("NOTE:%s" % esc(memo))
    out.append("END:VCARD")
    return "".join(fold(x) + "\r\n" for x in out)


def export_text(cards, drive_folder: str = "", lang: str = "ko", card_word: str = "", style: str = "google") -> str:
    return "".join(card_to_vcard(c, drive_folder, lang, card_word, style) for c in cards if (c.get("name") or "").strip())


# ── 읽기·합치기(R10) ──
def _unfold(text: str) -> list:
    lines = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    out = []
    for ln in lines:                         # QUOTED-PRINTABLE 의 '=' 줄 이음
        if out and out[-1].endswith("=") and "QUOTED-PRINTABLE" in out[-1].upper().split(":", 1)[0]:
            out[-1] = out[-1][:-1] + ln
        else:
            out.append(ln)
    return out


def _qp(v: str, charset: str) -> str:
    import quopri
    try:
        return quopri.decodestring(v.encode("ascii", "ignore")).decode(charset or "utf-8", "replace")
    except LookupError:
        return quopri.decodestring(v.encode("ascii", "ignore")).decode("utf-8", "replace")


def parse_line(ln: str):
    """'TEL;TYPE=CELL:010…' → (이름 대문자, {매개변수}, 값 — 이스케이프 풂)."""
    if ":" not in ln:
        return None
    head, val = ln.split(":", 1)
    parts = head.split(";")
    name = parts[0].split(".")[-1].upper()           # 'item1.TEL' 꼴
    params = {}
    for p in parts[1:]:
        k, _, v = p.partition("=")
        params.setdefault(k.upper(), []).append(v)
    if any("QUOTED-PRINTABLE" in (k + "=" + ",".join(v)).upper() for k, v in params.items()):   # 2.1 꼴(ENCODING= 또는 맨 이름)
        val = _qp(val, (params.get("CHARSET") or [""])[0])
    return name, params, unesc(val) if name not in ("N", "ADR", "ORG") else val


def parse_vcf(text: str) -> list:
    """카드마다 {'lines': [원래 줄(펴진 것)], 'fn', 'tels': {숫자}, 'emails', 'note'}."""
    cards, cur = [], None
    for ln in _unfold(text):
        u = ln.strip().upper()
        if u == "BEGIN:VCARD":
            cur = {"lines": [], "fn": "", "n": "", "tels": set(), "emails": set(), "note": "", "vals": set()}
            continue
        if u == "END:VCARD":
            if cur is not None:
                cards.append(cur)
            cur = None
            continue
        if cur is None or not ln.strip():
            continue
        cur["lines"].append(ln)
        p = parse_line(ln)
        if not p:
            continue
        name, _params, val = p
        if name == "FN":
            cur["fn"] = val
        elif name == "N":
            fam, giv = (val.split(";") + [""])[:2]
            cur["n"] = unesc(fam) + unesc(giv)          # 한글 '성+이름' — 붙여 쓴 FN 과 견준다
        elif name == "TEL":
            cur["tels"].add(digits(val))
        elif name == "EMAIL":
            cur["emails"].add(val.strip().lower())
        elif name == "NOTE":
            cur["note"] = val
        if name in ("TITLE", "ADR", "URL"):
            cur["vals"].add((name, re.sub(r"\s+", "", unesc(val)).lower()))
    return cards


def digits(num: str) -> str:
    d = re.sub(r"\D", "", num or "")
    if (num or "").strip().startswith("+82") or (d.startswith("82") and len(d) >= 11):
        d = "0" + d[2:]
    return d


def _key_name(s: str) -> str:
    return re.sub(r"\s+", "", s or "").lower()


def merge_text(existing: str, cards, drive_folder: str = "", lang: str = "ko", card_word: str = ""):
    """기존 vCard 글 + 명함들 → (합친 글, {'merged': 같은 사람, 'added': 새 사람, 'lines': 더한 줄 수})."""
    old = parse_vcf(existing)
    stats = {"merged": 0, "added": 0, "lines": 0}
    extra_cards = []
    for c in cards:
        if not (c.get("name") or "").strip():
            continue
        new = parse_vcf(card_to_vcard(c, drive_folder, lang, card_word))[0]
        nm = _key_name(new["fn"])
        hit = next((o for o in old if _key_name(o["fn"] or o["n"]) == nm and (o["tels"] & new["tels"] - {""})), None)
        if hit is None:
            extra_cards.append(new)
            old.append(new)                  # 같은 파일 안 다음 명함과도 견준다
            stats["added"] += 1
            continue
        stats["merged"] += 1
        add = []
        for ln in new["lines"]:
            p = parse_line(ln)
            if not p:
                continue
            name, _pr, val = p
            if name == "TEL" and digits(val) not in hit["tels"]:
                add.append(ln); hit["tels"].add(digits(val))
            elif name == "EMAIL" and val.strip().lower() not in hit["emails"]:
                add.append(ln); hit["emails"].add(val.strip().lower())
            elif name in ("TITLE", "ADR", "URL"):
                k = (name, re.sub(r"\s+", "", unesc(val)).lower())
                if k not in hit["vals"]:
                    add.append(ln); hit["vals"].add(k)
            elif name == "NOTE":
                have = set(x.strip() for x in hit["note"].splitlines())
                more = [x for x in val.splitlines() if x.strip() and x.strip() not in have]
                if more:
                    note = "\n".join([x for x in hit["note"].splitlines()] + more) if hit["note"] else "\n".join(more)
                    hit["lines"] = [x for x in hit["lines"] if (parse_line(x) or ("",))[0] != "NOTE"]
                    add.append("NOTE:" + esc(note))
                    hit["note"] = note
        hit["lines"] += add
        stats["lines"] += len(add)
    out = []
    for o in old:
        out.append("BEGIN:VCARD\r\n")
        out += [fold(x) + "\r\n" for x in o["lines"]]
        out.append("END:VCARD\r\n")
    return "".join(out), stats


def merged_path(existing_path: str, suffix: str = "") -> str:
    """기존 파일 옆 `<이름>_합침.vcf`(있으면 ` (2)`) — 기존 파일은 덮어쓰지 않는다. suffix 는 결과물 언어(부르는 쪽 tr)."""
    if not suffix:
        suffix = tr("합침")
    stem, _ext = os.path.splitext(existing_path)
    p, k = "%s_%s.vcf" % (stem, suffix), 2
    while os.path.exists(p):
        p = "%s_%s (%d).vcf" % (stem, suffix, k)
        k += 1
    return p


# ── 주소록 가져오기(§5.24 D22·D23 — 구글 주소록·리멤버 명함첩 vCard) ──
def _parts(val: str) -> list:
    """N·ADR·ORG 의 ';' 칸 — 이스케이프된 세미콜론(역빗금 + ;)은 칸을 나누지 않는다."""
    out, cur, i = [], "", 0
    while i < len(val):
        ch = val[i]
        if ch == "\\" and i + 1 < len(val):
            cur += val[i:i + 2]
            i += 2
            continue
        if ch == ";":
            out.append(unesc(cur))
            cur = ""
        else:
            cur += ch
        i += 1
    out.append(unesc(cur))
    return out


SYSTEM_LABELS = ("mycontacts", "starred", "friends", "family", "coworkers", "blocked", "chatbuddies", "all", "imported")   # 구글 기본 라벨


def _tel_kind(params: dict) -> str:
    t = ",".join(params.get("TYPE", []) + [k for k, v in params.items() if v == [""]]).upper()
    return "fax" if "FAX" in t else "cell" if ("CELL" in t or "MOBILE" in t) else "work"


def people_from_vcf(text: str, card_words=()) -> list:
    """vCard 글 → 사람들 [{name, company, dept, title, phones[(종류, 번호)], emails, urls, address, memo}].
    우리가 내보낸 NOTE 의 '명함: 폴더/파일'·드라이브 찾기 줄은 메모로 들이지 않는다(card_words = 그 낱말들)."""
    out, cur = [], None
    words = tuple(w for w in card_words if w)
    labels, groups = set(), set()                      # 라벨 이름(CATEGORIES)·그룹 카드 — 사람이 아닌 카드는 넣지 않는다(261120-60)
    for ln in _unfold(text):
        u = ln.strip().upper()
        if u == "BEGIN:VCARD":
            cur = {"name": "", "n": "", "company": "", "dept": "", "title": "", "phones": [], "emails": [], "urls": [],
                   "address": "", "memo": "", "labels": []}
            continue
        if u == "END:VCARD":
            if cur is not None:
                cur["name"] = cur["name"] or cur.pop("n", "")
                cur.pop("n", None)
                if cur.pop("_group", False):
                    groups.add(id(cur))
                if cur["name"] or cur["phones"] or cur["emails"]:
                    out.append(cur)
            cur = None
            continue
        if cur is None:
            continue
        p = parse_line(ln)
        if not p:
            continue
        name, params, val = p
        if (name in ("KIND", "X-ADDRESSBOOKSERVER-KIND") and val.strip().lower() == "group") \
                or name in ("MEMBER", "X-ADDRESSBOOKSERVER-MEMBER"):
            cur["_group"] = True
        elif name == "CATEGORIES":
            got = [x.strip() for x in val.split(",") if x.strip()]
            labels.update(got)
            cur["labels"] += [x for x in got if x.lower() not in SYSTEM_LABELS and x not in cur["labels"]]   # 라벨 → 해시태그(261121)
        if name == "FN":
            cur["name"] = val.strip()
        elif name == "N":
            fam, giv = (_parts(val) + ["", ""])[:2]
            if _hangul(fam + giv) or not (fam and giv):
                cur["n"] = (fam + giv).strip()
            else:
                cur["n"] = (giv + " " + fam).strip()
        elif name == "ORG":
            ps = _parts(val) + [""]
            cur["company"], cur["dept"] = ps[0].strip(), " ".join(x.strip() for x in ps[1:] if x.strip())
        elif name == "TITLE":
            cur["title"] = val.strip()
        elif name == "TEL" and val.strip():
            cur["phones"].append((_tel_kind(params), _phone.normalize(val)))   # 번호 꼴 한 곳(§5.11)
        elif name == "EMAIL" and val.strip():
            cur["emails"].append(val.strip())
        elif name == "URL" and val.strip():
            cur["urls"].append(val.strip())
        elif name == "ADR" and not cur["address"]:
            cur["address"] = " ".join(x.strip() for x in _parts(val) if x.strip())
        elif name == "NOTE":
            keep = [x for x in val.splitlines() if x.strip() and not x.startswith(DRIVE_SEARCH)
                    and not any(x.startswith(w + ": ") and "/" in x for w in words)]
            cur["memo"] = "\n".join(keep)
    low = {x.lower() for x in labels}

    def person(c):
        if id(c) in groups:
            return False
        bare = not (c["phones"] or c["emails"] or c["company"])
        return not (bare and c["name"].strip().lower() in low)    # 라벨 이름뿐인 카드
    return [c for c in out if person(c)]
