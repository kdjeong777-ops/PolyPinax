"""명함 인식 — 원천 그림 → OCR(로컬 Tesseract) → 칸 뽑기(규칙) → 후보와 점수 (명함 SOT §5.2, P1 261117-2).

★ 개인정보(명함 SOT §2.1): 완전 오프라인. 이 모듈은 명함 글을 로그·예외 메시지·print 에 싣지 않는다.
OCR 의 언어·쪽 나누기(psm)·실행 길은 단어학습 SOT §14.B 가 소유한다 — 여기서는 `ocr.DEFAULT_LANG`·
`ocr.DEFAULT_PSM`·`tess_run.data` 를 그대로 쓰고 값을 다시 적지 않는다.

뼈대
- `card_sources(path)` — 원본 PDF(1쪽 앞면·2쪽 뒷면)가 있으면 PDF, 없으면 그림 파일(앞·뒤 짝 이름으로)
- `read_side(images)` — 한 면을 두 번 읽어(PDF: 300 dpi 그대로 + 150 dpi×3 / 그림: 작으면 3배) 낱말 줄 목록
- `parse_lines(lines, hint)` — 줄 목록 → `SideResult`(전화·메일·누리집·이름/회사 후보·직함·주소·글자 비율)
- `merge_sides(front, back, hint)` — 앞뒤를 합쳐 `CardResult`(한글 칸·영문 칸, 홍보 면 판정)
- `recognize(path)` — 위를 차례로
- `card_filename(name, company)` — `성명_회사명`(명함 SOT §5.4)
"""
from __future__ import annotations

import io
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── 상수 (명함 SOT §4.2.1·§5.2) ──────────────────────────────────────────
CONTACT_DPI = 300        # 전화·메일·주소용 — 원본 PDF 그대로
NAME_DPI = 150           # 이름·회사용 — 낮게 그린 뒤
NAME_UPSCALE = 3         #   Lanczos 로 키운다(크고 장식적인 글꼴이 매끈해진다, 실측 §4.2.1)
SMALL_SIDE = 1000        # 그림 파일의 긴 변이 이보다 작으면 NAME_UPSCALE 배로 키워 읽는다
MAX_SIDE = 4000          # 키운 뒤 긴 변 상한(사진 OCR 상한과 같은 뜻 — 단어학습 SOT §14.22)
WORD_MIN_CONF = 0        # 신뢰도가 음수(글자 아님)인 것만 버린다 — 장식 글꼴 이름은 신뢰도가 낮아도 맞는 일이 많다(실측: 문턱 20 이면 이름 3위 안 10/26 → 0 이면 20/26)
IMG_EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp")
FRONT_SUFFIXES = ("_p0001", "_1")
BACK_SUFFIXES = ("_p0002", "_2")

# ── 사전(규칙) ───────────────────────────────────────────────────────────
# 한국 성씨(인구 상위 + 복성) — 이름 후보 점수용
SURNAMES = set("김이박최정강조윤장임한오서신권황안송류유홍전고문양손배백허남심노하곽성차주우구민진나지엄채원천방공현함변염여추도소석선설마길연위표명기반왕금옥육인맹제모탁국어은편용예봉경사부황보")
COMPOUND_SURNAMES = ("남궁", "황보", "제갈", "선우", "독고", "사공", "서문", "동방")
TITLES_KO = ("대표이사", "대표", "회장", "부회장", "사장", "부사장", "전무", "상무", "이사", "감사", "본부장", "실장",
             "센터장", "원장", "소장", "단장", "처장", "국장", "부장", "차장", "과장", "대리", "주임", "사원", "팀장",
             "파트장", "책임", "선임", "수석", "연구원", "연구위원", "위원", "교수", "부교수", "조교수", "박사", "공학박사",
             "기술사", "감리단장", "현장소장", "매니저", "프로", "고문", "자문위원", "사무관", "주무관", "서기관", "과장대리")
DEPT_KO = ("부", "팀", "실", "본부", "센터", "연구소", "사업단", "사업부", "그룹", "처", "과", "국", "학과")
TITLES_EN = ("ceo", "president", "director", "manager", "engineer", "professor", "researcher", "chairman", "vice",
             "executive", "general", "senior", "principal", "head", "chief", "officer", "ph.d", "phd", "dr.",
             "team leader", "leader", "consultant", "associate", "assistant")
CORP_MARKS_KO = ("주식회사", "유한회사", "합자회사", "사단법인", "재단법인", "(주)", "㈜", "(유)", "(사)", "(재)",
                 "(株)", "( 주)", "(주 )")
ORG_WORDS_KO = ("회사", "기업", "건설", "산업", "기술", "엔지니어링", "공사", "공단", "협회", "학회", "연구원", "연구소",
                "대학교", "대학", "아스콘", "개발", "그룹", "컨설팅", "공업", "화학", "테크", "솔루션", "시스템", "조합",
                "재단", "은행", "청", "시청", "구청", "도청", "부", "처", "원")
