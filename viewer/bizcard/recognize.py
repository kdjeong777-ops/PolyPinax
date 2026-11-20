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

from viewer.bizcard import phone as _phone       # 번호 꼴 한 곳(§5.11 '번호 꼴')

# ── 상수 (명함 SOT §4.2.1·§5.2) ──────────────────────────────────────────
CONTACT_DPI = 300        # 전화·메일·주소용 — 원본 PDF 그대로
NAME_DPI = 150           # 이름·회사용 — 낮게 그린 뒤
NAME_UPSCALE = 3         #   Lanczos 로 키운다(크고 장식적인 글꼴이 매끈해진다, 실측 §4.2.1)
SMALL_SIDE = 1000        # 그림 파일의 긴 변이 이보다 작으면 NAME_UPSCALE 배로 키워 읽는다
SMALL_EXTRA = 2          # 작은 그림은 NAME_UPSCALE×이 배로 한 판 더 읽는다(§5.22 실측 — 메일·번호를 두 판에서 세어 고른다)
MAX_SIDE = 4000         # 키운 뒤 긴 변 상한(사진 OCR 상한과 같은 뜻 — 단어학습 SOT §14.22)
WORD_MIN_CONF = 0        # 신뢰도가 음수(글자 아님)인 것만 버린다 — 장식 글꼴 이름은 신뢰도가 낮아도 맞는 일이 많다(실측: 문턱 20 이면 이름 3위 안 10/26 → 0 이면 20/26)
IMG_EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp")
FRONT_SUFFIXES = ("_p0001", "_1")
BACK_SUFFIXES = ("_p0002", "_2")

# ── 사전(규칙) ───────────────────────────────────────────────────────────
# 한국 성씨(인구 상위 + 복성) — 이름 후보 점수용
SURNAMES = set("김이박최정강조윤장임한오서신권황안송류유홍전고문양손배백허남심노하곽성차주우구민진나지엄채원천방공현함변염여추도소석선설마길연위표명기반왕금옥육인맹제모탁국어은편용예봉경사부황보")
COMPOUND_SURNAMES = ("남궁", "황보", "제갈", "선우", "독고", "사공", "서문", "동방")
TITLES_KO = ("대표이사", "전무이사", "상무이사", "사외이사", "대표", "부대표", "회장", "부회장", "사장", "부사장", "전무", "상무", "이사", "감사", "본부장", "실장",
             "센터장", "원장", "소장", "단장", "처장", "국장", "부장", "차장", "과장", "대리", "주임", "사원", "팀장",
             "파트장", "책임", "선임", "수석", "연구원", "연구위원", "위원", "교수", "부교수", "조교수", "감리단장", "현장소장", "매니저", "프로", "고문", "자문위원", "사무관", "주무관", "서기관", "과장대리",
             # 붙여 쓰는 겹 직함(§5.22 실측 — '선임 연구원' 을 '연구원' 으로 줄이지 않는다)
             "선임연구원", "책임연구원", "수석연구원", "주임연구원", "전임연구원", "선임연구위원", "수석연구위원", "부연구위원",
             "전문위원", "수석전문위원", "책임매니저", "수석매니저", "시설사무관", "행정사무관", "기술서기관", "전임기술원",
             "연구교수", "명예교수", "석좌교수", "겸임교수", "연구소장", "공장장", "상근부회장", "부부장", "부이사관", "감사관",
             "참사관", "보좌관", "변호사", "기자", "부국장", "총괄이사", "기술이사", "영업이사", "공사팀장", "품질관리자",
             "프로페셔널", "컨설턴트", "선임컨설턴트", "박사과정", "석사과정", "사무국장", "지소장", "부원장", "위원장")
# 자격·학위(261117-17 사용자 지시 '공학박사, 기술사 등은 직함이 아니야') — 직함 칸에 넣지 않고, 이름 앞뒤에 붙으면 떼기만 한다
QUALS = ("공학박사", "이학박사", "공학석사", "박사", "석사", "기술사")
DEPT_KO = ("부", "팀", "실", "본부", "센터", "연구소", "사업단", "사업부", "그룹", "처", "과", "국", "학과")
# 부서 끝말(긴 것 먼저) — 261117-11(사용자 지시 '부서도 추가해'). '부'·'처'·'국' 처럼 짧은 끝말은 기관 이름(…교통부)과 겹쳐
#   회사·기관 후보와 같은 낱말이면 부서로 보지 않는다
DEPT_SUFFIX = ("사업본부", "연구본부", "기술본부", "사업단", "사업부", "사업소", "사무소", "연구소", "연구실", "연구팀",
               "본부", "센터", "그룹", "파트", "지사", "지점", "학과", "팀", "실", "부", "처", "과", "국", "단")
DEPT_EN = re.compile(r"\b(dept\.?|department|division|div\.|team|center|centre|office|lab(oratory)?|group|bureau|section)\b", re.I)
TITLES_EN = ("ceo", "president", "director", "manager", "engineer", "professor", "researcher", "chairman", "vice",
             "executive", "general", "senior", "principal", "head", "chief", "officer", "ph.d", "phd", "dr.",
             "team leader", "leader", "consultant", "associate", "assistant")
CORP_MARKS_KO = ("주식회사", "유한회사", "합자회사", "합명회사", "사단법인", "재단법인", "농업회사법인", "영농조합법인", "의료법인",
                 "학교법인", "사회복지법인", "(주)", "㈜", "(유)", "(사)", "(재)", "(합)", "[주]", "[유]",
                 "(株)", "( 주)", "(주 )")     # §5.28 — 협동조합은 이름의 일부라 넣지 않는다
ORG_WORDS_KO = ("회사", "기업", "건설", "산업", "기술", "엔지니어링", "공사", "공단", "협회", "학회", "연구원", "연구소",
                "대학교", "대학", "아스콘", "개발", "그룹", "컨설팅", "공업", "화학", "테크", "솔루션", "시스템", "조합",
                "재단", "은행", "청", "시청", "구청", "도청", "부", "처", "원")
CORP_MARKS_EN = re.compile(r"\b(co\.?,?\s*ltd\.?|corp(oration)?\.?|inc\.?|ltd\.?|llc|company|co\.)\b", re.I)
ORG_WORDS_EN = ("university", "institute", "engineering", "construction", "consultants", "corporation", "company",
                "association", "ministry", "korea", "group", "technology", "college", "school", "department", "center",
                # §5.25(이름 정확도) — 외국 명함에서 이름으로 잘못 고른 기관 문구
                "road", "program", "division", "communication", "republic", "committee", "technopark", "solution",
                "factory", "maintenance", "pavement", "office", "bureau", "agency", "authority", "council", "laboratory",
                "transport", "highway", "government", "administration", "services", "international", "foundation",
                "society", "research", "development", "infrastructure")
EN_NAME_STOP = ("and", "of", "for", "the", "&")         # 이름 낱말이 아닌 이음말 — 'AND COMMUNICATIONS' 따위는 이름이 아니다
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
    ptexts: list = field(default_factory=list)         # 번호를 고른 줄 글(앞·뒷면·영어 읽기를 함께 세어 다시 고를 때, §5.22)

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
    t = re.sub(r"[(\[]\s*([주유사재합株])\s*[)\]]", "", t)       # (주)·[주]·(합) …(§5.28)
    t = re.sub(r"[\[【〔(]\s*[주유쥐]\s*[\]】〕)I]?(?=\s|$)", "", t)          # 깨져 읽힌 '[주】'·'【쥐'(§5.22)
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
    stem = re.sub(r"_\d{3}$", "", stem)                # 같은 이름 덧번호 '_001'(§5.22)
    if "_" not in stem:
        return "", ""
    comp, nm = stem.rsplit("_", 1)
    nm_ko = re.sub(r"공학박사|박사|[^가-힣]", "", nm)
    if nm_ko == "이름" or title_token(nm_ko) or qual_token(nm_ko) or dept_token(nm_ko):
        nm_ko = ""                                     # 자리 글자('이름')·직함·자격·부서를 이름으로 붙인 것(§5.22)
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
            out[side] = [_upscale(im, NAME_UPSCALE), _upscale(im, NAME_UPSCALE * SMALL_EXTRA)]
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
    src: str = ""          # 읽은 엔진 — "" 기본(Tesseract), "w" 보조 엔진(§5.23)

    def center(self):
        return self.cx, (self.cy if self.cy >= 0 else self.y + self.height / 2)


ENG_PASS = True          # 영어만으로 한 번 더 읽기(§5.15) — 언어 값은 단어학습 SOT §14.B 의 대체 언어(`ocr.FALLBACK_LANG`)


def O_FALLBACK() -> str:
    from viewer.study import ocr as O
    return O.FALLBACK_LANG


NAME_EXTRA_PSM = 11      # 이름용 덧읽기 — 흩어진 글(sparse). 기본 읽기에 없던 이름 26 중 9 를 찾았다(명함 SOT §4.4)


