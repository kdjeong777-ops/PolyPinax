# -*- coding: utf-8 -*-
"""261116-5(마스터 §11.10.6, 책갈피창·저장 SOT §4.7.29): 목차 쪽 — 다단과 책갈피창 '목차 페이지 만들기' 가 함께 쓰는 한 곳.

- 목차 줄 고르기(`toc_rows` — 고른 단계 이하 모두, 첫 책갈피 = 단계 1)
- 제목 판정(`auto_title` — 문서 언어: 한글 '목  차' / 라틴 'CONTENTS')
- 그리기(`render_toc` — Word 양식(`목차_샘플.docx`: `{{TITLE}}`·`{{TOC}}`·`TOC n` 스타일·점선 오른쪽 탭) 또는 fitz 대체)
- 줄 자리 찾기·링크(`add_links` — PDF 내부 링크, 다른 뷰어에서도)·표식(`/PolyPDFToc`)
- 책갈피창 길: `insert_toc`(원본 1쪽 뒤, 2쪽부터 끼운 새 임시 PDF 까지만 — 원본에 놓기는 메인 `_finalize_save`)

Qt 를 쓰지 않는다(배경 스레드용, 응답성 SOT §4.4).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from viewer.i18n import tr

TOC_MARK_KEY = "PolyPDFToc"        # 이 기능이 만든 목차 쪽의 쪽 사전 키(값 true) — 다시 만들 때 알아본다
KO_TITLE = "목  차"                # 사용자 지시 '목  차'(가운데 두 칸) — 문서의 글이라 번역하지 않는다
EN_TITLE = "CONTENTS"
MAX_LEVELS = 6

MARGIN_X = 56.0                    # 좌우 여백(pt) — 번호 끝이 여기에 맞는다
TOP = 64.0                         # 제목 글 기준선
FIRST_ROW = 116.0                  # 첫 줄 기준선
BOTTOM = 56.0                      # 아래 여백
TITLE_FS = 22.0
LINE_H = 22.0
INDENT = 18.0                      # 단계마다 들여쓰기
FS1, FS2 = 12.0, 11.0              # 단계 1 / 그 아래
NUM_RESERVE = 40.0                 # 번호 자리(가장 긴 번호 폭) — 줄을 바꾸지 않아 번호가 쪽 수를 바꾸지 않는다
LEADER = "·"

_HANGUL = re.compile(r"[가-힣ㄱ-ㆎ]")
_LATIN = re.compile(r"[A-Za-z]")


class Cancelled(Exception):
    """진행 콜백이 False — 사용자가 진행창에서 취소."""


# ── 고르기·제목 ──────────────────────────────────────────────

def auto_title(titles, ui_lang=None) -> str:
    """목차 줄 제목들의 언어로 기본 제목 — 한글이 더 많으면 '목  차', 라틴이 더 많으면 'CONTENTS', 비기면 화면 언어."""
    h = la = 0
    for t in titles or []:
        t = str(t)
        h += len(_HANGUL.findall(t))
        la += len(_LATIN.findall(t))
    if h > la:
        return KO_TITLE
    if la > h:
        return EN_TITLE
    if ui_lang is None:
        try:
            from viewer.i18n import language
            ui_lang = language()
        except Exception:
            ui_lang = "ko"
    return KO_TITLE if str(ui_lang or "").lower().startswith("ko") else EN_TITLE


def bookmark_title(title: str) -> str:
    """맨 앞 '목차' 책갈피 이름 — 띄어쓰기를 뺀 한글('목  차' → '목차'), 라틴은 띄어쓰기를 하나로."""
    t = str(title or "").strip()
    if _HANGUL.search(t) and not _LATIN.search(t):
        return re.sub(r"\s+", "", t)
    return re.sub(r"\s+", " ", t) or EN_TITLE


def level_label(lv: int) -> str:
    """단계 고르기 항목 — '1단계', '1~2단계' …(고른 단계 이하 모두)."""
    lv = int(lv)
    return tr("1단계") if lv <= 1 else tr("1~{n}단계").format(n=lv)


def max_level(toc) -> int:
    """책갈피 `[(단계, 제목, 쪽)…]` 의 최대 단계(첫 단계 = 1 로 맞춘 뒤)."""
    lv = [int(e[0]) for e in toc or []]
    if not lv:
        return 0
    return max(lv) - min(lv) + 1


def toc_rows(toc, levels: int, n_pages: int = None) -> list:
    """책갈피 `[(단계, 제목, 쪽 1-based)…]` → 고른 단계 **이하 모두** `[(단계, 제목, 쪽)]`.
    단계는 가장 얕은 책갈피가 1(책갈피창 §4.7.27 ③). 쪽 밖(1 미만·`n_pages` 넘음)은 버린다."""
    toc = list(toc or [])
    if not toc:
        return []
    base = min(int(e[0]) for e in toc)
    out = []
    for e in toc:
        lv = int(e[0]) - base + 1
        p = int(e[2])
        if lv > max(1, int(levels or 1)):
            continue
        if p < 1 or (n_pages is not None and p > int(n_pages)):
            continue
        out.append((lv, str(e[1]) or tr("(제목 없음)"), p))
    return out


# ── fitz 그리기 ──────────────────────────────────────────────

def _font():
    from viewer import twoup
    return twoup._kr_text, twoup._kr_width


def _fit(text, fs, bold, maxw):
    """maxw 안에 들게 끝을 '…' 로 줄인다."""
    _t, width = _font()
    if width(text, fs, bold) <= maxw:
        return text
    t = text
    while t and width(t + "…", fs, bold) > maxw:
        t = t[:-1]
    return (t + "…") if t else ""


def fitz_pages(n_rows, h) -> int:
    """`render_fitz` 가 그릴 쪽 수 — 줄을 바꾸지 않으므로 줄 수로만 정해진다(번호 없이 한 번 더 그리지 않아도 된다)."""
    first = max(1, int((h - BOTTOM - FIRST_ROW) // LINE_H) + 1)
    rest = max(1, int((h - BOTTOM - TOP) // LINE_H) + 1)
    if n_rows <= first:
        return 1
    return 1 + -(-(int(n_rows) - first) // rest)


def render_fitz(rows, w, h, title):
    """rows `[(단계, 제목, 번호 글)]` → (fitz 문서, 줄 자리 `[(쪽, Rect)]`). 줄은 바꾸지 않는다 — 쪽 수는 줄 수로만 정해진다."""
    import fitz
    put, width = _font()
    d = fitz.open()
    pg = d.new_page(width=w, height=h)
    if title:
        put(pg, ((w - width(title, TITLE_FS, True)) / 2.0, TOP), title, TITLE_FS, (0, 0, 0), True)
    y = FIRST_ROW
    rects = []
    right = w - MARGIN_X
    for lv, name, num in rows:
        if y > h - BOTTOM:
            pg = d.new_page(width=w, height=h)
            y = TOP
        lv = max(1, int(lv))
        bold = lv == 1
        fs = FS1 if lv == 1 else FS2
        x0 = MARGIN_X + INDENT * (lv - 1)
        name = _fit(str(name), fs, bold, max(20.0, right - NUM_RESERVE - 12.0 - x0))
        put(pg, (x0, y), name, fs, (0, 0, 0), bold)
        num = str(num)
        nw = width(num, fs, False) if num else 0.0
        if num:
            put(pg, (right - nw, y), num, fs, (0, 0, 0), False)
        # 점선 채움 — 제목 끝 뒤에서 번호 앞까지, 점은 번호 쪽(오른쪽)에 맞춘다
        lx0 = x0 + width(name, fs, bold) + 6.0
        lx1 = right - (nw if num else NUM_RESERVE) - 4.0
        unit = width(LEADER + " ", fs, False)
        k = int((lx1 - lx0) // unit) if unit > 0 else 0
        if k > 0:
            dots = (" " + LEADER) * k
            put(pg, (lx1 - width(dots, fs, False), y), dots, fs, (0.35, 0.35, 0.35), False)
        rects.append((d.page_count - 1, fitz.Rect(x0, y - fs, right, y + fs * 0.35)))
        y += LINE_H
    return d, rects


# ── Word 양식 ────────────────────────────────────────────────

def _text_width(doc):
    sec = doc.sections[0]
    try:
        return int(sec.page_width - sec.left_margin - sec.right_margin)
    except Exception:
        from docx.shared import Pt
        return int(Pt(468))


def ensure_toc_styles(doc, levels=MAX_LEVELS):
    """단락 스타일 `TOC 1`~ — 없으면 만든다(단계마다 18pt 들여쓰기·오른쪽 탭 + 점선 채움, 단계 1 굵게 12pt·그 아래 11pt).
    샘플·옛 양식 모두 같은 모양이 되게(있는 스타일은 사용자가 고친 것이라 그대로 둔다)."""
    from docx.enum.style import WD_STYLE_TYPE
    from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER
    from docx.shared import Pt
    names = {s.name for s in doc.styles}
    tw = _text_width(doc)
    for lv in range(1, int(levels) + 1):
        nm = "TOC %d" % lv
        if nm in names:
            continue
        st = doc.styles.add_style(nm, WD_STYLE_TYPE.PARAGRAPH)
        try:
            st.base_style = doc.styles["Normal"]
        except KeyError:
            pass
        pf = st.paragraph_format
        pf.left_indent = Pt(INDENT * (lv - 1))
        pf.space_after = Pt(4)
        pf.tab_stops.add_tab_stop(tw, WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
        st.font.size = Pt(FS1 if lv == 1 else FS2)
        st.font.bold = lv == 1


def _style(doc, lv):
    try:
        return doc.styles["TOC %d" % max(1, min(MAX_LEVELS, int(lv)))]
    except KeyError:
        return None


def fill_docx(template, rows, title, out_docx, ow=None, oh=None) -> bool:
    """양식의 `{{TITLE}}` → 제목, `{{TOC}}` 단락 → 줄마다 그 단계 스타일 `제목<탭>번호`. 양식이 없으면 기본 모양을 만든다."""
    try:
        from docx import Document
        from docx.shared import Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH
    except Exception:
        return False
    try:
        if template and os.path.exists(template):
            doc = Document(template)
            ensure_toc_styles(doc)
            for p in doc.paragraphs:
                if "{{TITLE}}" in p.text:
                    for r in p.runs:
                        if "{{TITLE}}" in r.text:
                            r.text = r.text.replace("{{TITLE}}", title)
                    if "{{TITLE}}" in p.text:
                        p.text = p.text.replace("{{TITLE}}", title)
            anchor = next((p for p in doc.paragraphs if "{{TOC}}" in p.text), None)
            for lv, name, num in rows:
                text = "%s\t%s" % (name, num)
                if anchor is not None:
                    anchor.insert_paragraph_before(text, style=_style(doc, lv))
                else:
                    doc.add_paragraph(text, style=_style(doc, lv))
            if anchor is not None:
                el = anchor._element
                el.getparent().remove(el)
        else:
            doc = Document()
            from viewer.twoup import _apply_page_size
            _apply_page_size(doc, ow, oh)
            ensure_toc_styles(doc)
            hp = doc.add_paragraph(); hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = hp.add_run(title); r.bold = True; r.font.size = Pt(TITLE_FS)
            doc.add_paragraph("")
            for lv, name, num in rows:
                doc.add_paragraph("%s\t%s" % (name, num), style=_style(doc, lv))
        doc.save(out_docx)
        return True
    except Exception:
        return False


def write_sample(path) -> bool:
    """`목차_샘플.docx` — 다단 [샘플 저장]·책갈피창 [샘플 만들기] 의 같은 양식(마스터 §11.10.6)."""
    try:
        from docx import Document
        from docx.shared import Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH
    except Exception:
        return False
    try:
        doc = Document()
        ensure_toc_styles(doc)
        hp = doc.add_paragraph(); hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = hp.add_run("{{TITLE}}"); r.bold = True; r.font.size = Pt(TITLE_FS)
        doc.add_paragraph("")
        doc.add_paragraph().add_run("{{TOC}}")            # 이 단락이 목차 줄로 바뀐다(단계마다 'TOC n' 스타일)
        doc.save(str(path))
        return True
    except Exception:
        return False


def _norm(s):
    return re.sub(r"\s+", "", str(s or ""))


def locate_rows(doc, rows, first=0, count=None):
    """Word 로 만든 목차 쪽에서 줄 자리를 차례로 찾는다 — 제목 앞부분(띄어쓰기 뺀 12자)이 든 다음 줄. 못 찾으면 None."""
    import fitz
    count = doc.page_count - first if count is None else count
    lines = []
    for pi in range(first, first + count):
        try:
            dd = doc[pi].get_text("dict")
        except Exception:
            continue
        for b in dd.get("blocks", []):
            for ln in b.get("lines", []):
                t = "".join(sp.get("text", "") for sp in ln.get("spans", []))
                if t.strip():
                    lines.append((pi - first, fitz.Rect(ln["bbox"]), _norm(t)))
    lines.sort(key=lambda e: (e[0], e[1].y0, e[1].x0))
    out, k = [], 0
    for _lv, name, _num in rows:
        key = _norm(name)[:12]
        hit = None
        j = k
        while key and j < len(lines):
            if key in lines[j][2]:
                hit = j
                break
            j += 1
        if hit is None:
            out.append(None)
            continue
        pi, r, _t = lines[hit]
        w = doc[first + pi].rect.width
        out.append((pi, fitz.Rect(min(r.x0, MARGIN_X), r.y0, max(r.x1, w - MARGIN_X), r.y1)))
        k = hit + 1
    return out


def render_toc(rows, w, h, title, template="", tmpdir=None, use_word=False, seq=0):
    """목차 문서와 줄 자리. `use_word` 면 양식(없으면 기본 모양)을 Word 로, 실패하면 fitz(다단과 같은 폴백)."""
    import fitz
    if use_word and tmpdir is not None:
        from viewer.twoup import _docx_to_pdf
        tx = str(Path(tmpdir) / ("toc_%s.docx" % seq)); tp = str(Path(tmpdir) / ("toc_%s.pdf" % seq))
        if fill_docx(template, rows, title, tx, ow=w, oh=h) and _docx_to_pdf(tx, tp):
            try:
                d = fitz.open(tp)
                return d, locate_rows(d, rows)
            except Exception:
                pass
    return render_fitz(rows, w, h, title)


def add_links(doc, first, rects, targets) -> int:
    """목차 줄 → 그 쪽(0-based `targets`) 내부 링크. `first` = 목차 첫 쪽의 자리. 넣은 수."""
    import fitz
    n = 0
    for r, t in zip(rects, targets):
        if r is None or t is None or not (0 <= int(t) < doc.page_count):
            continue
        pi, rect = r
        try:
            doc[first + pi].insert_link({"kind": fitz.LINK_GOTO, "from": rect, "page": int(t),
                                         "to": fitz.Point(0, 0)})
            n += 1
        except Exception:
            pass
    return n


def mark_pages(doc, first, count) -> None:
    for i in range(first, first + count):
        doc.xref_set_key(doc[i].xref, TOC_MARK_KEY, "true")


def marked_range(doc) -> tuple:
    """이 기능이 만든 목차 쪽 `(처음 0-based, 쪽 수)` — 2쪽(색인 1)부터 이어진 표식 쪽(261116-5 덧붙임 2),
    옛 판(맨 앞에 끼운 것)이면 1쪽부터. 없으면 (1, 0)."""
    def marked(i):
        try:
            t, v = doc.xref_get_key(doc[i].xref, TOC_MARK_KEY)
            return t == "bool" and v == "true"
        except Exception:
            return False
    n = doc.page_count
    start = 1 if n > 1 and marked(1) else (0 if n > 0 and marked(0) else 1)
    k = 0
    while start + k < n and marked(start + k):
        k += 1
    return start, k


def count_marked(doc) -> int:
    """이 기능이 만든 목차 쪽 수."""
    return marked_range(doc)[1]


def _layout(doc):
    """옛 목차를 뺀 원본 쪽(0-based) 목록과 옛 목차 `(처음, 쪽 수)`."""
    s, k_old = marked_range(doc)
    keep = [i for i in range(doc.page_count) if not (s <= i < s + k_old)]
    return keep, s, k_old


def _body_toc(doc, keep):
    """책갈피 → `[(단계, 제목, 남은 쪽 1-based)]` — 옛 목차 쪽을 가리키던 것은 버린다."""
    pos = {p: r for r, p in enumerate(keep)}
    out = []
    for l, t, p in doc.get_toc(simple=True):
        r = pos.get(int(p) - 1)
        if r is not None:
            out.append((int(l), str(t), r + 1))
    return out


# ── 책갈피창 '목차 페이지 만들기' (책갈피창·저장 SOT §4.7.29) ─────────────

def probe(path) -> dict:
    """배경: 창을 띄우기 전에 읽을 것 — 옛 목차 쪽 수·책갈피(옛 목차 뺀 쪽 번호)·본문 쪽 크기·암호."""
    import fitz
    with fitz.open(str(path)) as d:
        if d.needs_pass or d.is_encrypted:
            return {"encrypted": True}
        keep, _s, k = _layout(d)
        ref = d[keep[1] if len(keep) > 1 else keep[0]].rect if keep else d[0].rect
        return {"encrypted": False, "old": k, "pages": d.page_count, "toc": _body_toc(d, keep),
                "w": float(ref.width), "h": float(ref.height)}


def new_page(p, k) -> int:
    """남은 쪽 p(1-based) 의 끼운 뒤 실제 쪽 — 목차 k 쪽은 1쪽(표지) 바로 뒤(261116-5 덧붙임 2)."""
    return p if p == 1 else p + k


def numbered(rows, k):
    """`[(단계, 제목, 남은 쪽)]` → 그릴 줄 — 번호는 목차 k 쪽을 끼운 뒤의 실제 쪽(번호 없이 셀 때는 k=None)."""
    return [(lv, t, ("" if k is None else str(new_page(p, k)))) for lv, t, p in rows]


def insert_toc(src, out, title, levels, template="", tmpdir=None, progress=None) -> dict:
    """원본 **1쪽(표지) 바로 뒤**에 목차 쪽을 끼운 새 PDF(`out`)를 만든다 — 원본은 손대지 않는다(261116-5 덧붙임 2).
    옛 목차(표식 쪽)는 빼고, 2쪽 이후를 가리키는 책갈피만 목차 쪽 수만큼 밀고(1쪽 책갈피는 그대로) '목차'(2쪽) 책갈피,
    목차 줄은 그 쪽으로 링크. 원본은 한 번에 복사한 뒤 옛 목차를 빼고 끼운다 — 쪽 사이 링크가 남는다."""
    import fitz
    from viewer.page_edit_build import apply_toc, copy_info

    def tick(d, t, label):
        if progress is not None and progress(d, t, label) is False:
            raise Cancelled()

    out = Path(out)
    try:
        sdoc = fitz.open(str(src))
        try:
            if sdoc.needs_pass or sdoc.is_encrypted:
                raise RuntimeError(tr("암호 PDF 에는 목차 쪽을 끼우지 않습니다."))
            tick(0, 4, tr("목차 만드는 중…"))
            keep, s_old, k_old = _layout(sdoc)
            if not keep:
                raise RuntimeError(tr("목차 쪽 말고는 쪽이 없습니다."))
            body = _body_toc(sdoc, keep)
            rows = toc_rows(body, levels, len(keep))
            if not rows:
                raise RuntimeError(tr("고른 단계에 책갈피가 없습니다."))
            ttl = title if str(title or "").strip() else auto_title([t for _l, t, _p in rows])
            ref = sdoc[keep[1] if len(keep) > 1 else keep[0]].rect
            w, h = float(ref.width), float(ref.height)
            use_word = bool(template)
            if use_word:                                 # Word 는 나눔을 미리 알 수 없다 — 번호 없이 한 번 그려 센다
                d1, _r = render_toc(numbered(rows, None), w, h, ttl, template, tmpdir, use_word, "a")
                k = d1.page_count
                d1.close()
            else:
                k = fitz_pages(len(rows), h)
            tocdoc, rects = render_toc(numbered(rows, k), w, h, ttl, template, tmpdir, use_word, "b")
            if tocdoc.page_count != k:                   # Word 가 번호 탓에 다르게 나눴다 — 한 번 더
                k = tocdoc.page_count
                tocdoc.close()
                tocdoc, rects = render_toc(numbered(rows, k), w, h, ttl, template, tmpdir, use_word, "c")
                k = tocdoc.page_count
            # 마스터 §4.5.10 ①: 맑은 고딕 전체(약 15MB)가 들어가지 않게 목차 쪽만 쓴 글자로 — 원본 쪽 글꼴은 건드리지 않는다
            from viewer.pdf_font import subset_fonts_safely
            subset_fonts_safely(tocdoc)
            tick(1, 4, tr("쪽 복사 중"))
            odoc = fitz.open()
            try:
                odoc.insert_pdf(sdoc)                    # 한 번에 — 쪽 사이 링크 유지(page_edit_build 와 같은 까닭)
                if k_old:
                    odoc.delete_pages(from_page=s_old, to_page=s_old + k_old - 1)
                odoc.insert_pdf(tocdoc, start_at=1)      # 1쪽(표지) 바로 뒤
                tocdoc.close()
                # 책갈피: 1쪽 것은 그대로, 2쪽 이후는 k 만큼 — '목차'(2쪽)는 2쪽 이후를 가리키는 첫 맨 위 책갈피 앞
                base = min((l for l, _t, _p in body), default=1)
                bms, put = [], False
                for l, t, p in body:
                    if not put and l == base and p >= 2:
                        bms.append((bookmark_title(ttl), 2, 0)); put = True
                    bms.append((t, new_page(p, k), l - base))     # apply_toc 의 단계는 0부터
                if not put:
                    bms.append((bookmark_title(ttl), 2, 0))
                apply_toc(odoc, bms)
                copy_info(sdoc, odoc)
                links = add_links(odoc, 1, rects, [new_page(p, k) - 1 for _l, _t, p in rows])
                mark_pages(odoc, 1, k)
                tick(3, 4, tr("저장 중"))
                odoc.save(str(out), garbage=4, deflate=True)
                pages = odoc.page_count
            finally:
                odoc.close()
        finally:
            sdoc.close()
        tick(4, 4, tr("원본에 놓을 준비"))
        return {"path": str(out), "toc_pages": k, "old_toc_pages": k_old, "pages": pages, "keep": keep,
                "rows": len(rows), "links": links, "title": ttl}
    except BaseException:
        try:
            if out.exists():
                os.remove(str(out))
        except Exception:
            pass
        raise
