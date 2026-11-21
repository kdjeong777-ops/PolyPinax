"""할 일 → 엑셀(.xlsx) (명함 SOT §5.24.2 '할 일 엑셀', 261120-21).

Qt 없음 — 부르는 쪽(명함찾기 창)이 배경 워커에서 `write_todos` 를 부른다(응답성 SOT §6). 엑셀은 이미 쓰는 openpyxl
(형식 변환 SOT 의 xlsx 쓰기와 같은 의존성 — 새 패키지 없음). ★ 개인정보 — 파일은 사용자가 고른 자리에만, 로그에 값을 싣지 않는다(§2.1).
"""
from __future__ import annotations

from pathlib import Path

# 열(키, 머리말) — 할 일 칸은 그 할 일의 명단 줄들에 걸쳐 합친 칸
TODO_KEYS = ("start", "end", "state", "title", "memo")
PERSON_KEYS = ("name", "company", "title", "cell", "email")
WIDTHS = {"start": 12, "end": 12, "state": 10, "title": 24, "memo": 40, "name": 12, "company": 22, "p_title": 12,
          "cell": 16, "email": 28}


def _cell_phone(card) -> str:
    ph = [p for p in (card.get("phones") or []) if isinstance(p, (list, tuple)) and len(p) >= 2]
    num = next((n for k, n in ph if k == "cell"), "") or next((n for k, n in ph if k != "fax"), "")
    try:
        from viewer.bizcard import phone as PH
        return PH.normalize(num)
    except Exception:
        return num


def table(rows: list, ongoing: str) -> list:
    """할 일들(`people.todo_rows`) → 표 줄 [(할 일 칸 5 + 사람 칸 5, 이 줄이 그 할 일의 첫 줄인가, 그 할 일 줄 수)]."""
    out = []
    for t in rows:
        people = t.get("members") or [{}]
        todo = [t.get("start") or "", t.get("end") or ongoing, t.get("state_label") or t.get("state") or "",
                t.get("title") or "", t.get("memo") or ""]
        for i, c in enumerate(people):
            person = [c.get("name") or "", c.get("company") or "", c.get("title") or "", _cell_phone(c) if c else "",
                      (c.get("emails") or [""])[0] if c else ""]
            out.append((todo + person, i == 0, len(people)))
    return out


def write_todos(path, rows: list, heads: list, sheet: str, ongoing: str) -> int:
    """rows 를 path 에 .xlsx 로 — 머리말 굵게·고정, 할 일 칸은 그 명단 줄들에 걸쳐 합침, 줄바꿈 보임. 반환 = 할 일 수."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    ws = wb.active
    ws.title = (sheet or "Todo")[:31]
    ws.append(list(heads))
    head_fill = PatternFill("solid", fgColor="E4E4E4")        # 명함찾기 목록 머리말과 같은 회색(디자인 SOT §2.5 '명함 세부 카드')
    for col in range(1, len(heads) + 1):
        c = ws.cell(row=1, column=col)
        c.font = Font(bold=True)
        c.fill = head_fill
        c.alignment = Alignment(horizontal="center", vertical="center")
    ws.freeze_panes = "A2"
    top = Alignment(vertical="top", wrap_text=True)
    r = 2
    for vals, first, n in table(rows, ongoing):
        ws.append(vals)
        for col in range(1, len(vals) + 1):
            ws.cell(row=r, column=col).alignment = top
        if first and n > 1:
            for col in range(1, len(TODO_KEYS) + 1):
                ws.merge_cells(start_row=r, start_column=col, end_row=r + n - 1, end_column=col)
        r += 1
    keys = list(TODO_KEYS) + ["name", "company", "p_title", "cell", "email"]
    for i, k in enumerate(keys, 1):
        ws.column_dimensions[get_column_letter(i)].width = WIDTHS.get(k, 14)
    ws.auto_filter.ref = "A1:%s%d" % (get_column_letter(len(heads)), max(1, r - 1))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".part")
    wb.save(str(tmp))
    import os
    os.replace(tmp, path)                                     # 배경 워커에서 — 반쯤 쓴 파일이 남지 않게
    return len(rows)
