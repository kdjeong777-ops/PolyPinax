# -*- coding: utf-8 -*-
"""윈도우 내장 얼굴 찾기(Windows.Media.FaceAnalysis, winrt) — 공용 모듈(명함 얼굴 썸네일·사진 인물 태그가 함께 씀, 261122-18).

완전 오프라인(윈도우가 가진 것만). Qt·명함·사진 모듈을 import 하지 않는다 — `win_ocr.py` 와 같은 중립 자리.
- `available()` — 이 PC 에서 쓸 수 있나(winrt 가져오기·`FaceDetector.is_supported`). 한 번 알아보고 기억한다(이 실행 내내).
- `detect(img)` — PIL 그림 → 얼굴 상자 [(x, y, w, h)](그림 좌표). **얼굴이 없으면 `[]`, 못 썼으면 `None`**
  (쓸 수 없는 PC·그 그림만의 일시 오류). 일시 오류를 몇 번까지 참을지는 **부르는 쪽이 저마다** 센다(공용 카운터 없음 —
  명함 썸네일과 사진 인물 태그가 서로의 오류로 꺼지지 않게).
배경 스레드에서 부른다(`asyncio.run` — 돌고 있는 이벤트 루프 없음). 찾는 객체는 스레드마다 하나.
"""
from __future__ import annotations

import threading

DETECT_MAX = 1024             # 얼굴 찾기에 넣는 그림 긴 변(빠르게)
_state = {"tried": False, "ok": False}
_local = threading.local()


def available() -> bool:
    """이 PC 에서 얼굴 찾기를 쓸 수 있나 — 처음 한 번 알아보고 기억."""
    if not _state["tried"]:
        _state["tried"] = True
        try:
            from winrt.windows.media.faceanalysis import FaceDetector
            _state["ok"] = bool(FaceDetector.is_supported)
        except Exception:                                 # winrt 가 없거나 이 윈도우가 지원하지 않음
            _state["ok"] = False
    return _state["ok"]


def detect(img, max_side: int = DETECT_MAX):
    """얼굴 상자 목록 — 없으면 [], 못 썼으면 None(쓸 수 없는 PC·일시 오류)."""
    if not available():
        return None
    try:
        import asyncio
        from winrt.windows.media.faceanalysis import FaceDetector
        from winrt.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat
        from winrt.windows.storage.streams import Buffer
        g = img.convert("L")
        scale = 1.0
        if max(g.size) > max_side:
            scale = max_side / float(max(g.size))
            g = g.resize((max(1, int(g.width * scale)), max(1, int(g.height * scale))))
        raw = g.tobytes()
        buf = Buffer(len(raw))
        buf.length = len(raw)
        memoryview(buf)[:] = raw
        bmp = SoftwareBitmap.create_copy_from_buffer(buf, BitmapPixelFormat.GRAY8, g.width, g.height)

        async def _go():
            det = getattr(_local, "detector", None)
            if det is None:
                det = _local.detector = await FaceDetector.create_async()
            return await det.detect_faces_async(bmp)
        res = asyncio.run(_go())
        return [(f.face_box.x / scale, f.face_box.y / scale, f.face_box.width / scale, f.face_box.height / scale) for f in res]
    except Exception:                                     # 그 그림만의 일시 오류 — 부르는 쪽이 센다
        return None
