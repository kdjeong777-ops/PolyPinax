# -*- coding: utf-8 -*-
"""Word 머리글·바닥글 (형식 변환 SOT §1.1) — pdf2docx 가 만든 docx 에 넣는다(`proc._put_header_footer`).

종전의 python-docx 흐르는 '편집 가능' 쓰기는 261113-3 에 pdf2docx 길(§4.1 고침 8)로 바뀌어 지웠다.
"""
from __future__ import annotations

from viewer.convert import layout

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_WPS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
_V = "urn:schemas-microsoft-com:vml"
LINE_MIN_K = 1.2      # §1.3 — 글 문단 줄 간격 하한(글자 크기의 배). 1.15 → 42쪽, 1.2 → 43쪽, 1.3 → 48쪽(별첨4 Word, 표 행 '최소' 포함)
DEFAULT_PT = 11.0     # 런에 크기가 없을 때(Word 기본 글자 크기)


def no_hidden(path) -> dict:
    """글이 숨지 않게(형식 변환 SOT §1.3, 261116-30) — 만든 docx 를 마지막에 한 번 훑는다. Word 변환 길(pdf2docx·MS Word 모듈)이 모두 부른다.

    - 글이 든 문단의 줄 간격 '정확히' 는 **그 문단 가장 큰 글자 × `LINE_MIN_K` 아래로 두지 않는다**(규칙은 '정확히' 그대로 — '최소' 로
      바꾸면 Word 가 글꼴 고유 줄 높이(맑은 고딕 1.33배)로 늘려 별첨4 Word 가 40 → 66쪽이 되었다, 실측). 빈 문단은 그대로(1 pt 구역 끝·빈 머리글).
    - 표 행 높이 `exact` → `atLeast`(칸 글이 꺾이면 행이 자란다).
    - 글상자는 '도형을 글에 맞춤'(DrawingML `spAutoFit`, VML `mso-fit-shape-to-text`).
    반환: 바꾼 개수 `{"line": n, "row": n, "box": n}`."""
    import os
    import tempfile
    import zipfile
    from lxml import etree
    q = lambda ns, t: "{%s}%s" % (ns, t)
    n = {"line": 0, "row": 0, "box": 0}
    path = str(path)
    zin = zipfile.ZipFile(path)
    parts = {}
    for name in zin.namelist():
        if not (name == "word/document.xml" or (name.startswith("word/header") or name.startswith("word/footer"))
                and name.endswith(".xml")):
            continue
        root = etree.fromstring(zin.read(name))
        for p in root.iter(q(_W, "p")):
            if not "".join(t.text or "" for t in p.iter(q(_W, "t"))).strip():
                continue
            ppr = p.find(q(_W, "pPr"))
            sp = ppr.find(q(_W, "spacing")) if ppr is not None else None
            if sp is not None and sp.get(q(_W, "lineRule")) == "exact" and (sp.get(q(_W, "line")) or "").isdigit():
                sizes = [int(e.get(q(_W, "val"))) / 2.0 for e in p.iter(q(_W, "sz")) if (e.get(q(_W, "val")) or "").isdigit()]
                floor = int(round(max(sizes or [DEFAULT_PT]) * LINE_MIN_K * 20))      # 트윕(1/20 pt)
                if int(sp.get(q(_W, "line"))) < floor:
                    sp.set(q(_W, "line"), str(floor))
                    n["line"] += 1
        for h in root.iter(q(_W, "trHeight")):
            if h.get(q(_W, "hRule")) == "exact":
                h.set(q(_W, "hRule"), "atLeast")
                n["row"] += 1
        for bp in root.iter(q(_WPS, "bodyPr")):
            for old in list(bp):
                if old.tag in (q(_A, "noAutofit"), q(_A, "normAutofit"), q(_A, "spAutoFit")):
                    bp.remove(old)
            bp.insert(0, etree.Element(q(_A, "spAutoFit")))
            n["box"] += 1
        for tb in root.iter(q(_V, "textbox")):
            st = tb.get("style") or ""
            if "mso-fit-shape-to-text" not in st:
                tb.set("style", (st + ";" if st else "") + "mso-fit-shape-to-text:t")
                n["box"] += 1
        parts[name] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    if not any(n.values()):
        zin.close()
        return n
    fd, tmp = tempfile.mkstemp(suffix=".docx", dir=os.path.dirname(path) or ".")
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for it in zin.infolist():
                zout.writestr(it, parts.get(it.filename) or zin.read(it.filename))
        zin.close()
        os.replace(tmp, path)
    except Exception:
        zin.close()
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return n


