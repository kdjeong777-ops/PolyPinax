"""전역 테마 상태(다크/라이트) — 위젯·픽스맵 렌더가 색을 맞추도록 공유 (260606-14)."""
from __future__ import annotations

_DARK = False


def set_dark(on: bool) -> None:
    global _DARK
    _DARK = bool(on)


def is_dark() -> bool:
    return _DARK


# 디자인 SOT §2.5 '태그 켜짐' — `#` 거르기 단추(주 창 파일 목록·명함찾기, §2.7) 켜졌을 때 (바탕, 글자). 키 = 다크 여부
TAG_ACTIVE = {False: ("#e3efff", "#1456c4"), True: ("#1456c4", "#ffffff")}


def tag_button_style(active: bool) -> str:
    """`#` 거르기 단추 스타일 — 켜지면 테마별 바탕·글자 한 쌍 + 굵게, 꺼지면 테마 기본(빈 글)."""
    if not active:
        return ""
    bg, fg = TAG_ACTIVE[bool(_DARK)]
    return "QPushButton{background:%s;color:%s;font-weight:bold;}" % (bg, fg)
