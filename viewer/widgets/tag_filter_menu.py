# -*- coding: utf-8 -*-
"""찾기 칸 옆 `#` 풀다운 — 공용 위젯 하나(검색창 SOT §5.1 '공용 위젯 하나', 디자인 SOT §2.7, 261120-69).

주 창 파일 목록(`BookmarkTree`)과 명함찾기(`BizcardFindDialog`)가 같이 쓴다. 규칙은 한 곳:
- 풀다운은 입력 수단일 뿐, **진실은 찾기 칸 글** — 체크·풀기 = `#태그` 토큰 넣기·빼기, 열 때 칸 글로 체크 복원.
- 체크해도 닫히지 않는다(`QWidgetAction` + 체크 칸). 묶음 머리 굵게 — 형식·속성은 옵션 단추(묶음마다 하나만, 다시 누르면 풀림),
  주제는 체크 칸, 사진 촬영일은 '날짜' 묶음에 해·달로. 줄마다 `#태그  (개수)` 개수 많은 순, 높이 넘치면 스크롤.
- 개수 = 창이 주는 '지금 목록' 개수. 칸에 든 토큰이 목록에 없으면 **알려진 태그일 때만** `(0)` 으로 남겨 풀 수 있게.
- 단추 글 `#`, 칸에 `#태그` 가 n 개면 `#n` + 켜짐 색(`theme.tag_button_style`).
창마다 다른 것은 넘기는 값뿐 — 개수·알려진 태그·비우기 항목 이름·비었을 때 글·맨 위 진행 글·맨 아래 태그 일 항목·숨길 묶음.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QMenu

from viewer.i18n import tr, tr_noop

AXES = (tr_noop("형식"), tr_noop("속성"), tr_noop("주제"))   # 축 이름은 태그 데이터의 내부 값 — 키는 그대로, 머리글만 번역(다국어 SOT §5)


class TagFilterMenu(QObject):
    """button(QPushButton) 의 `#` 풀다운 — edit(QLineEdit) 글이 진실. counts() → {태그: 개수}, known() → 알려진 태그들.
    clear_label = 맨 아래 비우기 항목 글(칸 이름 따라), empty_text = 태그가 없을 때 글, head() → 맨 위 한 줄(없으면 ''),
    tail(menu) = 맨 아래 태그 일 항목을 더함, hide_axes = 보이지 않을 묶음(축 이름)."""

    def __init__(self, button, edit, counts, *, known=None, clear_label="", empty_text="", head=None, tail=None,
                 hide_axes=(), parent=None):
        super().__init__(parent or button)
        self.button, self.edit = button, edit
        self._counts, self._known, self._head, self._tail = counts, known, head, tail
        self.clear_label, self.empty_text = clear_label, empty_text
        self.hide_axes = tuple(hide_axes)
        self.menu = QMenu(button)
        self.menu.aboutToShow.connect(self.rebuild)
        button.setText("#")
        button.setMenu(self.menu)
        button.setFixedWidth(button.fontMetrics().horizontalAdvance("#99") + 24)   # 글 + 메뉴 화살표(종전 28px 는 화살표가 '#' 를 가렸다, 261120-75)

    # ── 찾기 칸 토큰 ──
    def active(self) -> list:
        return [c[1:] for c in self.edit.text().split() if c.startswith("#") and len(c) > 1]

    def add(self, tag: str):
        if ("#" + tag).lower() not in [c.lower() for c in self.edit.text().split()]:
            self.edit.setText((self.edit.text() + " #" + tag).strip())

    def remove(self, tag: str):
        keep = [c for c in self.edit.text().split() if not (c.startswith("#") and c[1:].lower() == tag.lower())]
        self.edit.setText(" ".join(keep))

    def pick_one(self, tag: str, on: bool, group):
        """형식·속성 묶음은 하나만 — 고르면 같은 묶음의 다른 토큰을 빼고 넣는다(칸을 한 번만 바꿈), 다시 누르면 푼다."""
        if not on:
            self.remove(tag)
            return
        others = {t.lower() for t, _b in group if t.lower() != tag.lower()}
        keep = [c for c in self.edit.text().split() if not (c.startswith("#") and c[1:].lower() in others)]
        if ("#" + tag).lower() not in [c.lower() for c in keep]:
            keep.append("#" + tag)
        for t, b in group:
            if t.lower() != tag.lower() and b.isChecked():
                b.blockSignals(True)
                b.setChecked(False)
                b.blockSignals(False)
        self.edit.setText(" ".join(keep))

    # ── 단추 ──
    def update_button(self) -> int:
        """단추 글 `#`/`#n` 과 켜짐 색 — n 을 돌려준다."""
        from viewer import theme as _theme
        n = len(self.active())
        self.button.setText("#%d" % n if n else "#")
        self.button.setStyleSheet(_theme.tag_button_style(bool(n)))
        return n

    # ── 메뉴 ──
    def rebuild(self):
        from PyQt6.QtWidgets import QCheckBox, QLabel, QRadioButton, QScrollArea, QVBoxLayout, QWidget, QWidgetAction
        from viewer import photo_tags as _pt
        try:
            from viewer.auto_tag import axis_of
        except Exception:
            def axis_of(_t):
                return "주제"
        m = self.menu
        m.clear()
        busy = self._head() if callable(self._head) else ""
        if busy:
            m.addAction(busy).setEnabled(False)
        counts = dict(self._counts() or {})
        active = {a.lower() for a in self.active()}
        known = {str(t).lower(): str(t) for t in (self._known() if callable(self._known) else []) or []}
        have = {t.lower() for t in counts}
        for a in active:                                  # 목록에 없어도 칸에 든 알려진 태그 — 풀 수 있게(0)
            if a not in have and a in known:
                counts[known[a]] = 0
        hidden = {h for h in self.hide_axes}
        tags = sorted(counts, key=lambda t: (-counts[t], t.lower()))
        groups = {g: [] for g in AXES}
        for t in tags:
            if _pt.is_date_tag(t):
                continue                                  # 사진 촬영일 — 아래 '날짜' 묶음에 해·달로
            g = axis_of(t)
            g = g if g in groups else "주제"
            if g not in hidden:
                groups[g].append(t)
        dates = _pt.date_groups(counts)
        if not any(groups.values()) and not dates:
            m.addAction(self.empty_text).setEnabled(False)
            self._add_tail()
            return
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(2)
        for gname in AXES:
            if not groups[gname]:
                continue
            lay.addWidget(QLabel("<b>%s</b>" % tr(gname)))
            one = gname in ("형식", "속성")
            btns = []
            for t in groups[gname]:
                cb = (QRadioButton if one else QCheckBox)(f"#{t}  ({counts.get(t, 0)})")
                if one:
                    cb.setAutoExclusive(False)
                    btns.append((t, cb))
                cb.setChecked(t.lower() in active)
                cb.toggled.connect((lambda on, tag=t, grp=btns: self.pick_one(tag, on, grp)) if one else
                                   (lambda on, tag=t: self.add(tag) if on else self.remove(tag)))
                lay.addWidget(cb)
        if dates:
            lay.addWidget(QLabel("<b>%s</b>" % tr("날짜")))
            for tok, n in dates:
                cb = QCheckBox(("#%s  (%d)" if len(tok) == 4 else "    #%s  (%d)") % (tok, n))
                cb.setChecked(tok.lower() in active)
                cb.toggled.connect(lambda on, tag=tok: self.add(tag) if on else self.remove(tag))
                lay.addWidget(cb)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(panel)
        area.setMaximumHeight(320)
        area.setMinimumWidth(200)
        wa = QWidgetAction(m)
        wa.setDefaultWidget(area)
        m.addAction(wa)
        m.addSeparator()
        m.addAction(self.clear_label).triggered.connect(lambda _c=False: self.edit.clear())
        self._add_tail()

    def _add_tail(self):
        if callable(self._tail):
            self._tail(self.menu)
