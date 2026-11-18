# -*- coding: utf-8 -*-
"""보조 OCR 엔진 — Windows 내장 OCR(`Windows.Media.Ocr`, 한국어 `ko`). 명함 인식만 쓴다(단어학습 SOT §14.25).

기기 안에서만 읽는다(외부 전송 없음). Windows 가 아니거나·winrt 꾸러미가 없거나·한국어 OCR 언어가 없으면
`available()` 이 False — 부르는 쪽은 Tesseract 만 쓴다.
"""
import asyncio
import hashlib
import sys
import threading
from collections import OrderedDict

LANG = "ko"
_MEMO_MAX = 8            # 같은 그림을 여러 번 읽는 일(이름 덧읽기 등)이 있어 최근 몇 장만 기억

_lock = threading.Lock()
_state = {"checked": False, "ok": False}
_memo: "OrderedDict[str, list]" = OrderedDict()


def _mods():
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.globalization import Language
    from winrt.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat
    from winrt.windows.storage.streams import Buffer
    return OcrEngine, Language, SoftwareBitmap, BitmapPixelFormat, Buffer


def available() -> bool:
    """쓸 수 있나(한 번 재고 기억). 배경 스레드에서 부른다."""
    with _lock:
        if _state["checked"]:
            return _state["ok"]
        ok = False
        if sys.platform == "win32":
            try:
                OcrEngine, Language, *_ = _mods()
                langs = [str(l.language_tag).lower() for l in OcrEngine.available_recognizer_languages]
                ok = any(t == LANG or t.startswith(LANG + "-") for t in langs) and \
                    OcrEngine.try_create_from_language(Language(LANG)) is not None
            except Exception:
                ok = False
        _state.update(checked=True, ok=ok)
        return ok


def reset_cache() -> None:
    """검사·언어 설치 뒤 다시 재게."""
    with _lock:
        _state.update(checked=False, ok=False)
        _memo.clear()


def read(gray) -> list:
    """회색조 PIL 그림 → [(줄 글, [(x, y, w, h), …낱말 상자])] (그림 픽셀 좌표). 못 읽으면 []."""
    if not available():
        return []
    key = hashlib.md5(gray.tobytes()).hexdigest() + "|%dx%d" % gray.size
    with _lock:
        if key in _memo:
            _memo.move_to_end(key)
            return _memo[key]
    try:
        out = _read(gray)
    except Exception:
        out = []
    with _lock:
        _memo[key] = out
        while len(_memo) > _MEMO_MAX:
            _memo.popitem(last=False)
    return out


def _read(gray) -> list:
    OcrEngine, Language, SoftwareBitmap, BitmapPixelFormat, Buffer = _mods()
    g = gray.convert("L")
    lim = int(OcrEngine.max_image_dimension or 0)
    scale = 1.0
    if lim and max(g.size) > lim:
        scale = lim / float(max(g.size))
        g = g.resize((max(1, int(g.width * scale)), max(1, int(g.height * scale))))
    raw = g.tobytes()
    buf = Buffer(len(raw))
    buf.length = len(raw)
    memoryview(buf)[:] = raw
    bmp = SoftwareBitmap.create_copy_from_buffer(buf, BitmapPixelFormat.GRAY8, g.width, g.height)
    eng = OcrEngine.try_create_from_language(Language(LANG))

    async def _go():
        return await eng.recognize_async(bmp)
    res = asyncio.run(_go())                           # 배경 스레드(돌고 있는 이벤트 루프 없음)
    out = []
    for ln in res.lines:
        boxes = []
        for w in ln.words:
            r = w.bounding_rect
            boxes.append((r.x / scale, r.y / scale, r.width / scale, r.height / scale))
        if boxes:
            out.append((str(ln.text), boxes))
    return out
