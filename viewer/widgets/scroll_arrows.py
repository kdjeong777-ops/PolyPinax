# -*- coding: utf-8 -*-
"""다크 테마 스크롤바 화살표를 밝게 — 앱 스타일 한 곳 (261115-2, 사용자 지시 — 화면 디자인 SOT §2.5 '스크롤바 화살표').

Fusion 은 스크롤바 ▲▼(가로 ◀▶) 화살표를 글자색 알파 160 으로 그려, 다크 바탕(밝기 77)에서 밝기 166 으로 묻혔다.
다크일 때만 Fusion 이 그린 뒤 그 자리에 꽉 찬 삼각형을 덧그린다(토큰 `ARROW`). 라이트는 Fusion 그대로.
위젯마다 스타일시트로 덮지 않는다 — 앱 스타일이라 모든 목록·창·대화상자의 스크롤바가 같은 결과.
261128-5(§2.4·§2.5): 다크 스크롤바 손잡이를 `THUMB` 회색으로 덧칠하고, 창 나눔 손잡이(`CE_Splitter`)는 두 테마 모두 둥근 점 3개(`GRIP`).
"""
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPolygonF
from PyQt6.QtWidgets import QStyle, QStyleOptionSlider

from viewer.widgets.keycaps import KeycapMenuStyle

ARROW = {"normal": "#e8e8e8", "hover": "#ffffff", "pressed": "#ffffff", "disabled": "#808080"}   # 다크 — §2.5
ARROW_W = 0.5          # 삼각형 밑변 = 단추 짧은 변 × 이 값
ARROW_H = 0.3          # 높이 = 짧은 변 × 이 값
# 261128-5(디자인 SOT §2.4·§2.5): 다크 스크롤바 손잡이(종전 단추색 #2d2d30 이라 묻힘) · 창 나눔 손잡이 점 3개(두 테마)
THUMB = {"normal": "#6e6e6e", "hover": "#808080", "pressed": "#8c8c8c"}          # 다크만 — 라이트는 Fusion 그대로
GRIP = {"dark": {"normal": "#6e6e6e", "hover": "#9a9a9a"},
        "light": {"normal": "#6e6e6e", "hover": "#4a4a4a"}}
GRIP_D = 4             # 점 지름(막대 짧은 변이 더 작으면 그만큼)
GRIP_GAP = 3           # 점 사이 빈칸


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


def thumb_color(opt) -> QColor:
    """다크 스크롤바 손잡이 색 — 그 손잡이가 눌림·가리킴인지 보고."""
    active = bool(opt.activeSubControls & QStyle.SubControl.SC_ScrollBarSlider)
    if active and (opt.state & QStyle.StateFlag.State_Sunken):
        return QColor(THUMB["pressed"])
    if active and (opt.state & QStyle.StateFlag.State_MouseOver):
        return QColor(THUMB["hover"])
    return QColor(THUMB["normal"])


def grip_dots(r, bar_vertical: bool):
    """창 나눔 막대 r 가운데의 점 3개 사각형(x, y, d) — 막대 방향으로 늘어선다(§2.4)."""
    short = r.width() if bar_vertical else r.height()
    d = max(1, min(GRIP_D, short))
    step = d + GRIP_GAP
    cx, cy = r.x() + r.width() / 2.0, r.y() + r.height() / 2.0
    out = []
    for k in (-1, 0, 1):
        x = cx - d / 2.0 + (0 if bar_vertical else k * step)
        y = cy - d / 2.0 + (k * step if bar_vertical else 0)
        out.append((int(round(x)), int(round(y)), d))
    return out


class ScrollArrowStyle(KeycapMenuStyle):
    """앱 스타일 — 키캡 메뉴(디자인 SOT §2.9.2) + 다크 스크롤바 화살표·손잡이(§2.5) + 창 나눔 손잡이 점 3개(§2.4)."""

    def drawControl(self, ce, opt, p, w=None):
        if ce != QStyle.ControlElement.CE_Splitter:
            return super().drawControl(ce, opt, p, w)
        # 261128-5: Fusion 의 작은 점 6개(밝고 어두운 음영) 대신 둥근 점 3개 — 스크롤 손잡이와 다른 꼴
        from viewer import theme
        tok = GRIP["dark" if theme.is_dark() else "light"]
        hot = bool(opt.state & QStyle.StateFlag.State_MouseOver)
        # QSplitterHandle 은 가로 splitter(세로 막대)일 때 State_Horizontal 을 켠다
        bar_vertical = bool(opt.state & QStyle.StateFlag.State_Horizontal)
        r = opt.rect
        if r.width() <= 1 or r.height() <= 1:
            return
        p.save()
        p.setRenderHint(p.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(tok["hover" if hot else "normal"]))
        for x, y, d in grip_dots(r, bar_vertical):
            p.drawEllipse(x, y, d, d)
        p.restore()

    def drawComplexControl(self, cc, opt, p, w=None):
        super().drawComplexControl(cc, opt, p, w)
        if cc != QStyle.ComplexControl.CC_ScrollBar or not isinstance(opt, QStyleOptionSlider):
            return
        from viewer import theme
        if not theme.is_dark():
            return
        sr = self.subControlRect(cc, opt, QStyle.SubControl.SC_ScrollBarSlider, w)
        if (not sr.isEmpty() and (opt.subControls & QStyle.SubControl.SC_ScrollBarSlider)
                and (opt.state & QStyle.StateFlag.State_Enabled) and opt.maximum > opt.minimum):
            p.save()                                  # 261128-5: 다크 손잡이 — 단추색이라 묻혔다(§2.5 '스크롤바 손잡이')
            p.setRenderHint(p.RenderHint.Antialiasing, True)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(thumb_color(opt))
            p.drawRoundedRect(sr.adjusted(1, 1, -1, -1).toRectF(), 3, 3)
            p.restore()
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