def ocr_lines(im, psm: int = 0, invert: bool = False, lang: str = "", win: bool = True) -> list:
    """그림 → [Line]. 언어·기본 psm 은 단어학습 SOT §14.B 기본값(코드 상수). `psm`·`invert` 는 이름 덧읽기용.
    `win`: 언어를 따로 주지 않은 읽기에 Windows 내장 OCR 판을 덧붙인다(§14.25 — 고른 자리 읽기는 붙이지 않는다)."""
    from viewer.study import ocr as O
    from viewer.study import tess_run
    _, ImageOps = _pil()
    info = O.ensure_tesseract()
    if not info.get("ok"):
        raise RuntimeError("Tesseract 사용 불가")
    g = ImageOps.autocontrast(im.convert("L"))
    if invert:
        g = ImageOps.invert(g)                         # 어두운 바탕에 흰 글자
    want_win = win and WIN_OCR and not lang
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
    if want_win:
        out += win_lines(g)                            # 보조 엔진 판(단어학습 SOT §14.25) — 영어 덧읽기에는 안 붙인다
    return out


WIN_OCR = True           # 기본 언어 판에 Windows 내장 OCR 판을 덧붙인다(단어학습 SOT §14.25, 명함 SOT §5.23) — 없으면 Tesseract 만


def win_lines(g) -> list:
    """회색조 그림 → Windows 내장 OCR 의 [Line](src="w"). 쓸 수 없으면 []."""
    from viewer.study import win_ocr
    if not win_ocr.available():
        return []
    W, H = float(g.width or 1), float(g.height or 1)
    out = []
    for text, boxes in win_ocr.read(g):
        x0 = min(b[0] for b in boxes); x1 = max(b[0] + b[2] for b in boxes)
        y0 = min(b[1] for b in boxes); y1 = max(b[1] + b[3] for b in boxes)
        out.append(Line(text, max(b[3] for b in boxes) / H, 90.0, y0 / H, (x0 + x1) / 2 / W, (y0 + y1) / 2 / H, "w"))
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
    """한국 꼴로 읽힌 세 묶음 → 국내 꼴(꼴은 `phone.format_kr` 한 곳 — §5.11 '번호 꼴'). 휴대폰·지역번호만, 그 밖은 None.
    `+82` 로 읽힌 것도 국내 꼴로 돌려준다 — 기본 국가가 한국이 아닐 때 국제 꼴로 바꾸는 것은 `pick_phones` 끝에서."""
    a = area.lstrip("0")
    if (a in _MOBILE or a in _AREA) and len(mid) in (3, 4):
        return _phone.format_kr("0" + a + mid + last) or None
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


def pick_phones(texts: list) -> list:
    """여러 번 읽은 줄들 → [(kind, 번호)] (§5.22). 한 자리만 다르게 읽힌 같은 번호는 묶어 **많이 나온 것**으로,
    종류는 붙은 표시(F·Fax / M·HP / T·Tel)를 판끼리 세어 정하고, 전화는 'T·Tel' 표시가 붙은 번호를 앞에."""
    occ, intl = [], set()                              # intl — '+82' 로 읽힌 번호(기본 국가가 한국이 아니면 국제 꼴로, §5.11)
    for tx in texts:
        t = _fix_digits(tx)
        spans = []
        for m in _PHONE.finditer(t):
            num = norm_phone(m.group(2), m.group(3), m.group(4), bool(m.group(1)))
            if not num:
                continue
            if m.group(1) and "+" in m.group(1):
                intl.add(num)
            spans.append(m.span())
            before = " " + t[:m.start()][-12:]
            lab = "fax" if _LABEL_FAX.search(before) else "cell" if _LABEL_CELL.search(before) \
                else "tel" if _LABEL_TEL.search(before) else ""
            if num.startswith("01") and lab in ("", "tel"):
                lab = "cell"                           # 01x 는 'Phone' 표시여도 휴대폰
            elif lab == "cell" and not re.match(r"0(1|[789]0)", num):
                lab = "tel"                            # 휴대폰 표시가 잘못 붙은 지역 번호
            occ.append((num, lab))
        for m in _PHONE_LOOSE.finditer(t):
            # 한국 꼴로 안 읽힌 번호 — 해외 번호('+1-555-…'·'Cell (555) …')·묶음이 다른 국내 번호('0100000 0000')(§5.23)
            if any(a < m.end() and m.start() < b for a, b in spans):
                continue
            before = " " + t[:m.start()][-12:]
            lab = "fax" if _LABEL_FAX.search(before) else "cell" if _LABEL_CELL.search(before)                 else "tel" if _LABEL_TEL.search(before) else ""
            num = loose_phone(m.group(0), _phone.KR)
            if not num or not (lab or num.startswith("+")):
                continue                               # 표시도 '+' 도 없으면 번호인지 알 수 없다(날짜·주소 숫자)
            if m.group(0).lstrip().startswith("+82"):
                intl.add(num)
            if num.startswith("01") and lab in ("", "tel"):
                lab = "cell"
            occ.append((num, lab))
    groups = []
    canon = lambda lab, num: lab if lab in ("fax", "cell") else ("cell" if num.startswith("01") else "work")
    for i, (num, lab) in enumerate(occ):
        g = None
        for gg in groups:
            if canon(lab, num) != gg["canon"]:
                continue                               # 종류가 다르면(전화 ↔ 팩스, 한 자리 차이가 흔하다) 다른 번호
            if any(n == num or (len(n) == len(num) and n[:4] == num[:4] and _edit(n, num) <= 1) for n in gg["nums"]):
                g = gg
                break
        if g is None:
            g = {"nums": {}, "labels": [], "first": i, "canon": canon(lab, num)}
            groups.append(g)
        g["nums"][num] = g["nums"].get(num, 0) + 1
        g["labels"].append(lab)
    out = []
    for g in groups:
        num = max(g["nums"], key=lambda n: (g["nums"][n], -list(g["nums"]).index(n)))
        labs = [x for x in g["labels"] if x]
        if labs:
            top = max(("fax", "cell", "tel"), key=lambda k: labs.count(k))
            kind = {"tel": "work"}.get(top, top)
        else:
            kind = "cell" if num.startswith("01") else "work"
        out.append((("tel" in labs), g["first"], kind, num))
    out.sort(key=lambda x: (not x[0], x[1]))           # 'T·Tel' 표시가 붙은 번호가 앞(첫 전화)
    kr = _phone.country() == _phone.KR
    return [(k, n if kr or n not in intl else _phone.to_intl(n)) for _l, _f, k, n in out]


_PHONE_LOOSE = re.compile(r"(?<![\d+])(?:\+\s?\d{1,3}[\s.\-]?)?\(?\d{2,8}\)?(?:[\s.\-]{1,2}\(?\d{2,8}\)?){1,4}(?![\d])")


def loose_phone(s: str, ctry: str = None) -> str:
    """한국 꼴이 아닌 번호 덩어리 → 적을 꼴. '+' 국제 번호는 묶음 그대로 '-' 로, 묶음이 다른 국내 번호는
    한국 꼴로(`phone.format_kr`), `+82` 는 기본 국가가 한국이면 국내 꼴·아니면 `+82-…`(§5.11), 북미 10자리는 3-3-4.
    번호로 보기 어려우면 ""(§5.23)."""
    plus = s.lstrip().startswith("+")
    groups = re.findall(r"\d+", s)
    d = "".join(groups)
    kr82 = plus and d.startswith("82")
    if kr82:
        d, plus = "0" + d[2:].lstrip("0"), False
    if not plus and d.startswith("0"):
        ok = (d.startswith("01") and len(d) == 11) or (d.startswith("02") and len(d) in (9, 10)) \
            or (d[1:3] in _AREA and len(d) in (10, 11))
        num = _phone.format_kr(d) if ok else ""
        if num and kr82 and (_phone.country() if ctry is None else ctry) != _phone.KR:
            num = _phone.to_intl(num)
        return num
    if plus:
        return "+" + "-".join(groups) if 9 <= len(d) <= 14 else ""
    if len(d) == 10 and d[0] in "23456789":
        return "%s-%s-%s" % (d[:3], d[3:6], d[6:])
    if len(d) == 11 and d[0] == "1":
        return "%s-%s-%s" % (d[:3], d[3:7], d[7:])     # 중국 휴대폰
    return ""


def find_phones(text: str) -> list:
    out = []
    t = _fix_digits(text)
    for m in _PHONE.finditer(t):
        num = norm_phone(m.group(2), m.group(3), m.group(4), bool(m.group(1)))
        if num:
            out.append((phone_kind(t, num, m.start()), num))
    return out


def find_emails(text: str, domains=()) -> list:
    """글 속 메일(나온 차례, 겹친 것도 그대로) — 이름표 떼기·도메인 오인식 고치기(`fix_email`)까지."""
    t = text.replace("©", "@").replace("(at)", "@").replace("[at]", "@")
    t = re.sub(r"\s*@\s*", "@", t)
    t = re.sub(r"(?<=[A-Za-z0-9])\s*[,;]\s*(?=(com|net|kr|org|co|re|ac|go|or)\b)", ".", t)
    t = re.sub(r"@([A-Za-z0-9\-]{2,}?)(net|com)(?![A-Za-z0-9.\-])", r"@\1.\2", t)   # 점이 빠진 'hanmailnet'
    out = []
    for m in _EMAIL.finditer(t):
        e = fix_email(m.group(0).strip(".-").lower(), domains)
        if e.count("@") == 1 and "." in e.split("@")[1]:
            out.append(e)
    return out


# 흔한 메일 도메인 — 한두 글자 오인식(`hanmal.net`·`nale.com`·`gmall.com`)을 바로잡는 기준(§5.22)
KNOWN_MAIL = ("naver.com", "hanmail.net", "daum.net", "gmail.com", "nate.com", "hotmail.com", "yahoo.com", "kakao.com",
              "korea.kr", "empas.com", "empal.com", "chol.com", "outlook.com", "outlook.kr", "korea.com", "lycos.co.kr",
              "dreamwiz.com", "paran.com", "hanafos.com", "yahoo.co.kr", "hanmir.com")
