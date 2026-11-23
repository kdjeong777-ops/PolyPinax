"""전화번호 꼴 — 명함의 모든 길(인식·명함찾기 세부 칸·명함 읽기 확인 표·vCard·주소록 가져오기)이 쓰는 한 곳(명함 SOT §5.11 '번호 꼴').

Qt 없음. 국내 꼴: 휴대폰 `010-1234-5678`(옛 01x 10자리 `011-123-4567`), 서울 `02-123-4567`/`02-1234-5678`,
그 밖 지역·070 등 `031-123-4567`/`031-1234-5678`, 050x `0505-123-4567`/`0504-1234-5678`, 대표번호 `1588-1234`.
`+82` 는 기본 국가가 한국이면 국내 꼴(`+82 10…` → `010-…`), 아니면 `+82-10-1234-5678`.
"""
import re

KR = "KR"
COUNTRIES = (KR, "")                 # "" = 지정 안 함(+82 도 국제 꼴 그대로)
DEFAULT_COUNTRY = KR
_PREF = "phone_country"              # settings.json preferences.picture.phone_country

_country = None                      # 읽어 둔 기본 국가(None = 아직 안 읽음)


def country() -> str:
    """기본 국가 — 설정을 처음 한 번만 읽는다(배경 인식에서도 파일을 다시 읽지 않게). 창을 열 때 `reload()`."""
    global _country
    if _country is None:
        reload()
    return _country


def reload():
    global _country
    c = DEFAULT_COUNTRY
    try:
        from viewer import settings_store
        pic = settings_store.peek_pref("picture")
        if isinstance(pic, dict) and pic.get(_PREF) in COUNTRIES:
            c = pic.get(_PREF)
    except Exception:
        pass
    _country = c


def set_country(c: str):
    """설정 적용·검사용."""
    global _country
    _country = c if c in COUNTRIES else DEFAULT_COUNTRY


def digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


OLD_MOBILE = ("011", "016", "017", "018", "019")   # 옛 휴대폰 앞자리 — 전화 칸에서 빼 메모로(명함 SOT §5.11 '번호 종류 바로잡기', 261120-55)
OLD_MEMO = "예전 휴대폰"                             # 메모 줄 머리 — 데이터라 번역하지 않는다(다국어 SOT §5)


def kr_digits(num: str):
    """한국 번호를 국내 꼴 숫자로(`+82`·`82…`·앞 0 빠진 01x 를 0 으로) — 외국 번호(+ 로 시작하는 82 아닌 것)면 None."""
    t = (num or "").strip()
    d = digits(t)
    if t.startswith("+"):
        return ("0" + d[2:].lstrip("0")) if d.startswith("82") else None
    if d.startswith("0082") and len(d) >= 13:                 # 국제 전화 꼴 0082(261120-72)
        return "0" + d[4:].lstrip("0")
    if d.startswith("82") and len(d) >= 11:
        return "0" + d[2:].lstrip("0")
    if not d.startswith("0") and len(d) == 10 and d[:2] in ("10", "11", "16", "17", "18", "19"):
        return "0" + d
    return d


def mobile_key(kind: str, num: str) -> str:
    """같은 사람을 가르는 휴대폰 열쇠(§5.24.8 '묶기') — 국내는 010 꼴만, 외국은 종류가 휴대폰일 때만, 팩스·일반 전화는 ''."""
    if kind == "fax":
        return ""
    d = kr_digits(num)
    if d is None:
        f = digits(num)
        return f if kind == "cell" and len(f) >= 9 else ""
    return d if d.startswith("010") and len(d) >= 10 else ""


def fix_kinds(phones):
    """번호 종류 바로잡기(261120-55) — 010 은 '휴대폰', 휴대폰인데 010 아니면 일반 전화, 옛 011·016~019 는 빼서 돌려준다(메모로).
    팩스·외국 번호는 그대로. 반환 (전화 목록[(종류, 번호)], 뺀 옛 휴대폰 번호들)."""
    out, old = [], []
    for x in phones or []:
        kind, num = (x[0], x[-1]) if isinstance(x, (list, tuple)) and len(x) >= 2 else ("", x)
        d = kr_digits(num) if kind != "fax" and num else None
        if d is not None:
            if d.startswith("010"):
                kind = "cell"
            elif d[:3] in OLD_MOBILE and len(d) in (10, 11):
                old.append(num)
                continue
            elif kind == "cell":
                kind = "work"
        out.append((kind, num))
    return out, old


def memo_with_old(memo: str, old) -> str:
    """옛 휴대폰 번호를 메모 끝에 `예전 휴대폰 011-…` 줄로 — 같은 줄이 있으면 다시 넣지 않는다."""
    memo = memo or ""
    lines = memo.split("\n") if memo else []
    for n in old or []:
        line = "%s %s" % (OLD_MEMO, n)
        if line not in lines:
            lines.append(line)
    return "\n".join(lines)