CORP_MARKS_EN = re.compile(r"\b(co\.?,?\s*ltd\.?|corp(oration)?\.?|inc\.?|ltd\.?|llc|company|co\.)\b", re.I)
ORG_WORDS_EN = ("university", "institute", "engineering", "construction", "consultants", "corporation", "company",
                "association", "ministry", "korea", "group", "technology", "college", "school", "department", "center")
FREE_MAIL = ("gmail", "naver", "hanmail", "daum", "nate", "hotmail", "yahoo", "kakao", "outlook", "korea.com",
             "empal", "dreamwiz", "paran", "lycos", "chol", "hanmir", "live", "icloud", "me.com")
# 성의 로마자(메일 아이디와 닮음)
SURNAME_ROMAN = {"김": ("kim", "gim"), "이": ("lee", "yi", "rhee", "ri"), "박": ("park", "pak", "bak"),
                 "최": ("choi", "choe", "chae"), "정": ("jung", "jeong", "chung", "jeung"), "강": ("kang", "gang"),
                 "조": ("cho", "jo", "joe"), "윤": ("yoon", "yun"), "장": ("jang", "chang"), "임": ("lim", "im", "yim"),
                 "한": ("han",), "오": ("oh", "o"), "서": ("seo", "suh", "sur"), "신": ("shin", "sin"),
                 "권": ("kwon", "gwon"), "황": ("hwang",), "안": ("ahn", "an"), "송": ("song",), "류": ("ryu", "yu", "you"),
                 "유": ("yoo", "yu", "you"), "홍": ("hong",), "전": ("jeon", "jun", "chun"), "고": ("ko", "go"),
                 "문": ("moon", "mun"), "양": ("yang",), "손": ("son", "sohn"), "배": ("bae", "pae"),
                 "백": ("baek", "paik", "back"), "허": ("heo", "hur", "huh"), "남": ("nam",), "노": ("noh", "roh", "no"),
                 "하": ("ha",), "곽": ("kwak",), "성": ("sung", "seong"), "차": ("cha",), "주": ("joo", "ju", "chu"),
                 "우": ("woo", "wu"), "구": ("koo", "ku", "gu"), "민": ("min",), "진": ("jin",), "나": ("na", "ra"),
                 "지": ("ji",), "엄": ("eom", "um"), "채": ("chae",), "원": ("won",), "천": ("chun", "cheon"),
                 "방": ("bang",), "공": ("kong",), "현": ("hyun",), "함": ("ham",), "변": ("byun",), "염": ("yeom",),
                 "여": ("yeo",), "추": ("choo", "chu"), "도": ("do", "doh"), "소": ("so",), "석": ("seok", "suk"),
                 "선": ("sun",), "설": ("seol",), "마": ("ma",), "길": ("gil",), "연": ("yeon",), "위": ("wi", "wee"),
                 "표": ("pyo",), "명": ("myung",), "기": ("ki",), "반": ("ban",), "왕": ("wang",), "금": ("keum",),
                 "옥": ("ok",), "육": ("yook",), "인": ("in",), "맹": ("maeng",), "제": ("je",), "모": ("mo",),
                 "탁": ("tak",), "국": ("kook",), "어": ("eo",), "은": ("eun",), "편": ("pyun",), "용": ("yong",),
                 "예": ("ye",), "봉": ("bong",), "경": ("kyung",)}

_HANGUL = re.compile(r"[가-힣]")
_LATIN = re.compile(r"[A-Za-z]")
_PHONE = re.compile(r"(?<!\d)(\+?82[\s.\-)]*)?\(?0?(\d{1,3})\)?[\s.\-)]{0,3}(\d{3,4})[\s.\-]{1,3}(\d{4})(?!\d)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+")
_URL = re.compile(r"\b(?:https?://)?(?:www\.)[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+(?:/\S*)?", re.I)
_ADDR_KO = re.compile(r"(특별시|광역시|특별자치시|특별자치도|[가-힣]+도\b|[가-힣]+시\b|[가-힣]+군\b|[가-힣]+구\b)"
                      r".*(로|길|동|읍|면|리)\s*\d*")
_LABEL_CELL = re.compile(r"(^|[\s\[(])(m|mo|mob|mobile|h\.?p|c\.?p|cell|휴대폰|휴대|핸드폰|모바일)[\s.:)\]]", re.I)
_LABEL_FAX = re.compile(r"(^|[\s\[(])(f|fax|팩스|전송)[\s.:)\]]", re.I)
_LABEL_TEL = re.compile(r"(^|[\s\[(])(t|tel|phone|전화|직통|대표)[\s.:)\]]", re.I)
_AREA = {"2", "31", "32", "33", "41", "42", "43", "44", "51", "52", "53", "54", "55", "61", "62", "63", "64",
         "70", "80", "50", "60"}
