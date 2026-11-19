# -*- coding: utf-8 -*-
"""탭 줄 검색창 — 찾은 글은 떠나면 흐린 자리표시로 (검색창 SOT §6, 261117-39).

- 이 칸으로 찾은 뒤(`mark_searched`) 칸 글이 찾은 그 글 그대로인 채 초점이 다른 항목으로 떠나면
  칸을 비우고 그 글을 자리표시 글(흐린 글)로 보인다 → 다시 누르면 지울 것 없이 새로 쓴다.
- 칸이 빈 채 → 를 치면 흐린 글을 칸에 되살린다(커서 끝). 최근 목록이 열려 있어도 같다(목록 쪽에서도 받는다).
- 목록이 없고 칸이 빈 채 Esc → 흐린 글을 버리고 자리표시를 처음 글('검색')로.
- 창 바꾸기·팝업으로 가는 초점은 흐리지 않는다. 결과·강조는 건드리지 않는다(칸 글만).
"""
from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, Qt


class SearchGhost(QObject):
    _KEEP = (Qt.FocusReason.ActiveWindowFocusReason, Qt.FocusReason.PopupFocusReason)
    _MODS = (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier
             | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier)   # 숫자판 화살표(Keypad)는 그대로 받는다

    def __init__(self, edit, on_restore=None, extra=()):
        super().__init__(edit)
        self.edit = edit
        self.on_restore = on_restore                     # 되살린 뒤 부른다(열린 최근 목록을 그 글로 좁히기)
        self.default = edit.placeholderText()
        self.ghost = ""
        self._searched = ""
        edit.installEventFilter(self)
        for w in extra:                                  # 최근 목록 팝업 — 열린 동안 키는 칸의 거르개를 거치지 않는다
            w.installEventFilter(self)

    def mark_searched(self, text: str) -> None:
        """이 칸으로 찾았다 — 이 글 그대로 떠나면 흐린 글이 된다."""
        self._searched = (text or "").strip()

    def _dim(self) -> None:
        t = self.edit.text().strip()
        if not t or t != self._searched:
            return                                       # 쳐 놓기만 한 글·찾은 뒤 고친 글은 그대로
        self.ghost = t
        self.edit.clear()
        self.edit.setPlaceholderText(t)

    def restore(self) -> bool:
        if not self.ghost or self.edit.text():
            return False
        self.edit.setText(self.ghost)
        self.edit.setCursorPosition(len(self.ghost))
        if self.on_restore is not None:
            self.on_restore()
        return True

    def drop(self) -> bool:
        if not self.ghost or self.edit.text():
            return False
        self.ghost = ""
        self.edit.setPlaceholderText(self.default)
        return True

    def eventFilter(self, obj, ev):
        t = ev.type()
        if obj is self.edit and t == QEvent.Type.FocusOut:
            if ev.reason() not in self._KEEP:
                self._dim()
        elif t == QEvent.Type.KeyPress and not (ev.modifiers() & self._MODS):
            if ev.key() == Qt.Key.Key_Right:
                return self.restore()
            if ev.key() == Qt.Key.Key_Escape and obj is self.edit:
                return self.drop()
        return False
