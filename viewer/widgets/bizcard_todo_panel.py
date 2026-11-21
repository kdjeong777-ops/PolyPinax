# -*- coding: utf-8 -*-
"""명함찾기 할 일 칸 — 탭 줄 오른쪽 (명함 SOT §5.24.10, 261120-34).

할 일 탭마다 기록 목록(명함 DB `todo_notes`) — 최신부터, ◀(이전)·▶(다음), 고쳐 [저장] 하면 새 기록(옛 기록 그대로),
[삭제] = 보던 기록 하나. 기록 = 내용·수정일·체크(했음)·시작/끝(탭 기간 안)·해시태그(기록 전용). ★ 명함 값은 로그에 싣지 않는다.
"""
from __future__ import annotations

import datetime

from PyQt6.QtCore import Qt, QDate, pyqtSignal
from PyQt6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QCheckBox,
                             QDateEdit, QToolButton, QMessageBox, QSizePolicy)

from viewer.i18n import tr
from viewer.bizcard import people as P

TODO_PANEL_H = 200                  # 할 일 칸 최소 높이 — 사람 칸이 낮으면 이 높이로 늘인다(§5.24.10 '배치')


def _today() -> str:
    return datetime.date.today().isoformat()


def _qd(s: str) -> QDate:
    d = QDate.fromString(s or "", "yyyy-MM-dd")
    return d if d.isValid() else QDate.currentDate()


class TodoPanel(QFrame):
    changed = pyqtSignal()           # 기록을 저장·삭제한 뒤(부르는 쪽이 탭 이름·엑셀 등을 새로)

    def __init__(self, store_fn, parent=None):
        super().__init__(parent)
        self._store = store_fn
        self.gid = None
        self.notes, self.idx = [], 0
        self.info = None
        self._loading = False
        self.setObjectName("bizTodoPanel")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedHeight(TODO_PANEL_H)                  # 위 띠가 창 높이를 더 가져가지 않게(목록·세부가 줄지 않게)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 4, 6, 4)
        v.setSpacing(4)
        head = QHBoxLayout()
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
        self.lbl_made = QLabel("")
        self.lbl_pos = QLabel("")
        head.addWidget(self.btn_prev)
        head.addWidget(self.lbl_title, 1)
        head.addWidget(self.lbl_made)
        head.addWidget(self.lbl_pos)
        head.addWidget(self.btn_next)
        v.addLayout(head)
        self.ed_tags = QLineEdit()
        self.ed_tags.setPlaceholderText(tr("#해시태그 — 빈칸으로 나눔(이 기록에만)"))
        v.addWidget(self.ed_tags)
        row = QHBoxLayout()
        self.chk_done = QCheckBox(tr("했음"))
        self.d_start, self.d_end = QDateEdit(), QDateEdit()
        for d in (self.d_start, self.d_end):
            d.setCalendarPopup(True)
            d.setDisplayFormat("yyyy-MM-dd")
        self.chk_end = QCheckBox(tr("끝"))
        self.chk_end.setToolTip(tr("체크하지 않으면 끝 없이 계속"))
        row.addWidget(self.chk_done)
        row.addSpacing(8)
        row.addWidget(QLabel(tr("기한")))
        row.addWidget(self.d_start)
        row.addWidget(QLabel("~"))
        row.addWidget(self.chk_end)
        row.addWidget(self.d_end)
        row.addStretch(1)
        v.addLayout(row)
        self.ed_body = QPlainTextEdit()
        self.ed_body.setPlaceholderText(tr("할 일 내용"))
        v.addWidget(self.ed_body, 1)
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
        self.ed_body.textChanged.connect(self._dirty)
        self.chk_done.toggled.connect(lambda _o: self._dirty())
        self.chk_end.toggled.connect(lambda on: (self.d_end.setEnabled(on), self._dirty()))
        self.d_start.dateChanged.connect(lambda _d: self._dirty())
        self.d_end.dateChanged.connect(lambda _d: self._dirty())
        self.dirty = False

    # ── 채우기 ──
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
        note = self.notes[self.idx] if n else {"body": "", "done": False, "start": self.info["start"], "end": self.info["end"],
                                                "tags": [], "made": ""}
        self._loading = True
        try:
            self.lbl_title.setText(self.info["title"])
            self.lbl_made.setText(tr("수정일 {d}").format(d=note["made"]) if note.get("made") else "")
            self.lbl_pos.setText("%d/%d" % (self.idx + 1, n) if n else "")
            self.btn_prev.setEnabled(self.idx < n - 1)
            self.btn_next.setEnabled(self.idx > 0)
            self.btn_del.setEnabled(bool(n))
            lo = _qd(self.info["start"])
            for d in (self.d_start, self.d_end):            # 기한은 탭 기간 안(§5.24.10 '기한')
                d.setMinimumDate(lo)
                d.setMaximumDate(_qd(self.info["end"]) if self.info["end"] else QDate(9999, 12, 31))
            self.d_start.setDate(_qd(note.get("start") or self.info["start"]))
            end = note.get("end") or ""
            self.chk_end.setChecked(bool(end))
            self.d_end.setEnabled(bool(end))
            self.d_end.setDate(_qd(end or note.get("start") or self.info["start"]))
            self.chk_done.setChecked(bool(note.get("done")))
            self.ed_tags.setText(" ".join("#" + t for t in note.get("tags") or []))
            self.ed_body.setPlainText(note.get("body") or "")
        finally:
            self._loading = False
        self.dirty = False
        self.btn_save.setEnabled(False)

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
        start = self.d_start.date().toString("yyyy-MM-dd")
        end = self.d_end.date().toString("yyyy-MM-dd") if self.chk_end.isChecked() else ""
        return {"body": self.ed_body.toPlainText(), "done": self.chk_done.isChecked(), "start": start, "end": end,
                "tags": normalize_tags(self.ed_tags.text().replace("#", " "))}

    # ── 저장·삭제 ──
    def save(self) -> bool:
        """고친 것을 오늘 날짜의 새 기록으로(맨 앞) — 보던 기록은 그대로. True = 저장함."""
        if self.gid is None:
            return False
        note = self.values()
        if note["end"] and note["end"] < note["start"]:
            QMessageBox.information(self, tr("할 일"), tr("끝 날짜가 시작 날짜보다 앞입니다."))
            return False
        P.note_add(self._store(), self.gid, note, _today())
        self.notes = P.todo_notes(self._store(), self.gid)
        self.dirty = False
        self.go(0, ask=False)
        self.changed.emit()
        return True

    def delete(self, ask: bool = True) -> bool:
        if self.gid is None or not self.notes:
            return False
        if ask and QMessageBox.question(self, tr("할 일"), tr("이 기록을 지웁니다 — 되돌릴 수 없습니다.")) \
                != QMessageBox.StandardButton.Yes:
            return False
        P.note_delete(self._store(), self.notes[self.idx]["id"])
        self.notes = P.todo_notes(self._store(), self.gid)
        self.dirty = False
        self.go(self.idx, ask=False)
        self.changed.emit()
        return True
