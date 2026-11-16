# -*- coding: utf-8 -*-
"""261116-30: 변환 결과에서 글이 숨지 않게 — 최소 줄 간격·상자는 글에 맞춰 (형식 변환 SOT §1.3).

사용자 보고: "변환된 word, ppt 등의 일부 페이지 줄간격이 너무 좁거나, 박스 안에 있을 때 박스가 작아 뒤의 내용이 안보이는 경우가 있어
줄간격은 최소 줄간격을 주어서 절대 일부가 숨겨져서 안보이게 하지 않도록 수정해."
픽스처 `test_fixtures.tight_pdf()` — 촘촘한 문단·꼭 맞는 상자·꼭 맞는 표·가로로 눌러 그린 칸 글(보통 너비면 두 줄)·세로로 눌러 그린 문단.
  A  Word 원본 모양·줄잇기(실제 `convert.run`): 글 문단 줄 간격 ≥ 가장 큰 글자 × 1.2(최소 줄 간격), 표 행 높이 '정확히' 가 없다, 모든 글이 docx 에 있다
  B  `docx_writer.no_hidden` — 글 문단 줄 간격을 글자 × 1.2 로 올림(규칙은 정확히), 빈 문단은 그대로, 표 행 exact → atLeast, 글상자 '도형을 글에 맞춤'
  C  PowerPoint: 바로 아래 줄과의 거리 ≥ 글자 크기 × PPT_LINE_K(겹치지 않음), 글상자는 '도형을 글에 맞춤'
  D  HWPX 줄잇기: 본문 문단 줄 간격 ≥ 100 %
  E  (Word·PowerPoint 가 있으면) 찍은 PDF 에 모든 글이 있다
**수정 전 코드로 A·B·C 실패.**
"""
import os, re, shutil, sys, tempfile, zipfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pathlib import Path
from PyQt6.QtCore import QStandardPaths
QStandardPaths.setTestModeEnabled(True)
import test_fixtures
from viewer import convert

fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


WANT = ["6번째줄", "상자안셋째줄", "칸22", "칸00", "눌린칸00", "눌린칸11", "눌린줄4"]
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def norm(s):
    return re.sub(r"\s+", "", s or "")


def docx_checks(path, label):
    x = zipfile.ZipFile(str(path)).read("word/document.xml").decode("utf-8")
    paras = re.findall(r"<w:p[ >](?:(?!<w:p[ >]).)*?</w:p>", x, re.S)
    k_min = 1.2
    bad = []
    for p in paras:
        if not norm("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p))):
            continue
        m = re.search(r'<w:spacing [^>]*w:line="(\d+)"[^>]*w:lineRule="exact"|<w:spacing [^>]*w:lineRule="exact"[^>]*w:line="(\d+)"', p)
        if not m:
            continue
        line = int(m.group(1) or m.group(2)) / 20.0
        sizes = [int(v) / 2.0 for v in re.findall(r'<w:sz w:val="(\d+)"', p)] or [11.0]
        if line < max(sizes) * k_min - 0.06:
            bad.append((line, max(sizes)))
    chk(not bad, f"A {label}: 글 문단 줄 간격 ≥ 가장 큰 글자 × 1.2(최소 줄 간격)", f"{len(bad)}개 {bad[:3]}")
    chk('w:hRule="exact"' not in x, f"A {label}: 표 행 높이 '정확히' 가 없다", str(x.count('w:hRule="exact"')))
    txt = norm("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", x)))
    chk(all(w in txt for w in WANT), f"A {label}: 모든 글이 docx 에 있다", str([w for w in WANT if w not in txt]))


