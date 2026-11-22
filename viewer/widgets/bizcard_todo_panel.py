# -*- coding: utf-8 -*-
"""명함찾기 할 일 칸 — 탭 줄 오른쪽 (명함 SOT §5.24.10, 261120-34·-39).

할 일 탭마다 기록 목록(명함 DB `todo_notes`) — 최신부터, ◀(이전)·▶(다음), 고쳐 [저장] 하면 새 기록(옛 기록 그대로),
[삭제] = 보던 기록 하나. 기록 = 줄 목록(줄마다 ☐ 체크 · 기한 날짜 · 글)·해시태그(기록 전용, 제목 오른쪽).
★ 명함 값은 로그에 싣지 않는다.
"""
from __future__ import annotations

import datetime

from PyQt6.QtCore import Qt, QDate, QEvent, pyqtSignal
from PyQt6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QCheckBox, QDateEdit,
                             QToolButton, QMessageBox, QSizePolicy, QScrollArea, QWidget)

from viewer.i18n import tr
from viewer.bizcard import people as P

TODO_PANEL_H = 200                  # 할 일 칸 높이 — 사람 칸이 낮으면 이 높이로 늘인다(§5.24.10 '배치')


def _today() -> str:
    return datetime.date.today().isoformat()


def _qd(s: str) -> QDate:
    d = QDate.fromString(s or "", "yyyy-MM-dd")
    return d if d.isValid() else QDate.currentDate()


class _ItemRow(QWidget):
    """줄 하나 — ☐ 체크 · 기한 날짜 · 글(§5.24.10 '줄'). 체크하면 글이 흐리게 + 가운데 줄."""

    def __init__(self, panel, item):
        super().__init__()
        self.panel = panel
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        self.chk = QCheckBox()
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        self.text = QLineEdit()
        self.text.setFrame(False)
        h.addWidget(self.chk)
        h.addWidget(self.date)
        h.addWidget(self.text, 1)
        lo, hi = panel.period()
        self.date.setMinimumDate(lo)
        self.date.setMaximumDate(hi)
        due = _qd(item.get("due") or _today())
        self.date.setDate(min(max(due, lo), hi))             # 처음 오늘 — 탭 기간 밖이면 기간 끝으로
        self.chk.setChecked(bool(item.get("done")))
        self.text.setText(item.get("text") or "")
        self._style()
        self.chk.toggled.connect(lambda _o: (self._style(), panel._dirty()))
        self.date.dateChanged.connect(lambda _d: panel._dirty())
        self.text.textEdited.connect(lambda _t: panel._dirty())
        self.text.installEventFilter(self)

    def _style(self):
        f = self.text.font()
        f.setStrikeOut(self.chk.isChecked())
        self.text.setFont(f)
        pal = self.text.palette()
        role = pal.ColorRole.PlaceholderText if self.chk.isChecked() else pal.ColorRole.WindowText
        pal.setColor(pal.ColorRole.Text, self.palette().color(role))
        self.text.setPalette(pal)

    def value(self) -> dict:
        return {"done": self.chk.isChecked(), "due": self.date.date().toString("yyyy-MM-dd"), "text": self.text.text()}

    def eventFilter(self, obj, ev):
        if obj is self.text and ev.type() == QEvent.Type.KeyPress:
            k = ev.key()
            if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.panel.add_row(after=self)               # Enter = 바로 아래 새 줄
                return True
            if k == Qt.Key.Key_Backspace and not self.text.text():
                self.panel.remove_row(self)                  # 빈 줄 Backspace = 그 줄 지움
                return True
            if k in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                self.panel.move_focus(self, -1 if k == Qt.Key.Key_Up else 1)
                return True
        return False


class _ClickArea(QWidget):
    """줄들 아래 빈 자리 — 누르면 끝에 새 줄(§5.24.10 '줄')."""

    def __init__(self, cb):
        super().__init__()
        self._cb = cb

    def mousePressEvent(self, e):
        self._cb()
        super().mousePressEvent(e)