_MAIL_LABEL = re.compile(r"^(e-?mail|email|mail|mall|e)[.\-:_]", re.I)


def _edit(a: str, b: str) -> int:
    """편집 거리(짧은 글자열 — 도메인·아이디 비교용)."""
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def fix_email(e: str, domains=()) -> str:
    """읽은 메일 다듬기(§5.22) — 앞에 붙은 이름표('e-mail.'·'e.')를 떼고, 끝이 빠진 '.co'·'.ke' 는 '.kr' 로,
    도메인이 흔한 메일·같은 명함 누리집 도메인과 한두 글자 다르면 그것으로."""
    if e.count("@") != 1:
        return e
    loc, dom = e.split("@")
    m = _MAIL_LABEL.match(loc)
    if m and len(loc) - m.end() >= 2:
        loc = loc[m.end():]
    dom = re.sub(r"\.k[ef]$", ".kr", dom)
    dom = re.sub(r"\.(co|go|re|ac|or|ne)kr$", r".\1.kr", dom)             # 점이 빠진 'or kr'
    if re.search(r"\.(co|go|re|ac|or|ne)$", dom):
        dom += ".kr"
    if dom not in KNOWN_MAIL and dom not in domains and dom not in DOMAIN_ORG:
        best, bd = "", 9
        for k, lim in [(x, 2 if len(dom) >= 8 else 1) for x in KNOWN_MAIL] + [(x, 2) for x in domains] \
                + [(x, 1) for x in DOMAIN_ORG if len(x) >= 6]:
            d = _edit(dom, k)
            if d <= lim and d < bd:
                best, bd = k, d
        if best:
            dom = best
    return loc + "@" + dom


_MAIL_MIX = re.compile(r"(?<=\d)[osilq]|[osilq](?=\d)")   # 숫자 옆 o·s·i·l·q — 0·5·1·9 를 잘못 읽은 판이 많다(§5.23 실측)


