"""다중 명함 나누기 확인 창 (명함 SOT §5.26, D31).

찾은 명함 테두리를 사진 위에 보이고, 사람이 고친다 — 테두리를 눌러 고르고 Delete 로 빼기, 빈 곳을 끌어 새 테두리 그리기.
사진마다 체크(나눌지). 계산·자르기는 `multisplit`·`importer.SplitWorker`(배경), 이 창은 고르기만.
★ 명함 글·경로는 로그에 싣지 않는다(§2.1).
"""
from __future__ import annotations

import os

from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import QImage, QPainter, QPen, QColor, QPolygonF
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QSplitter, QWidget, QSizePolicy)

from viewer.i18n import tr

ROLE = Qt.ItemDataRole.UserRole
MIN_DRAG = 12                     # 이보다 작게 끈 것은 새 테두리로 보지 않음(화면 px)


class BoxView(QWidget):
    """사진 + 명함 테두리(원래 해상도 좌표). 누르면 고르기, 빈 곳 끌기 = 새 테두리, Delete = 빼기."""
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(320, 320)
        self.img = QImage()
        self.full = (1, 1)
        self.quads = []
        self.sel = -1
        self._drag = None

    def set_photo(self, img: QImage, full, quads):
        self.img, self.full, self.quads, self.sel = img, tuple(full), [list(map(list, q)) for q in quads], -1
        self.update()

    # 좌표 — 화면 ↔ 원래 해상도
    def _frame(self):
        if self.img.isNull():
            return 1.0, 0.0, 0.0
        s = min(self.width() / self.full[0], self.height() / self.full[1])
        ox = (self.width() - self.full[0] * s) / 2
        oy = (self.height() - self.full[1] * s) / 2
        return s, ox, oy

    def to_screen(self, x, y):
        s, ox, oy = self._frame()
        return QPointF(ox + x * s, oy + y * s)

    def to_image(self, p):
        s, ox, oy = self._frame()
        return ((p.x() - ox) / s, (p.y() - oy) / s)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), self.palette().window())
        if self.img.isNull():
            p.end()
            return
        s, ox, oy = self._frame()
        p.drawImage(QRectF(ox, oy, self.full[0] * s, self.full[1] * s), self.img)
        for i, q in enumerate(self.quads):
            pen = QPen(QColor(self.palette().highlight().color()) if i == self.sel else QColor(220, 40, 40), 3)
            p.setPen(pen)
            p.drawPolygon(QPolygonF([self.to_screen(x, y) for x, y in q]))
            p.drawText(self.to_screen(*q[0]) + QPointF(6, 18), str(i + 1))
        if self._drag is not None:
            p.setPen(QPen(QColor(self.palette().highlight().color()), 2, Qt.PenStyle.DashLine))
            p.drawRect(QRectF(self._drag[0], self._drag[1]).normalized())
        p.end()

    def _hit(self, pt):
        for i in range(len(self.quads) - 1, -1, -1):
            if QPolygonF([self.to_screen(x, y) for x, y in self.quads[i]]).containsPoint(pt, Qt.FillRule.OddEvenFill):
                return i
        return -1

    def mousePressEvent(self, e):
        self.setFocus()
        if e.button() != Qt.MouseButton.LeftButton:
            return
        i = self._hit(e.position())
        if i >= 0:
            self.sel = i
            self.update()
            return
        self.sel = -1
        self._drag = [e.position(), e.position()]
        self.update()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self._drag[1] = e.position()
            self.update()

    def mouseReleaseEvent(self, e):
        if self._drag is None:
            return
        a, b = self._drag
        self._drag = None
        if abs(a.x() - b.x()) >= MIN_DRAG and abs(a.y() - b.y()) >= MIN_DRAG:
            (x0, y0), (x1, y1) = self.to_image(a), self.to_image(b)
            x0, x1 = sorted((max(0.0, min(self.full[0], x0)), max(0.0, min(self.full[0], x1))))
            y0, y1 = sorted((max(0.0, min(self.full[1], y0)), max(0.0, min(self.full[1], y1))))
            self.quads.append([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
            self.sel = len(self.quads) - 1
            self.changed.emit()
        self.update()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and 0 <= self.sel < len(self.quads):
            del self.quads[self.sel]
            self.sel = -1
            self.changed.emit()
            self.update()
            return
        super().keyPressEvent(e)


class MultiSplitDialog(QDialog):
    """found = [(경로, 모서리들(원래 해상도), {'size','rgb','pv'})] → 확인 뒤 `jobs`(나눌 것)·`skipped`(나누지 않기로 한 사진)."""

    def __init__(self, found, parent=None, old_counts=None):
        super().__init__(parent)
        self.setWindowTitle(tr("다중 명함 나누기"))
        self.resize(1100, 760)
        self._found = [(p, [list(map(list, q)) for q in qs], pv) for p, qs, pv in found]
        self.jobs, self.skipped = [], []
        old_counts = old_counts or {}
        v = QVBoxLayout(self)
        n_cards = sum(len(q) for _p, q, _v in self._found)
        k_old = sum(1 for p, _q, _v in self._found if old_counts.get(p))
        self.lbl = QLabel(tr("사진 {n}장에서 명함 {m}장을 찾았습니다 — 체크한 사진을 명함마다 잘라 따로 읽습니다. 원본은 '다중 원본' 폴더로 옮깁니다.").format(
            n=len(self._found), m=n_cards)
            + ("\n" + tr("이미 한 장으로 들어간 명함 {k}장은 지웁니다(휴지통).").format(k=k_old) if k_old else ""))
        self.lbl.setWordWrap(True)
        v.addWidget(self.lbl)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.list = QListWidget()
        self.view = BoxView()
        split.addWidget(self.list)
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(self.view, 1)
        hint = QLabel(tr("테두리를 눌러 고른 뒤 Delete 로 빼고, 빈 곳을 끌어 새 테두리를 그립니다."))
        hint.setWordWrap(True)
        rv.addWidget(hint)
        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 4)
        v.addWidget(split, 1)
        for i, (p, qs, _pv) in enumerate(self._found):
            it = QListWidgetItem()
            it.setData(ROLE, i)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if len(qs) >= 2 else Qt.CheckState.Unchecked)
            self.list.addItem(it)
            self._label(i)
        self.list.currentRowChanged.connect(self._show)
        self.view.changed.connect(self._view_changed)
        bot = QHBoxLayout()
        bot.addStretch(1)
        self.btn_ok = QPushButton(tr("나누기"))
        self.btn_ok.clicked.connect(lambda _c=False: self.accept_split())
        b_no = QPushButton(tr("나누지 않음"))
        b_no.setToolTip(tr("이 사진들은 나누지 않고 한 장으로 둡니다(다음에 다시 묻지 않음 — 다시 나누려면 [다중 명함 나누기])"))
        b_no.clicked.connect(lambda _c=False: self.reject_all())
        bot.addWidget(self.btn_ok)
        bot.addWidget(b_no)
        v.addLayout(bot)
        if self._found:
            self.list.setCurrentRow(0)

    def _label(self, i):
        p, qs, _pv = self._found[i]
        self.list.item(i).setText("%s  (%s)" % (os.path.basename(p), tr("{n}장").format(n=len(qs))))

    def _show(self, i):
        if not (0 <= i < len(self._found)):
            return
        p, qs, pv = self._found[i]
        img = QImage(pv["rgb"], pv["pv"][0], pv["pv"][1], 3 * pv["pv"][0], QImage.Format.Format_RGB888).copy()
        self.view.set_photo(img, pv["size"], qs)
        self._cur = i

    def _view_changed(self):
        i = getattr(self, "_cur", -1)
        if 0 <= i < len(self._found):
            p, _qs, pv = self._found[i]
            self._found[i] = (p, [list(map(list, q)) for q in self.view.quads], pv)
            self._label(i)
            if len(self.view.quads) >= 2:
                self.list.item(i).setCheckState(Qt.CheckState.Checked)

    def accept_split(self):
        self.jobs, self.skipped = [], []
        for i, (p, qs, _pv) in enumerate(self._found):
            if self.list.item(i).checkState() == Qt.CheckState.Checked and len(qs) >= 2:
                self.jobs.append((p, qs))
            else:
                self.skipped.append(p)
        self.accept()

    def reject_all(self):
        self.jobs, self.skipped = [], [p for p, _q, _v in self._found]
        self.reject()
