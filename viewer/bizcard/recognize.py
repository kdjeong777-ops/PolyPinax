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
# 부서 끝말(긴 것 먼저) — 261117-11(사용자 지시 '부서도 추가해'). '부'·'처'·'국' 처럼 짧은 끝말은 기관 이름(…교통부)과 겹쳐
#   회사·기관 후보와 같은 낱말이면 부서로 보지 않는다
DEPT_SUFFIX = ("사업본부", "연구본부", "기술본부", "사업단", "사업부", "사업소", "사무소", "연구소", "연구실", "연구팀",
               "본부", "센터", "그룹", "파트", "지사", "지점", "학과", "팀", "실", "부", "처", "과", "국", "단")
DEPT_EN = re.compile(r"\b(dept\.?|department|division|div\.|team|center|centre|office|lab(oratory)?|group|bureau|section)\b", re.I)
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
_SEP = r"\s.\-·•∙・‧,"                 # 번호 구분자 — 점·가운뎃점·쉼표도(사용자 지시 261117-9 '010.0000.0000')
_PHONE = re.compile(r"(?<!\d)(\+?82[%s)]*)?\(?0?(\d{1,3})\)?[%s)]{0,3}(\d{3,4})[%s]{1,3}(\d{4})(?!\d)" % (_SEP, _SEP, _SEP))
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
    feat: dict = field(default_factory=dict)   # 점수 특징(§5.11) — 학습·다시 매기기, 'cx'·'cy' = 줄 가운데(그림 비율)


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
    dept_ko: str = ""
    dept_en: str = ""
    hangul: int = 0
    latin: int = 0
    conf: float = 0.0

    rotated: int = 0                                   # 세로로 누운 명함을 돌려 읽었으면 그 각도(§5.11)

    @property
    def has_contact(self) -> bool:
        return bool(self.phones or self.emails)


@dataclass
class CardResult:
    name: str = ""
    company: str = ""
    dept: str = ""                                     # 부서(261117-11)
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
    rotated: int = 0                                   # 앞면을 돌려 읽었으면 그 각도(세로로 누운 명함, §5.11)


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
        folder = p.parent.parent if p.parent.name.lower() == pdf_dir_name.lower() else p.parent
        base = p.stem
    else:
        folder = p.parent
        base = _stem_base(p)
        pdf = next((c for c in (folder / pdf_dir_name / (base + ".pdf"), folder / (base + ".pdf")) if c.exists()), None)
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
    cx: float = 0.5        # 줄 가운데(그림 너비 비율) — 양식 위치(§5.11)
    cy: float = -1.0       # 줄 가운데(그림 높이 비율), 음수면 y + height/2

    def center(self):
        return self.cx, (self.cy if self.cy >= 0 else self.y + self.height / 2)


ENG_PASS = True          # 영어만으로 한 번 더 읽기(§5.15) — 언어 값은 단어학습 SOT §14.B 의 대체 언어(`ocr.FALLBACK_LANG`)


def O_FALLBACK() -> str:
    from viewer.study import ocr as O
    return O.FALLBACK_LANG


NAME_EXTRA_PSM = 11      # 이름용 덧읽기 — 흩어진 글(sparse). 기본 읽기에 없던 이름 26 중 9 를 찾았다(명함 SOT §4.4)


def ocr_lines(im, psm: int = 0, invert: bool = False, lang: str = "") -> list:
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
    lang = O.resolve_lang(lang or O.DEFAULT_LANG)
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
        groups[k].append((d["left"][i], w, float(d["height"][i]), c, float(d["top"][i]), float(d["width"][i])))
    W = float(g.width or 1)
    out = []
    for k in order:
        ws = sorted(groups[k])
        x0 = min(x[0] for x in ws); x1 = max(x[0] + x[5] for x in ws)
        y0 = min(x[4] for x in ws); y1 = max(x[4] + x[2] for x in ws)
        out.append(Line(" ".join(x[1] for x in ws), max(x[2] for x in ws) / H,
                        sum(x[3] for x in ws) / len(ws), y0 / H, (x0 + x1) / 2 / W, (y0 + y1) / 2 / H))
    return out


# ── 칸 뽑기 ──────────────────────────────────────────────────────────────
_DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "Q": "0", "D": "0", "I": "1", "l": "1", "|": "1", "i": "1",
                            "S": "5", "B": "8", "Z": "2"})


