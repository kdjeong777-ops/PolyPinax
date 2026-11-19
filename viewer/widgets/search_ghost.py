# -*- coding: utf-8 -*-
"""검색 칸 공통 — 찾은 글은 떠나면 흐리게 (검색창 SOT §6.1, 261117-39·261117-42·261117-60).

- 칸 글이 '찾은 글'(즉시 거르기 칸은 친 글, Enter 칸은 Enter·`mark_searched` 로 찾은 그 글)인 채
  초점이 떠나면 **글은 그대로 두고 색만 흐리게** 한다 — 거르기·결과·칸 글을 읽는 코드는 그대로다.
- 다시 초점이 오면(마우스로 글 가운데를 눌러도·Tab 으로 와도) 흐린 색 그대로, 고름 없이 **커서만 맨 앞**.
- **첫 입력**(글자·Backspace/Delete·붙여넣기·한글 조합 첫 글자)이면 옛 글을 지우고 친 것만 남긴다 —
  칸 글을 몰래 다 고른 뒤 그 입력을 칸에 그대로 보내므로 칸 글은 한 번에 친 글로 바뀐다(거르기 한 번).
- → (또는 End)면 옛 글을 제 색으로 되살리고 커서는 끝. 그 밖 Ctrl 조합·오른쪽 클릭 메뉴는 되살린 뒤 칸 뜻대로.
- 창 바꾸기·팝업으로 가는 초점은 흐리지 않는다. 흐린 동안 칸 속성 `searchGhostDim` 이 True.
- `extra` — 칸 대신 키를 받는 팝업(탭 줄 칸의 최근 목록: 키를 칸 거르개 없이 칸에 넘긴다)에도 같은 키 규칙.
"""
from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtGui import QColor, QKeySequence, QPalette

GHOST_COLOR = "#8a8a8a"                                  # 디자인 SOT §2.3 — 라이트·다크 같음
PROP = "searchGhostDim"


class SearchGhost(QObject):
    _KEEP = (Qt.FocusReason.ActiveWindowFocusReason, Qt.FocusReason.PopupFocusReason)
    _CTRL = (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier
             | Qt.KeyboardModifier.AltModifier)
    _MOD_KEYS = (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta, Qt.Key.Key_AltGr,
                 Qt.Key.Key_CapsLock, Qt.Key.Key_NumLock, Qt.Key.Key_Hangul, Qt.Key.Key_Hangul_Hanja)

    def __init__(self, edit, instant: bool = False, extra=()):
        super().__init__(edit)
        self.edit = edit
        self.instant = instant                           # 즉시 거르기 칸 — 친 글 = 찾은 글
        self.dim = False
        self._searched = ""
        self._suffix = ""
        self._own_palette = False
        self._extra = tuple(extra)
        edit.installEventFilter(self)
        for w in self._extra:
            w.installEventFilter(self)
        if not instant:
            edit.returnPressed.connect(lambda: self.mark_searched(edit.text()))
        edit.textEdited.connect(lambda _t: self._set_dim(False))
        edit.textChanged.connect(self._on_changed)

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
        ed.setProperty(PROP, on)
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

    # ---- 동작 ----
    def _home(self) -> None:
        """흐린 채 커서만 맨 앞(고름 없음)."""
        if self.dim and self.edit.hasFocus():
            self.edit.deselect()
            self.edit.setCursorPosition(0)

    def _first_input(self) -> None:
        """첫 입력 — 옛 글을 몰래 다 고르고 제 색으로. 이어 가는 입력이 고름(=옛 글)을 바꾼다."""
        self._set_dim(False)
        self.edit.selectAll()

    def _restore(self, to_end: bool) -> None:
        self._set_dim(False)
        if to_end:
            self.edit.end(False)

    def _on_changed(self, _t) -> None:
        if self.dim:
            self._set_dim(False)                         # 다른 길로 칸 글이 바뀌었다 — 떠날 때 다시 잰다

    def _on_key(self, ev) -> bool:
        k = ev.key()
        mods = ev.modifiers()
        if k in self._MOD_KEYS:
            return False                                 # Ctrl·Shift 만 누른 것 — 다음 키를 본다(Ctrl+V 가 붙인 글만 남게)
        if k in (Qt.Key.Key_Right, Qt.Key.Key_End) and not (mods & self._CTRL):
            self._restore(True)                          # -39: → 로 옛 글 되살리기
            return True
        if k in (Qt.Key.Key_Left, Qt.Key.Key_Home) and not (mods & self._CTRL):
            return True                                  # 커서는 이미 맨 앞 — 흐린 채
        if k in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete) or ev.matches(QKeySequence.StandardKey.Paste):
            self._first_input()
            return False
        if mods & self._CTRL:
            self._restore(False)                         # Ctrl+A·Ctrl+C 등 — 옛 글을 쓰는 것
            return False
        s = ev.text()
        if s and s.isprintable():
            self._first_input()
        return False                                     # Esc·Enter·Tab·↑↓ 등은 칸 뜻대로

    def eventFilter(self, obj, ev):
        t = ev.type()
        if obj is not self.edit:                         # extra(팝업) — 키·한글 조합만
            if self.dim and self.edit.hasFocus():
                if t == QEvent.Type.KeyPress:
                    return self._on_key(ev)
                if t == QEvent.Type.ShortcutOverride and ev.matches(QKeySequence.StandardKey.Paste):
                    self._first_input()
                if t == QEvent.Type.InputMethod and (ev.preeditString() or ev.commitString()):
                    self._first_input()
            return False
        if t == QEvent.Type.FocusOut:
            if ev.reason() not in self._KEEP and self._should_dim():
                self._set_dim(True)
        elif not self.dim:
            pass
        elif t == QEvent.Type.FocusIn:
            QTimer.singleShot(0, self._home)             # Tab 이 다 고르는 것·누른 자리 커서를 그 뒤에 되돌린다
        elif t == QEvent.Type.KeyPress:
            return self._on_key(ev)
        elif t == QEvent.Type.ShortcutOverride and ev.matches(QKeySequence.StandardKey.Paste):
            self._first_input()                          # Ctrl+V 가 단축키로 먼저 잡혀도 붙인 글만 남게
        elif t == QEvent.Type.InputMethod:
            if ev.preeditString() or ev.commitString():
                self._first_input()                      # 한글 조합 첫 글자 — 조합이 고름(옛 글)을 지운다
        elif t == QEvent.Type.MouseButtonPress:
            QTimer.singleShot(0, self._home)             # 글 가운데를 눌러도 맨 앞(누름은 칸·최근 목록에 그대로 간다)
        elif t in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonDblClick):
            if t == QEvent.Type.MouseButtonDblClick:
                QTimer.singleShot(0, self._home)
            return True                                  # 흐린 동안 끌어 고르기·두 번 눌러 고르기 없음
        elif t == QEvent.Type.ContextMenu:
            self._restore(False)
        return False