ROOT = Path(tempfile.mkdtemp(prefix="convnohidden_test_"))
try:
    src = ROOT / "촘촘한 문서.pdf"
    shutil.copy2(test_fixtures.tight_pdf(), str(src))
    outs = {}
    for k in ("docx_shape", "docx_edit", "pptx_shape", "hwpx_edit"):
        p = convert.run(str(src), k)
        d = ROOT / f"{k}{p.suffix}"
        shutil.move(str(p), str(d))
        outs[k] = d
    docx_checks(outs["docx_shape"], "Word 원본 모양")
    docx_checks(outs["docx_edit"], "Word 줄잇기")

    # B. no_hidden 단위
    from docx import Document
    from docx.enum.text import WD_LINE_SPACING
    from docx.enum.table import WD_ROW_HEIGHT
    from docx.shared import Pt
    dd = Document()
    p1 = dd.add_paragraph("글이 든 문단")
    p1.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY; p1.paragraph_format.line_spacing = Pt(9)
    p2 = dd.add_paragraph("")
    p2.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY; p2.paragraph_format.line_spacing = Pt(1)
    t = dd.add_table(rows=1, cols=1)
    t.rows[0].height_rule = WD_ROW_HEIGHT.EXACTLY; t.rows[0].height = Pt(8)
    t.cell(0, 0).text = "칸 글"
    bp = ROOT / "b.docx"
    dd.save(str(bp))
    # 글상자 하나(VML) — Word 가 만든 글상자 꼴
    z = zipfile.ZipFile(str(bp)); parts = {n: z.read(n) for n in z.namelist()}; z.close()
    xml = parts["word/document.xml"].decode("utf-8")
    vml = ('<w:p><w:r><w:pict><v:shape xmlns:v="urn:schemas-microsoft-com:vml" style="width:50pt;height:10pt">'
           '<v:textbox style="mso-next-textbox:x"><w:txbxContent><w:p><w:r><w:t>상자 글</w:t></w:r></w:p></w:txbxContent>'
           '</v:textbox></v:shape></w:pict></w:r></w:p>')
    xml = xml.replace("<w:sectPr", vml + "<w:sectPr", 1)
    parts["word/document.xml"] = xml.encode("utf-8")
    with zipfile.ZipFile(str(bp), "w", zipfile.ZIP_DEFLATED) as zo:
        for n, b in parts.items():
            zo.writestr(n, b)
    try:
        from viewer.convert.docx_writer import no_hidden
        got = no_hidden(bp)
    except ImportError as e:
        got = None
        chk(False, "B no_hidden 이 있다", repr(e))
    if got is not None:
        x = zipfile.ZipFile(str(bp)).read("word/document.xml").decode("utf-8")
        d2 = Document(str(bp))
        chk(d2.paragraphs[0].paragraph_format.line_spacing_rule == WD_LINE_SPACING.EXACTLY
            and abs(d2.paragraphs[0].paragraph_format.line_spacing.pt - 11 * 1.2) < 0.1,
            "B 글 문단 줄 간격 9 pt → 글자(기본 11 pt) × 1.2 로 올림", str(d2.paragraphs[0].paragraph_format.line_spacing.pt))
        chk(d2.paragraphs[1].paragraph_format.line_spacing_rule == WD_LINE_SPACING.EXACTLY, "B 빈 문단은 그대로(1 pt — 빈 쪽을 만들지 않게)")
        chk(d2.tables[0].rows[0].height_rule == WD_ROW_HEIGHT.AT_LEAST, "B 표 행 exact → atLeast")
        chk("mso-fit-shape-to-text:t" in x, "B 글상자는 '도형을 글에 맞춤'")

    # C. PowerPoint
    from pptx import Presentation
    from pptx.enum.text import MSO_AUTO_SIZE
    from viewer.convert import pptx_writer
    k_line = getattr(pptx_writer, "PPT_LINE_K", 1.2)
    prs = Presentation(str(outs["pptx_shape"]))
    boxes = []
    for sh in prs.slides[0].shapes:
        if sh.has_text_frame and not sh.has_table if hasattr(sh, "has_table") else sh.has_text_frame:
            runs = [r for p in sh.text_frame.paragraphs for r in p.runs]
            if runs and runs[0].text.strip():
                boxes.append((sh.top / 12700, sh.left / 12700, (sh.left + sh.width) / 12700, runs[0].font.size.pt, sh))
    boxes.sort()
    over = []
    for i, (t0, l0, r0, s0, _sh) in enumerate(boxes):
        nxt = next(((t1, s1) for t1, l1, r1, s1, _ in boxes[i + 1:] if t1 > t0 + 0.5 and l1 < r0 and r1 > l0), None)
        if nxt and s0 > 7.0 + 1e-6 and nxt[0] - t0 < s0 * k_line - 0.3:
            over.append((round(t0, 1), round(nxt[0] - t0, 1), s0))
    chk(len(boxes) >= 10 and not over, "C PowerPoint — 바로 아래 줄과 겹치지 않는다(글자 크기를 줄인다)", str(over[:4]))
    chk(boxes and all(b[4].text_frame.auto_size == MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT for b in boxes), "C 글상자는 '도형을 글에 맞춤'")

    # D. HWPX 줄잇기
    z = zipfile.ZipFile(str(outs["hwpx_edit"]))
    hdr = z.read("Contents/header.xml").decode("utf-8")
    secs = "".join(z.read(n).decode("utf-8") for n in z.namelist() if re.match(r"Contents/section\d+\.xml$", n))
    used = set(re.findall(r'paraPrIDRef="(\d+)"', secs))
    low = []
    for pid in used:
        m = re.search(r'<hh:paraPr [^>]*\sid="%s"[^>]*>.*?</hh:paraPr>' % pid, hdr, re.S)
        if m:
            low += [int(v) for v in re.findall(r'<hh:lineSpacing type="PERCENT" value="(\d+)"', m.group(0)) if int(v) < 100]
    chk(not low, "D HWPX 줄잇기 — 줄 간격 100 % 아래가 없다", str(low[:5]))

    # E. 프로그램으로 찍어 글 확인
    from viewer.convert.word_com import word_installed
    if word_installed():
        import fitz
        import pythoncom
        import win32com.client as w
        pythoncom.CoInitialize()
        app = w.DispatchEx("Word.Application"); app.Visible = False; app.DisplayAlerts = 0
        try:
            for k in ("docx_shape", "docx_edit"):
                doc = app.Documents.Open(str(outs[k]), ReadOnly=True)
                pdf = ROOT / f"{k}.pdf"; doc.ExportAsFixedFormat(str(pdf), 17); doc.Close(False)
                t = norm("".join(pg.get_text() for pg in fitz.open(str(pdf))))
                chk(all(w_ in t for w_ in WANT), f"E Word 로 찍은 {k} 에 모든 글", str([w_ for w_ in WANT if w_ not in t]))
        finally:
            app.Quit()
    else:
        print("SKIP - E Word 가 없다")
finally:
    shutil.rmtree(ROOT, ignore_errors=True)

print("\n=== " + ("ALL PASS" if not fails else f"FAILURE ({len(fails)})") + " ===")
for m in fails:
    print(" -", m)
sys.stdout.flush()
os._exit(1 if fails else 0)
