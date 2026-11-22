# -*- coding: utf-8 -*-
"""명함 얼굴 썸네일 (명함 SOT §5.24.2 '즐겨찾기 줄'·§5.24.1 '목록 표 얼굴', 261120-76) — Qt 없음, 배경 일꾼이 부른다.

① 인물 사진 — 얼굴이 있으면 그 얼굴만(윈도우 내장 얼굴 찾기, 완전 오프라인), 없으면 중요 부분(테두리가 많은 곳) 정사각
② 인물 사진이 없으면 명함 앞면 가운데 정사각(종전 그대로)
결과는 로컬 데이터 폴더 `bizcard_faces/` 에 SIZE px JPG 로 남긴다 — 열쇠 = 사진 경로·크기·고친 시각·판.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

SIZE = 96                     # 캐시 그림 한 변(목록 풍선 FACE_TIP 과 같게)
VERSION = 1                   # 자르는 법을 바꾸면 올린다(옛 캐시는 쓰지 않음)
DETECT_MAX = 1024             # 얼굴 찾기에 넣는 그림 긴 변(빠르게)
HEAD_ROOM = 0.35              # 얼굴 상자 위로 더하는 여백(상자 높이 비율)
FACE_PAD = 1.7                # 얼굴 상자 → 정사각 한 변(얼굴 상자 긴 변의 배수)
_detector = None
_no_detector = False


def cache_dir() -> Path:
    from viewer import settings_store
    d = Path(settings_store.local_data_dir()) / "bizcard_faces"
    d.mkdir(parents=True, exist_ok=True)
    return d


def source(card, folder) -> tuple:
    """(그림 경로, 명함 그림인가) — 첫 인물 사진, 없으면 정리본 앞면(그림 명함), 둘 다 없으면 ('', False)."""
    from viewer.bizcard import people as P
    from viewer.bizcard.vcard import is_contact
    pf = P.photo_front(card, folder)
    photos = P.person_photos(pf) if pf else []
    if photos:
        return photos[0], False
    f = card.get("front") or ""
    if f and not is_contact(card) and os.path.exists(f):
        return f, True
    return "", False


def _key(path, from_card) -> str:
    st = os.stat(path)
    raw = "%s|%d|%d|%d|%d" % (os.path.normcase(os.path.abspath(path)), st.st_size, st.st_mtime_ns, int(bool(from_card)), VERSION)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def cached(path, from_card=False) -> str:
    """캐시가 있으면 그 경로, 없으면 ''(계산하지 않음 — 메인이 부른다)."""
    try:
        p = cache_dir() / (_key(path, from_card) + ".jpg")
    except OSError:
        return ""
    return str(p) if p.exists() else ""


def faces(img) -> list:
    """윈도우 얼굴 찾기 — [(x, y, w, h)](그림 좌표). 못 쓰면 []."""
    global _detector, _no_detector
    if _no_detector:
        return []
    try:
        import asyncio
        from winrt.windows.media.faceanalysis import FaceDetector
        from winrt.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat
        from winrt.windows.storage.streams import Buffer
        if not FaceDetector.is_supported:
            _no_detector = True
            return []
        g = img.convert("L")
        scale = 1.0
        if max(g.size) > DETECT_MAX:
            scale = DETECT_MAX / float(max(g.size))
            g = g.resize((max(1, int(g.width * scale)), max(1, int(g.height * scale))))
        raw = g.tobytes()
        buf = Buffer(len(raw))
        buf.length = len(raw)
        memoryview(buf)[:] = raw
        bmp = SoftwareBitmap.create_copy_from_buffer(buf, BitmapPixelFormat.GRAY8, g.width, g.height)

        async def _go():
            global _detector
            if _detector is None:
                _detector = await FaceDetector.create_async()
            return await _detector.detect_faces_async(bmp)
        res = asyncio.run(_go())                         # 배경 스레드(돌고 있는 이벤트 루프 없음)
        return [(f.face_box.x / scale, f.face_box.y / scale, f.face_box.width / scale, f.face_box.height / scale) for f in res]
    except Exception:
        _no_detector = True
        return []


def face_box(img, boxes) -> tuple:
    """가장 큰 얼굴 → 정사각(머리 위 여백 조금) (l, t, r, b), 그림 안으로."""
    x, y, w, h = max(boxes, key=lambda b: b[2] * b[3])
    side = min(max(w, h) * FACE_PAD, min(img.size))
    cx, cy = x + w / 2.0, y + h / 2.0 - h * (HEAD_ROOM - 0.25)
    return _clamp(cx - side / 2, cy - side / 2, side, img.size)


def salient_box(img) -> tuple:
    """중요 부분 — 테두리(밝기 변화)가 가장 많은 정사각, 사진은 위쪽 가운데로 조금 치우쳐(사람이 있을 자리)."""
    import numpy as np
    from PIL import ImageFilter
    side = min(img.size)
    if img.width == img.height:
        return (0, 0, side, side)
    small = 128.0 / max(img.size)
    g = img.convert("L").resize((max(1, int(img.width * small)), max(1, int(img.height * small))))
    e = np.asarray(g.filter(ImageFilter.FIND_EDGES), dtype=np.float64)
    s = max(1, int(round(side * small)))
    ii = np.pad(e.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    H, W = e.shape
    best, bx, by = -1.0, 0, 0
    for yy in range(0, max(1, H - s + 1)):
        for xx in range(0, max(1, W - s + 1)):
            v = ii[yy + s, xx + s] - ii[yy, xx + s] - ii[yy + s, xx] + ii[yy, xx]
            # 치우침 — 가로는 가운데, 세로는 위쪽(1/3)일수록 조금 더
            cx = (xx + s / 2.0) / W - 0.5
            cy = (yy + s / 2.0) / H - 0.38
            v *= 1.0 - 0.6 * (cx * cx + cy * cy)
            if v > best:
                best, bx, by = v, xx, yy
    return _clamp(bx / small, by / small, side, img.size)


def _clamp(l, t, side, size) -> tuple:
    W, H = size
    side = min(side, W, H)
    l = max(0.0, min(l, W - side))
    t = max(0.0, min(t, H - side))
    return (int(l), int(t), int(l + side), int(t + side))


def crop(path, from_card=False):
    """썸네일 그림(PIL, SIZE 정사각)."""
    from PIL import Image, ImageOps
    with Image.open(path) as im0:
        im = ImageOps.exif_transpose(im0).convert("RGB")
    if from_card:                                         # 명함 앞면 — 가운데 정사각(종전 그대로)
        side = min(im.size)
        box = ((im.width - side) // 2, (im.height - side) // 2, (im.width - side) // 2 + side, (im.height - side) // 2 + side)
    else:
        fs = faces(im)
        box = face_box(im, fs) if fs else salient_box(im)
    return im.crop(box).resize((SIZE, SIZE), Image.LANCZOS)


def thumb(path, from_card=False) -> str:
    """캐시 경로 — 없으면 만들어 둔다(배경에서 부른다). 실패면 ''."""
    if not path or not os.path.exists(path):
        return ""
    try:
        out = cache_dir() / (_key(path, from_card) + ".jpg")
        if not out.exists():
            im = crop(path, from_card)
            tmp = out.with_suffix(".part")
            im.save(tmp, "JPEG", quality=90)
            os.replace(tmp, out)
        return str(out)
    except Exception:
        return ""