_MOBILE = {"10", "11", "16", "17", "18", "19"}


# ── 결과 꼴 ──────────────────────────────────────────────────────────────
@dataclass
class Cand:
    text: str
    score: float
    why: tuple = ()


@dataclass
class SideResult:
    phones: list = field(default_factory=list)        # [(kind, "010-0000-0000")] kind: cell|work|fax
    emails: list = field(default_factory=list)
    urls: list = field(default_factory=list)
    names_ko: list = field(default_factory=list)      # [Cand] 점수 내림차순
    names_en: list = field(default_factory=list)
    companies_ko: list = field(default_factory=list)
    companies_en: list = field(default_factory=list)
    titles_ko: list = field(default_factory=list)
    titles_en: list = field(default_factory=list)
    address_ko: str = ""
    address_en: str = ""
    hangul: int = 0
    latin: int = 0
    conf: float = 0.0

    @property
    def has_contact(self) -> bool:
        return bool(self.phones or self.emails)


@dataclass
class CardResult:
    name: str = ""
    company: str = ""
    title: str = ""
    phones: list = field(default_factory=list)
    emails: list = field(default_factory=list)
    urls: list = field(default_factory=list)
    address: str = ""
    en: dict = field(default_factory=dict)             # name·company·title·address (R7 영문 따로)
    name_cands: list = field(default_factory=list)     # [Cand] — 확인 표 고르기 칸(상위 3)
    company_cands: list = field(default_factory=list)
    langs: tuple = ()                                  # ("한글",) / ("영어",) / 둘 다 — 해시태그용
    back_promo: Optional[bool] = None                  # 뒷면이 연락처 없는 홍보 면이면 True, 뒷면이 없으면 None
    need_check: tuple = ()                             # 사람 확인이 필요한 칸 이름들
    sources: dict = field(default_factory=dict)        # {"front": 경로, "back": 경로, "pdf": 경로}


# ── 이름·회사 다듬기 ──────────────────────────────────────────────────────
def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


def clean_name_ko(s: str) -> str:
    """한글 이름 — 빈칸·기호를 뺀다(성과 이름을 붙여 쓴다, R3)."""
    return re.sub(r"[^가-힣]", "", _nfc(s))


def clean_name_en(s: str) -> str:
    s = re.sub(r"[^A-Za-z .'\-]", " ", _nfc(s))
    return re.sub(r"\s+", " ", s).strip()


def strip_corp(s: str) -> str:
    """회사명에서 법인 꼴·앞뒤 기호를 뗀다(R4). 한 글자씩 띄운 회사명은 붙인다."""
    t = _nfc(s)
    t = re.sub(r"\(\s*([주유사재株])\s*\)", "", t)
    for m in CORP_MARKS_KO:
        t = t.replace(m, " ")
    t = CORP_MARKS_EN.sub(" ", t)
    t = re.sub(r"[|•·◆◇■□▶►●○◎*#^~`_]+", " ", t)
    t = re.sub(r"(?<=[가-힣])\s+(?=[가-힣])", "", t)    # 한글 회사명은 붙여 쓴다 — OCR 의 띄어 읽기('가 나 다 기술')를 믿지 않는다
    t = re.sub(r"\s+", " ", t).strip(" ,.-_()[]{}<>'\"")
    return t


def card_filename(name: str, company: str, ext: str = ".jpg") -> str:
    """`성명_회사명.jpg`(명함 SOT §5.4). 회사가 없으면 `성명.jpg`. 파일 이름에 못 쓰는 글자는 뺀다."""
    def safe(x):
        x = re.sub(r'[\\/:*?"<>|\r\n\t]', "", _nfc(x)).strip(" .")
        return x
    n = safe(clean_name_ko(name) if _HANGUL.search(name or "") and not _LATIN.search(name or "") else clean_name_en(name))
    c = safe(strip_corp(company))
    base = "_".join(x for x in (n, c) if x) or "명함"
    return base + ext


def parse_hint(path) -> tuple:
    """ScanSnap 이 붙인 파일 이름 `회사_이름(_p0001|_1)` → (이름 힌트, 회사 힌트). 부정확할 수 있다(후보 점수에만)."""
    stem = Path(path).stem
    for suf in FRONT_SUFFIXES + BACK_SUFFIXES:
        if stem.endswith(suf):
            stem = stem[: -len(suf)]
            break
    if "_" not in stem:
        return "", ""
    comp, nm = stem.rsplit("_", 1)
    nm_ko = re.sub(r"공학박사|박사|[^가-힣]", "", nm)
    if 2 <= len(nm_ko) <= 4:
        name = nm_ko
    elif _LATIN.search(nm) and not _HANGUL.search(nm):
        name = clean_name_en(nm)
    else:
        name = ""
    return name, strip_corp(comp)


