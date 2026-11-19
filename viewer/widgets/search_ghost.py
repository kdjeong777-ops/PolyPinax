# -*- coding: utf-8 -*-
"""검색 칸 공통 — 찾은 글은 떠나면 흐리게 (검색창 SOT §6.1, 261117-39·261117-42).

- 칸 글이 '찾은 글'(즉시 거르기 칸은 친 글, Enter 칸은 Enter·`mark_searched` 로 찾은 그 글)인 채
  초점이 떠나면 **글은 그대로 두고 색만 흐리게** 한다 — 거르기·결과·칸 글을 읽는 코드는 그대로다.
- 다시 초점이 오면 칸 글을 다 고른다(고른 동안도 흐린 색) → 친 글이 곧 새 검색어.
- → (또는 ←·Home·End·마우스)로 고름이 풀리면 제 색으로 — 흐린 글을 다시 쓴다. 글을 고쳐도 끝.
- 창 바꾸기·팝업으로 가는 초점은 흐리지 않는다.
"""
from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtGui import QColor, QPalette

GHOST_COLOR = "#8a8a8a"                                  # 디자인 SOT §2.3 — 라이트·다크 같음


class SearchGhost(QObject):
    _KEEP = (Qt.FocusReason.ActiveWindowFocusReason, Qt.FocusReason.PopupFocusReason)

    def __init__(self, edit, instant: bool = False):
        super().__init__(edit)
        self.edit = edit
        self.instant = instant                           # 즉시 거르기 칸 — 친 글 = 찾은 글
        self.dim = False
        self._searched = ""
        self._arming = False
        self._suffix = ""
        self._own_palette = False
        edit.installEventFilter(self)
        if not instant:
            edit.returnPressed.connect(lambda: self.mark_searched(edit.text()))
        edit.textEdited.connect(lambda _t: self._set_dim(False))
        edit.textChanged.connect(self._on_changed)
        edit.selectionChanged.connect(self._on_selection)

    # ---- 찾은 글 ----
    def mark_searched(self, text: str) -> None:
        """이 칸으로(또는 다른 길로 이 칸 글로) 찾았다 — 이 글 그대로 떠나면 흐려진다."""
        self._searched = (text or "").strip()

    def _should_dim(self) -> bool:
        t = self.edit.text().strip()
        if not t:
            return False
        return self.instant or t == self._searched

    # ---- 모양 ----
    def _set_dim(self, on: bool) -> None:
        on = bool(on)
        if on == self.dim:
            return
        self.dim = on
        ed = self.edit
        if on:
            if ed.styleSheet():
                sel = ("QLineEdit#%s" % ed.objectName()) if ed.objectName() else "QLineEdit"
                self._suffix = "\n%s{color:%s;selection-background-color:transparent;selection-color:%s;}" % (
                    sel, GHOST_COLOR, GHOST_COLOR)
                ed.setStyleSheet(ed.styleSheet() + self._suffix)
            else:
                self._own_palette = ed.testAttribute(Qt.WidgetAttribute.WA_SetPalette)
                self._saved_palette = QPalette(ed.palette())
                pal = QPalette(ed.palette())
                c = QColor(GHOST_COLOR)
                for g in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
                    pal.setColor(g, QPalette.ColorRole.Text, c)
                    pal.setColor(g, QPalette.ColorRole.HighlightedText, c)
                    pal.setColor(g, QPalette.ColorRole.Highlight, pal.color(g, QPalette.ColorRole.Base))
                ed.setPalette(pal)
        else:
            if self._suffix:
                ss = ed.styleSheet()
                if self._suffix in ss:                   # 그 사이 칸 스타일이 바뀌었으면 우리 규칙만 뺀다
                    ed.setStyleSheet(ss.replace(self._suffix, ""))
                self._suffix = ""
            else:
                ed.setPalette(self._saved_palette if self._own_palette else QPalette())   # 테마를 계속 따르게

    def is_armed(self) -> bool:
        """흐린 글을 다 고른 채(새로 쓸 참) — 탭 줄 칸의 최근 목록이 좁히지 않고 전부 펼칠 때 쓴다."""
        ed = self.edit
        return self.dim and ed.hasSelectedText() and ed.selectedText() == ed.text()

    # ---- 신호 ----
    def _on_changed(self, _t) -> None:
        if self.dim and not self.edit.hasFocus():
            self._set_dim(False)                         # 다른 길로 칸 글이 바뀌었다 — 떠날 때 다시 잰다

    def _on_selection(self) -> None:
        if self.dim and not self._arming and self.edit.hasFocus() and not self.is_armed():
            self._set_dim(False)                         # → 등으로 고름이 풀렸다 — 흐린 글을 다시 쓴다

    def _arm(self) -> None:
        self._arming = False
        if self.dim and self.edit.hasFocus():
            self.edit.selectAll()

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == QEvent.Type.FocusOut:
            if ev.reason() not in self._KEEP and self._should_dim():
                self._set_dim(True)
        elif t == QEvent.Type.FocusIn:
            if self.dim:
                self._arming = True                      # 마우스 누름이 고름을 풀어도 흐림을 끝내지 않게
                QTimer.singleShot(0, self._arm)
        return False
