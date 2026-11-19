# -*- coding: utf-8 -*-
"""탭 줄 검색창 아래 최근 검색어 펼침 목록 (검색창 SOT §6·§10, 261117-31).

- 칸을 마우스로 누르거나 ↓ 를 치면 최근 검색어(`recent_searches`, 새 것 위)를 바로 아래 펼친다. 목록이 비면 열지 않는다.
- 글자를 치면 그 글자를 **담은** 검색어로 좁힌다(대소문자 무시).
- 고르면(마우스·Enter) `on_pick(항목 dict)` — 부르는 쪽이 칸을 채우고 `Aa`·`.*` 를 되살려 찾는다.
- 모양은 Qt 기본 팝업 목록(테마 팔레트) — 화면 디자인 SOT §2.3.
"""
from __future__ import annotations

from PyQt6.QtCore import QEvent, QModelIndex, QObject, Qt, QTimer
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QCompleter

ROLE_QUERY = Qt.ItemDataRole.UserRole + 1          # 견주고 칸에 넣는 글(검색어만)
ROLE_ROW = Qt.ItemDataRole.UserRole + 2            # 항목 차례


def label(r: dict) -> str:
    """줄 글 — 즐겨찾기 탭 `최근 검색어 ▾` 와 같은 꼴(켠 토글만 `  Aa`·`  .*`)."""
    return (r.get("query", "") + ("  Aa" if r.get("case") else "") + ("  .*" if r.get("regex") else ""))


class RecentSearchPopup(QObject):
    MAX_VISIBLE = 10

    def __init__(self, edit, on_pick):
        super().__init__(edit)
        self.edit = edit
        self.on_pick = on_pick
        self.items: list = []
        self.model = QStandardItemModel(self)
        c = QCompleter(self.model, edit)
        c.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        c.setFilterMode(Qt.MatchFlag.MatchContains)
        c.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        c.setCompletionRole(ROLE_QUERY)
        c.setMaxVisibleItems(self.MAX_VISIBLE)
        c.setWidget(edit)
        c.activated[QModelIndex].connect(self._picked)
        self.completer = c
        edit.textEdited.connect(self._on_edited)
        edit.installEventFilter(self)
        self._picking = False

    def set_items(self, items) -> None:
        self.items = [dict(r) for r in (items or [])]
        self.model.clear()
        for i, r in enumerate(self.items):
            it = QStandardItem(label(r))
            it.setData(r.get("query", ""), ROLE_QUERY)
            it.setData(i, ROLE_ROW)
            it.setEditable(False)
            self.model.appendRow(it)

    def is_open(self) -> bool:
        return self.completer.popup().isVisible()

    def open(self) -> None:
        """지금 칸 글자로 좁혀 펼친다 — 맞는 것이 없으면 닫는다."""
        if not self.items:
            return
        ed = self.edit
        armed = bool(ed.property("searchGhostDim"))       # 261117-42·-60(검색창 SOT §6.1): 흐린 글 = 새로 쓸 참 — 전부
        self.completer.setCompletionPrefix("" if armed else ed.text())
        if self.completer.completionCount() <= 0:
            self.completer.popup().hide()
            return
        self.completer.complete(self.edit.rect())

    def _on_edited(self, _t) -> None:
        if self.items:
            self.open()

    def _picked(self, index) -> None:
        row = index.data(ROLE_ROW)
        if row is None or not (0 <= int(row) < len(self.items)):
            return
        r = self.items[int(row)]
        self.edit.setText(r.get("query", ""))
        self._picking = True                              # 같은 Enter 가 칸의 returnPressed 로도 가면 한 번만 찾는다
        QTimer.singleShot(0, lambda rr=dict(r): self._fire(rr))

    def _fire(self, r) -> None:
        self._picking = False
        self.on_pick(r)

    def consume_return(self) -> bool:
        """칸의 Enter 처리 앞에 부른다 — 목록에서 고른 그 Enter 면 True(칸 검색은 건너뛴다)."""
        return self._picking

    def eventFilter(self, obj, ev):
        if obj is self.edit:
            t = ev.type()
            if t == QEvent.Type.MouseButtonPress and ev.button() == Qt.MouseButton.LeftButton:
                QTimer.singleShot(0, self.open)
            elif t == QEvent.Type.KeyPress and ev.key() == Qt.Key.Key_Down and not self.is_open():
                self.open()
                return self.is_open()
        return False