def pick_emails(text: str, domains=()) -> list:
    """여러 번 읽은 글에서 메일 고르기 — 같은 도메인에 아이디가 한두 글자만 다른 것은 **가장 많이 나온 것** 하나로(§5.22)."""
    allm = find_emails(text, domains)
    cnt = {}
    for e in allm:
        cnt[e] = cnt.get(e, 0) + 1

    def known(e):
        d = e.split("@")[1]
        return d in KNOWN_MAIL or d in domains or d in DOMAIN_ORG

    def rank(e):                                       # 아는 도메인 → 많이 나온 것 → 숫자 옆 헷갈리는 글자 적은 것 → 긴 아이디 → 숫자 많은 것
        loc = e.split("@")[0]
        return (known(e), cnt[e], -len(_MAIL_MIX.findall(loc)), len(loc), len(re.findall(r"\d", loc)))

    def twins(a, b):
        la, da = a.split("@")
        lb, db = b.split("@")
        if da != db and _edit(da, db) > 2:
            return False
        if la == lb or _edit(la, lb) <= max(1, max(len(la), len(lb)) // 4):
            return True
        short, long_ = sorted((la, lb), key=len)
        return da == db and len(short) >= 2 and long_.endswith(short) and long_ != "e" + short   # 앞이 잘려 읽힌 아이디
    out = []
    for e in dict.fromkeys(allm):
        twin = next((o for o in out if twins(o, e)), None)
        if twin is None:
            out.append(e)
        elif rank(e) > rank(twin):
            out[out.index(twin)] = e
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
NAME_FEATS = ("bias", "h", "sur", "title", "org", "len2", "len3", "len4", "mail", "hint", "conf", "frag", "both", "tpl", "twin2")
NAME_W = {"bias": -1.5, "h": 2.0, "sur": 2.5, "title": 1.2, "org": -2.0, "len2": 0.1, "len3": 0.6, "len4": -0.4,
          "mail": 0.8, "hint": 5.0, "conf": 1.0, "frag": -0.5, "both": 0.7, "tpl": 3.0,
          "twin2": -2.0}         # 보조 엔진에서만 나왔고 기본 엔진 후보와 한 글자만 다름 — 보조 엔진이 글자를 잘못 읽은 쪽(§5.23)


def name_score(f: dict, w: Optional[dict] = None) -> float:
    w = w or NAME_W
    # 'adj' = §5.25 고정 보정(배우지 않는다 — NAME_FEATS 밖이라 이 PC 에서 배운 가중치와 무관하게 늘 더한다)
    return round(sum(w.get(k, 0.0) * float(f.get(k, 0.0)) for k in NAME_FEATS) + float(f.get("adj", 0.0)), 3)


# ── 이름 고정 보정(§5.25, 정답 대조 학습 2/3) — 배우는 가중치(NAME_FEATS)와 따로, 점수를 다 매긴 뒤 더한다 ──
# 이름(성 뒤 글자)에 흔히 쓰는 음절 — 한 글자만 다른 후보끼리 가를 때만 쓴다(OCR 이 '승'→'층', '찬'→'차' 로 읽는 일)
NAME_SYL = set("가각간갑강개건걸겸경계고곤공관광교구국군권규균극근금기길나남내녕노능다단달담대덕도돈동두득라란람랑래량려련렬령례로록룡루류륜률리린림"
               "마만명모목무문미민바박반방배백범법벽병보복본봉부분빈사산삼상새생서석선설섭성세소속손솔송수숙순술승시식신실심"
               "아안애양언엄여역연열염엽영예오옥온완왕요용우욱운웅원월위유육윤율은을음응의이익인일임"
               "자작장재전점정제조종주준중지직진찬창채천철청초총춘충치칠탁태택판팔평표필하학한함항해행향허헌혁현형혜호홍화환활황회효후훈휘흠흥희")
COMMON_SURNAMES = set("김이박최정강조윤장임한오서신권황안송류유홍전고문양손배백허남심노하곽성차주우구민진나지엄채원천방공현함변염여추도석선설")
# 이름이 아닌 낱말 조각 — 이것이 든 후보는 이름이 아니다(직함·기관·연락처 낱말이 성씨 글자로 시작해 후보가 되는 일)
NOT_NAME_PARTS = ("사무소", "사무", "공과", "공학", "전화", "부문", "기업", "도로", "기술", "사업", "설계", "연구", "본부", "지사", "센터",
                  "대학", "학교", "주소", "팩스", "휴대", "메일", "법률", "표준", "영업", "관리", "지원", "협회", "정보", "보수",
                  "유지", "시설", "공단", "공사", "건설", "산업", "개발", "시험", "검사", "안전", "품질", "환경", "교통", "구조",
                  "토목", "건축", "전기", "기계", "재료", "도시", "계획", "행정", "총무", "기획", "홍보", "경영", "회계",
                  "주식", "회사", "중앙", "공장", "지점")
ADJ_RARE = -3.0        # 한 글자만 다른 짝에서 드문 음절·드문 성 쪽(파일 이름 힌트 덤을 넘을 만큼 — ScanSnap 도 '승'→'층' 으로 읽는다)
ADJ_WORD = -3.0        # 이름이 아닌 낱말 조각
ADJ_PART = -1.5        # 성이 빠진 두 글자 조각('길동' — '홍길동' 이 후보에 있음)


def _rare_count(n: str) -> int:
    if n[:2] in COMPOUND_SURNAMES and len(n) >= 3:
        sur, given = n[:2], n[2:]
    else:
        sur, given = n[:1], n[1:]
    return int(sur not in COMMON_SURNAMES and sur not in COMPOUND_SURNAMES) + sum(1 for ch in given if ch not in NAME_SYL)


def name_adjust(cands: dict) -> dict:
    """후보 글 → 고정 보정 점수(§5.25). 한 글자(세 글자 이름은 두 글자까지) 다른 짝에서 드문 음절·성이 더 많은 쪽,
    이름이 아닌 낱말이 든 것, 성 빠진 두 글자 조각을 내린다."""
    adj = {t: 0.0 for t in cands}
    texts = list(cands)
    for t in texts:
        if any(w in t for w in NOT_NAME_PARTS):
            adj[t] += ADJ_WORD
        if len(t) == 2 and any(len(u) == 3 and (u[1:] == t and u[0] in SURNAMES or u[:2] == t) for u in texts):
            adj[t] += ADJ_PART                         # '길동'(홍길동)·'홍길'(홍길동) — 세 글자 이름의 조각
    for i, a in enumerate(texts):
        for b in texts[i + 1:]:
            if len(a) != len(b) or len(a) < 2:
                continue
            d = _edit(a, b)
            if d == 1 or (d == 2 and len(a) >= 3):
                ra, rb = _rare_count(a), _rare_count(b)
                if ra > rb:
                    adj[a] += ADJ_RARE
                elif rb > ra:
                    adj[b] += ADJ_RARE
    return adj


def fix_latin_name(n: str) -> str:
    """영문 이름의 'I'·'l' 헷갈림 — 소문자 뒤의 대문자 I 는 l('MitcheII' → 'Mitchell')."""
    return " ".join(re.sub(r"(?<=[a-z])I+", lambda m: "l" * len(m.group(0)), w) for w in n.split())


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
_STRIP_LONG = sorted(TITLES_KO + QUALS, key=len, reverse=True)     # 이름에서 뗄 것(직함 + 자격)


def qual_token(tok: str) -> str:
    """자격·학위 낱말인가('공학박사'·'토목구조기술사' 처럼 자격으로 끝나는 짧은 한글 낱말)."""
    t = re.sub(r"[^가-힣]", "", tok)
    if not t or len(t) > 9:
        return ""
    return t if any(t.endswith(q) for q in QUALS) else ""


_ROLE_PREFIX = ("선임", "책임", "수석", "주임", "전임", "위촉", "초빙", "객원", "연수", "전문", "학생", "인턴", "박사후", "부", "선임연구",
                "수석전문", "상임", "비상임", "명예")


def title_token(tok: str) -> str:
    """낱말이 직위인가 — '시험실장'·'품질팀장'·'기술이사' 처럼 직함으로 끝나는 짧은 한글 낱말이면 그 낱말."""
    t = re.sub(r"[^가-힣]", "", tok)
    if not t or len(t) > 9:
        return ""
    for k in _TITLES_LONG:
        if t.endswith(k):
            if k.endswith("원") and len(t) > len(k) and not t[:-len(k)].endswith(_ROLE_PREFIX):
                return ""                              # '…환경연구원'·'…기술연구원' 은 기관 이름(§5.23 실측 — 직함 '…연구원' 은 앞말이 선임·책임 등)
            return t if len(t) - len(k) <= 4 else ""      # '가나다시험연구원' 은 기관 이름 — 앞말이 길면 직위가 아니다
    return ""


def join_letter_lines(lines: list) -> list:
    """한 글자씩 따로 읽힌 줄(넓게 띄운 큰 이름 '김   갑   중' 을 흩어진 글 읽기가 글자마다 따로 낸 것)을 같은 높이·같은 줄끼리
    왼쪽부터 이어 새 줄로(§5.22). 2~4 글자일 때만."""
    singles = [ln for ln in lines if re.fullmatch(r"[가-힣]", ln.text.strip())]
    out, used = [], set()
    for i, a in enumerate(singles):
        if i in used:
            continue
        ay = a.center()[1]
        grp = [i]
        for j in range(i + 1, len(singles)):
            b = singles[j]
            if j in used or not (0.6 <= b.height / max(a.height, 1e-6) <= 1.6):
                continue
            if abs(b.center()[1] - ay) <= 0.5 * max(a.height, b.height):
                if any(abs(singles[k].cx - b.cx) < 0.5 * b.height for k in grp):
                    used.add(j)                        # 같은 자리 글자(뒤집어 읽은 판 등) — 한 번만
                    continue
                grp.append(j)
        if 2 <= len(grp) <= 4:
            used.update(grp)
            g = sorted((singles[k] for k in grp), key=lambda x: x.cx)
            if all(g[k + 1].cx - g[k].cx < 0.35 for k in range(len(g) - 1)):
                out.append(Line("".join(x.text.strip() for x in g), max(x.height for x in g),
                                sum(x.conf for x in g) / len(g), min(x.y for x in g),
                                sum(x.cx for x in g) / len(g), ay))
    return out


def name_candidates_ko(lines: list, emails: list, hint: str = "", weights: Optional[dict] = None) -> list:
    """한글 이름 후보(R3) — 특징(크기·성씨·직함 이웃·메일 아이디·파일 이름 힌트 …)의 가중합(명함 SOT §5.2 의 3·§5.11)."""
    lines = list(lines) + join_letter_lines(lines)
    cands = {}
    prim = set()
    hmax = max((ln.height for ln in lines), default=1) or 1
    for idx, ln in enumerate(lines):
        raw = merge_spaced(ln.text)
        near = " ".join(x.text for x in lines[max(0, idx - 1): idx + 2])
        pieces = set()
        whole = clean_name_ko(" ".join(t for t in raw.split() if not (title_token(t) or qual_token(t))))
        if 2 <= len(whole) <= 4 and len(re.sub(r"[^가-힣\s]", "", raw).split()) <= 4:
            pieces.add(whole)                       # '홍 길 동' · '홍길동 부장' → '홍길동'
        for run in re.findall(r"[가-힣]+", " ".join(t for t in raw.split() if not (title_token(t) or qual_token(t)))):
            if 2 <= len(run) <= 4:
                pieces.add(run)
            elif len(run) > 4:                      # '홍길동부장'·'기술연구소홍길동' — 성씨 자리에서 3·2자 조각
                bare = re.sub("|".join(_STRIP_LONG), "", run)     # '대표이사홍길동' → '홍길동'(붙은 직함을 뗀 통째 — 조각이 아니다)
                if 2 <= len(bare) <= 4 and bare != run:
                    pieces.add(bare)
                for i, ch in enumerate(run):
                    if ch in SURNAMES:
                        for L in (3, 2):
                            if i + L <= len(run):
                                pieces.add(run[i:i + L])
        for n in pieces:
            if n in TITLES_KO or title_token(n) or qual_token(n) or any(n.endswith(d) and len(n) > 2 for d in ("회사", "기술", "건설", "산업")):
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
                          and n != re.sub("|".join(_STRIP_LONG), "", re.sub(r"[^가-힣]", "", raw))),
                 "both": 0.0, "tpl": 0.0, "cx": round(cx, 3), "cy": round(cy, 3)}
            why = tuple(k for k in ("title", "mail", "hint") if f[k])
            sc = name_score(f, weights)
            if ln.src != "w":
                prim.add(n)
            if n not in cands or cands[n].score < sc:
                cands[n] = Cand(n, sc, why, f)
    if prim:
        # 보조 엔진에만 있는 후보가 기본 엔진 후보와 한 글자만 다르면 보조 엔진의 잘못 읽음으로 본다
        #   (§5.23 실측: 한 글자 다른 1·2위 35쌍 — 정답이 기본에만 19, 보조에만 4)
        for c in list(cands.values()):
            if c.text not in prim and any(len(p) == len(c.text) and _edit(p, c.text) == 1 for p in prim):
                f = dict(c.feat)
                f["twin2"] = 1.0
                cands[c.text] = Cand(c.text, name_score(f, weights), tuple(c.why), f)
    if hint and hint not in cands and re.fullmatch(r"[가-힣]{2,4}", hint) and _surname_score(hint) > 0:
        # 파일 이름의 이름(ScanSnap 이 읽은 것)은 OCR 에 없어도 후보로(§5.22 실측 — 파일 이름 이름이 맞는 비율 73%, 이 OCR 1위 53%)
        f = {"bias": 1.0, "h": 0.0, "sur": 1.0, "title": 0.0, "org": 0.0, "len2": float(len(hint) == 2),
             "len3": float(len(hint) == 3), "len4": float(len(hint) == 4), "mail": 1.0 if _email_hint(hint, emails) else 0.0,
             "hint": 1.0, "conf": 0.0, "frag": 0.0, "both": 0.0, "tpl": 0.0, "cx": -1.0, "cy": -1.0}
        cands[hint] = Cand(hint, name_score(f, weights), ("hint", "파일이름"), f)
    if hint and len(hint) == 2 and hint in cands:
        # 파일 이름이 성을 빠뜨린 두 글자('길동')이고 OCR 에 '성+그 두 글자'('홍길동')가 있으면 덤을 세 글자 쪽으로(§5.25)
        full = [c for c in cands.values() if len(c.text) == 3 and c.text[1:] == hint and c.text[0] in SURNAMES]
        if full:
            best = max(full, key=lambda c: c.score)
            for c, hv in ((best, 1.0), (cands[hint], 0.0)):
                f = dict(c.feat)
                f["hint"] = hv
                cands[c.text] = Cand(c.text, name_score(f, weights), tuple(c.why) + (("hint",) if hv == 1.0 else ()), f)
            hint = best.text
    if hint and hint in cands:
        # ScanSnap 은 흔한 이름으로 한 글자 바꿔 붙이는 일이 많다 — OCR 이 한 글자만 다르게 읽은 후보가 있으면 그쪽에
        #   덤을 옮긴다(§5.22 실측: 그런 45장 중 OCR 쪽이 맞음 33, 파일 이름이 맞음 8)
        near = [c for c in cands.values() if c.text != hint and len(c.text) == len(hint) and _edit(c.text, hint) == 1
                and c.feat.get("h", 0) > 0 and _surname_score(c.text) > 0 and not c.feat.get("twin2")]
        if near:
            best = max(near, key=lambda c: c.score)
            for c, hv in ((best, 1.0), (cands[hint], 0.3)):
                f = dict(c.feat)
                f["hint"] = hv
                cands[c.text] = Cand(c.text, name_score(f, weights), tuple(c.why) + (("hint",) if hv == 1.0 else ()), f)
    adj = name_adjust(cands)                            # §5.25 고정 보정(배우는 가중치 밖)
    for t, c in list(cands.items()):
        if adj[t]:
            f = dict(c.feat, adj=adj[t])
            cands[t] = Cand(c.text, name_score(f, weights), c.why, f)
    return sorted(cands.values(), key=lambda c: (-c.score, c.text))   # 같은 점수는 글자 차례(실행마다 같게 — set 차례는 실행마다 다르다)


