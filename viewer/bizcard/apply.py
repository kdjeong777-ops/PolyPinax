"""정리본 쓰기 — 확인 표 [적용] (명함 SOT §5.3·§5.4·§5.6·§5.10, P2).

원본은 건드리지 않는다(D10) — 정리 폴더에 새 JPG 만 쓴다. 배경 스레드에서 부른다(파일·PDF 그리기).
태그는 여기서 붙이지 않는다 — 끝난 뒤 메인이 앱의 태그 저장소 하나로(`tags_for`).
★ 명함 글은 로그·예외 메시지에 싣지 않는다(§2.1).
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from viewer.bizcard import recognize as R

JPEG_QUALITY = 95          # D3
JPEG_DPI = 300
BACK_SUFFIX = "_뒷면"


class ApplyCancelled(Exception):
    pass


def unique_path(folder: Path, name: str, taken: set) -> Path:
    stem, ext = os.path.splitext(name)
    k = 1
    while True:
        cand = folder / (name if k == 1 else "%s (%d)%s" % (stem, k, ext))
        if os.path.normcase(str(cand)) not in taken and not cand.exists():
            taken.add(os.path.normcase(str(cand)))
            return cand
        k += 1


def _save_jpeg(im, dst: Path):
    tmp = dst.with_name(dst.name + ".part")
    im.convert("RGB").save(str(tmp), "JPEG", quality=JPEG_QUALITY, subsampling=0, dpi=(JPEG_DPI, JPEG_DPI))
    os.replace(str(tmp), str(dst))


def write_side(src_img: str, pdf: str, page: int, dst: Path) -> bool:
    """한 면을 정리본 JPG 로 — PDF 가 있으면 그 쪽을 300 dpi 로 그림, JPG 는 바이트 그대로, 그 밖은 JPG 로 한 번."""
    if pdf:
        import fitz
        from PIL import Image
        import io
        doc = fitz.open(pdf)
        try:
            if page >= doc.page_count:
                return False
            pix = doc[page].get_pixmap(dpi=JPEG_DPI)
            _save_jpeg(Image.open(io.BytesIO(pix.tobytes("png"))), dst)
        finally:
            doc.close()
        return True
    if not src_img:
        return False
    if Path(src_img).suffix.lower() in (".jpg", ".jpeg"):
        tmp = dst.with_name(dst.name + ".part")
        shutil.copy2(src_img, tmp)
        os.replace(str(tmp), str(dst))
        return True
    from PIL import Image, ImageOps
    with Image.open(src_img) as im:
        _save_jpeg(ImageOps.exif_transpose(im), dst)
    return True


LANG_TAGS = ("한글", "영어")


def _has_hangul(s: str) -> bool:
    return any("가" <= ch <= "힣" for ch in s or "")


def lang_tag(name: str, company: str, langs, ordered: bool = True) -> str:
    """언어 해시태그 하나(D25·§5.5) — 성명·회사명에 한글이 있으면 '한글', 아니면 langs 의 첫째(인식이 글자 수가
    많은 쪽을 앞에 둔다). ordered=False = 이미 붙은 태그에서 온 것(차례에 뜻 없음) — 둘 다면 '영어'
    (성명·회사명에 한글이 없고 글자 수는 남아 있지 않음). 없으면 ""."""
    langs = [x for x in (langs or []) if x in LANG_TAGS]
    if not langs:
        return ""
    if _has_hangul(name) or _has_hangul(company):
        return "한글"
    return langs[0] if ordered or len(langs) == 1 else "영어"


def tags_for(row: dict) -> list:
    """해시태그(R6·§5.5) — #명함 · #회사 · #한글 또는 #영어(하나, D25)."""
    tags = ["명함"]
    comp = R.strip_corp(row.get("company") or "")
    if comp:
        tags.append(comp)
    lt = lang_tag(row.get("name") or "", comp, row.get("langs"), row.get("langs_ordered", True))
    if lt:
        tags.append(lt)
    return tags


def apply_cards(rows: list, out_dir, db=None, progress=None) -> list:
    """rows: [{key, front, back, pdf, keep_back, name, company, title, phones, emails, urls, address, en, langs,
    scanned, top1}] → [(정리본 앞면, 정리본 뒷면 또는 "", 태그)]. 이미 정리한 원천은 DB 행만 고치고 파일은 새로 쓰지 않는다."""
    from viewer.bizcard.store import BizcardStore
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    st = BizcardStore(db)
    taken = set()
    done = []
    try:
        for i, r in enumerate(rows):
            if progress is not None and progress(i, len(rows)) is False:
                raise ApplyCancelled()
            old = st.card_by_src(r["key"])
            if old and Path(old["front"]).exists():
                front, back = Path(old["front"]), (Path(old["back"]) if old.get("back") else None)
            else:
                front = unique_path(out_dir, R.card_filename(r.get("name") or "", r.get("company") or ""), taken)
                if not write_side(r.get("front", ""), r.get("pdf", ""), 0, front):
                    continue
                back = None
                if r.get("keep_back") and (r.get("back") or r.get("pdf")):
                    bp = unique_path(out_dir, front.stem + BACK_SUFFIX + ".jpg", taken)
                    if write_side(r.get("back", ""), r.get("pdf", ""), 1, bp):
                        back = bp
            tags = tags_for(r)
            st.upsert({"front": str(front), "back": str(back) if back else "", "src_key": r["key"],
                       "src_pdf": r.get("pdf", ""), "name": r.get("name", ""), "company": R.strip_corp(r.get("company") or ""),
                       "title": r.get("title", ""), "dept": r.get("dept", ""), "phones": r.get("phones") or [], "emails": r.get("emails") or [],
                       "urls": r.get("urls") or [], "address": r.get("address", ""), "en": r.get("en") or {},
                       "tags": tags, "scanned": r.get("scanned", ""), "top1": r.get("top1"),
                       "memo": (old or {}).get("memo", "")})          # 다시 적용해도 메모는 지키기
            done.append((str(front), str(back) if back else "", tags))
        if progress is not None:
            progress(len(rows), len(rows))
    finally:
        st.close()
    return done