def _fix_digits(s: str) -> str:
    """전화번호처럼 보이는 덩어리(숫자 5개 이상 + 구분자) 안의 글자 오인식만 고친다(낱말은 건드리지 않는다)."""
    def fix(m):
        t = m.group(0)
        return t.translate(_DIGIT_FIX) if len(re.findall(r"\d", t)) >= 5 else t
    return re.sub(r"[\d(+][\dOoQDIl|iSBZ%s)]{7,}[\dOoQDIl|iSBZ]" % _SEP, fix, s)


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


# 이름 점수 가중치(§5.11) — 기본값은 P1 의 손 규칙 그대로. 확정한 명함이 쌓이면 `learn.train` 이 이 PC 에서 고친다.
NAME_FEATS = ("bias", "h", "sur", "title", "org", "len2", "len3", "len4", "mail", "hint", "conf", "frag", "both", "tpl")
NAME_W = {"bias": -1.5, "h": 2.0, "sur": 2.5, "title": 1.2, "org": -2.0, "len2": 0.1, "len3": 0.6, "len4": -0.4,
          "mail": 0.8, "hint": 1.5, "conf": 1.0, "frag": -0.5, "both": 0.7, "tpl": 3.0}


def name_score(f: dict, w: Optional[dict] = None) -> float:
    w = w or NAME_W
    return round(sum(w.get(k, 0.0) * float(f.get(k, 0.0)) for k in NAME_FEATS), 3)


def merge_spaced(text: str) -> str:
    """한 글자씩 띄운 한글을 붙인다 — '시험실장 홍  길  동' → '시험실장 홍길동'(사용자 지시 261117-9)."""
    toks = text.split()
    out, run = [], []
    for t in toks + [""]:
        if len(t) == 1 and _HANGUL.match(t):
            run.append(t)
            continue
        if run:
            out.append("".join(run) if len(run) >= 2 else run[0])
            run = []
        if t:
            out.append(t)
    return " ".join(out)


_TITLES_LONG = sorted(TITLES_KO, key=len, reverse=True)


def title_token(tok: str) -> str:
    """낱말이 직위인가 — '시험실장'·'품질팀장'·'기술이사' 처럼 직함으로 끝나는 짧은 한글 낱말이면 그 낱말."""
    t = re.sub(r"[^가-힣]", "", tok)
    if not t or len(t) > 9:
        return ""
    for k in _TITLES_LONG:
        if t.endswith(k):
            return t if len(t) - len(k) <= 4 else ""      # '가나다시험연구원' 은 기관 이름 — 앞말이 길면 직위가 아니다
    return ""


