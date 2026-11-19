"""다중 명함 사진 나누기 (명함 SOT §5.26, D31) — 한 사진에 여럿 늘어놓고 찍은 명함을 명함마다 잘라낸다.

Qt 없음 · numpy·Pillow 만(새 의존성 없음). 배경 스레드에서 부른다(`importer.MultiWorker`).
★ 명함 글·경로는 로그·예외 메시지에 싣지 않는다(§2.1).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import numpy as np

from viewer.bizcard import recognize as R

DET = 600                 # 찾기용 긴 변(px)
MULTI_DIR = "다중 원본"    # 나눈 원본을 옮겨 두는 하위 폴더(훑기에서 빠짐)
SEEN_KEY = "multi_seen"   # meta — 센 사진 {경로 열쇠: 지문}
CROP_WORD = "명함"         # 잘라낸 파일 이름 `<원본> 명함 01.jpg`
_CROP_RE = re.compile(r" %s \d{2}$" % CROP_WORD)
_SAT_MAX = 90             # 흰 명함 — 채도가 낮다
_ERODE = 5                # 붙은 명함 떼기(깎기 크기)
_GROW = 1.5               # 깎은 만큼 되돌려 넓힘(찾기 그림 px)
_MIN_AREA = 0.004
_RATIO = (1.3, 2.2)       # 명함 긴 변/짧은 변
_MIN_FILL = 0.88          # 볼록 껍질이 직사각형을 채우는 정도
_MAX_AREA = 0.45          # 이보다 큰 덩이는 바닥·책상
_BG_DIST = 45             # 바닥색과 이만큼 넘게 다르면 명함 쪽(RGB 거리)
_USE_DIST = False         # 바닥색 거리 — 시험해 보니 바닥에 무늬·빛이 있으면 덩이가 커져 끔(SOT §5.26)
_CARD = 1.75              # 보통 명함 긴 변/짧은 변(90×50 mm 꼴)


def img_exts() -> tuple:
    from viewer.photo_io import HEIF_EXTS
    return tuple(R.IMG_EXTS) + tuple(HEIF_EXTS)


def is_crop(path) -> bool:
    return bool(_CROP_RE.search(Path(str(path)).stem))


def open_image(path):
    """보이는 방향(EXIF)으로, HEIC 도(사진 모드와 같은 해독기)."""
    from PIL import Image, ImageOps
    from viewer import photo_io
    if photo_io.is_heif(path):
        photo_io.heif_ready()
    with Image.open(str(path)) as im:
        return ImageOps.exif_transpose(im).convert("RGB")


def detect_file(path, preview: int = 0):
    """파일 → (모서리들(원래 해상도), 원래 (폭, 높이), 미리 보기 그림 또는 None). JPEG 는 줄여 해독(draft)해 빠르다."""
    from PIL import Image, ImageOps
    from viewer import photo_io
    if photo_io.is_heif(path):
        photo_io.heif_ready()
    with Image.open(str(path)) as im:
        full = im.size
        try:
            im.draft("RGB", (DET * 2, DET * 2))       # JPEG 만 — 1/2~1/8 로 해독
        except Exception:
            pass
        small = ImageOps.exif_transpose(im).convert("RGB")
    o = (im.getexif() or {}).get(0x0112, 1) if hasattr(im, "getexif") else 1
    if o in (5, 6, 7, 8):
        full = (full[1], full[0])
    k = full[0] / float(small.size[0])
    quads = [[[x * k, y * k] for x, y in q] for q in find_cards(small)]
    pv = None
    if preview:
        pv = small.copy()
        pv.thumbnail((preview, preview))
    return quads, full, pv


def _otsu(g) -> int:
    h = np.bincount(g.ravel(), minlength=256).astype(float)
    p = h / max(1.0, h.sum())
    w = np.cumsum(p)
    m = np.cumsum(p * np.arange(256))
    sb = (m[-1] * w - m) ** 2 / (w * (1 - w) + 1e-12)
    return int(np.argmax(sb))


def _label(mask):
    """4-이웃 연결 성분 — 줄마다 런(run)으로 합친다(그림이 작아 파이썬으로도 빠르다)."""
    H, W = mask.shape
    lab = np.zeros((H, W), np.int32)
    par = [0]

    def f(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    prev = []
    for y in range(H):
        d = np.diff(np.concatenate(([0], mask[y].astype(np.int8), [0])))
        cur = []
        for s, e in zip(np.where(d == 1)[0], np.where(d == -1)[0]):
            n = len(par)
            par.append(n)
            for ps, pe, pl in prev:
                if ps < e and pe > s:
                    a, b = f(n), f(pl)
                    if a != b:
                        par[max(a, b)] = min(a, b)
            cur.append((s, e, n))
            lab[y, s:e] = n
        prev = cur
    root = np.array([f(i) for i in range(len(par))], np.int32)
    return root[lab]


def _hull(pts):
    pts = sorted(set(map(tuple, pts.tolist())))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def _grow(r, d):
    """직사각형을 가운데에서 바깥으로 d 만큼(깎은 만큼 되돌림)."""
    c = r.mean(0)
    out = []
    for p in r:
        v = p - c
        n = float(np.hypot(*v)) or 1.0
        out.append(p + v / n * d * 1.41421356)
    return np.array(out)


def _min_rect(h):
    h = np.array(h, float)
    best = None
    for i in range(len(h)):
        e = h[(i + 1) % len(h)] - h[i]
        n = float(np.hypot(*e))
        if n == 0:
            continue
        u = e / n
        v = np.array([-u[1], u[0]])
        a, b = h @ u, h @ v
        area = (a.max() - a.min()) * (b.max() - b.min())
        if best is None or area < best[0]:
            best = (area, u, v, a.min(), a.max(), b.min(), b.max())
    _, u, v, a0, a1, b0, b1 = best
    return np.array([u * a0 + v * b0, u * a1 + v * b0, u * a1 + v * b1, u * a0 + v * b1])


def _pieces(side, unit, strict: bool = False) -> tuple:
    """덩이 직사각형(짧은 변, 긴 변) → (몇 장, 'long'|'short' 어느 변을 나누나). 명함 꼴이 아니면 (0, '')."""
    S, L = side
    best = None
    for k in range(1, 9 if unit else 2):                 # 한 장 크기를 모르면 나누지 않는다(반쪽만 흰 명함을 쪼개지 않게)
        for along, a, b in (("long", L / k, S), ("short", L, S / k)):
            pr = max(a, b) / max(1.0, min(a, b))
            if not (_RATIO[0] < pr < _RATIO[1]):
                continue
            score = abs(pr - _CARD)
            if unit:                                     # 한 장 짧은 변이 알려져 있으면 크기도 맞아야
                sh, lo = min(a, b), max(a, b)
                if not (0.7 * unit < sh < 1.4 * unit):
                    continue
                if strict and not (0.8 * unit < sh < 1.2 * unit and 0.75 * unit * _CARD < lo < 1.25 * unit * _CARD):
                    continue                             # 가장자리에 닿은 덩이 — 한 장 크기와 꼭 맞을 때만(책상 띠를 명함으로 보지 않게)
                score += abs(sh - unit) / unit
            if best is None or score < best[0] - 1e-9:
                best = (score, k, along)
    return (best[1], best[2]) if best else (0, "")


def _split_rect(r, k, along) -> list:
    """직사각형 r(네 모서리)을 한 변을 따라 k 등분."""
    if k <= 1:
        return [r]
    e1, e2 = r[1] - r[0], r[3] - r[0]
    long_is_e1 = np.hypot(*e1) >= np.hypot(*e2)
    cut = e1 if (along == "long") == long_is_e1 else e2
    other = e2 if cut is e1 else e1
    out = []
    for j in range(k):
        p0 = r[0] + cut * (j / k)
        p1 = r[0] + cut * ((j + 1) / k)
        out.append(np.array([p0, p1, p1 + other, p0 + other]))
    return out


def find_cards(im) -> list:
    """PIL 그림 → 명함마다 네 모서리 [[x,y]×4](원래 해상도), 위→아래·왼쪽→오른쪽 차례."""
    from PIL import Image, ImageFilter
    W, H = im.size
    s = DET / float(max(W, H))
    sm = im.resize((max(1, round(W * s)), max(1, round(H * s))), Image.BILINEAR)
    g = np.asarray(sm.convert("L"))
    sat = np.asarray(sm.convert("HSV"))[..., 1].astype(int)
    rgb = np.asarray(sm).astype(int)
    edge = np.concatenate([rgb[:6].reshape(-1, 3), rgb[-6:].reshape(-1, 3), rgb[:, :6].reshape(-1, 3), rgb[:, -6:].reshape(-1, 3)])
    bg = np.median(edge, 0)                            # 바닥색 = 가장자리 띠의 가운데 값
    dist = np.sqrt(((rgb - bg) ** 2).sum(-1))
    tdist = max(_BG_DIST, float(np.percentile(np.sqrt(((edge - bg) ** 2).sum(-1)), 75)) * 1.5)
    # 흰 명함(밝고 채도 낮음) 또는 바닥색과 뚜렷이 다른 곳(어두운 반쪽·색 띠가 있는 명함)
    mask = ((g > _otsu(g)) & (sat < _SAT_MAX)) | ((dist > tdist) if _USE_DIST else False)
    mi = Image.fromarray((mask * 255).astype(np.uint8))
    mi = mi.filter(ImageFilter.MinFilter(_ERODE)).filter(ImageFilter.MaxFilter(3))
    mi = mi.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    m = np.asarray(mi) > 0
    if not m.any():
        return []
    lab = _label(m)
    h_, w_ = m.shape
    comps = []
    ids, cnt = np.unique(lab[lab > 0], return_counts=True)
    for i, c in zip(ids, cnt):
        if c < _MIN_AREA * m.size or c > _MAX_AREA * m.size:
            continue                                   # 너무 작음 / 너무 큼(바닥·책상)
        ys, xs = np.nonzero(lab == i)
        hl = _hull(np.stack([xs, ys], 1))
        if len(hl) < 3:
            continue
        r = _min_rect(hl)
        side = sorted([float(np.hypot(*(r[1] - r[0]))), float(np.hypot(*(r[2] - r[1])))])
        hx, hy = np.array(hl, float).T
        harea = 0.5 * abs(np.dot(hx, np.roll(hy, 1)) - np.dot(hy, np.roll(hx, 1)))
        if harea / (side[0] * side[1] + 1e-9) < _MIN_FILL:
            continue                                   # 직사각형이 아님(바닥 조각·겹친 것)
        border = xs.min() == 0 or ys.min() == 0 or xs.max() == w_ - 1 or ys.max() == h_ - 1
        comps.append((r, side, border))
    # 명함 한 장 크기 = 꼴이 명함인 것들의 짧은 변 가운데 값 — 붙어서 한 덩이가 된 것을 몇 장으로 나눌지 가린다
    singles = [sd[0] for _r, sd, _b in comps if _RATIO[0] < sd[1] / max(1.0, sd[0]) < _RATIO[1]]
    unit = float(np.median(singles)) if singles else 0.0
    out = []
    for r, side, border in comps:
        k, along = _pieces(side, unit, strict=border)   # 가장자리에 닿은 덩이는 한 장 크기와 꼭 맞게만 나눈다
        if k == 0:
            continue
        if border and unit and side[0] < 0.6 * unit:
            continue                                   # 가장자리에서 잘린 조각
        out += [_grow(q, _GROW) / s for q in _split_rect(r, k, along)]
    if not out:
        return []
    hs = sorted(min(np.ptp(q[:, 0]), np.ptp(q[:, 1])) for q in out)
    row = hs[len(hs) // 2] * 0.5                       # 같은 줄로 볼 높이 차(명함 짧은 변의 절반)
    out.sort(key=lambda q: q[:, 1].mean())
    rows, cur = [], [out[0]]
    for q in out[1:]:
        if q[:, 1].mean() - np.mean([p[:, 1].mean() for p in cur]) < row:
            cur.append(q)
        else:
            rows.append(cur)
            cur = [q]
    rows.append(cur)
    return [q.tolist() for r_ in rows for q in sorted(r_, key=lambda q: q[:, 0].mean())]


def crop(im, quad):
    """네 모서리 → 반듯한 명함 그림(긴 변 가로)."""
    from PIL import Image
    r = np.array(quad, float)
    c = r.mean(0)
    r = r[np.argsort(np.arctan2(r[:, 1] - c[1], r[:, 0] - c[0]))]
    r = np.roll(r, -int(np.argmin(r.sum(1))), 0)       # 왼쪽 위부터 시계 방향
    w = int(round(np.hypot(*(r[1] - r[0]))))
    h = int(round(np.hypot(*(r[3] - r[0]))))
    quad8 = (r[0][0], r[0][1], r[3][0], r[3][1], r[2][0], r[2][1], r[1][0], r[1][1])
    out = im.transform((max(1, w), max(1, h)), Image.QUAD, quad8, Image.BICUBIC)
    if h > w:
        out = out.rotate(90, expand=True)
    return out


def _unique(path: Path) -> Path:
    p, k = path, 2
    while p.exists():
        p, k = path.with_name("%s (%d)%s" % (path.stem, k, path.suffix)), k + 1
    return p


def split_file(path, quads=None, out_dir=None, moved=None) -> list:
    """다중 사진 하나 → 잘라낸 JPG 경로들(원본 옆 — out_dir 을 주면 거기 — `<원본> 명함 01.jpg`), 원본은 그 폴더의 `다중 원본\\` 으로.
    두 장 미만이면 [] (아무것도 안 함). out_dir = 정리본을 나눌 때 원천 폴더(정리 폴더는 훑기에서 빠지므로, §5.26 '이미 들어간 명함')."""
    path = Path(str(path))
    base = Path(str(out_dir)) if out_dir else path.parent
    im = open_image(path)
    quads = quads if quads is not None else find_cards(im)
    if len(quads) < 2:
        return []
    made = []
    for i, q in enumerate(quads, 1):
        dst = _unique(base / ("%s %s %02d.jpg" % (path.stem, CROP_WORD, i)))
        tmp = dst.with_name(dst.name + ".part")
        crop(im, q).save(tmp, "JPEG", quality=95)
        os.replace(tmp, dst)
        made.append(str(dst))
    hold = base / MULTI_DIR
    hold.mkdir(exist_ok=True)
    dst = _unique(hold / path.name)
    os.replace(path, dst)
    if moved is not None:
        moved.append((str(path), str(dst)))            # 되돌리기 기록(중복 검토 §5.26 '이미 들어간 명함')
    return made


def candidates(folder) -> list:
    """폴더 맨 위의 그림 중 세어 볼 것 — 잘라낸 것·뒷면(`_2`)은 뺀다."""
    folder = Path(str(folder))
    exts = img_exts()
    out = []
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    for n in names:
        p = folder / n
        if not p.is_file() or p.suffix.lower() not in exts or is_crop(p):
            continue
        if any(p.stem.endswith(s) for s in R.BACK_SUFFIXES):
            continue
        out.append(str(p))
    return out
