# -*- coding: utf-8 -*-
"""PDF → 다른 형식 (형식 변환 SOT, 261014-11).

- `FORMATS` — 형식 목록. **다 만든 형식만** `ready` 다(메뉴에는 그것만 보인다 — 형식 변환 SOT §1·§2.1).
- `out_path` — 같은 폴더·같은 이름, 겹치면 ` (2)` 부터(§2.3).
- `parse_range` — `3-12`·`1,4,7-9` 꼴(1부터) → 0부터 쪽 목록.
- `run` — 한 파일을 변환한다. **배경 스레드에서** 부른다(문서는 `PageSource` 가 그 스레드에서 연다).
  `progress(했음, 전체, 글) -> bool` 이 False 면 멈추고 `Cancelled` — 만들던 파일은 지운다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from viewer.i18n import tr, tr_noop
from viewer.progress_text import step

IMAGE_DPI = 150     # 크기 '보통'(처음 값)

# 261117-5(§2.3.1, 사용자 결정): 이미지 형식·화질·크기 — 쪽 그림은 흰 바탕(alpha=False)이라 JPG·WebP 로 잃는 것이 없다
IMAGE_FORMATS = (("jpg", "JPG", ".jpg"), ("png", "PNG", ".png"), ("webp", "WebP", ".webp"))   # (키, 이름, 확장자) — 맨 앞이 처음 값
IMAGE_QUALITY = (("high", tr_noop("높음"), 92), ("normal", tr_noop("보통"), 80))              # JPG·WebP 압축 품질(PNG 는 손실 없음)
IMAGE_SIZES = ((96, tr_noop("작게")), (150, tr_noop("보통")), (300, tr_noop("크게")))          # dpi
IMAGE_DEFAULT = {"fmt": "jpg", "quality": "high", "dpi": IMAGE_DPI}


def image_opts(raw=None) -> dict:
    """이미지 선택값을 바로잡는다(모르는 값은 처음 값) — {"fmt", "quality", "dpi"}."""
    raw = raw if isinstance(raw, dict) else {}
    out = dict(IMAGE_DEFAULT)
    if raw.get("fmt") in {k for k, _n, _e in IMAGE_FORMATS}:
        out["fmt"] = raw["fmt"]
    if raw.get("quality") in {k for k, _n, _q in IMAGE_QUALITY}:
        out["quality"] = raw["quality"]
    try:
        if int(raw.get("dpi")) in {d for d, _n in IMAGE_SIZES}:
            out["dpi"] = int(raw["dpi"])
    except (TypeError, ValueError):
        pass
    return out


class Cancelled(Exception):
    pass


class NothingToWrite(Exception):
    """만들 것이 없다(예: 표가 없는 문서의 Excel) — 실패가 아니라 알림."""


@dataclass(frozen=True)
class Format:
    key: str
    label: str          # tr_noop — 화면에서 tr() 로 옮긴다(다국어 SOT §6)
    ext: str            # 확장자 — 이미지는 고른 형식·장 수로 정한다(`image_out`)
    ready: bool
    group: str = "doc"  # 변환 창 왼쪽 분류 — "doc" 문서 · "image" 이미지(261117-5, §5)


# 261026-2(§2.1, 사용자 지시): 형식마다 '모양 그대로' 가 위 — 맨 위가 변환 창의 처음 고른 형식
FORMATS = (
    # 261113-3(§1·§2.1, 사용자 지시): 방식 이름 '모양 그대로' → '원본 모양', '편집 가능' → '줄잇기',
    #   'Microsoft Word 사용' → 'MS Word 모듈 적용'(내부 키는 그대로). Word 셋은 원본 모양 → 줄잇기 → MS Word(261017-12 를 고침)
    Format("docx_shape", tr_noop("Word (원본 모양)"), ".docx", True),
    Format("docx_edit", tr_noop("Word (줄잇기)"), ".docx", True),
    Format("docx_word", tr_noop("Word (MS Word 모듈 적용)"), ".docx", True),    # §4.4 — Word 가 없으면 흐리게(`available`)
    Format("hwpx_shape", tr_noop("한글 HWPX (원본 모양)"), ".hwpx", True),
    Format("hwpx_edit", tr_noop("한글 HWPX (줄잇기)"), ".hwpx", True),
    Format("pptx_shape", tr_noop("PowerPoint (원본 모양)"), ".pptx", True),     # 261014-19(§1)
    Format("xlsx", tr_noop("Excel (표)"), ".xlsx", True),
    Format("txt", tr_noop("텍스트"), ".txt", True),
    Format("png", tr_noop("이미지"), "", True, "image"),    # 261117-5: 키는 그대로, 형식(JPG·PNG·WebP)은 창에서(§2.3.1)
)
GROUPS = (("doc", tr_noop("문서")), ("image", tr_noop("이미지")))    # 변환 창 왼쪽 분류 차례(§5)


# 진행 창 2줄의 단계 이름(§5, 261026-2) — 엔진 내부 이름(pdf2docx parse/make)·날 글(p.12)은 화면에 내지 않는다
STAGES = {
    "pages": tr_noop("쪽 변환"),
    "parse": tr_noop("쪽 분석"),
    "make": tr_noop("Word 쓰기"),
    "ocr": tr_noop("OCR 글자층"),
    "edges": tr_noop("머리말·꼬리말 찾기"),
    "save": tr_noop("저장"),
    "word": tr_noop("Word 로 변환"),
}


def step_text(stage: str, k=None, n=None, page=None, doc_pages=None) -> str:
    """진행 창 2줄 — `단계 k/n · 원본 p쪽`(k/n 은 이 일감의 몇째 쪽, p 는 원본 쪽 번호, 둘 다 1부터). 없는 칸은 뺀다.
    `doc_pages`(문서 쪽 수)를 주면 p 도 그 자릿수에 맞춰 채운다(글 폭이 흔들리지 않게 — 디자인 SOT §2.7)."""
    return step(tr(STAGES[stage]), k, n, page, doc_pages)


def page_step(ps, pages, i: int) -> str:
    """쓰기 함수가 쪽마다 — `쪽 변환 i+1/n · 원본 p쪽`."""
    return step_text("pages", i + 1, len(pages), int(pages[i]) + 1, ps.page_count)


WORD_REQUIRED = tr_noop("Microsoft Word 가 설치된 PC 에서만 작동합니다.")
WORD_HELP = tr_noop("Microsoft Word 가 PDF 를 다시 흘려 Word 문서로 만듭니다. "
                    "Microsoft Word 가 설치된 PC 에서만 작동합니다(쪽 맞춤은 하지 않습니다).")


def ready_formats() -> list:
    """다 만든 형식 — 261113-3(§5): 'MS Word 모듈 적용' 은 Word 가 없어도 목록에 둔다(흐리게 — `available`)."""
    return [f for f in FORMATS if f.ready]


def available(key: str) -> bool:
    """이 PC 에서 고를 수 있는가 — 'MS Word 모듈 적용' 은 Word 가 설치돼 있을 때만(§4.4)."""
    if key == "docx_word":
        from viewer.convert.word_com import word_installed
        return word_installed()
    return True


def help_text(key: str) -> str:
    """형식 항목의 '?' 설명(화면 문구, tr 적용) — 지금은 'MS Word 모듈 적용' 만(261113-3 사용자 결정)."""
    return tr(WORD_HELP) if key == "docx_word" else ""


def fmt(key: str) -> Format:
    for f in FORMATS:
        if f.key == key:
            return f
    raise KeyError(key)


def out_path(src, key: str) -> Path:
    """같은 폴더·같은 이름 — 이미 있으면 ` (2)`, ` (3)` …(형식 변환 SOT §2.3). 이미지는 폴더(장 수에 따른 자리는 `image_out`)."""
    from viewer.pathutil import unique_path
    s = Path(src)
    f = fmt(key)
    return unique_path(s.with_name(s.stem + f.ext) if f.ext else s.with_name(s.stem), first=2)


def image_ext(fmt_key: str) -> str:
    return next((e for k, _n, e in IMAGE_FORMATS if k == fmt_key), ".jpg")


def image_out(src, pages, opts) -> Path:
    """이미지 결과 자리(§2.3.1) — 여러 장이면 `<이름>` 폴더(있으면 ` (2)`), 한 장이면 폴더 없이 `<이름>_p<쪽>.<확장자>`(겹치면 ` (2)`)."""
    from viewer.pathutil import unique_path
    s = Path(src)
    if len(pages) == 1:
        return unique_path(s.with_name(f"{s.stem}_p{int(pages[0]) + 1:04d}{image_ext(opts['fmt'])}"), first=2)
    return unique_path(s.with_name(s.stem), first=2)


def parse_range(text: str, n: int) -> list:
    """`3-12`·`1,4,7-9`(1부터) → 0부터 쪽 목록(차례대로, 겹침 없음). 틀리면 ValueError."""
    out = []
    for part in str(text or "").replace(" ", "").split(","):
        if not part:
            continue
        a, sep, b = part.partition("-")
        lo = int(a); hi = int(b) if sep else lo
        if lo > hi:
            lo, hi = hi, lo
        if lo < 1 or hi > n:
            raise ValueError(part)
        out.extend(range(lo - 1, hi))
    seen, res = set(), []
    for p in out:
        if p not in seen:
            seen.add(p); res.append(p)
    if not res:
        raise ValueError(text)
    return res


PHOTO_KEYS = ("docx_shape", "docx_edit", "hwpx_shape", "hwpx_edit", "txt")   # 사진에 뜻 있는 형식(사진 보기 SOT §4.35)


def run(src, key: str, pages=None, *, fixes=None, forced_pages=(), progress=None, photo_rot: int = 0, photo_crop=None,
        image=None) -> Path:
    """한 파일을 변환해 결과 경로를 돌려준다. 배경 스레드에서 부른다. 사진이면 `photo_rot`(보기 회전)·`photo_crop`(보기 크롭)대로 구운 1쪽으로.
    이미지(`png` 키)는 `image`={"fmt","quality","dpi"}(§2.3.1, 없으면 처음 값)."""
    from viewer.convert import writers
    from viewer.convert.source import PageSource
    if not available(key):
        raise RuntimeError(tr(WORD_REQUIRED))

    def tick(i, n, label=""):
        if progress is not None and progress(i, n, label) is False:
            raise Cancelled()

    with PageSource(src, fixes=fixes, forced_pages=forced_pages, photo_rot=photo_rot, photo_crop=photo_crop) as ps:
        pg = list(pages) if pages else list(range(ps.page_count))
        if key == "png":
            opts = image_opts(image)
            dst = image_out(src, pg, opts)
            write = lambda *a: writers.WRITERS[key](*a, opts=opts)  # noqa: E731
        else:
            dst = out_path(src, key)
            write = writers.WRITERS[key]
        try:
            write(ps, pg, dst, tick)
        except BaseException:
            _remove(dst)
            raise
    return dst


def _remove(p: Path) -> None:
    """만들다 만 결과를 지운다(취소·실패). 이미지 폴더는 통째로."""
    import shutil
    try:
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            os.remove(p)
    except Exception:
        pass