def name_candidates_ko(lines: list, emails: list, hint: str = "", weights: Optional[dict] = None) -> list:
    """한글 이름 후보(R3) — 특징(크기·성씨·직함 이웃·메일 아이디·파일 이름 힌트 …)의 가중합(명함 SOT §5.2 의 3·§5.11)."""
    cands = {}
    hmax = max((ln.height for ln in lines), default=1) or 1
    for idx, ln in enumerate(lines):
        raw = merge_spaced(ln.text)
        near = " ".join(x.text for x in lines[max(0, idx - 1): idx + 2])
        pieces = set()
        whole = clean_name_ko(" ".join(t for t in raw.split() if not title_token(t)))
        if 2 <= len(whole) <= 4 and len(re.sub(r"[^가-힣\s]", "", raw).split()) <= 4:
            pieces.add(whole)                       # '홍 길 동' · '홍길동 부장' → '홍길동'
        for run in re.findall(r"[가-힣]+", " ".join(t for t in raw.split() if not title_token(t))):
            if 2 <= len(run) <= 4:
                pieces.add(run)
            elif len(run) > 4:                      # '홍길동부장'·'기술연구소홍길동' — 성씨 자리에서 3·2자 조각
                bare = re.sub("|".join(_TITLES_LONG), "", run)     # '대표이사홍길동' → '홍길동'(붙은 직함을 뗀 통째 — 조각이 아니다)
                if 2 <= len(bare) <= 4 and bare != run:
                    pieces.add(bare)
                for i, ch in enumerate(run):
                    if ch in SURNAMES:
                        for L in (3, 2):
                            if i + L <= len(run):
                                pieces.add(run[i:i + L])
        for n in pieces:
            if n in TITLES_KO or title_token(n) or any(n.endswith(d) and len(n) > 2 for d in ("회사", "기술", "건설", "산업")):
                continue
            cx, cy = ln.center()
            f = {"bias": 1.0, "h": round(ln.height / hmax, 3),
                 "sur": 1.0 if _surname_score(n) > 0 else 0.0,
                 "title": 1.0 if (_is_titleish(near) or any(title_token(t) for t in near.split())) else 0.0,
                 "org": 1.0 if (_is_orgish(raw.replace(n, "")) or _ADDR_KO.search(raw)) else 0.0,
                 "len2": float(len(n) == 2), "len3": float(len(n) == 3), "len4": float(len(n) == 4),
                 "mail": 1.0 if _email_hint(n, emails) else 0.0, "hint": float(bool(hint) and n == hint),
                 "conf": round(ln.conf / 100.0, 3),
                 "frag": float(n not in re.findall(r"[가-힣]+", raw) and n != whole
                          and n != re.sub("|".join(_TITLES_LONG), "", re.sub(r"[^가-힣]", "", raw))),
                 "both": 0.0, "tpl": 0.0, "cx": round(cx, 3), "cy": round(cy, 3)}
            why = tuple(k for k in ("title", "mail", "hint") if f[k])
            sc = name_score(f, weights)
            if n not in cands or cands[n].score < sc:
                cands[n] = Cand(n, sc, why, f)
    return sorted(cands.values(), key=lambda c: (-c.score, c.text))   # 같은 점수는 글자 차례(실행마다 같게 — set 차례는 실행마다 다르다)


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
    return sorted(cands.values(), key=lambda c: (-c.score, c.text))   # 같은 점수는 글자 차례(실행마다 같게 — set 차례는 실행마다 다르다)


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
        cx, cy = ln.center()
        if c not in cands or cands[c].score < s:
            cands[c] = Cand(c, round(s, 3), (), {"cx": round(cx, 3), "cy": round(cy, 3)})
    if hint and hint not in cands and _HANGUL.search(hint):
        cands[hint] = Cand(hint, 0.5, ("파일이름",))
    return sorted(cands.values(), key=lambda c: (-c.score, c.text))   # 같은 점수는 글자 차례(실행마다 같게 — set 차례는 실행마다 다르다)


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
    return sorted(cands.values(), key=lambda c: (-c.score, c.text))   # 같은 점수는 글자 차례(실행마다 같게 — set 차례는 실행마다 다르다)


def titles_of(lines: list) -> tuple:
    ko, en, sub = [], [], []
    for ln in lines:
        for tok in merge_spaced(ln.text).split():
            tt = title_token(tok)
            if tt and tt not in ko and not _ADDR_KO.search(ln.text):
                ko.append(tt)                          # '시험실장 홍길동' → 직위 '시험실장'(낱말 통째가 먼저)
        for t in TITLES_KO:
            if t in ln.text and t not in sub:
                sub.append(t)                          # 줄 안에 든 직함 글자(기관 이름 속 '연구원' 일 수 있어 뒤로)
    ko += [t for t in sub if t not in ko and not any(t in k for k in ko)]
    for ln in lines:
        low = ln.text.lower()
        if not _HANGUL.search(ln.text) and any(k in low for k in TITLES_EN) and len(ln.text) < 60 \
                and not re.search(r"\d{3}", ln.text):
            en.append(ln.text.strip())
    # 긴 직함 먼저('대표이사' 가 '대표'·'이사' 를 덮는다)
    ko = [t for t in ko if not any(t != u and t in u for u in ko)]
    return ko, en


def dept_token(tok: str) -> str:
    """부서 낱말인가 — 한글 2~12자이고 부서 끝말로 끝나며 직위가 아닌 것('품질관리팀'·'기술연구소'·'도로시설과')."""
    t = re.sub(r"[^가-힣]", "", tok)
    if not (2 <= len(t) <= 12) or title_token(t):
        return ""
    for k in DEPT_SUFFIX:
        if t.endswith(k) and len(t) > len(k):
            return t
    return ""


