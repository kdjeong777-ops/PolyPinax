"""앱 밖 아이콘 한 벌 만들기 — 디자인 SOT §4.7 (261120-16, 사용자 지시·결정).

앱 아이콘 `resources/icon.png`(붉은 종이 + 흰 'PDF')와 **같은 꼴**로 색과 안 그림만 바꾼다.
  - PolyPix(사진)    `resources/polypix.png`·`polypix.ico`    — 파랑 바탕 + 흰 산 둘(해 없음)
  - PolyCardex(명함) `resources/polycardex.png`·`polycardex.ico` — 보라 바탕 + 흰 사람(머리·어깨)
'PDF' 글자 자리를 좌우 바탕색으로 메우고, **빨강 계열 픽셀만** 색상을 돌린다(흰 종이·옅은 하늘빛 테두리는 그대로).
그림을 바꾸면 다시 돌려 png·ico 를 커밋한다(빌드는 만들지 않는다 — resources 는 --add-data 로 실린다).
    python scripts/make_app_icons.py
"""
import colorsys
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.stdout.reconfigure(encoding="utf-8")            # 검사 작성 SOT §14.7.2-21 — 한글을 찍는다
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "resources")

SIZES = (16, 24, 32, 48, 64, 128, 256)
TEXT_BOX = (132, 318, 196, 277)                     # icon.png(533×468) 의 'PDF' 글자 자리 x0, x1, y0, y1
RED_REF = (231, 47, 45)                             # 앞장 바탕 빨강(가운데 줄)
WHITE = (255, 255, 255, 255)
# 디자인 SOT §4.7 표 — 바탕 색은 icons.py 토큰과 같은 값(ACCENT["play"] 라이트·FILE_KIND_COLOR["HEIC"] 라이트)
ICONS = {"polypix": ((0x15, 0x65, 0xc0), "mountains"),
         "polycardex": ((0x7b, 0x3f, 0xb3), "person")}


def _erase_text(im: Image.Image) -> Image.Image:
    a = np.array(im).astype(float)
    x0, x1, y0, y1 = TEXT_BOX
    l, r = x0 - 8, x1 + 8
    for y in range(y0 - 6, y1 + 7):
        cl, cr = a[y, l, :3], a[y, r, :3]
        t = (np.arange(l + 1, r) - l) / (r - l)
        a[y, l + 1:r, :3] = cl[None, :] * (1 - t[:, None]) + cr[None, :] * t[:, None]
    return Image.fromarray(a.astype(np.uint8), "RGBA")


BACK_TEXT = (459, 479, 198, 238)                    # 뒷장에 비친 'F' 조각 자리 x0, x1, y0, y1 — 지휘 점검(261120-16)


def _erase_back_text(im: Image.Image) -> Image.Image:
    """뒷장 오른쪽 가장자리에 비친 원본 글자 조각('F')을 메운다. 획이 왼쪽 옅은 테두리에 붙어 있어,
    테두리 끝선은 조각 **위·아래 줄**에서 재서 잇고(그 왼쪽은 그대로), 끝선 오른쪽의 밝은 획(흰·분홍 — 바탕 빨강은
    초록 성분이 낮다)은 같은 x 의 위·아래 바탕색을 세로로 이어 메운다."""
    a = np.array(im).astype(float)
    x0, x1, y0, y1 = BACK_TEXT
    yt, yb = y0 - 2, y1 + 1

    def red(x, y):
        return a[y, x, 1] < 70 and a[y, x, 0] > 110

    def edge(y):                                     # 그 줄에서 테두리가 끝나고 빨강이 시작하는 x
        x = x0 - 12
        while x < x1 and not red(x, y):
            x += 1
        return x

    et, eb = edge(yt), edge(yb)
    for y in range(y0, y1):
        t = (y - yt) / (yb - yt)
        e = int(round(et * (1 - t) + eb * t)) - 1        # 획 둘레의 어두운 윤곽까지 — 조각 범위 안은 모두 잇는다
        for x in range(e, x1):
            a[y, x, :3] = a[yt, x, :3] * (1 - t) + a[yb, x, :3] * t
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def _recolor(im: Image.Image, target) -> Image.Image:
    rgb = im.convert("RGB")
    h, s, v = [np.array(ch).astype(float) / 255 for ch in rgb.convert("HSV").split()]
    th, ts, tv = colorsys.rgb_to_hsv(*(c / 255 for c in target))
    rh, rs, rv = colorsys.rgb_to_hsv(*(c / 255 for c in RED_REF))
    dist = np.minimum(np.abs(h - rh), 1 - np.abs(h - rh))
    w = np.clip((s - 0.12) / 0.3, 0, 1) * np.clip((0.12 - dist) / 0.06, 0, 1)     # 빨강 계열일수록 1
    hsv = [(h + (th - rh)) % 1.0, np.clip(s * ts / rs, 0, 1), np.clip(v * tv / rv, 0, 1)]
    rec = np.array(Image.merge("HSV", [Image.fromarray((np.clip(c, 0, 1) * 255).astype(np.uint8)) for c in hsv])
                   .convert("RGB")).astype(float)
    mix = np.array(rgb).astype(float) * (1 - w[..., None]) + rec * w[..., None]
    out = Image.fromarray(mix.astype(np.uint8), "RGB").convert("RGBA")
    out.putalpha(im.getchannel("A"))
    return out


def _mountains(d: ImageDraw.ImageDraw) -> None:
    x0, x1, base = 112, 338, 322
    d.polygon([(x0, base), (x0 + 96, 150), (x0 + 192, base)], fill=WHITE)
    d.polygon([(x0 + 112, base), (x1 - 60, 196), (x1, base)], fill=WHITE)


def _person(d: ImageDraw.ImageDraw) -> None:
    cx = (TEXT_BOX[0] + TEXT_BOX[1]) / 2
    top, r, sw, sh = 140, 48, 108, 94
    d.ellipse((cx - r, top, cx + r, top + 2 * r), fill=WHITE)
    d.pieslice((cx - sw, top + 2 * r + 10, cx + sw, top + 2 * r + 10 + 2 * sh), 180, 360, fill=WHITE)


def render(name: str) -> Image.Image:
    """icon.png 꼴의 `name` 아이콘(533×468 RGBA)."""
    color, glyph = ICONS[name]
    im = _recolor(_erase_back_text(_erase_text(Image.open(os.path.join(RES, "icon.png")).convert("RGBA"))), color)
    (_mountains if glyph == "mountains" else _person)(ImageDraw.Draw(im))
    return im


def square(im: Image.Image) -> Image.Image:
    """위아래를 투명하게 채워 정사각으로 — ico 의 각 크기가 16×16·32×32 … 가 되게(바로가기·탐색기 아이콘 칸)."""
    n = max(im.size)
    c = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    c.paste(im, ((n - im.width) // 2, (n - im.height) // 2), im)
    return c


def main() -> int:
    for name in ICONS:
        im = square(render(name))
        png = os.path.join(RES, name + ".png")
        im.save(png, "PNG")
        im.save(os.path.join(RES, name + ".ico"), format="ICO", sizes=[(s, s) for s in SIZES])
        print("ok", png)
    return 0


if __name__ == "__main__":
    sys.exit(main())