# ── 원천 ─────────────────────────────────────────────────────────────────
def _stem_base(p: Path) -> str:
    s = p.stem
    for suf in FRONT_SUFFIXES + BACK_SUFFIXES:
        if s.endswith(suf):
            return s[: -len(suf)]
    return s


def card_sources(path, pdf_dir_name: str = "pdf") -> dict:
    """한 명함의 원천 — {"pdf": 원본 PDF 또는 None, "front": 그림, "back": 그림 또는 None}.

    `path` 는 앞면 그림·뒷면 그림·원본 PDF 어느 것이든. 원본 PDF 는 그림 폴더의 하위 `pdf\\<앞부분>.pdf`
    (D2 — 사용자 자료 실측). PDF 가 있으면 인식은 PDF 로(명함 SOT §5.2 의 1)."""
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        pdf = p
        folder = p.parent.parent if p.parent.name.lower() == pdf_dir_name else p.parent
        base = p.stem
    else:
        folder = p.parent
        base = _stem_base(p)
        cand = folder / pdf_dir_name / (base + ".pdf")
        pdf = cand if cand.exists() else None
    front = back = None
    for suf in FRONT_SUFFIXES:
        for ext in IMG_EXTS:
            q = folder / (base + suf + ext)
            if q.exists():
                front = front or q
    for suf in BACK_SUFFIXES:
        for ext in IMG_EXTS:
            q = folder / (base + suf + ext)
            if q.exists():
                back = back or q
    if front is None and p.suffix.lower() in IMG_EXTS and p.stem.endswith(BACK_SUFFIXES) is False:
        front = p
    return {"pdf": pdf, "front": front, "back": back}


def _pil():
    from PIL import Image, ImageOps
    return Image, ImageOps


def _render_pdf_page(doc, i: int, dpi: int):
    Image, _ = _pil()
    pix = doc[i].get_pixmap(dpi=dpi)
    return Image.open(io.BytesIO(pix.tobytes("png")))


def _upscale(im, k: float):
    Image, _ = _pil()
    w, h = im.size
    k = min(k, MAX_SIDE / max(w, h)) if max(w, h) * k > MAX_SIDE else k
    if k <= 1.0:
        return im
    return im.resize((int(w * k), int(h * k)), Image.LANCZOS)


