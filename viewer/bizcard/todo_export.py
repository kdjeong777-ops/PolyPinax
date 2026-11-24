"""탭 하나 → 엑셀(.xlsx)·Word(.docx) (명함찾기 SOT §5.24.2 '할 일 내보내기', 261120-42 — 종전 261120-21 '모든 할 일 엑셀'을 바꿈).

Qt 없음 — 부르는 쪽(명함찾기 창)이 배경 워커에서 `write_xlsx`·`write_docx` 를 부른다(응답성 SOT §6). 엑셀 openpyxl·Word python-docx 는
이미 쓰는 의존성(형식 변환·단어학습 — 새 패키지 없음). 자료는 `people.tab_export` 꼴 + 부르는 쪽이 붙인 `state_label`.
★ 개인정보 — 파일은 사용자가 고른 자리에만, 로그에 값을 싣지 않는다(§2.1).
"""
from __future__ import annotations

import os
from pathlib import Path

MARK = {True: "☑", False: "☐"}
HEAD_GRAY = "E4E4E4"                 # 명함찾기 목록 머리말과 같은 회색(디자인 SOT §2.5 '명함 세부 카드')
FONT_KO = "맑은 고딕"
NOTE_WIDTHS = (12, 6, 12, 60)        # 수정일·완료·기한·내용
PEOPLE_WIDTHS = (12, 22, 12, 16, 28)  # 이름·회사·직함·휴대폰·메일


def _cell_phone(card) -> str:
    ph = [p for p in (card.get("phones") or []) if isinstance(p, (list, tuple)) and len(p) >= 2]
    num = next((n for k, n in ph if k == "cell"), "") or next((n for k, n in ph if k != "fax"), "")
    try:
        from viewer.bizcard import phone as PH
        return PH.normalize(num)
    except Exception:
        return num


def note_rows(data: dict) -> list:
    """할 일 표 줄 [(수정일, 완료, 기한, 내용, 이 줄이 그 기록의 첫 줄인가, 그 기록 줄 수)] — 최신 기록 먼저."""
    out = []
    for n in data.get("notes") or []:
        items = [i for i in n.get("items") or [] if (i.get("text") or "").strip()]
        for k, i in enumerate(items):
            out.append((n.get("made") or "", MARK[bool(i.get("done"))], i.get("due") or "", i.get("text") or "",
                        k == 0, len(items)))
    return out


def people_rows(data: dict) -> list:
    """명단 표 줄 [이름, 회사, 직함, 휴대폰, 메일] — 명단 차례."""
    return [[c.get("name") or "", c.get("company") or "", c.get("title") or "", _cell_phone(c),
             (c.get("emails") or [""])[0]] for c in data.get("members") or []]


def info_lines(data: dict, L: dict) -> list:
    """머리 줄 [(이름표, 값)] — 할 일 탭은 기간·상태·해시태그(빈 값은 뺌)."""
    if not data.get("todo"):
        return []
    out = [(L["period"], "%s ~ %s" % (data.get("start") or "", data.get("end") or L["ongoing"])),
           (L["state"], data.get("state_label") or "")]
    if data.get("tags"):
        out.append((L["tags"], " ".join("#" + t for t in data["tags"])))
    return out


def _replace(tmp: Path, path) -> None:
    os.replace(tmp, path)            # 배경 워커에서 — 반쯤 쓴 파일이 남지 않게