def set_hf_distance(sec, per_page) -> None:
    """머리글·바닥글 자리 = 원본 머리말 위쪽·꼬리말 아래쪽(쪽 높이 비율로 옮긴다)."""
    from docx.shared import Pt
    ph = sec.page_height.pt
    edges = [e for es in per_page.values() for e in es]
    heads = [e["rect"][1] / float(e.get("ph") or ph) for e in edges if e["where"] == "head"]
    foots = [e["rect"][3] / float(e.get("ph") or ph) for e in edges if e["where"] == "foot"]
    if heads:
        sec.header_distance = Pt(max(0.0, min(heads) * ph))
    if foots:
        sec.footer_distance = Pt(max(0.0, (1.0 - max(foots)) * ph))


def _page_field(run) -> None:
    """런 안에 Word 쪽 번호 필드(PAGE)."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    for kind, text in (("begin", None), (None, " PAGE "), ("separate", None), (None, "1"), ("end", None)):
        if kind:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
        elif text == " PAGE ":
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        else:
            el = OxmlElement("w:t")
            el.text = text
        run._r.append(el)


def _header_footer(out, sec, plan) -> None:
    """머리말·꼬리말(형식 변환 SOT §1.1) — Word 머리글·바닥글 기능으로, 쪽 번호는 PAGE 필드, 홀·짝이 다르면 따로."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt
    al = {"LEFT": WD_ALIGN_PARAGRAPH.LEFT, "CENTER": WD_ALIGN_PARAGRAPH.CENTER, "RIGHT": WD_ALIGN_PARAGRAPH.RIGHT}
    if any(k in plan[w] for w in ("head", "foot") for k in ("ODD", "EVEN")):
        out.settings.odd_and_even_pages_header_footer = True
    for where in ("head", "foot"):
        for kind, lines in plan[where].items():
            if kind == "EVEN":
                part = sec.even_page_header if where == "head" else sec.even_page_footer
            else:
                part = sec.header if where == "head" else sec.footer
            part.is_linked_to_previous = False
            first = True
            for ln in lines:
                pw = sec.page_width.pt
                text, align, indent = layout.compose(ln, pw, sec.left_margin.pt, pw - sec.right_margin.pt)
                para = part.paragraphs[0] if first and part.paragraphs else part.add_paragraph()
                first = False
                para.alignment = al.get(align)
                pf = para.paragraph_format
                pf.left_indent = Pt(indent) if indent else None
                pf.space_before = pf.space_after = Pt(0)       # 기본 서식의 문단 뒤 간격이 바닥글을 위로 민다
                pf.line_spacing = 1.0
                bits = text.split(layout.NUM_TOKEN)
                for k, bit in enumerate(bits):
                    run = para.add_run(bit)
                    run.font.size = Pt(ln["size"])
                    run.font.bold = bool(ln["bold"])
                    run.font.name = layout.SERIF_FACE if ln["serif"] else layout.SANS_FACE
                    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), run.font.name)
                    if k < len(bits) - 1:
                        _page_field(para.add_run())
    start = plan.get("start")
    if start and int(start) > 1:
        pg = OxmlElement("w:pgNumType")
        pg.set(qn("w:start"), str(int(start)))
        sec._sectPr.append(pg)