def name_candidates_en(lines: list, emails: list, hint: str = "") -> list:
    cands = {}
    hmax = max((ln.height for ln in lines), default=1) or 1
    for idx, ln in enumerate(lines):
        t = ln.text.strip()
        if _HANGUL.search(t) or "@" in t or re.search(r"\d", t):
            continue
        low = t.lower()
        low_ns = low.replace(" ", "")                    # 'UNIVE RSITY' 처럼 띄어 읽힌 기관 낱말도(§5.25)
        if CORP_MARKS_EN.search(t) or any(w in low_ns for w in ORG_WORDS_EN):
            continue
        if any(w.lower() in EN_NAME_STOP for w in t.split()):
            continue
        nm = re.sub(r",?\s*(ph\.?\s?d\.?|p\.?e\.?|m\.?s\.?)$", "", t, flags=re.I)
        words = [w for w in nm.replace(",", " ").split() if w]
        while len(words) > 2 and re.fullmatch(r"[A-Za-z]\.?", words[0]) is not None and not words[0].endswith("."):
            words = words[1:]                          # 앞에 붙은 낱글자 잡음('T John Doe', §5.22)
        if not (2 <= len(words) <= 4) or not all(re.fullmatch(r"[A-Z][A-Za-z'\-]*\.?", w) for w in words):
            continue
        if any(w.lower().strip(".") in TITLES_EN for w in words):
            continue
        n = fix_latin_name(" ".join(words))
        near = " ".join(x.text.lower() for x in lines[max(0, idx - 1): idx + 2])
        s = 2.0 * (ln.height / hmax) + (1.0 if any(k in near for k in TITLES_EN) else 0.0)
        local = re.sub(r"[^a-z]", "", (emails[0].split("@")[0] if emails else ""))
        if local and any(w.lower().strip(".") in local for w in words if len(w) > 1):
            s += 0.8
        if hint and n.lower() == hint.lower():
            s += 1.5
        cands[n] = Cand(n, round(s, 3))
    return sorted(cands.values(), key=lambda c: (-c.score, c.text))   # 같은 점수는 글자 차례(실행마다 같게 — set 차례는 실행마다 다르다)


_MARK = r"(?:\(\s*[주유사재합株]\s*\)|\[\s*[주유]\s*\]|㈜|주식회사|유한회사|합자회사|합명회사|사단법인|재단법인|농업회사법인|영농조합법인|의료법인|학교법인|사회복지법인)"   # §5.28
_MARK_RX = re.compile(_MARK)
_WORD_OK = re.compile(r"[가-힣A-Za-z0-9&·\-]+")


def _corp_word_stop(tok: str) -> bool:
    """회사명 낱말 잇기를 멈출 자리 — 부서·직함·자격 낱말, 숫자·연락처·누리집."""
    return bool(dept_token(tok) or title_token(tok) or qual_token(tok) or re.search(r"\d{3}|@|www|\.kr|\.com", tok, re.I)
                or not _WORD_OK.fullmatch(tok) or re.fullmatch(r"[\d\-]+", tok) or project_line(tok))   # 숫자만·공사 이름(§5.22)


def corp_adjacent(text: str) -> list:
    """(주)·(유)·㈜·주식회사 … 가 **앞이나 뒤에 붙은 낱말들** = 회사 이름(261117-17 사용자 지시). 법인 꼴에서 바깥쪽으로
    낱말을 잇다가 부서·직함·자격·연락처를 만나면 멈춘다(같은 줄의 부서·직함은 섞지 않는다). 한글은 붙여 쓴다."""
    t = merge_spaced(_nfc(text))
    out = []
    for m in _MARK_RX.finditer(t):
        after = t[m.end():].split()
        before = t[:m.start()].split()
        words = []
        for tok in after:                              # 뒤로 — '(주) 가나다 기술 품질팀' → 가나다·기술
            if _MARK_RX.search(tok) or _corp_word_stop(tok):
                break
            words.append(tok)
        if not words:
            for tok in reversed(before):               # 앞으로 — '가나다 기술(주)' → 가나다·기술
                if _MARK_RX.search(tok) or _corp_word_stop(tok):
                    break
                words.insert(0, tok)
        c = strip_corp(nospace_ko(" ".join(words)))
        if 2 <= len(c) <= 30 and c not in out and not project_line(c):
            out.append(c)
    return out


ORG_TAIL_STRONG = ("주식회사", "회사", "기업", "건설", "산업", "기술", "엔지니어링", "공사", "공단", "협회", "학회", "연구원",
                   "교육원", "진흥원", "관리원", "인증원", "기술원", "평가원", "정보원", "시험원", "대학교", "대학", "아스콘", "개발",
                   "그룹", "컨설팅", "컨설턴트", "공업", "중공업", "화학", "유화", "테크", "텍", "솔루션", "시스템", "조합", "재단",
                   "은행", "청", "시청", "구청", "도청", "군청", "연합회", "중앙회", "의회", "신문", "방송", "건축사사무소", "사무소",
                   "교통부", "노동부", "환경부", "자원부", "안전부", "재정부", "통신부", "수산부", "외교부", "국방부", "법무부",
                   "교육부", "복지부", "가족부", "관광부", "식품부", "기업부", "통일부", "감사원", "국회", "공사(주)")


def org_token(w: str) -> bool:
    """한 낱말이 기관·회사 이름인가(§5.22) — 한글 3~20자, 강한 기관 끝말로 끝나고 부서·직함·공사 이름이 아닌 것."""
    if not (3 <= len(w) <= 20) or not _HANGUL.search(w) or re.search(r"[^가-힣A-Za-z&·\-]", w):
        return False
    if title_token(w) or qual_token(w) or project_line(w) or w in ORG_TAIL_STRONG:
        return False
    if not w.endswith(ORG_TAIL_STRONG):
        return False
    return not (dept_token(w) and not w.endswith(("교통부", "노동부", "환경부", "자원부", "안전부", "재정부", "통신부", "수산부",
                                                  "외교부", "국방부", "법무부", "교육부", "복지부", "가족부", "관광부", "식품부",
                                                  "기업부", "통일부", "공사", "공단", "연구원", "교육원", "진흥원", "관리원",
                                                  "기술원", "대학교")))


def project_line(s: str) -> bool:
    """공사 이름(현장) 줄인가 — '…도로건설공사'·'…확장공사'·'(2공구)'·'현장'(§5.22). 회사가 아니라 부서 칸에 간다."""
    c = re.sub(r"\s", "", s)
    return bool(re.search(r"(도로|건설|확장|개량|조성|시설|정비|보수|개설)공사|공구|현장|감리단|사업단", c)) \
        and not c.endswith(("한국도로공사", "도로공사", "주택공사", "토지주택공사"))


def _org_piece(w: str) -> bool:
    """기관 이름의 뒤 조각(앞말이 떨어져 읽힌 것)인가 — 3자 이하이거나 기관 끝말 그 자체('교통부'·'엔지니어링')."""
    return bool(w) and (len(w) <= 3 or w in ORG_TAIL_STRONG)