def write_xlsx(path, data: dict, L: dict) -> None:
    """data 를 path 에 .xlsx — 할 일 탭은 시트 '할 일'(제목·머리 줄·할 일 표, 한 기록의 수정일 칸은 그 줄들에 걸쳐 합침)과
    '명단', 보통 탭은 '명단' 하나. 머리말 굵게·회색·고정, 거르기, 줄바꿈 보임. L = 화면 언어 문구."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    fill = PatternFill("solid", fgColor=HEAD_GRAY)
    top = Alignment(vertical="top", wrap_text=True)

    def head(ws, row, heads, widths):
        for col, (h, w) in enumerate(zip(heads, widths), 1):
            c = ws.cell(row=row, column=col, value=h)
            c.font = Font(bold=True)
            c.fill = fill
            c.alignment = Alignment(horizontal="center", vertical="center")
            ws.column_dimensions[get_column_letter(col)].width = w
        ws.freeze_panes = "A%d" % (row + 1)

    def body(ws, row, rows):
        for vals in rows:
            for col, v in enumerate(vals, 1):
                ws.cell(row=row, column=col, value=v).alignment = top
            row += 1
        return row

    ws_p = wb.active
    if data.get("todo"):
        ws = ws_p
        ws.title = L["sheet_todo"][:31]
        ws.cell(row=1, column=1, value=data.get("name") or "").font = Font(bold=True, size=14)
        r = 2
        for k, v in info_lines(data, L):
            ws.cell(row=r, column=1, value=k).font = Font(bold=True)
            ws.cell(row=r, column=2, value=v)
            r += 1
        r += 1
        hr = r
        head(ws, hr, [L["made"], L["done"], L["due"], L["text"]], NOTE_WIDTHS)
        r = hr + 1
        merges = []
        for made, mark, due, text, first, n in note_rows(data):
            for col, v in enumerate((made if first else None, mark, due, text), 1):
                ws.cell(row=r, column=col, value=v).alignment = top
            ws.cell(row=r, column=2).alignment = Alignment(horizontal="center", vertical="top")
            if first and n > 1:
                merges.append((r, r + n - 1))
            r += 1
        for a, b in merges:                            # 다 쓴 뒤 합친다(합친 칸에는 값을 쓸 수 없다)
            ws.merge_cells(start_row=a, start_column=1, end_row=b, end_column=1)
        ws.auto_filter.ref = "A%d:D%d" % (hr, max(hr, r - 1))
        ws_p = wb.create_sheet()
    ws_p.title = L["sheet_people"][:31]
    head(ws_p, 1, [L["name"], L["company"], L["p_title"], L["cell"], L["email"]], PEOPLE_WIDTHS)
    r = body(ws_p, 2, people_rows(data))
    ws_p.auto_filter.ref = "A1:E%d" % max(1, r - 1)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".part")
    wb.save(str(tmp))
    _replace(tmp, path)


def _ko_font(run, bold=False, size=None):
    from docx.oxml.ns import qn
    from docx.shared import Pt
    run.font.name = FONT_KO
    run.bold = bold or None
    if size:
        run.font.size = Pt(size)
    rpr = run._element.get_or_add_rPr()
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rf)
    rf.set(qn("w:eastAsia"), FONT_KO)             # 한글이 서양 글꼴로 밀리지 않게(text_word 와 같은 길)


def _shade(cell, hex_fill):
    from docx.oxml.ns import qn
    tcpr = cell._element.get_or_add_tcPr()
    shd = tcpr.makeelement(qn("w:shd"), {qn("w:val"): "clear", qn("w:color"): "auto", qn("w:fill"): hex_fill})
    tcpr.append(shd)


def _table(doc, heads, rows, widths):
    from docx.shared import Cm
    t = doc.add_table(rows=1, cols=len(heads))
    t.style = "Table Grid"
    for c, h in zip(t.rows[0].cells, heads):
        c.text = ""
        _ko_font(c.paragraphs[0].add_run(h), bold=True)
        _shade(c, HEAD_GRAY)
    for vals in rows:
        cells = t.add_row().cells
        for c, v in zip(cells, vals):
            c.text = ""
            lines = str(v).split("\n")
            p = c.paragraphs[0]
            for k, line in enumerate(lines):
                run = p.add_run(line)
                _ko_font(run)
                if k < len(lines) - 1:
                    run.add_break()
    for row in t.rows:
        for c, w in zip(row.cells, widths):
            c.width = Cm(w)
    return t


def write_docx(path, data: dict, L: dict) -> None:
    """data 를 path 에 .docx — 제목, 머리 줄(할 일 탭), 할 일 표(최신 기록 → 지난 기록), 명단 표. 머리말 굵게·회색."""
    from docx import Document
    doc = Document()
    p = doc.add_paragraph()
    _ko_font(p.add_run(data.get("name") or ""), bold=True, size=16)
    for k, v in info_lines(data, L):
        p = doc.add_paragraph()
        _ko_font(p.add_run(k + ": "), bold=True)
        _ko_font(p.add_run(v))
    if data.get("todo"):
        p = doc.add_paragraph()
        _ko_font(p.add_run(L["sheet_todo"]), bold=True, size=12)
        rows = [(r[0] if r[4] else "", r[1], r[2], r[3]) for r in note_rows(data)]   # 수정일은 그 기록의 첫 줄에만
        _table(doc, [L["made"], L["done"], L["due"], L["text"]], rows, (2.4, 1.2, 2.4, 10.0))
    p = doc.add_paragraph()
    _ko_font(p.add_run(L["sheet_people"]), bold=True, size=12)
    _table(doc, [L["name"], L["company"], L["p_title"], L["cell"], L["email"]], people_rows(data), (2.2, 3.6, 2.0, 3.0, 5.2))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".part")
    doc.save(str(tmp))
    _replace(tmp, path)


WRITERS = {"xlsx": write_xlsx, "docx": write_docx}