def format_kr(d: str) -> str:
    """국내 번호 숫자(0 또는 1로 시작) → 하이픈 꼴. 알 수 없는 길이면 ""."""
    n = len(d)
    if d.startswith("02"):
        if n == 9:
            return "02-%s-%s" % (d[2:5], d[5:])
        if n == 10:
            return "02-%s-%s" % (d[2:6], d[6:])
        return ""
    if d.startswith("050") and n in (11, 12):
        return "%s-%s-%s" % (d[:4], d[4:-4], d[-4:])
    if d.startswith("0") and n in (10, 11):
        return "%s-%s-%s" % (d[:3], d[3:-4], d[-4:])
    if n == 8 and d[:2] in ("15", "16", "18"):
        return "%s-%s" % (d[:4], d[4:])
    return ""


def to_intl(num: str) -> str:
    """국내 꼴 `010-1234-5678` → `+82-10-1234-5678`."""
    return "+82-" + num[1:] if num.startswith("0") else num


def normalize(s: str, ctry: str = None) -> str:
    """적어 둘 꼴. 번호가 아닌 글(내선·낱말이 섞인 것)이나 알 수 없는 길이는 그대로 둔다(지우지 않는다)."""
    t = (s or "").strip()
    if not t or re.search(r"[^\d\s.\-()+·]", t):
        return t
    ctry = country() if ctry is None else ctry
    d = digits(t)
    if t.startswith("+"):
        if d.startswith("82"):
            dom = format_kr("0" + d[2:].lstrip("0"))
            if dom:
                return dom if ctry == KR else to_intl(dom)
        groups = re.findall(r"\d+", t)
        return "+" + "-".join(groups)
    return format_kr(d) or t


def _partial(d: str) -> str:
    """치는 중인 국내 번호 숫자 → 지금까지의 하이픈 꼴(`format_typing`)."""
    n = len(d)
    if not d:
        return ""
    if d.startswith("02"):
        if n <= 2:
            return d
        if n <= 5:
            return "02-" + d[2:]
        if n <= 9:
            return "02-%s-%s" % (d[2:5], d[5:])
        if n == 10:
            return "02-%s-%s" % (d[2:6], d[6:])
        return d
    if d.startswith("050"):
        if n <= 4:
            return d
        if n <= 7:
            return d[:4] + "-" + d[4:]
        if n <= 11:
            return "%s-%s-%s" % (d[:4], d[4:7], d[7:])
        if n == 12:
            return "%s-%s-%s" % (d[:4], d[4:8], d[8:])
        return d
    if d.startswith("010"):                    # 지금 휴대폰은 늘 3-4-4 — 치는 중에 가운데가 3↔4 로 흔들리지 않게
        if n <= 3:
            return d
        if n <= 7:
            return "010-" + d[3:]
        if n <= 11:
            return "010-%s-%s" % (d[3:7], d[7:])
        return d
    if d.startswith("0"):
        if n <= 3:
            return d
        if n <= 6:
            return d[:3] + "-" + d[3:]
        if n <= 10:
            return "%s-%s-%s" % (d[:3], d[3:6], d[6:])
        if n == 11:
            return "%s-%s-%s" % (d[:3], d[3:7], d[7:])
        return d
    if d[:2] in ("15", "16", "18"):
        if n <= 4:
            return d
        if n <= 8:
            return d[:4] + "-" + d[4:]
        return d
    return d


def format_typing(text: str, cursor: int, prev: str = "") -> tuple:
    """입력 칸에서 친 대로 하이픈을 넣는다 → (새 글, 새 커서). 사용자가 친 `-` 는 숫자 자리로 다시 맞춰져 겹치지 않는다.
    `+` 국제 번호·숫자 아닌 글이 섞이면 그대로(칸을 떠날 때 `normalize`). 하이픈 하나를 지웠으면(숫자는 그대로) 그 앞 숫자를 지운다."""
    if text.startswith("+") or re.search(r"[^\d\s.\-()]", text):
        return text, cursor
    cursor = max(0, min(cursor, len(text)))
    k = len(digits(text[:cursor]))             # 커서 앞 숫자 수 — 꼴이 바뀌어도 같은 숫자 뒤에 커서
    d = digits(text)
    if prev and len(text) < len(prev) and d == digits(prev) and k > 0:
        d = d[:k - 1] + d[k:]                  # 하이픈만 지운 Backspace → 그 앞 숫자를 지운다
        k -= 1
    new = _partial(d)
    pos, seen = 0, 0
    if k:
        for i, ch in enumerate(new):
            if ch.isdigit():
                seen += 1
                if seen == k:
                    pos = i + 1
                    break
    return new, pos


def attach(edit):
    """QLineEdit 에 '치는 대로 하이픈'·'떠날 때 적을 꼴' 을 붙인다(명함찾기 세부 칸·확인 표 전화 칸 편집기)."""
    state = {"prev": edit.text()}

    def on_edited(t):
        new, pos = format_typing(t, edit.cursorPosition(), state["prev"])
        if new != t:
            edit.setText(new)
            edit.setCursorPosition(pos)
        state["prev"] = new

    def on_done():
        n = normalize(edit.text())
        if n != edit.text():
            edit.setText(n)
        state["prev"] = edit.text()

    edit.textEdited.connect(on_edited)
    edit.editingFinished.connect(on_done)
    edit.textChanged.connect(lambda t: state.__setitem__("prev", t) if t != state["prev"] and not edit.isModified() else None)
    edit._phone_state = state
    return edit
