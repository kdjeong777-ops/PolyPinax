"""명함 그림 구획 나누기(명함 SOT §5.28) — 줄인 그림을 재귀 XY 자르기로 잎(줄·낱말 무리)으로 나누고 잎마다 높이·획 굵기를 잰다.
굵거나 큰 잎을 골라 원래 해상도에서 다시 읽게 한다(`recognize.block_lines`). numpy·PIL 만 쓴다. 배경 일꾼에서 부른다(응답성 SOT §4)."""
from __future__ import annotations

LONG = 1200              # 긴 변을 이만큼으로 줄여(또는 키워) 잰다 — 명함 크기와 무관하게
BLOCK_TOPK = 3           # 다시 읽을 구획 수(정답 대조 학습 묶음 — 4 와 같고 OCR 은 3/4)
BOLD_MIN = 1.1           # 카드 기준 대비 굵기 비 — 이 이상이거나
SIZE_MIN = 1.2           #   높이 비가 이 이상인 잎만 다시 읽는다


def _np():
    import numpy as np
    return np


def gray(im):
    from PIL import Image, ImageOps
    g = ImageOps.autocontrast(im.convert("L"), cutoff=1)
    k = LONG / float(max(g.size) or 1)
    return g.resize((max(1, int(g.width * k)), max(1, int(g.height * k))), Image.LANCZOS)


def _otsu(a) -> int:
    np = _np()
    h = np.bincount(a.ravel(), minlength=256).astype(float)
    p = h / max(1.0, h.sum())
    om = np.cumsum(p)
    mu = np.cumsum(p * np.arange(256))
    sb = (mu[-1] * om - mu) ** 2 / (om * (1 - om) + 1e-12)
    return int(np.argmax(sb))


def binarize(g):
    """회색조 → 글자 칠(True). 어두운 바탕은 뒤집고, 줄 절반 넘게 칠한 괘선·가장자리 띠는 지운다."""
    np = _np()
    a = np.asarray(g, dtype=np.uint8)
    ink = a < _otsu(a)
    if ink.mean() > 0.5:
        ink = ~ink
    H, W = ink.shape
    ink[ink.sum(1) > 0.5 * W, :] = False
    ink[:, ink.sum(0) > 0.5 * H] = False
    b = max(2, int(0.01 * min(H, W)))
    ink[:b, :] = False
    ink[-b:, :] = False
    ink[:, :b] = False
    ink[:, -b:] = False
    return ink


def _runs(prof, min_gap: int, tol: int = 0) -> list:
    """프로필이 tol 넘는 구간들 — 빈 틈이 min_gap 보다 짧으면 잇는다."""
    on = prof > tol
    segs, i, n = [], 0, len(prof)
    while i < n:
        if on[i]:
            j = i
            while j < n and on[j]:
                j += 1
            segs.append([i, j])
            i = j
        else:
            i += 1
    out = segs[:1]
    for s in segs[1:]:
        if s[0] - out[-1][1] < min_gap:
            out[-1][1] = s[1]
        else:
            out.append(s)
    return out


def xy_cut(ink, box, out: list, depth: int = 0) -> list:
    """재귀 XY 자르기 — 빈 가로줄로 먼저, 다음 빈 세로 띠로. 잎 = (y0, y1, x0, x1) 픽셀."""
    y0, y1, x0, x1 = box
    sub = ink[y0:y1, x0:x1]
    if depth > 40 or sub.sum() < 6:
        return out
    rows = _runs(sub.sum(1), 4, tol=max(1, int(0.004 * (x1 - x0))))      # 잡티 몇 점은 빈 줄로 본다
    if len(rows) > 1:
        for a, b in rows:
            xy_cut(ink, (y0 + a, y0 + b, x0, x1), out, depth + 1)
        return out
    ys, ye = rows[0] if rows else (0, sub.shape[0])
    sub2 = sub[ys:ye]
    h = ye - ys
    gap = max(8, int(min(h, 0.03 * ink.shape[1]) * 1.6))                 # 글자 높이(또는 너비 3%)의 1.6 배 넘는 빈 띠
    cols = _runs(sub2.sum(0), gap)
    if len(cols) <= 1 and h > 0.12 * ink.shape[0]:
        cols = _runs(sub2.sum(0), 10)                                     # 키 큰 덩이(QR·괘선 옆 여러 줄)는 좁은 띠로도
    if len(cols) > 1:
        for a, b in cols:
            xy_cut(ink, (y0 + ys, y0 + ye, x0 + a, x0 + b), out, depth + 1)
        return out
    xs, xe = cols[0] if cols else (0, sub2.shape[1])
    out.append((y0 + ys, y0 + ye, x0 + xs, x0 + xe))
    return out


def _erode(m):
    np = _np()
    p = np.pad(m, 1, constant_values=False)
    r = p[1:-1, 1:-1].copy()
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            r &= p[dy:dy + m.shape[0], dx:dx + m.shape[1]]
    return r


def stroke(m) -> float:
    """획 굵기(픽셀) ≈ 2 × 평균 거리 — 침식을 거듭해 살아남은 점 수의 합 ÷ 처음 점 수."""
    n0 = int(m.sum())
    if not n0:
        return 0.0
    tot, cur = 0, m
    for _ in range(30):
        cur = _erode(cur)
        c = int(cur.sum())
        if not c:
            break
        tot += c
    return 2.0 * tot / n0 + 1.0


def leaves(im) -> list:
    """그림(PIL) → 잎 목록 {y0, y1, x0, x1(그림 비율), h(높이 비율), sw(획 굵기 px)}. 바탕·그림 덩이는 뺀다."""
    ink = binarize(gray(im))
    H, W = ink.shape
    out = []
    for y0, y1, x0, x1 in xy_cut(ink, (0, H, 0, W), []):
        h, w = y1 - y0, x1 - x0
        if h < 6 or w < 4:
            continue
        m = ink[y0:y1, x0:x1]
        if float(m.mean()) > 0.6 or h > 0.35 * H:
            continue
        out.append({"y0": y0 / H, "y1": y1 / H, "x0": x0 / W, "x1": x1 / W, "h": h / H, "sw": stroke(m)})
    return out


def _wmedian(vals, ws) -> float:
    np = _np()
    if not vals:
        return 1.0
    o = np.argsort(vals)
    v, w = np.asarray(vals)[o], np.asarray(ws)[o]
    c = np.cumsum(w)
    return float(v[min(len(v) - 1, int(np.searchsorted(c, c[-1] / 2)))])


def pick_blocks(lv: list, k: int = 0) -> list:
    """다시 읽을 잎 — 카드 기준(너비로 무게 준 중앙값)보다 굵거나 큰 글 잎을 굵기비×크기비 차례로 k 개(0 = `BLOCK_TOPK`)."""
    k = k or BLOCK_TOPK
    txt = [x for x in lv if 0.012 < x["h"] < 0.25 and (x["x1"] - x["x0"]) > 0.03]
    if not txt:
        return []
    ws = [x["x1"] - x["x0"] for x in txt]
    sw_ref = _wmedian([x["sw"] for x in txt], ws)
    h_ref = _wmedian([x["h"] for x in txt], ws)
    sc = []
    for x in txt:
        b, s = x["sw"] / max(0.5, sw_ref), x["h"] / max(1e-3, h_ref)
        if b >= BOLD_MIN or s >= SIZE_MIN:
            sc.append((b * s, x))
    sc.sort(key=lambda t: -t[0])
    return [x for _, x in sc[:k]]