def dept_of(lines: list, companies=()) -> tuple:
    """부서(한글, 영문) — 회사·기관 후보와 같은 낱말·법인 꼴이 든 줄·주소 줄은 뺀다. 한 줄에 여럿이면 이어 쓴다('기술본부 품질팀')."""
    comp = {re.sub(r"\s", "", c) for c in companies if c}
    ko = en = ""
    for ln in lines:
        raw = merge_spaced(ln.text)
        if _ADDR_KO.search(raw) or any(m in raw for m in CORP_MARKS_KO) or find_phones(raw) or "@" in raw:
            continue
        toks = [dept_token(t) for t in raw.split()]
        toks = [t for t in toks if t and t not in comp and not any(t in c or c in t for c in comp if len(c) >= 3)]
        if toks and not ko:
            ko = " ".join(dict.fromkeys(toks))
        t = ln.text.strip()
        if not en and not _HANGUL.search(t) and DEPT_EN.search(t) and len(t) < 60 and not re.search(r"\d{3}", t) \
                and not CORP_MARKS_EN.search(t):
            en = t
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
    r.dept_ko, r.dept_en = dept_of(lines, [c.text for c in r.companies_ko[:1]] + [hint_company])   # 회사 1위만 뺀다(부서 줄도 기관꼴 후보가 된다)
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
                c.feat["both"] = 1.0
                c.score = name_score(c.feat)
                c.why = tuple(c.why) + ("두판",)
        r.names_ko.sort(key=lambda c: -c.score)
    if ENG_PASS and images:
        # 261117-13(사용자 보고 '영어와 한글이 같이 있을 때 인식을 잘 못함'): 한글+영어로 읽으면 영문 글이 한글로 깨지는 일이 많다 —
        #   연락처용 그림을 영어만으로 한 번 더 읽어 메일·누리집·영문 칸(이름·회사·직함·부서·주소)을 보탠다(§5.15)
        el = ocr_lines(images[0], lang=O_FALLBACK())
        re_ = parse_lines(el)
        r.emails += [e for e in re_.emails if e not in r.emails]
        r.urls += [u for u in re_.urls if u not in r.urls]
        seen = {n for _k, n in r.phones}
        r.phones += [(k, n) for k, n in re_.phones if n not in seen]
        en = {c.text: c for c in r.names_en}
        for c in re_.names_en:
            if c.text not in en or en[c.text].score < c.score + 0.3:
                en[c.text] = Cand(c.text, round(c.score + 0.3, 3), tuple(c.why) + ("영어",), c.feat)
        r.names_en = sorted(en.values(), key=lambda c: (-c.score, c.text))
        ce = {c.text: c for c in r.companies_en}
        for c in re_.companies_en:
            ce.setdefault(c.text, Cand(c.text, round(c.score + 0.3, 3), ("영어",), c.feat))
        r.companies_en = sorted(ce.values(), key=lambda c: (-c.score, c.text))
        r.titles_en = re_.titles_en or r.titles_en
        r.address_en = re_.address_en or r.address_en
        r.dept_en = re_.dept_en or r.dept_en
        r.latin = max(r.latin, re_.latin)
    if extra and not r.has_contact and images:
        # 세로로 누운 명함(사용자 지시 261117-9) — 0도에서 연락처를 못 찾았을 때만 90·270도로 돌려 본다(명함 SOT §5.11)
        for ang in (180, 90, 270):              # 실측(가로 592장): 돌려야 읽힌 14장 중 180도 10·90도 3·270도 1
            rot = [im.rotate(ang, expand=True) for im in images]
            rl = [ln for im in rot for ln in ocr_lines(im)]
            rr = parse_lines(rl, hint_name, hint_company)
            if rr.has_contact:
                rr.rotated = ang
                return rr
    return r


def is_promo(side: Optional[SideResult]) -> Optional[bool]:
    """뒷면이 홍보 면인가(R8) — 전화·메일이 없고 이름 후보도 약하면 True. 지우기는 확인 표 뒤(D8)."""
    if side is None:
        return None
    if side.has_contact:
        return False
    strong_name = (side.names_ko and side.names_ko[0].score >= 3.5) or (side.names_en and side.names_en[0].score >= 2.5)
    return not strong_name


CAND_KEEP = 8            # 후보를 이만큼 남긴다 — 확인 표는 위 셋을 보이고, 다시 매기기(§5.11)는 모두 쓴다

