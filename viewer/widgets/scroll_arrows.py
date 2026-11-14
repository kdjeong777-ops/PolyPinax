# -*- coding: utf-8 -*-
"""다크 테마 스크롤바 화살표를 밝게 — 앱 스타일 한 곳 (261115-2, 사용자 지시 — 화면 디자인 SOT §2.5 '스크롤바 화살표').

Fusion 은 스크롤바 ▲▼(가로 ◀▶) 화살표를 글자색 알파 160 으로 그려, 다크 바탕(밝기 77)에서 밝기 166 으로 묻혔다.
다크일 때만 Fusion 이 그린 뒤 그 자리에 꽉 찬 삼각형을 덧그린다(토큰 `ARROW`). 라이트는 Fusion 그대로.
위젯마다 스타일시트로 덮지 않는다 — 앱 스타일이라 모든 목록·창·대화상자의 스크롤바가 같은 결과.
"""
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPolygonF
from PyQt6.QtWidgets import QStyle, QStyleOptionSlider

from viewer.widgets.keycaps import KeycapMenuStyle

ARROW = {"normal": "#e8e8e8", "hover": "#ffffff", "pressed": "#ffffff", "disabled": "#808080"}   # 다크 — §2.5
ARROW_W = 0.5          # 삼각형 밑변 = 단추 짧은 변 × 이 값
ARROW_H = 0.3          # 높이 = 짧은 변 × 이 값


def arrow_color(opt, sc) -> QColor:
    """그 단추(위/아래)의 상태에 맞는 다크 화살표 색."""
    st = opt.state
    if not (st & QStyle.StateFlag.State_Enabled):
        return QColor(ARROW["disabled"])
    active = bool(opt.activeSubControls & sc)
    if active and (st & QStyle.StateFlag.State_Sunken):
        return QColor(ARROW["pressed"])
    if active and (st & QStyle.StateFlag.State_MouseOver):
        return QColor(ARROW["hover"])
    return QColor(ARROW["normal"])


def _triangle(r, direction) -> QPolygonF:
    """r 가운데의 꽉 찬 삼각형 — direction 'up'·'down'·'left'·'right'."""
    s = min(r.width(), r.height())
    w, h = s * ARROW_W, s * ARROW_H
    cx, cy = r.x() + r.width() / 2.0, r.y() + r.height() / 2.0
    if direction == "up":
        pts = [(cx - w / 2, cy + h / 2), (cx + w / 2, cy + h / 2), (cx, cy - h / 2)]
    elif direction == "down":
        pts = [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2), (cx, cy + h / 2)]
    elif direction == "left":
        pts = [(cx + h / 2, cy - w / 2), (cx + h / 2, cy + w / 2), (cx - h / 2, cy)]
    else:
        pts = [(cx - h / 2, cy - w / 2), (cx - h / 2, cy + w / 2), (cx + h / 2, cy)]
    return QPolygonF([QPointF(x, y) for x, y in pts])


class ScrollArrowStyle(KeycapMenuStyle):
    """앱 스타일 — 키캡 메뉴(디자인 SOT §2.9.2) + 다크 스크롤바 화살표(§2.5)."""

    def drawComplexControl(self, cc, opt, p, w=None):
        super().drawComplexControl(cc, opt, p, w)
        if cc != QStyle.ComplexControl.CC_ScrollBar or not isinstance(opt, QStyleOptionSlider):
            return
        from viewer import theme
        if not theme.is_dark():
            return
        vert = opt.orientation == Qt.Orientation.Vertical
        rtl = opt.direction == Qt.LayoutDirection.RightToLeft
        for sc, d in ((QStyle.SubControl.SC_ScrollBarSubLine, "up" if vert else ("right" if rtl else "left")),
                      (QStyle.SubControl.SC_ScrollBarAddLine, "down" if vert else ("left" if rtl else "right"))):
            r = self.subControlRect(cc, opt, sc, w)
            if r.isEmpty() or not (opt.subControls & sc):
                continue
            p.save()
            p.setRenderHint(p.RenderHint.Antialiasing, True)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(arrow_color(opt, sc))
            p.drawPolygon(_triangle(r.adjusted(1, 1, -1, -1), d))
            p.restore()