class TodoPanel(QFrame):
    changed = pyqtSignal()           # 기록을 저장·삭제한 뒤(부르는 쪽이 탭 이름·엑셀 등을 새로)

    def __init__(self, store_fn, parent=None):
        super().__init__(parent)
        self._store = store_fn
        self.gid = None
        self.notes, self.idx = [], 0
        self.info = None
        self._loading = False
        self.rows = []
        self.setObjectName("bizTodoPanel")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        # 높이: 바라는 높이 TODO_PANEL_H(위 띠가 창 높이를 더 가져가지 않게), 위 띠가 더 높으면 그만큼 채운다 — 위·아래 끝이
        # 왼쪽 탭 줄 위 끝·사람 칸 아래 끝과 늘 같다(§5.24.10 '배치' 줄 맞춤, 261120-75 — 종전 고정 높이는 가운데 놓여 3px 씩 어긋났다)
        self.setMinimumHeight(TODO_PANEL_H)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 4, 6, 4)
        v.setSpacing(4)
        self.head_w = QWidget()                             # 머리 줄 — 높이는 탭 줄에 맞춤(set_head_height, 261120-75)
        head = QHBoxLayout(self.head_w)
        head.setContentsMargins(0, 0, 0, 0)
        self.btn_prev = QToolButton()
        self.btn_prev.setArrowType(Qt.ArrowType.LeftArrow)
        self.btn_prev.setToolTip(tr("이전 기록"))
        self.btn_next = QToolButton()
        self.btn_next.setArrowType(Qt.ArrowType.RightArrow)
        self.btn_next.setToolTip(tr("다음 기록"))
        self.lbl_title = QLabel("")
        f = self.lbl_title.font()
        f.setBold(True)
        self.lbl_title.setFont(f)
        self.ed_tags = QLineEdit()                          # 제목 오른쪽(사용자 지시 '이름 오른쪽에 위치하도록 해 (공간 확보)')
        self.ed_tags.setPlaceholderText(tr("#해시태그 — 빈칸으로 나눔(이 기록에만)"))
        self.lbl_made = QLabel("")
        self.lbl_pos = QLabel("")
        head.addWidget(self.btn_prev)
        head.addWidget(self.lbl_title)
        head.addWidget(self.ed_tags, 1)
        head.addWidget(self.lbl_made)
        head.addWidget(self.lbl_pos)
        head.addWidget(self.btn_next)
        v.addWidget(self.head_w)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        self.lines = QVBoxLayout(body)
        self.lines.setContentsMargins(0, 0, 0, 0)
        self.lines.setSpacing(2)
        self.click_area = _ClickArea(self._click_empty)
        self.click_area.setMinimumHeight(24)
        self.click_area.setToolTip(tr("눌러서 새 줄 — ☐ 체크·기한 날짜(처음 오늘)·글"))
        self.click_area.setCursor(Qt.CursorShape.IBeamCursor)
        self.lines.addWidget(self.click_area, 1)
        self.scroll.setWidget(body)
        v.addWidget(self.scroll, 1)
        bot = QHBoxLayout()
        bot.addStretch(1)
        self.btn_save = QPushButton(tr("저장"))
        self.btn_save.setToolTip(tr("고친 내용을 오늘 날짜의 새 기록으로 — 보던 기록은 그대로 남습니다"))
        self.btn_del = QPushButton(tr("삭제"))
        self.btn_del.setToolTip(tr("보고 있는 기록 하나를 지웁니다"))
        for b in (self.btn_save, self.btn_del):
            b.setAutoDefault(False)
            b.setDefault(False)
            bot.addWidget(b)
        v.addLayout(bot)
        self.btn_prev.clicked.connect(lambda _c=False: self.go(self.idx + 1))   # ◀ = 이전(오래된) 기록
        self.btn_next.clicked.connect(lambda _c=False: self.go(self.idx - 1))   # ▶ = 다음(새) 기록
        self.btn_save.clicked.connect(lambda _c=False: self.save())
        self.btn_del.clicked.connect(lambda _c=False: self.delete())
        self.ed_tags.textEdited.connect(lambda _t: self._dirty())
        self.dirty = False

    def sizeHint(self):
        from PyQt6.QtCore import QSize
        return QSize(super().sizeHint().width(), TODO_PANEL_H)

    def set_head_height(self, h: int) -> None:
        """내용 칸 위 끝이 왼쪽 사람 칸 위 끝과 맞게 — h = 탭 줄 위 끝 → 사람 칸 위 끝 거리(§5.24.10 '배치', 261120-75)."""
        m = self.layout().contentsMargins()
        want = max(self.head_w.minimumSizeHint().height(), h - m.top() - self.layout().spacing() - self.frameWidth())
        if self.head_w.height() != want or self.head_w.minimumHeight() != want:
            self.head_w.setFixedHeight(want)

    # ── 채우기 ──
    def period(self):
        """탭 기간(줄 날짜는 이 안만) — (시작, 끝). 끝이 없으면 먼 날."""
        if not self.info:
            return QDate(1900, 1, 1), QDate(9999, 12, 31)
        lo = _qd(self.info["start"]) if self.info.get("start") else QDate(1900, 1, 1)
        hi = _qd(self.info["end"]) if self.info.get("end") else QDate(9999, 12, 31)
        return lo, max(lo, hi)

    def set_group(self, gid) -> bool:
        """할 일 탭 gid 의 기록(최신부터)을 보인다. 할 일이 아니면 False(부르는 쪽이 칸을 숨긴다)."""
        st = self._store()
        info = P.todo_info(st, gid) if gid is not None else None
        if info is None:
            self.gid, self.info, self.notes = None, None, []
            return False
        P.notes_init(st)
        self.gid, self.info = gid, info
        self.notes = P.todo_notes(st, gid)
        self.go(0, ask=False)
        return True

    def go(self, idx: int, ask: bool = True):
        if ask and self.dirty and not self._ask_leave():
            return
        n = len(self.notes)
        self.idx = max(0, min(idx, n - 1)) if n else 0
        note = self.notes[self.idx] if n else {"items": [], "tags": [], "made": ""}
        self._loading = True
        try:
            self.lbl_title.setText(self.info["title"])
            self.lbl_made.setText(tr("수정일 {d}").format(d=note["made"]) if note.get("made") else "")
            self.lbl_pos.setText("%d/%d" % (self.idx + 1, n) if n else "")
            self.btn_prev.setEnabled(self.idx < n - 1)
            self.btn_next.setEnabled(self.idx > 0)
            self.btn_del.setEnabled(bool(n))
            self.ed_tags.setText(" ".join("#" + t for t in note.get("tags") or []))
            for r in list(self.rows):
                self.lines.removeWidget(r)
                r.deleteLater()
            self.rows = []
            for it in note.get("items") or []:
                self._insert_row(len(self.rows), it)
        finally:
            self._loading = False
        self.dirty = False
        self.btn_save.setEnabled(False)

    # ── 줄 ──
    def _insert_row(self, at: int, item) -> _ItemRow:
        r = _ItemRow(self, item)
        self.rows.insert(at, r)
        self.lines.insertWidget(at, r)
        return r

    def add_row(self, after=None) -> _ItemRow:
        """새 줄(☐ · 오늘 · 빈 글) — after 바로 아래, 없으면 끝. 커서는 그 줄 글로."""
        if self.gid is None:
            return None
        at = (self.rows.index(after) + 1) if after in self.rows else len(self.rows)
        r = self._insert_row(at, {"done": False, "due": _today(), "text": ""})
        r.text.setFocus()
        self._dirty()
        self.scroll.ensureWidgetVisible(r)
        return r

    def remove_row(self, row):
        if row not in self.rows:
            return
        i = self.rows.index(row)
        self.rows.remove(row)
        self.lines.removeWidget(row)
        row.deleteLater()
        if self.rows:
            prev = self.rows[max(0, i - 1)]
            prev.text.setFocus()
            prev.text.end(False)
        self._dirty()

    def move_focus(self, row, step: int):
        i = self.rows.index(row) + step
        if 0 <= i < len(self.rows):
            self.rows[i].text.setFocus()

    def _click_empty(self):
        """줄 아래 빈 자리를 누름 — 마지막 줄이 비어 있으면 그 줄로, 아니면 새 줄."""
        if self.rows and not self.rows[-1].text.text():
            self.rows[-1].text.setFocus()
            return
        self.add_row()

    def _dirty(self, *_a):
        if self._loading or self.gid is None:
            return
        self.dirty = True
        self.btn_save.setEnabled(True)

    def _ask_leave(self) -> bool:
        b = QMessageBox.question(self, tr("할 일"), tr("고친 할 일 내용을 저장할까요?"),
                                 QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard |
                                 QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save)
        if b == QMessageBox.StandardButton.Cancel:
            return False
        if b == QMessageBox.StandardButton.Save:
            return self.save()
        self.dirty = False
        return True

    def values(self) -> dict:
        from viewer.tag_store import normalize_tags
        return {"items": [r.value() for r in self.rows if r.text.text().strip()],
                "tags": normalize_tags(self.ed_tags.text().replace("#", " "))}

    # ── 저장·삭제 ──
    def save(self) -> bool:
        """고친 것을 오늘 날짜의 새 기록으로(맨 앞) — 보던 기록은 그대로. True = 저장함."""
        if self.gid is None:
            return False
        P.note_add(self._store(), self.gid, self.values(), _today())
        self.notes = P.todo_notes(self._store(), self.gid)
        self.dirty = False
        self.go(0, ask=False)
        self.changed.emit()
        return True

    def delete(self, ask: bool = True) -> bool:
        if self.gid is None or not self.notes:
            return False
        if ask and QMessageBox.question(self, tr("할 일"), tr("이 기록을 지웁니다 — 지운 기록은 ≡ 메뉴 '주소록 ▸ 변경 기록·되살리기' 에서 되살릴 수 있습니다.")) \
                != QMessageBox.StandardButton.Yes:
            return False
        P.note_delete(self._store(), self.notes[self.idx]["id"])
        self.notes = P.todo_notes(self._store(), self.gid)
        self.dirty = False
        self.go(self.idx, ask=False)
        self.changed.emit()
        return True