# 누리집·메일 도메인 → 직장(§5.11, 사용자 지시 261117-9 'www.seoul.go.kr 이면 서울시청').
#   기본 표는 공공 기관 일부 — 확인 표에서 회사를 확정하면 그 도메인을 이 PC 의 명함 DB 에 배워 더한다(`domain_map`).
DOMAIN_ORG = {
    "seoul.go.kr": "서울시청", "busan.go.kr": "부산시청", "daegu.go.kr": "대구시청", "incheon.go.kr": "인천시청",
    "gwangju.go.kr": "광주시청", "daejeon.go.kr": "대전시청", "ulsan.go.kr": "울산시청", "sejong.go.kr": "세종시청",
    "gg.go.kr": "경기도청", "gwd.go.kr": "강원도청", "provin.gangwon.kr": "강원도청", "chungbuk.go.kr": "충청북도청",
    "chungnam.go.kr": "충청남도청", "jeonbuk.go.kr": "전북도청", "jeonnam.go.kr": "전라남도청",
    "gb.go.kr": "경상북도청", "gyeongnam.go.kr": "경상남도청", "jeju.go.kr": "제주도청",
    "molit.go.kr": "국토교통부", "me.go.kr": "환경부", "moef.go.kr": "기획재정부", "mois.go.kr": "행정안전부",
    "motie.go.kr": "산업통상자원부", "msit.go.kr": "과학기술정보통신부", "mof.go.kr": "해양수산부",
    "ex.co.kr": "한국도로공사", "lh.or.kr": "한국토지주택공사", "kict.re.kr": "한국건설기술연구원",
    "kalis.or.kr": "국토안전관리원", "kcl.re.kr": "한국건설생활환경시험연구원", "ktr.or.kr": "한국화학융합시험연구원",
    "koroad.or.kr": "도로교통공단", "korail.com": "한국철도공사", "kr.or.kr": "국가철도공단", "krihs.re.kr": "국토연구원",
}


def domain_of(s: str) -> str:
    s = (s or "").lower().strip()
    s = s.split("@", 1)[1] if "@" in s else re.sub(r"^(https?://)?(www\d?\.)?", "", s).split("/")[0]
    return s.strip(".")


def org_from_domains(emails, urls, learned: Optional[dict] = None) -> str:
    """메일·누리집 도메인 → 직장. 배운 표가 먼저, 다음이 기본 표. 개인 메일(gmail 등)은 보지 않는다.
    'xx.seoul.go.kr' 처럼 아래 도메인이면 위로 올라가며 찾는다."""
    for raw in list(urls or []) + list(emails or []):
        d = domain_of(raw)
        if not d or any(d == f or d.startswith(f + ".") for f in FREE_MAIL):
            continue
        parts = d.split(".")
        for i in range(len(parts) - 1):
            k = ".".join(parts[i:])
            if learned and k in learned:
                return learned[k]
            if k in DOMAIN_ORG:
                return DOMAIN_ORG[k]
    return ""


def layout_key(emails, urls, company: str = "") -> str:
    """같은 양식(같은 회사의 명함)을 알아보는 열쇠 — 회사 도메인, 없으면 회사명(법인 꼴 없이)."""
    for raw in list(emails or []) + list(urls or []):
        d = domain_of(raw)
        if d and not any(d == f or d.startswith(f + ".") for f in FREE_MAIL) and not d.endswith("korea.kr"):
            return "d:" + d
    c = strip_corp(company or "")
    return ("c:" + c) if c else ""


