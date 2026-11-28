# -*- coding: utf-8 -*-
"""꾸미기 체크 표시 — 모양·크기·선 굵기, 벡터 조각 그리기, 양식 칸 찾기 (편집 꾸밈 SOT §4.6.14, 261128-13).

- 표시는 **사진 꾸밈**으로 넣는다(등록 이미지와 같은 길 — 옮기기·크기·지우기·되돌리기·저장·인쇄·평탄화가 그대로).
  그림은 1쪽 **벡터 PDF 조각**(`pdf`) + 화면용 PNG(`png`) — 굽기는 벡터 그대로(`show_pdf_page`, §4.6.11 '굽기·저장').
- 선 굵기는 크기의 `W_FRAC` — 크기를 바꾸면 굵기도 같은 비율(도장처럼 한 그림이라 늘이면 함께 커진다).
- 누른 곳에 그린 칸(□)이 있으면 그 칸 가운데에 칸의 `BOX_FIT` 크기, 없으면 누른 자리 가운데에 `MM_DEFAULT`(사용자 결정 '칸 맞춤 + 기본 크기').
- Qt 를 쓰지 않는다.
"""
from __future__ import annotations

KINDS = ("v", "dot", "x", "o")                  # ✓ 체크 · ● 꽉 찬 원 · ✕ 가위표 · ○ 동그라미 — 맨 앞이 처음 값
from viewer.i18n import tr_noop                 # 이름만 표시(뽑기용) — 화면에서 tr()
KIND_LABEL = {"v": tr_noop("체크"), "dot": tr_noop("꽉 찬 원"), "x": tr_noop("가위표"), "o": tr_noop("동그라미")}   # 메뉴 그림은 그 모양 자체(§4.8 — 글리프 금지)
SIZES_MM = (3.0, 4.0, 5.0)                      # ▾ 크기(칸이 없을 때) — 작게·보통·크게
MM_DEFAULT = 4.0
W_FRAC = 0.13                                   # 선 굵기 = 크기 × 이 값(4 mm → 0.52 mm ≈ 1.5 pt — 볼펜 굵기)
BOX_FIT = 0.75                                  # 칸에 넣을 때 칸 한 변의 이 몫
BOX_MM = (2.5, 15.0)                            # 칸으로 볼 한 변(mm) — 이보다 작거나 크면 칸이 아니다(글자 획·표 칸)
BOX_RATIO = (0.7, 1.43)                         # 칸으로 볼 가로/세로 비
PNG_DPI = 600
PT_PER_MM = 72.0 / 25.4


def _shape(page, kind: str, s: float, color, width: float) -> None:
    """정사각 s pt 쪽 가운데에 모양 하나."""
    import fitz
    c = s / 2.0
    h = s / 2.0
    if kind == "dot":
        page.draw_circle(fitz.Point(c, c), h * 0.62, color=None, fill=color, width=0)
        return
    if kind == "o":
        page.draw_circle(fitz.Point(c, c), h * 0.70, color=color, width=width)
        return
    sh = page.new_shape()
    if kind == "x":
        a = h * 0.62
        sh.draw_line(fitz.Point(c - a, c - a), fitz.Point(c + a, c + a))
        sh.draw_line(fitz.Point(c + a, c - a), fitz.Point(c - a, c + a))
    else:                                       # v
        sh.draw_polyline([fitz.Point(c - h * 0.80, c + h * 0.02), fitz.Point(c - h * 0.22, c + h * 0.62),
                          fitz.Point(c + h * 0.85, c - h * 0.70)])
    sh.finish(color=color, width=width, lineCap=1, lineJoin=1, closePath=False)
    sh.commit()


def render(kind: str, size_pt: float, rgb=(0.0, 0.0, 0.0)) -> dict:
    """{'pdf': 1쪽 벡터 조각, 'png': 투명 그림, 'aspect': 1.0} — 크기 size_pt(정사각)."""
    import fitz
    kind = kind if kind in KINDS else KINDS[0]
    s = max(4.0, float(size_pt))
    doc = fitz.open()
    try:
        pg = doc.new_page(width=s, height=s)
        _shape(pg, kind, s, tuple(float(v) for v in rgb), max(0.6, s * W_FRAC))
        pdf = doc.tobytes(garbage=3, deflate=True)
        png = pg.get_pixmap(dpi=PNG_DPI, alpha=True).tobytes("png")
    finally:
        doc.close()
    return {"pdf": pdf, "png": png, "aspect": 1.0}


def find_box(page, x: float, y: float):
    """PDF 쪽 좌표(회전 전) (x, y) 를 덮는 그린 칸(□) — 가장 작은 것의 (x0, y0, x1, y1), 없으면 None.
    벡터로 그린 칸만 본다(스캔본은 None — 기본 크기). 선 굵기만큼 바깥도 누른 것으로 본다."""
    lo, hi = BOX_MM[0] * PT_PER_MM, BOX_MM[1] * PT_PER_MM
    best = None
    try:
        drawings = page.get_drawings()
    except Exception:
        return None
    for d in drawings:
        cands = []
        for it in d.get("items", ()):
            if it and it[0] == "re":
                cands.append(it[1])
            elif it and it[0] == "qu":
                cands.append(it[1].rect)
        if not cands and d.get("closePath") and len(d.get("items", ())) in (4, 5):
            cands.append(d["rect"])            # 선 넷으로 그린 칸
        tol = float(d.get("width") or 1.0) + 1.0
        for r in cands:
            w, h = abs(r.x1 - r.x0), abs(r.y1 - r.y0)
            if not (lo <= w <= hi and lo <= h <= hi):
                continue
            if not (BOX_RATIO[0] <= w / max(h, 1e-6) <= BOX_RATIO[1]):
                continue
            if not (min(r.x0, r.x1) - tol <= x <= max(r.x0, r.x1) + tol
                    and min(r.y0, r.y1) - tol <= y <= max(r.y0, r.y1) + tol):
                continue
            if best is None or w * h < (best[2] - best[0]) * (best[3] - best[1]):
                best = (min(r.x0, r.x1), min(r.y0, r.y1), max(r.x0, r.x1), max(r.y0, r.y1))
    return best


def place_rect(cx: float, cy: float, size: float, pw: float, ph: float) -> list:
    """가운데 (cx, cy)·한 변 size(pt) 의 상자를 쪽 비율 [x, y, w, h] 로 — 쪽 밖이면 안으로."""
    size = min(size, pw, ph)
    x0 = min(max(0.0, cx - size / 2.0), pw - size)
    y0 = min(max(0.0, cy - size / 2.0), ph - size)
    return [x0 / pw, y0 / ph, size / pw, size / ph]