def side_images(src: dict) -> dict:
    """{"front": [그림, …], "back": [그림, …]} — 면마다 두 번 읽을 그림(앞 = 연락처용, 뒤 = 이름용)."""
    Image, ImageOps = _pil()
    out = {"front": [], "back": []}
    if src.get("pdf"):
        import fitz
        doc = fitz.open(str(src["pdf"]))
        try:
            for i, side in ((0, "front"), (1, "back")):
                if i < doc.page_count:
                    out[side] = [_render_pdf_page(doc, i, CONTACT_DPI),
                                 _upscale(_render_pdf_page(doc, i, NAME_DPI), NAME_UPSCALE)]
        finally:
            doc.close()
        return out
    for side in ("front", "back"):
        p = src.get(side)
        if not p:
            continue
        im = ImageOps.exif_transpose(Image.open(str(p)))
        im.load()
        if max(im.size) < SMALL_SIDE:
            out[side] = [_upscale(im, NAME_UPSCALE)]
        else:
            out[side] = [im, _upscale(im.resize((im.width // 2, im.height // 2)), NAME_UPSCALE)]
    return out


# ── OCR ─────────────────────────────────────────────────────────────────
@dataclass
class Line:
    text: str
    height: float          # 줄에서 가장 큰 낱말 높이(그림 픽셀 ÷ 그림 높이 — 그림 크기와 무관한 비율)
    conf: float
    y: float               # 줄 위치(그림 높이 비율)


NAME_EXTRA_PSM = 11      # 이름용 덧읽기 — 흩어진 글(sparse). 기본 읽기에 없던 이름 26 중 9 를 찾았다(명함 SOT §4.4)


def ocr_lines(im, psm: int = 0, invert: bool = False) -> list:
    """그림 → [Line]. 언어·기본 psm 은 단어학습 SOT §14.B 기본값(코드 상수). `psm`·`invert` 는 이름 덧읽기용."""
    from viewer.study import ocr as O
    from viewer.study import tess_run
    _, ImageOps = _pil()
    info = O.ensure_tesseract()
    if not info.get("ok"):
        raise RuntimeError("Tesseract 사용 불가")
    g = ImageOps.autocontrast(im.convert("L"))
    if invert:
        g = ImageOps.invert(g)                         # 어두운 바탕에 흰 글자
    lang = O.resolve_lang(O.DEFAULT_LANG)
    d = tess_run.data([g], lang, "--psm %d" % (psm or O.DEFAULT_PSM))[0]
    H = float(g.height or 1)
    groups = {}
    order = []
    n = len(d.get("text", []))
    for i in range(n):
        w = (d["text"][i] or "").strip()
        try:
            c = float(d["conf"][i])
        except (TypeError, ValueError):
            c = -1
        if not w or c < WORD_MIN_CONF:
            continue
        k = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append((d["left"][i], w, float(d["height"][i]), c, float(d["top"][i])))
    out = []
    for k in order:
        ws = sorted(groups[k])
        out.append(Line(" ".join(x[1] for x in ws), max(x[2] for x in ws) / H,
                        sum(x[3] for x in ws) / len(ws), min(x[4] for x in ws) / H))
    return out


# ── 칸 뽑기 ──────────────────────────────────────────────────────────────
_DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "Q": "0", "D": "0", "I": "1", "l": "1", "|": "1", "i": "1",
                            "S": "5", "B": "8", "Z": "2"})


def _fix_digits(s: str) -> str:
    """전화번호처럼 보이는 덩어리(숫자 5개 이상 + 구분자) 안의 글자 오인식만 고친다(낱말은 건드리지 않는다)."""
    def fix(m):
        t = m.group(0)
        return t.translate(_DIGIT_FIX) if len(re.findall(r"\d", t)) >= 5 else t
    return re.sub(r"[\d(+][\dOoQDIl|iSBZ\s.\-)]{7,}[\dOoQDIl|iSBZ]", fix, s)


def norm_phone(area: str, mid: str, last: str, intl: bool = False) -> Optional[str]:
    a = area.lstrip("0")
    if a in _MOBILE:
        return "0%s-%s-%s" % (a, mid, last) if len(mid) in (3, 4) else None
    if a in _AREA:
        if a == "2" and len(mid) in (3, 4):
            return "02-%s-%s" % (mid, last)
        return "0%s-%s-%s" % (a, mid, last) if len(mid) in (3, 4) else None
    if a in ("1",) or (len(a) == 3 and a.startswith("15")) or (len(a) == 3 and a.startswith("16")):
        return None
    return None


def phone_kind(line: str, number: str, pos: int) -> str:
    before = line[:pos][-12:]
    if _LABEL_FAX.search(" " + before):
        return "fax"
    if _LABEL_CELL.search(" " + before):
        return "cell"
    if number.startswith("01"):
        return "cell"
    return "work"


def find_phones(text: str) -> list:
    out = []
    t = _fix_digits(text)
    for m in _PHONE.finditer(t):
        num = norm_phone(m.group(2), m.group(3), m.group(4), bool(m.group(1)))
        if num:
            out.append((phone_kind(t, num, m.start()), num))
    return out


def find_emails(text: str) -> list:
    t = text.replace("©", "@").replace("(at)", "@").replace("[at]", "@")
    t = re.sub(r"\s*@\s*", "@", t)
    t = re.sub(r"(?<=[A-Za-z0-9])\s*[,;]\s*(?=(com|net|kr|org|co|re|ac|go|or)\b)", ".", t)
    out = []
    for m in _EMAIL.finditer(t):
        e = m.group(0).strip(".-").lower()
        if e.count("@") == 1 and "." in e.split("@")[1]:
            out.append(e)
    return out


def find_urls(text: str) -> list:
    return [m.group(0).rstrip(".,;").lower() for m in _URL.finditer(text)]


def _is_titleish(s: str) -> bool:
    return any(t in s for t in TITLES_KO)


def _is_orgish(s: str) -> bool:
    return any(m in s for m in CORP_MARKS_KO) or any(s.endswith(w) or (w in s and len(w) >= 2) for w in ORG_WORDS_KO)


def _surname_score(n: str) -> float:
    if n[:2] in COMPOUND_SURNAMES and len(n) in (3, 4):
        return 1.0
    return 1.0 if n[0] in SURNAMES else -1.5


def _email_hint(n: str, emails: list) -> float:
    rom = SURNAME_ROMAN.get(n[0], ())
    for e in emails:
        local = re.sub(r"[^a-z]", "", e.split("@")[0])
        if any(local.startswith(r) or local.endswith(r) for r in rom):
            return 0.8
    return 0.0


def name_candidates_ko(lines: list, emails: list, hint: str = "") -> list:
    """한글 이름 후보(R3) — 큰 글자·성씨·직함 이웃·메일 아이디·파일 이름 힌트로 점수(명함 SOT §5.2 의 3)."""
    cands = {}
    hmax = max((ln.height for ln in lines), default=1) or 1
    for idx, ln in enumerate(lines):
        raw = ln.text
        near = " ".join(x.text for x in lines[max(0, idx - 1): idx + 2])
        pieces = set()
        whole = clean_name_ko(re.sub("|".join(TITLES_KO), " ", raw))
        if 2 <= len(whole) <= 4 and len(re.sub(r"[^가-힣\s]", "", raw).split()) <= 4:
            pieces.add(whole)                       # '홍 길 동' · '홍길동 부장' → '홍길동'
        for run in re.findall(r"[가-힣]+", re.sub("|".join(sorted(TITLES_KO, key=len, reverse=True)), " ", raw)):
            if 2 <= len(run) <= 4:
                pieces.add(run)
            elif len(run) > 4:                      # '홍길동부장'·'기술연구소홍길동' — 성씨 자리에서 3·2자 조각
                for i, ch in enumerate(run):
                    if ch in SURNAMES:
                        for L in (3, 2):
                            if i + L <= len(run):
                                pieces.add(run[i:i + L])
        for n in pieces:
            if n in TITLES_KO or any(n.endswith(d) and len(n) > 2 for d in ("회사", "기술", "건설", "산업")):
                continue
            s = 0.0
            why = []
            s += 2.0 * (ln.height / hmax); why.append("크기")
            s += _surname_score(n)
            if _is_titleish(near):
                s += 1.2; why.append("직함")
            if _is_orgish(raw) or _ADDR_KO.search(raw):
                s -= 2.0
            if n not in re.findall(r"[가-힣]+", raw) and n != whole:
                s -= 0.5                            # 긴 낱말에서 떼어 낸 조각
            if len(n) == 3:
                s += 0.6
            elif len(n) == 2:
                s += 0.1
            elif len(n) == 4:
                s -= 0.4
            s += _email_hint(n, emails)
            if hint and n == hint:
                s += 1.5; why.append("파일이름")
            s += 0.01 * ln.conf
            if n not in cands or cands[n].score < s:
                cands[n] = Cand(n, round(s, 3), tuple(why))
    return sorted(cands.values(), key=lambda c: -c.score)


def name_candidates_en(lines: list, emails: list, hint: str = "") -> list:
    cands = {}
    hmax = max((ln.height for ln in lines), default=1) or 1
    for idx, ln in enumerate(lines):
        t = ln.text.strip()
        if _HANGUL.search(t) or "@" in t or re.search(r"\d", t):
            continue
        low = t.lower()
        if CORP_MARKS_EN.search(t) or any(w in low for w in ORG_WORDS_EN):
            continue
        nm = re.sub(r",?\s*(ph\.?\s?d\.?|p\.?e\.?|m\.?s\.?)$", "", t, flags=re.I)
        words = [w for w in nm.replace(",", " ").split() if w]
        if not (2 <= len(words) <= 4) or not all(re.fullmatch(r"[A-Z][A-Za-z'\-]*\.?", w) for w in words):
            continue
        if any(w.lower().strip(".") in TITLES_EN for w in words):
            continue
        n = " ".join(words)
        near = " ".join(x.text.lower() for x in lines[max(0, idx - 1): idx + 2])
        s = 2.0 * (ln.height / hmax) + (1.0 if any(k in near for k in TITLES_EN) else 0.0)
        local = re.sub(r"[^a-z]", "", (emails[0].split("@")[0] if emails else ""))
        if local and any(w.lower().strip(".") in local for w in words if len(w) > 1):
            s += 0.8
        if hint and n.lower() == hint.lower():
            s += 1.5
        cands[n] = Cand(n, round(s, 3))
    return sorted(cands.values(), key=lambda c: -c.score)


def company_candidates_ko(lines: list, emails: list, urls: list, hint: str = "") -> list:
    cands = {}
    hmax = max((ln.height for ln in lines), default=1) or 1
    for ln in lines:
        raw = ln.text
        if not _HANGUL.search(raw) or _ADDR_KO.search(raw) or find_phones(raw) or "@" in raw:
            continue
        has_mark = any(m in raw for m in CORP_MARKS_KO)
        org = _is_orgish(raw)
        if not (has_mark or org):
            continue
        c = strip_corp(re.sub("|".join(TITLES_KO), " ", raw))
        c = re.sub(r"\s+", " ", c).strip()
        if not (2 <= len(re.sub(r"\s", "", c)) <= 30):
            continue
        s = 1.0 * (ln.height / hmax) + (2.0 if has_mark else 0.8)
        if hint and (c.replace(" ", "") == hint.replace(" ", "")):
            s += 1.5
        if c not in cands or cands[c].score < s:
            cands[c] = Cand(c, round(s, 3))
    if hint and hint not in cands and _HANGUL.search(hint):
        cands[hint] = Cand(hint, 0.5, ("파일이름",))
    return sorted(cands.values(), key=lambda c: -c.score)


def company_candidates_en(lines: list, emails: list, urls: list) -> list:
    cands = {}
    for ln in lines:
        t = ln.text.strip()
        if _HANGUL.search(t) or "@" in t:
            continue
        if CORP_MARKS_EN.search(t) or any(w in t.lower() for w in ORG_WORDS_EN):
            c = re.sub(r"\s+", " ", t).strip(" ,.")
            if 3 <= len(c) <= 60 and not re.search(r"\d{3}", c):
                cands[c] = Cand(c, 2.0 if CORP_MARKS_EN.search(t) else 1.0)
    for e in emails:
        dom = e.split("@")[1].split(".")[0]
        if dom and not any(f.split(".")[0] == dom for f in FREE_MAIL):
            cands.setdefault(dom, Cand(dom, 0.3, ("메일",)))
    return sorted(cands.values(), key=lambda c: -c.score)


def titles_of(lines: list) -> tuple:
    ko, en = [], []
    for ln in lines:
        for t in TITLES_KO:
            if t in ln.text and t not in ko:
                ko.append(t)
        low = ln.text.lower()
        if not _HANGUL.search(ln.text) and any(k in low for k in TITLES_EN) and len(ln.text) < 60 \
                and not re.search(r"\d{3}", ln.text):
            en.append(ln.text.strip())
    # 긴 직함 먼저('대표이사' 가 '대표'·'이사' 를 덮는다)
    ko = [t for t in ko if not any(t != u and t in u for u in ko)]
    return ko, en


def address_of(lines: list) -> tuple:
    ko = en = ""
    for ln in lines:
        t = ln.text
        if not ko and _ADDR_KO.search(t) and not find_emails(t):
            ko = re.sub(r"^(주소|addr\.?|a\.?)\s*[:.]?\s*", "", t, flags=re.I).strip()
        if not en and not _HANGUL.search(t) and re.search(r"\b(seoul|busan|incheon|daegu|daejeon|gwangju|ulsan|sejong|"
                                                          r"gyeonggi|korea|-gu|-si|-do|-ro|-gil)\b", t, re.I) \
                and re.search(r"\d", t) and not find_phones(t):
            en = t.strip()
    return ko, en


def parse_lines(lines: list, hint_name: str = "", hint_company: str = "", name_extra: list = ()) -> SideResult:
    """한 면의 줄 목록 → `SideResult`. OCR 없이도 시험할 수 있는 순수 함수."""
    r = SideResult()
    txt = "\n".join(ln.text for ln in lines)
    seen = set()
    for ln in lines:
        for kind, num in find_phones(ln.text):
            if num not in seen:
                seen.add(num)
                r.phones.append((kind, num))
    r.emails = list(dict.fromkeys(find_emails(txt)))
    r.urls = list(dict.fromkeys(find_urls(txt)))
    r.hangul = len(_HANGUL.findall(txt))
    r.latin = len(_LATIN.findall(re.sub(_EMAIL, "", txt)))
    hk = hint_name if _HANGUL.search(hint_name or "") else ""
    he = hint_name if hint_name and not hk else ""
    r.names_ko = name_candidates_ko(list(lines) + list(name_extra), r.emails, hk)
    r.names_en = name_candidates_en(lines, r.emails, he)
    r.companies_ko = company_candidates_ko(lines, r.emails, r.urls, hint_company)
    r.companies_en = company_candidates_en(lines, r.emails, r.urls)
    r.titles_ko, r.titles_en = titles_of(lines)
    r.address_ko, r.address_en = address_of(lines)
    r.conf = sum(ln.conf for ln in lines) / len(lines) if lines else 0.0
    return r


def _weak_name(r: SideResult) -> bool:
    c = r.names_ko
    return not c or c[0].score < NAME_STRONG or (len(c) > 1 and c[0].score - c[1].score < NAME_GAP)


NAME_STRONG = 4.0        # 1위 후보 점수가 이 아래이거나
NAME_GAP = 1.0           #   2위와의 차이가 이 아래면 '약함' — 이름 덧읽기·확인 표 '확인 필요'


def read_side(images: list, hint_name: str = "", hint_company: str = "", extra: bool = True) -> Optional[SideResult]:
    """한 면을 그림 여럿으로 읽어 합친다 — 줄은 모두 모아 한 번에 뽑고, 두 판에서 모두 나온 이름에 덤."""
    if not images:
        return None
    per = [ocr_lines(im) for im in images]
    allines = [ln for ls in per for ln in ls]
    r = parse_lines(allines, hint_name, hint_company)
    if extra and _weak_name(r):
        # 이름이 약할 때만 덧읽기(한 장 약 2배 시간 — 앞면에서만, 명함 SOT §4.4)
        nim = images[-1]                               # 이름용 그림(PDF 는 150 dpi×3, 작은 그림은 3배)
        more = ocr_lines(nim, NAME_EXTRA_PSM) + ocr_lines(nim, NAME_EXTRA_PSM, invert=True)
        r = parse_lines(allines, hint_name, hint_company, more)
    if len(per) > 1:
        sets = [{c.text for c in parse_lines(ls).names_ko[:5]} for ls in per]
        both = set.intersection(*sets) if sets else set()
        for c in r.names_ko:
            if c.text in both:
                c.score = round(c.score + 0.7, 3)
                c.why = tuple(c.why) + ("두판",)
        r.names_ko.sort(key=lambda c: -c.score)
    return r


def is_promo(side: Optional[SideResult]) -> Optional[bool]:
    """뒷면이 홍보 면인가(R8) — 전화·메일이 없고 이름 후보도 약하면 True. 지우기는 확인 표 뒤(D8)."""
    if side is None:
        return None
    if side.has_contact:
        return False
    strong_name = (side.names_ko and side.names_ko[0].score >= 3.5) or (side.names_en and side.names_en[0].score >= 2.5)
    return not strong_name


def merge_sides(front: Optional[SideResult], back: Optional[SideResult], hint_name: str = "",
                hint_company: str = "", ui_lang: str = "ko") -> CardResult:
    """앞뒤 합치기(R7) — 한글 칸이 주, 영문은 `en` 에 따로. 영문판(ui_lang='en')이면 영문이 주."""
    sides = [s for s in (front, back) if s is not None]
    c = CardResult()
    seen = set()
    for s in sides:
        for k, n in s.phones:
            if n not in seen:
                seen.add(n)
                c.phones.append((k, n))
        c.emails += [e for e in s.emails if e not in c.emails]
        c.urls += [u for u in s.urls if u not in c.urls]

    def pool(attr):
        d = {}
        for s in sides:
            for cd in getattr(s, attr):
                if cd.text not in d or d[cd.text].score < cd.score:
                    d[cd.text] = Cand(cd.text, cd.score, cd.why)
        return sorted(d.values(), key=lambda x: -x.score)

    nk, ne = pool("names_ko"), pool("names_en")
    ck, ce = pool("companies_ko"), pool("companies_en")
    hangul = sum(s.hangul for s in sides)
    latin = sum(s.latin for s in sides)
    langs = []
    if hangul >= 4:
        langs.append("한글")
    if latin >= 12:
        langs.append("영어")
    c.langs = tuple(langs)
    tk = [t for s in sides for t in s.titles_ko]
    te = [t for s in sides for t in s.titles_en]
    ak = next((s.address_ko for s in sides if s.address_ko), "")
    ae = next((s.address_en for s in sides if s.address_en), "")
    en = {"name": ne[0].text if ne else "", "company": ce[0].text if ce else "",
          "title": te[0] if te else "", "address": ae}
    ko_ok = bool(nk) and hangul >= 4
    if ui_lang == "en" or not ko_ok:
        # 영문판이거나 한글이 없는 명함(외국인 등) — 영문이 주
        c.name, c.company, c.title, c.address = en["name"], en["company"], en["title"], en["address"] or ak
        c.name_cands, c.company_cands = ne[:3] or nk[:3], ce[:3] or ck[:3]
        c.en = {}
        if ui_lang == "en" and not c.name and nk:
            c.name, c.name_cands = nk[0].text, nk[:3]
    else:
        c.name = nk[0].text
        c.company = ck[0].text if ck else (hint_company or "")
        c.title = tk[0] if tk else ""
        c.address = ak
        c.name_cands, c.company_cands = nk[:3], ck[:3]
        c.en = {k: v for k, v in en.items() if v}
    need = []
    top = c.name_cands
    if not top or (len(top) > 1 and top[0].score - top[1].score < NAME_GAP) or top[0].score < NAME_STRONG:
        need.append("name")
    if not c.company:
        need.append("company")
    if not c.phones and not c.emails:
        need.append("contact")
    c.need_check = tuple(need)
    c.back_promo = is_promo(back)
    return c


def recognize(path, ui_lang: str = "ko") -> CardResult:
    """명함 하나(앞면 그림·원본 PDF 어느 경로든) → `CardResult`. 배경 스레드에서 부른다(응답성 SOT §4)."""
    src = card_sources(path)
    hint_name, hint_company = parse_hint(src.get("front") or src.get("pdf") or path)
    ims = side_images(src)
    front = read_side(ims["front"], hint_name, hint_company)
    back = read_side(ims["back"], hint_name, hint_company, extra=False)
    res = merge_sides(front, back, hint_name, hint_company, ui_lang)
    res.sources = {k: (str(v) if v else "") for k, v in src.items()}
    return res