def _in_box(f: dict, box) -> bool:
    if not box or f.get("back"):
        return False
    x, y = f.get("cx", -1), f.get("cy", -1)
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def rescore(res: dict, weights: Optional[dict] = None, layouts: Optional[dict] = None,
            domain_map: Optional[dict] = None, corrections: Optional[dict] = None) -> dict:
    """캐시에 남은 인식 결과(사전)를 지금의 가중치·양식·도메인 표로 다시 매긴다 — OCR 은 다시 하지 않는다(§5.11).
    이름·회사 1위가 바뀌면 `name`·`company` 도 바꾼다(확인 표가 사용자가 고친 값을 따로 지킨다)."""
    r = dict(res)
    corr = corrections or {}
    for fld in ("dept", "title"):                  # 교정(§5.15) — 전에 사람이 고친 오인식은 고친 글로
        if r.get(fld) in corr.get(fld, {}):
            r[fld] = corr[fld][r[fld]]
    lay = (layouts or {}).get(layout_key(r.get("emails"), r.get("urls"), r.get("company", ""))) or {}
    names = []
    for c in r.get("name_cands") or []:
        c = dict(c)
        c["text"] = corr.get("name", {}).get(c.get("text"), c.get("text"))
        f = dict(c.get("feat") or {})
        if f:
            f["tpl"] = 1.0 if _in_box(f, lay.get("name")) else 0.0
            c["score"] = name_score(f, weights)
            c["feat"] = f
        names.append(c)
    names.sort(key=lambda c: -c["score"])
    comps = []
    for c in r.get("company_cands") or []:
        c = dict(c)
        c["text"] = corr.get("company", {}).get(c.get("text"), c.get("text"))
        if _in_box(c.get("feat") or {}, lay.get("company")):
            c["score"] = round(float(c.get("score", 0)) + 3.0, 3)
        comps.append(c)
    org = org_from_domains(r.get("emails"), r.get("urls"), domain_map)
    if org and not any(c["text"] == org for c in comps) and (not comps or comps[0]["score"] < 2.0):
        comps.insert(0, {"text": org, "score": 2.5, "why": ["도메인"], "feat": {}})
    comps.sort(key=lambda c: -c["score"])
    if names and r.get("name") in [c["text"] for c in names] + [""]:
        r["name"] = names[0]["text"]
    if comps:
        r["company"] = comps[0]["text"]
    r["name_cands"], r["company_cands"] = names, comps
    need = list(r.get("need_check") or [])
    if any(c.get("feat") for c in names):          # 특징이 있을 때만 다시 판정(없으면 처음 판정 그대로)
        need = [x for x in need if x != "name"]
        if not names or (len(names) > 1 and names[0]["score"] - names[1]["score"] < NAME_GAP) \
                or names[0]["score"] < NAME_STRONG:
            need.insert(0, "name")
    if r.get("company") and "company" in need:
        need.remove("company")
    r["need_check"] = need
    return r


def merge_sides(front: Optional[SideResult], back: Optional[SideResult], hint_name: str = "",
                hint_company: str = "", ui_lang: str = "ko", domain_map: Optional[dict] = None) -> CardResult:
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
        for si, s in enumerate(sides):
            for cd in getattr(s, attr):
                f = dict(cd.feat or {})
                if s is back:
                    f["back"] = 1.0                    # 뒷면 후보 — 양식 위치는 앞면 기준(§5.11)
                if cd.text not in d or d[cd.text].score < cd.score:
                    d[cd.text] = Cand(cd.text, cd.score, cd.why, f)
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
    dk = next((s.dept_ko for s in sides if s.dept_ko), "")
    de = next((s.dept_en for s in sides if s.dept_en), "")
    en = {"name": ne[0].text if ne else "", "company": ce[0].text if ce else "", "dept": de,
          "title": te[0] if te else "", "address": ae}
    ko_ok = bool(nk) and hangul >= 4
    if ui_lang == "en" or not ko_ok:
        # 영문판이거나 한글이 없는 명함(외국인 등) — 영문이 주
        c.name, c.company, c.title, c.address = en["name"], en["company"], en["title"], en["address"] or ak
        c.dept = de or dk
        c.name_cands, c.company_cands = ne[:CAND_KEEP] or nk[:CAND_KEEP], ce[:CAND_KEEP] or ck[:CAND_KEEP]
        c.en = {}
        if ui_lang == "en" and not c.name and nk:
            c.name, c.name_cands = nk[0].text, nk[:CAND_KEEP]
    else:
        c.name = nk[0].text
        c.company = ck[0].text if ck else ""
        c.title = tk[0] if tk else ""
        c.dept = dk
        c.address = ak
        c.name_cands, c.company_cands = nk[:CAND_KEEP], ck[:CAND_KEEP]
        org = org_from_domains(c.emails, c.urls, domain_map)
        if org and (not ck or ck[0].score < 2.0):      # 회사 줄이 없거나 약하면 누리집·메일 도메인으로(사용자 지시 261117-9)
            c.company = org
            c.company_cands = [Cand(org, 2.5, ("도메인",))] + [x for x in c.company_cands if x.text != org]
        if not c.company and hint_company:
            c.company = hint_company
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
    c.rotated = int(getattr(front, "rotated", 0) or 0) if front is not None else 0
    return c