def company_candidates_ko(lines: list, emails: list, urls: list, hint: str = "") -> list:
    cands = {}
    seen_tok = {}
    hmax = max((ln.height for ln in lines), default=1) or 1
    for ln in lines:
        raw = ln.text
        if not _HANGUL.search(raw) or _ADDR_KO.search(raw) or find_phones(raw) or "@" in raw:
            continue
        cx, cy = ln.center()
        for c in corp_adjacent(raw):                   # 법인 꼴이 붙은 낱말이 1위(줄 통째보다 앞)
            s = 3.5 + 1.0 * (ln.height / hmax) + (1.5 if hint and c == hint.replace(" ", "") else 0.0)
            if c not in cands or cands[c].score < s:
                cands[c] = Cand(c, round(s, 3), ("법인",), {"cx": round(cx, 3), "cy": round(cy, 3)})
        has_mark = any(m in raw for m in CORP_MARKS_KO)
        org = _is_orgish(raw)
        if not (has_mark or org):
            continue
        merged = merge_spaced(_nfc(raw))
        tok_found = False
        ws = [strip_corp(re.sub(r"^[^가-힣A-Za-z]*[가-힣株好쥐任]?\)", "", tok)).strip(" ,.;:/'\"") for tok in merged.split()]
        pairs = [(w, 0.0) for w in ws] + [(a + b, 0.2) for a, b in zip(ws, ws[1:])
                                          if len(a) >= 2 and _HANGUL.search(a) and not org_token(a) and _org_piece(b)]
        for w, plus in pairs:                          # 줄 속 기관 낱말('LH 한국토지주택공사' → '한국토지주택공사', '국토 교통부' → '국토교통부', §5.22)
            if org_token(w):
                tok_found = True
                s = 1.0 * (ln.height / hmax) + (2.0 if has_mark else 0.8) + 0.4 + plus \
                    + (1.5 if hint and w == hint.replace(" ", "") else 0.0)
                seen_tok[w] = seen_tok.get(w, 0) + 1
                if w not in cands or cands[w].score < s:
                    cands[w] = Cand(w, round(s, 3), ("낱말",), {"cx": round(cx, 3), "cy": round(cy, 3)})
        c = strip_corp(re.sub("|".join(TITLES_KO), " ", raw))
        c = re.sub(r"\s+", " ", c).strip()
        if not (2 <= len(re.sub(r"\s", "", c)) <= 30):
            continue
        s = 1.0 * (ln.height / hmax) + (2.0 if has_mark else 0.8)
        toks = merged.split()
        if "/" in raw or any(dept_token(x) or title_token(x) or qual_token(x) for x in toks) or project_line(merged):
            s -= 1.5                                   # 부서·직함·공사 이름이 든 줄(§5.22)
        if re.search(r"\d", c) or any(not re.fullmatch(r"[가-힣A-Za-z&·\-]+", x) for x in c.split()):
            s -= 0.7                                   # 숫자·기호 낀 줄
        if tok_found and not org_token(c.replace(" ", "")):
            s -= 2.0                                   # 같은 줄에서 깨끗한 기관 낱말을 뽑았으면 줄 통째는 뒤로(§5.22)
        if hint and (c.replace(" ", "") == hint.replace(" ", "")):
            s += 1.5
        cx, cy = ln.center()
        if c not in cands or cands[c].score < s:
            cands[c] = Cand(c, round(s, 3), (), {"cx": round(cx, 3), "cy": round(cy, 3)})
    if hint and hint not in cands and _HANGUL.search(hint):
        cands[hint] = Cand(hint, 0.5, ("파일이름",))
    org = org_from_domains(emails, urls)
    if org:                                            # 메일·누리집 도메인이 아는 기관이면 그 이름과 한두 글자 다른 후보('안국도로공사')를 그 이름으로(§5.22)
        near = [c for c in cands.values()
                if c.text == org or org in c.text.replace(" ", "") or _edit(c.text.replace(" ", ""), org) <= max(1, len(org) // 6)]
        if near:
            best = max(near, key=lambda c: c.score)
            cands[org] = Cand(org, round(best.score + 1.0, 3), ("도메인",), best.feat)
    for w, n in seen_tok.items():                      # 여러 번(여러 판·줄) 같은 글로 읽힌 기관 낱말에 덤(§5.22)
        if n > 1 and w in cands:
            cands[w].score = round(cands[w].score + min(0.9, 0.3 * (n - 1)), 3)
    for a in list(cands.values()):                     # 조각 후보('교통부')를 품은 깨끗한 긴 후보('국토교통부')를 앞으로(§5.22)
        if not _org_piece(a.text):
            continue
        for b in cands.values():
            if b is not a and len(b.text) > len(a.text) and b.text.endswith(a.text) and org_token(b.text) \
                    and b.score <= a.score:
                b.score = round(a.score + 0.1, 3)
    _pick_twin_variant(cands)
    return sorted(cands.values(), key=lambda c: (-c.score, c.text))   # 같은 점수는 글자 차례(실행마다 같게 — set 차례는 실행마다 다르다)


ORG_PIECES_KO = ORG_TAIL_STRONG + ("이앤씨", "이엔씨", "씨앤씨", "디엔씨", "에스앤씨", "엔씨", "하이테크", "코리아", "엔지니어스",
                                   "인터내셔널", "글로벌", "디자인", "건영", "토건", "종합건설", "산업인증원")


def _rare_ko(s: str) -> int:
    """완성형(KS X 1001) 2350자 밖의 한글 음절 수 — 명함 글에는 거의 없으니 잘못 읽은 표시('강름뮘주')."""
    # 파이썬 euc-kr 은 2350자 밖 음절도 8바이트 조합 꼴로 적어 주므로 예외가 아니라 길이(2바이트)로 가른다
    return sum(1 for ch in s if "가" <= ch <= "힣" and len(ch.encode("euc-kr")) != 2)


def _pick_twin_variant(cands: dict) -> None:
    """한두 글자만 다르게 읽힌 같은 회사 이름 판들('…엔지니어팅'·'…엔지니어링') 중 하나를 고른다 — 드문 글자 없는 것 →
    아는 회사 낱말 많은 것 → 점수(여러 줄에 나온 수는 넣지 않는다 — 실측에서 나빠짐). 고른 판이 무리의 가장 높은 점수를 갖는다(§5.23, 두 엔진을 합치면 판이 늘어난다)."""
    ko = [c for c in cands.values() if re.fullmatch(r"[가-힣]{3,}", c.text)]
    done = set()
    for a in sorted(ko, key=lambda c: -c.score):
        if a.text in done:
            continue
        grp = [b for b in ko if b.text not in done and len(b.text) == len(a.text)
               and _edit(a.text, b.text) <= max(1, len(a.text) // 4)]
        done.update(b.text for b in grp)
        if len(grp) < 2:
            continue
        key = lambda c: (-_rare_ko(c.text), sum(p in c.text for p in ORG_PIECES_KO), c.score)
        lead = max(grp, key=key)
        top = max(b.score for b in grp)
        if lead.score < top:
            lead.score = round(top + 0.01, 3)


def company_candidates_en(lines: list, emails: list, urls: list) -> list:
    cands = {}
    for ln in lines:
        t = ln.text.strip()
        if _HANGUL.search(t) or "@" in t:
            continue
        if CORP_MARKS_EN.search(t) or any(w in t.lower() for w in ORG_WORDS_EN):
            c = re.sub(r"\s+", " ", t).strip(" ,.")
            c = re.sub(r"(\s+([\d:;'\"|.,\-]+|[A-Za-z]))+$", "", c).strip(" ,.:")   # 끝에 붙은 숫자·기호·낱글자(§5.22)
            if 3 <= len(c) <= 60 and not re.search(r"\d{3}", c):
                cands[c] = Cand(c, 2.0 if CORP_MARKS_EN.search(t) else 1.0)
    for e in emails:
        dom = e.split("@")[1].split(".")[0]
        if dom and not any(f.split(".")[0] == dom for f in FREE_MAIL):
            cands.setdefault(dom, Cand(dom, 0.3, ("메일",)))
    return sorted(cands.values(), key=lambda c: (-c.score, c.text))   # 같은 점수는 글자 차례(실행마다 같게 — set 차례는 실행마다 다르다)


def nospace_ko(s: str) -> str:
    """한글 사이 띄어쓰기를 없앤다 — 부서·직함·회사명은 붙여 쓴다(사용자 지시 261117-15)."""
    return re.sub(r"(?<=[가-힣])\s+(?=[가-힣])", "", (s or "").strip())


def _titles_in(compact: str) -> list:
    """띄어쓰기를 지운 한글 줄에서 직함을 **가장 긴 것부터** 겹치지 않게 — '대표 이사' 를 '대표'·'이사' 로 쪼개지 않는다(261117-15)."""
    out, i = [], 0
    while i < len(compact):
        hit = next((t for t in _TITLES_LONG if compact.startswith(t, i)), None)
        if hit:
            out.append(hit)
            i += len(hit)
        else:
            i += 1
    return out


_ORG_TAIL = ("연구원", "공사", "공단", "협회", "학회", "대학교", "대학", "기술원", "재단", "조합")


def titles_of(lines: list) -> tuple:
    ko, en, sub = [], [], []
    for ln in lines:
        merged = merge_spaced(ln.text)
        if _ADDR_KO.search(ln.text):
            continue
        toks = [t for t in re.split(r"[\s/|·,]+", merged) if t]
        found = False
        i = 0
        while i < len(toks):
            tt = title_token(toks[i])
            if i + 1 < len(toks):
                both = re.sub(r"[^가-힣]", "", toks[i] + toks[i + 1])
                if both in TITLES_KO:                  # '책임 연구원'·'시설 사무관' → 겹 직함 하나로(옆 낱말과 합쳐, §5.22)
                    tt, i = both, i + 1
            if tt:
                found = True
                if tt not in ko:
                    ko.append(tt)                      # '시험실장 홍길동' → 직위 '시험실장'(낱말 통째가 먼저)
            i += 1
        compact = re.sub(r"[^가-힣]", "", merged)
        if found or any(m in ln.text for m in CORP_MARKS_KO) or compact.endswith(_ORG_TAIL):   # 낱말로 찾은 줄은 붙여 찾지 않는다('…부 부장' ≠ '부부장')
            continue                                   # 회사·기관 줄 속 '연구원' 등은 직함이 아니다
        for t in _titles_in(compact):
            if t not in sub:
                sub.append(t)                          # 띄워 읽은 '대표 이사' → '대표이사'(줄이지 않는다)
    ko += [t for t in sub if t not in ko and not any(t in k for k in ko)]
    for ln in lines:
        low = ln.text.lower()
        if not _HANGUL.search(ln.text) and any(k in low for k in TITLES_EN) and len(ln.text) < 60 \
                and not re.search(r"\d{3}", ln.text):
            en.append(ln.text.strip())
    # 긴 직함 먼저('대표이사' 가 '대표'·'이사' 를 덮는다) — 줄이지 않는다
    ko = [t for t in ko if not any(t != u and t in u for u in ko)]
    ko.sort(key=lambda t: -len(t))
    return ko, en


def dept_token(tok: str) -> str:
    """부서 낱말인가 — 한글 2~12자이고 부서 끝말로 끝나며 직위가 아닌 것('품질관리팀'·'기술연구소'·'도로시설과')."""
    t = re.sub(r"[^가-힣]", "", tok)
    if not (2 <= len(t) <= 20) or title_token(t):
        return ""
    full = re.sub(r"[^가-힣A-Za-z0-9&()\-]", "", tok)          # '감리2부'·'Smart사업부' — 숫자·영문도 남긴다(§5.22)
    if not full.endswith(t[-1]):
        return ""
    for k in DEPT_SUFFIX:
        if t.endswith(k) and len(t) > len(k):
            return full
    return ""


def dept_runs(parts: list, names=()) -> list:
    """한 줄의 낱말들 → 부서 묶음들. 직함·자격·기관명·이름·기호 낱말에서 끊고, 끊긴 묶음은 **부서 끝말 낱말로 끝날 때만**
    (뒤쪽 부서 아닌 낱말은 버림) 붙여 쓴 한 덩어리로. 한글 3자 미만은 버린다(§5.22)."""
    out, run = [], []

    def flush():
        while run and not dept_token(run[-1]):
            run.pop()
        while run and re.fullmatch(r"[A-Za-z]{3,}", run[0]):
            run.pop(0)                                 # 앞에 붙은 영문 낱말(로고 글자 등)
        p = "".join(run)
        if len(_HANGUL.findall(p)) >= 3:
            out.append(p)
        run.clear()

    for p in parts:
        w = re.sub(r"[^가-힣A-Za-z0-9&()\-]", "", p)
        hw = re.sub(r"[^가-힣]", "", w)
        if not w or title_token(p) or qual_token(p) or org_token(w) or w in ORG_TAIL_STRONG or (hw and hw in names) \
                or not re.search(r"[가-힣A-Za-z]", w):
            flush()
            continue
        run.append(w)
    flush()
    return out


def dept_of(lines: list, companies=(), names=()) -> tuple:
    """부서(한글, 영문) — 회사·기관 후보와 같은 낱말·법인 꼴이 든 줄·주소 줄은 뺀다. 한 줄에 여럿이면 이어 쓴다('기술본부 품질팀')."""
    comp = {re.sub(r"\s", "", c) for c in companies if c}
    ko = en = ""
    got, last = [], -9
    for i, ln in enumerate(lines):
        raw = merge_spaced(ln.text)
        if _ADDR_KO.search(raw) or any(m in raw for m in CORP_MARKS_KO) or find_phones(raw) or "@" in raw:
            continue
        parts = [t for t in re.split(r"[\s/|·]+", raw) if t]
        if project_line(raw):                          # 공사 이름(현장)은 부서 칸에(§5.22) — 직함·자격 낱말만 뺀다
            p = re.sub(r"[^가-힣A-Za-z0-9()\-]", "", "".join(t for t in parts if not (title_token(t) or qual_token(t))))
            toks = [p] if len(p) >= 4 else []
        else:
            toks = dept_runs(parts, names)             # '도로교통연구 본부' → 이어진 낱말 묶음 통째(§5.22)
        toks = [t for t in toks if t and t not in comp and not any(t in c or c in t for c in comp if len(c) >= 3)]
        if toks and (not got or i == last + 1):        # 바로 다음 줄의 부서는 이어 쓴다('…사업단' + '품질팀', §5.22)
            got += toks
            last = i
        elif got and i > last + 1:
            last = 10 ** 9                             # 떨어진 줄은 잇지 않는다
        if not ko and got and last == 10 ** 9:
            ko = "".join(dict.fromkeys(got))
    if not ko and got:
        ko = "".join(dict.fromkeys(got))               # 부서는 붙여 쓴다(261117-15 — '기술본부품질관리팀')
    for ln in lines:
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
    r.ptexts = [ln.text for ln in lines]
    r.phones = pick_phones(r.ptexts)
    r.urls = list(dict.fromkeys(find_urls(txt)))
    r.emails = pick_emails(txt, tuple(domain_of(u) for u in r.urls))
    r.hangul = len(_HANGUL.findall(txt))
    r.latin = len(_LATIN.findall(re.sub(_EMAIL, "", txt)))
    hk = hint_name if _HANGUL.search(hint_name or "") else ""
    he = hint_name if hint_name and not hk else ""
    r.names_ko = name_candidates_ko(list(lines) + list(name_extra), r.emails, hk)
    r.names_en = name_candidates_en(lines, r.emails, he)
    r.companies_ko = company_candidates_ko(lines, r.emails, r.urls, hint_company)
    r.companies_en = company_candidates_en(lines, r.emails, r.urls)
    r.titles_ko, r.titles_en = titles_of(lines)
    r.dept_ko, r.dept_en = dept_of(lines, [c.text for c in r.companies_ko[:1]] + [hint_company],
                                   [c.text for c in r.names_ko[:3] if not dept_token(c.text)] + ([hk] if hk else []))   # 회사 1위만 뺀다(부서 줄도 기관꼴 후보가 된다)
    r.address_ko, r.address_en = address_of(lines)
    r.conf = sum(ln.conf for ln in lines) / len(lines) if lines else 0.0
    return r


def _weak_name(r: SideResult) -> bool:
    c = r.names_ko
    return not c or c[0].score < NAME_STRONG or (len(c) > 1 and c[0].score - c[1].score < NAME_GAP)


NAME_STRONG = 4.0        # 1위 후보 점수가 이 아래이거나
NAME_GAP = 1.0           #   2위와의 차이가 이 아래면 '약함' — 이름 덧읽기·확인 표 '확인 필요'


BLOCK_READ = True         # 굵거나 큰 구획을 잘라 한 줄로 다시 읽어 그 판에 더한다(§5.28)

def block_lines(im) -> list:
    """이름용 그림 → 굵거나 큰 구획(`layout.pick_blocks`)을 둘레를 조금 넓혀 잘라 한 줄(psm 7)로 읽은 [Line](그림 비율 좌표)."""
    from viewer.bizcard import layout
    try:
        picks = layout.pick_blocks(layout.leaves(im))
    except Exception:
        return []
    IW, IH = im.size
    out = []
    for b in picks:
        h = b["y1"] - b["y0"]
        dx = 0.3 * h * IH / max(1, IW)
        x0, x1 = max(0.0, b["x0"] - dx), min(1.0, b["x1"] + dx)
        y0, y1 = max(0.0, b["y0"] - 0.2 * h), min(1.0, b["y1"] + 0.2 * h)
        crop = im.crop((int(x0 * IW), int(y0 * IH), int(x1 * IW) + 1, int(y1 * IH) + 1))
        for ln in ocr_lines(prep_box(crop), 7, win=False):
            out.append(Line(ln.text, (y1 - y0) * 0.8, ln.conf, y0, (x0 + x1) / 2, (y0 + y1) / 2, "b"))
    return out


def read_side(images: list, hint_name: str = "", hint_company: str = "", extra: bool = True) -> Optional[SideResult]:
    """한 면을 그림 여럿으로 읽어 합친다 — 줄은 모두 모아 한 번에 뽑고, 두 판에서 모두 나온 이름에 덤."""
    if not images:
        return None
    per = [ocr_lines(im) for im in images]
    if extra and BLOCK_READ:
        # 굵거나 큰 구획 다시 읽기(§5.28) — 이름용 그림의 기본 판에. 약할 때만 읽으면 정답 대조 학습·평가 모두 떨어져 늘 읽는다
        per[-1] = per[-1] + block_lines(images[-1])
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
        r.urls += [u for u in re_.urls if u not in r.urls]
        r.emails = pick_emails("\n".join(ln.text for ln in allines + el), tuple(domain_of(u) for u in r.urls))   # 두 언어 읽기를 함께 세어 고른다(§5.22)
        r.ptexts = r.ptexts + re_.ptexts
        r.phones = pick_phones(r.ptexts)               # 두 언어 읽기를 함께 세어 고른다(§5.22)
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
    # 공공 기관 더(§5.22)
    "koreaexim.go.kr": "한국수출입은행", "kaia.re.kr": "국토교통과학기술진흥원", "koti.re.kr": "한국교통연구원",
    "kroad.or.kr": "한국도로협회", "sisul.or.kr": "서울시설공단", "kbiz.or.kr": "중소기업중앙회", "kei.re.kr": "한국환경연구원",
    "kgs.or.kr": "한국가스안전공사", "kca.go.kr": "한국소비자원", "airport.co.kr": "한국공항공사", "kicte.or.kr": "건설기술교육원",
    "keiti.re.kr": "한국환경산업기술원", "kier.re.kr": "한국에너지기술연구원", "kimm.re.kr": "한국기계연구원",
    "krict.re.kr": "한국화학연구원", "kips.kr": "한국제품안전관리원", "kip.re.kr": "한국조달연구원", "sit.re.kr": "서울기술연구원",
    "korcham.net": "대한상공회의소", "pps.go.kr": "조달청", "moel.go.kr": "고용노동부", "bai.go.kr": "감사원",
    "jejutp.or.kr": "제주테크노파크", "jntp.or.kr": "전남테크노파크", "snu.ac.kr": "서울대학교", "uos.ac.kr": "서울시립대학교",
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


def correction_ok(field: str, wrong: str, right: str) -> bool:
    """교정으로 배울·쓸 만한가(261117-18 사용자 보고 '이사는 대표이사가 아니고 대표이사는 그냥 이사가 아니야, 선임은 선임'):
    교정은 **오인식**(`다표이사` → `대표이사`)만이다. 다른 값을 고른 것은 교정이 아니다 —
    ① 한쪽이 다른 쪽을 그대로 품으면(`선임` ↔ `선임컨설턴트`, `대표이사` ↔ `이사`) 늘이거나 줄인 것
    ② 직함 칸에서 고치기 전 값이 이미 올바른 직함·자격 낱말이면(`이사` → `대표이사`) 다른 직함을 고른 것."""
    w = nospace_ko(re.sub(r"[^가-힣A-Za-z0-9@.\- ]", "", wrong or "")).strip()
    r = nospace_ko(re.sub(r"[^가-힣A-Za-z0-9@.\- ]", "", right or "")).strip()
    if not w or not r or w == r:
        return False
    if w in r or r in w:
        return False
    if field == "title" and (w in TITLES_KO or qual_token(w)):   # 목록 그대로의 직함·자격(이사·선임 …) — '다표이사' 같은 오인식은 배운다
        return False
    return True


def unglue_name(company: str, name: str) -> str:
    """회사명 앞뒤에 붙어 읽힌 이름을 뗀다('가나다기업홍길동' → '가나다기업', §5.22)."""
    if not company or not name or not _HANGUL.search(name):
        return company
    c = company.strip()
    if c.endswith(name) and len(c) - len(name) >= 2:
        return c[: -len(name)].strip()
    if c.startswith(name) and len(c) - len(name) >= 2:
        return c[len(name):].strip()
    return company


# ── 회사 다듬기(§5.28, 정답 대조 학습 2/3 로 고침) ──
TIDY_TAIL = tuple(sorted(set(ORG_TAIL_STRONG) | {"대학교", "대학원", "사무소", "연구원", "공사", "공단", "관리청", "관리사무소",
                                                 "협동조합", "주식회사", "산업", "아스콘", "레미콘"}, key=len, reverse=True))
TIDY_DOWN = 3.0          # 구호·학회 목록·끝말만으로 된 낱말을 내리는 값
TIDY_DUP = 0.3           # 다듬은 글이 같은 후보가 여럿이면 덤
_SLOGAN = re.compile(r"(하는|일등|벤처|중소|우수|유망|전문|친환경|강소|선도|글로벌|혁신|으뜸|최고의?)\s*기업$")
_AFTER_TAIL = re.compile(r"(교수|과장|팀장|부장|차장|주무관|학과|학부|본부|센터|연구소|과$|팀$|실$|부$|소장|원장)")
_TIDY_GENERIC = re.compile(r"(?:%s)+" % "|".join(re.escape(t) for t in TIDY_TAIL))


def tidy_company(t: str, name: str = "") -> str:
    """회사 후보 글 다듬기 — 앞뒤 찌꺼기, 기관 끝말 뒤의 낱말·부서·직함·짧은 조각, 끝에 붙은 그 명함의 이름을 뗀다(§5.28)."""
    s = re.sub(r"[、「」『』〔〕\[\]()（）|ㅣ©®■▲•·…“”\"'`^_~]+", " ", _nfc(t)).strip()
    if len(_HANGUL.findall(s)) >= 2:
        toks = s.split()
        while len(toks) > 1 and not _HANGUL.search(toks[0]) and (len(toks[0]) < 2 or not toks[0].isupper()):
            toks.pop(0)                                    # 앞 영문 조각('e_') — 대문자 약칭('ABC')은 둔다
        while len(toks) > 1 and not _HANGUL.search(toks[-1]) and len(toks[-1]) <= 5 and not toks[-1].isupper() \
                and "&" not in toks[-1]:
            toks.pop()                                     # 뒤 소문자 영문 조각
        for i, tk in enumerate(toks[:-1]):                 # 기관 끝말로 끝난 낱말 뒤 낱말(사람 이름·부서)
            if _HANGUL.search(tk) and tk.endswith(TIDY_TAIL):
                toks = toks[:i + 1]
                break
        if len(toks) > 1 and re.fullmatch(r"[가-힣]{3}", toks[-1]) and toks[-1][0] in SURNAMES:
            toks = toks[:-1]                               # 끝 낱말이 사람 이름 꼴
        s = "".join(toks) if all(_HANGUL.search(x) for x in toks) else " ".join(toks)
        s = re.sub(r"[^가-힣A-Za-z0-9& ]", "", s).strip()
        ends = sorted({m.end() for tl in TIDY_TAIL for m in re.finditer(re.escape(tl), s) if m.start() > 0}, reverse=True)
        for e in ends:                                     # 기관 끝말 뒤에 붙은 부서·직함·짧은 조각 — 가장 뒤 끝말부터
            rest = s[e:]
            if not rest or rest.startswith(TIDY_TAIL):
                continue
            if _AFTER_TAIL.search(rest) or title_token(rest) or (dept_token(rest) and not rest.endswith(TIDY_TAIL)) \
                    or (re.fullmatch(r"[가-힣]{1,2}", rest) and not s.endswith(TIDY_TAIL) and not s.endswith(ORG_PIECES_KO)):
                s = s[:e]
                break
    if name and re.fullmatch(r"[가-힣]{3}", name) and name[0] in SURNAMES and len(s) >= len(name) + 2 and s.endswith(name):
        s = s[:-len(name)]
    return s


def tidy_companies(comps: list, name: str = "") -> list:
    """회사 후보(사전) 다듬기·다시 매기기(§5.28) — 같은 글은 묶어 덤, 구호·학회 목록·끝말만인 낱말은 내림,
    앞부분만 읽힌 것보다 기관 끝말까지 있는 긴 것을 앞으로."""
    many_societies = sum(1 for c in comps if "학회" in c.get("text", "")) >= 2
    out = {}
    for c in comps:
        t = tidy_company(c.get("text", ""), name)
        if len(t) < 2:
            continue
        sc = float(c.get("score", 0))
        if _TIDY_GENERIC.fullmatch(t) and len(t) <= 4:
            sc -= TIDY_DOWN
        if _SLOGAN.search(t) or (many_societies and t.endswith("학회")):
            sc -= TIDY_DOWN
        if t in out:
            o = out[t]
            o["score"] = round(max(o["score"], sc) + TIDY_DUP, 3)
        else:
            out[t] = dict(c, text=t, score=round(sc, 3))
    keys = list(out)
    for a in keys:
        for b in keys:
            if a != b and b.startswith(a) and len(b) - len(a) <= 6 and b.endswith(TIDY_TAIL) and not a.endswith(TIDY_TAIL):
                out[b]["score"] = max(out[b]["score"], round(out[a]["score"] + 0.1, 3))
    return sorted(out.values(), key=lambda c: (-c["score"], c["text"]))


def rescore(res: dict, weights: Optional[dict] = None, layouts: Optional[dict] = None,
            domain_map: Optional[dict] = None, corrections: Optional[dict] = None) -> dict:
    """캐시에 남은 인식 결과(사전)를 지금의 가중치·양식·도메인 표로 다시 매긴다 — OCR 은 다시 하지 않는다(§5.11).
    이름·회사 1위가 바뀌면 `name`·`company` 도 바꾼다(확인 표가 사용자가 고친 값을 따로 지킨다)."""
    r = dict(res)
    corrections = {f: {w: v for w, v in (m or {}).items() if correction_ok(f, w, v)}   # 잘못 배운 교정(다른 값을 고른 것)은 쓰지 않는다
                   for f, m in (corrections or {}).items()}
    for fld in ("dept", "title", "company"):       # 붙여 쓰기(261117-15) — 옛 캐시 값도
        if r.get(fld):
            r[fld] = nospace_ko(r[fld])
    if r.get("title") and qual_token(r["title"]):  # 자격은 직함이 아니다(261117-17) — 옛 캐시에 직함으로 남은 '공학박사' 등은 비운다
        r["title"] = ""
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
    if comps and _HANGUL.search(comps[0]["text"]):
        comps = tidy_companies(comps, r.get("name", ""))   # §5.28 — 한글 1위일 때만(이름이 정해진 뒤 — 회사 끝에 붙은 이름을 뗀다)
    if comps:
        r["company"] = unglue_name(comps[0]["text"], r.get("name", ""))
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


def order_langs(hangul: int, latin: int) -> tuple:
    """면의 말(해시태그용) — 한글 4자·라틴 12자 이상이면 그 말, 둘 다면 글자 수가 많은 쪽을 앞에.
    태그는 이 첫째 하나(성명·회사명이 한글이면 한글 — apply.lang_tag, D25)."""
    langs = []
    if hangul >= 4:
        langs.append("한글")
    if latin >= 12:
        langs.append("영어")
    if len(langs) == 2 and latin > hangul:
        langs.reverse()
    return tuple(langs)


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
    if len(sides) > 1 and all(s.ptexts for s in sides):
        c.phones = pick_phones([t for s in sides for t in s.ptexts])   # 앞·뒷면을 함께 세어(§5.22)
    if len(c.emails) > 1:                              # 앞·뒷면에서 따로 고른 같은 메일의 변형도 하나로(§5.22)
        c.emails = pick_emails("\n".join(c.emails), tuple(domain_of(u) for u in c.urls))

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
    c.langs = order_langs(hangul, latin)
    tk = [t for s in sides for t in s.titles_ko]
    te = [t for s in sides for t in s.titles_en]
    ak = next((s.address_ko for s in sides if s.address_ko), "")
    ae = next((s.address_en for s in sides if s.address_en), "")
    dk = next((s.dept_ko for s in sides if s.dept_ko), "")
    de = next((s.dept_en for s in sides if s.dept_en), "")
    en = {"name": ne[0].text if ne else "", "company": ce[0].text if ce else "", "dept": de,
          "title": te[0] if te else "", "address": ae}
    ko_ok = bool(nk) and hangul >= 4 and not (ne and latin > 6 * hangul and "hint" not in nk[0].why)   # 영문 명함의 깨진 한글(§5.22)
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
        return nospace_ko(" ".join(x for x in t.split() if not title_token(x)) or t)
    if fld == "title":
        return nospace_ko(merge_spaced(text))
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
            lines = ocr_lines(g, psm, lang=lang, win=False)
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
