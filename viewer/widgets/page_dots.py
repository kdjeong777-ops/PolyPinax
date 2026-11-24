"""쪽 점 표시 — 작은 원 n개, 지금 쪽은 채운 원·나머지는 빈 원, 누르면 그 쪽(디자인 SOT §4.5 '쪽 점', 261117-57).

여러 장 중 몇째를 보는지 보이는 곳이면 이것을 다시 쓴다(명함찾기 사진창 앞·뒷면 — 명함찾기 SOT §5.24.3).
색은 팔레트(강조색·mid)라 라이트·다크 테마를 따른다. 한 장뿐이면 숨는다.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QPen
from PyQt6.QtWidgets import QWidget


class PageDots(QWidget):
    """쪽 점 표시 — 쪽마다 작은 원, 지금 쪽은 채운 원·나머지는 빈 원, 누르면 그 쪽(`picked(i)`)."""
    picked = pyqtSignal(int)
    D = 7                                   # 원 지름(px)
    GAP = 6                                 # 원 사이

    def __init__(self, parent=None):
        super().__init__(parent)
        self.count, self.current = 1, 0
        self.setFixedHeight(self.D + 6)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_state(self, count: int, current: int):
        self.count, self.current = max(1, int(count)), max(0, min(int(current), max(1, int(count)) - 1))
        self.setFixedWidth(self.count * self.D + (self.count - 1) * self.GAP + 4)
        self.setVisible(self.count > 1)                  # 한 면뿐이면 숨김
        self.update()

    def dot_center(self, i: int) -> QPointF:
        return QPointF(2 + i * (self.D + self.GAP) + self.D / 2, self.height() / 2)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pal = self.palette()
        for i in range(self.count):
            c = self.dot_center(i)
            r = QRectF(c.x() - self.D / 2 + 0.5, c.y() - self.D / 2 + 0.5, self.D - 1, self.D - 1)
            if i == self.current:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(pal.highlight())
            else:
                p.setPen(QPen(pal.mid().color(), 1.2))
                p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(r)
        p.end()

    def mousePressEvent(self, e):
        x = e.position().x()
        for i in range(self.count):
            if abs(x - self.dot_center(i).x()) <= (self.D + self.GAP) / 2:
                if i != self.current:
                    self.picked.emit(i)
                return