# ── 고른 자리 읽기(§5.15·§5.16) ────────────────────────────────────────────
BOX_PAD = 12             # 자른 그림 둘레에 붙이는 흰 여백(픽셀) — 글자가 가장자리에 붙으면 OCR 이 못 읽는다
BOX_MIN_H = 90           # 자른 그림 높이가 이보다 작으면 이만큼 되게 키운다(상한 NAME_UPSCALE 배)
BOX_PSMS = (7, 6, NAME_EXTRA_PSM)   # 한 줄 → 여러 줄 → 흩어진 글 차례로 읽어 칸에 맞는 것을 고른다


def _box_value(text: str, fld: str) -> str:
    if fld == "name":
        t = merge_spaced(text)
        toks = [x for x in t.split() if not title_token(x)]
        ko = clean_name_ko(" ".join(toks))
        return ko if ko else clean_name_en(text)
    if fld == "company":
        return strip_corp(merge_spaced(text))
    if fld == "dept":
        t = merge_spaced(text)
        return " ".join(x for x in t.split() if not title_token(x)) or t
    if fld in ("cell", "tel"):
        ph = find_phones(text)
        return ph[0][1] if ph else ""
    if fld == "email":
        em = find_emails(text)
        return em[0] if em else ""
    return merge_spaced(text).strip()


def _box_good(val: str, fld: str, conf: float) -> float:
    """칸에 맞는 정도 — 이름은 한글 2~4자(또는 영문 이름), 그 밖은 읽은 글자 수·신뢰도."""
    if not val:
        return -1.0
    if fld == "name":
        if re.fullmatch(r"[가-힣]{2,4}", val):
            return 3.0 + conf / 100 + (1.0 if val[0] in SURNAMES else 0.0)
        return 1.0 + conf / 100 if re.fullmatch(r"[A-Za-z][A-Za-z .'\-]{2,40}", val) else 0.1
    if fld in ("cell", "tel", "email"):
        return 3.0 + conf / 100
    han = len(_HANGUL.findall(val))
    junk = len(re.findall(r"[^가-힣A-Za-z0-9 ()·&.,\-]", val))
    return 1.0 + min(han, 12) * 0.2 + conf / 100 - junk * 0.5


def prep_box(crop):
    """자른 그림 → 읽기 좋은 그림: 작으면 키우고 둘레에 흰 여백."""
    Image, ImageOps = _pil()
    g = crop.convert("RGB")
    if g.height < BOX_MIN_H:
        k = min(float(NAME_UPSCALE), BOX_MIN_H / max(1, g.height))
        g = g.resize((max(1, int(g.width * k)), max(1, int(g.height * k))), Image.LANCZOS)
    return ImageOps.expand(g, border=BOX_PAD, fill="white")


def read_box(im, box, fld: str) -> tuple:
    """그림(PIL)에서 비율 상자 자리만 읽는다 → (칸 값, 자른 그림). OCR 을 부르니 **배경에서** 부른다(응답성 SOT §4).
    그린 그대로 자르고(넓히지 않음), 키우고 여백을 붙여 한 줄·여러 줄·흩어진 글로 읽어 칸에 가장 맞는 결과를 고른다.
    메일 칸은 대체 언어(영어)로도 읽는다(§5.15)."""
    W, H = im.size
    x0, y0, x1, y1 = box
    crop = im.crop((int(max(0.0, x0) * W), int(max(0.0, y0) * H),
                    min(W, int(min(1.0, x1) * W) + 1), min(H, int(min(1.0, y1) * H) + 1)))
    g = prep_box(crop)
    best, best_s = "", -1.0
    langs = [""] + ([O_FALLBACK()] if fld in ("email", "cell", "tel") else [])
    for lang in langs:
        for psm in BOX_PSMS:
            lines = ocr_lines(g, psm, lang=lang)
            if not lines:
                continue
            text = " ".join(ln.text for ln in lines).strip()
            conf = sum(ln.conf for ln in lines) / len(lines)
            val = _box_value(text, fld)
            s = _box_good(val, fld, conf)
            if s > best_s:
                best, best_s = val, s
            if fld == "name" and s >= 3.5:
                break                              # 이름 꼴이 나오면 더 읽지 않는다
    return best, crop


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
