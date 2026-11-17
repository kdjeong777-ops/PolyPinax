# -*- coding: utf-8 -*-
"""변환 창 — 분류·형식·범위를 고른다 (형식 변환 SOT §2·§5, 261014-11 · 261117-5).

왼쪽 분류 목록 '문서'·'이미지'(`convert.GROUPS`, 보이는 분류가 하나면 숨김), 오른쪽 세부:
문서 = 다 만든 문서 형식(`convert.ready_formats`), 이미지 = 형식(JPG·PNG·WebP)·화질·크기(§2.3.1, 고른 값은 `prefs` 에 기억).
범위는 두 분류 공통 — 문서 전체 / 쪽 범위(`3-12`·`1,4,7-9`) / 고른 쪽(썸네일에서 왔을 때). 여러 파일(책갈피창 일괄)이면 문서 전체만.
모양은 디자인 SOT §2.24.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QRadioButton, QLineEdit,
                             QLabel, QDialogButtonBox, QButtonGroup, QListWidget, QStackedWidget,
                             QFormLayout, QWidget, QAbstractItemView)

from viewer.i18n import tr
from viewer import convert


class ConvertDialog(QDialog):
    def __init__(self, parent=None, *, files=(), page_count: int = 0, preset: str | None = None,
                 picked_pages=None, keys=None, prefs: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("변환"))
        self.setMinimumWidth(420)
        self._n = int(page_count or 0)
        self._picked = list(picked_pages or [])
        self._prefs = prefs
        files = list(files)
        lay = QVBoxLayout(self)
        from pathlib import Path
        who = (tr('대상: {name}').format(name=Path(files[0]).name) if len(files) == 1
               else tr('대상: {n}개 파일').format(n=len(files)))
        self.lbl_target = QLabel(who)
        self.lbl_target.setWordWrap(True)
        lay.addWidget(self.lbl_target)

        shown = [f for f in convert.ready_formats() if keys is None or f.key in keys]   # 사진은 뜻 있는 형식만(사진 보기 SOT §4.35)
        self._groups = [g for g, _n in convert.GROUPS if any(f.group == g for f in shown)]
        self._image_key = next((f.key for f in shown if f.group == "image"), None)

        body = QHBoxLayout()
        self.lst_groups = QListWidget()
        self.lst_groups.setObjectName("convert_groups")
        self.lst_groups.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        names = dict(convert.GROUPS)
        for g in self._groups:
            self.lst_groups.addItem(tr(names[g]))
        fm = self.lst_groups.fontMetrics()
        w = max([fm.horizontalAdvance(self.lst_groups.item(i).text()) for i in range(self.lst_groups.count())] or [40])
        self.lst_groups.setFixedWidth(w + 48)
        self.lst_groups.setVisible(len(self._groups) > 1)
        body.addWidget(self.lst_groups)
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        lay.addLayout(body)

        # ── 문서 쪽 ──
        self.fmt_group = QButtonGroup(self)
        self._fmt_btn = {}
        g_fmt = QGroupBox(tr("형식"))
        fl = QVBoxLayout(g_fmt)
        for f in shown:
            if f.group != "doc":
                continue
            b = QRadioButton(tr(f.label))
            b.setObjectName("fmt_" + f.key)
            self.fmt_group.addButton(b)
            help_html = convert.help_text(f.key)
            if help_html:                         # 261113-3(형식 변환 SOT §5): '?' 설명 — 지금은 'MS Word 모듈 적용' 만
                from viewer.widgets.help_button import HelpButton
                row_f = QHBoxLayout()
                row_f.addWidget(b)
                hb = HelpButton(help_html, tr(f.label), self)
                hb.setObjectName("help_" + f.key)
                row_f.addWidget(hb)
                row_f.addStretch(1)
                fl.addLayout(row_f)
            else:
                fl.addWidget(b)
            if not convert.available(f.key):      # Word 가 없는 PC — 흐리게, 까닭은 풍선 도움말·'?' 로
                b.setEnabled(False)
                b.setToolTip(tr(convert.WORD_REQUIRED))
            self._fmt_btn[f.key] = b
        fl.addStretch(1)
        self._page = {}
        if "doc" in self._groups:
            self._page["doc"] = self.stack.addWidget(g_fmt)

        # ── 이미지 쪽(§2.3.1) ──
        opts = convert.image_opts(prefs)
        self.img_fmt, self.img_q, self.img_dpi = {}, {}, {}
        g_img = QGroupBox(tr("이미지"))
        form = QFormLayout(g_img)

        def radio_row(items, store, prefix, current):
            box = QWidget()
            hl = QHBoxLayout(box)
            hl.setContentsMargins(0, 0, 0, 0)
            grp = QButtonGroup(box)
            for key, text in items:
                rb = QRadioButton(text)
                rb.setObjectName(prefix + str(key))
                grp.addButton(rb)
                hl.addWidget(rb)
                store[key] = rb
                rb.setChecked(key == current)
            hl.addStretch(1)
            return box
        form.addRow(tr("형식"), radio_row([(k, n) for k, n, _e in convert.IMAGE_FORMATS], self.img_fmt, "img_fmt_", opts["fmt"]))
        form.addRow(tr("화질"), radio_row([(k, tr(n)) for k, n, _q in convert.IMAGE_QUALITY], self.img_q, "img_q_", opts["quality"]))
        form.addRow(tr("크기"), radio_row([(d, tr("{name} ({dpi} dpi)").format(name=tr(n), dpi=d)) for d, n in convert.IMAGE_SIZES],
                                          self.img_dpi, "img_dpi_", opts["dpi"]))
        self.lbl_q = form.labelForField(self.img_q[convert.IMAGE_QUALITY[0][0]].parentWidget())
        for rb in self.img_fmt.values():
            rb.toggled.connect(self._sync_quality)
        if "image" in self._groups:
            self._page["image"] = self.stack.addWidget(g_img)
        self._sync_quality()

        usable = [k for k, b in self._fmt_btn.items() if b.isEnabled()]
        first = preset if preset in usable else next(iter(usable), None)
        if first:
            self._fmt_btn[first].setChecked(True)
        start = "image" if (preset is not None and preset == self._image_key) else (self._groups[0] if self._groups else None)
        self.lst_groups.currentRowChanged.connect(self._on_group)
        if start in self._groups:
            self.lst_groups.setCurrentRow(self._groups.index(start))
            self._on_group(self._groups.index(start))

        g_rng = QGroupBox(tr("범위"))
        rl = QVBoxLayout(g_rng)
        self.rb_all = QRadioButton(tr("문서 전체"))
        row = QHBoxLayout()
        self.rb_range = QRadioButton(tr("쪽 범위"))
        self.ed_range = QLineEdit()
        self.ed_range.setPlaceholderText(tr("예: 3-12 또는 1,4,7-9"))
        self.ed_range.textEdited.connect(lambda _t: self.rb_range.setChecked(True))
        row.addWidget(self.rb_range); row.addWidget(self.ed_range, 1)
        self.rb_picked = QRadioButton(tr('고른 쪽 ({n}쪽)').format(n=len(self._picked)))
        rl.addWidget(self.rb_all); rl.addLayout(row); rl.addWidget(self.rb_picked)
        self.rb_picked.setVisible(bool(self._picked))
        (self.rb_picked if self._picked else self.rb_all).setChecked(True)
        if len(files) != 1:                       # 일괄은 문서 전체만(SOT §2.2)
            self.rb_range.setEnabled(False); self.ed_range.setEnabled(False)
        lay.addWidget(g_rng)

        self.lbl_err = QLabel("")
        self.lbl_err.setStyleSheet("color:#b3261e;")
        lay.addWidget(self.lbl_err)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(tr("변환"))
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        # 정한 최소 폭이 레이아웃 최소를 덮으면 이미지 쪽 라디오 줄 글이 잘린다 — 둘 중 큰 쪽(디자인 SOT §2.24)
        self.setMinimumWidth(max(420, lay.minimumSize().width()))

    def _on_group(self, row: int):
        if 0 <= row < len(self._groups):
            self.stack.setCurrentIndex(self._page[self._groups[row]])

    def _sync_quality(self, *_a):
        """PNG 는 손실이 없어 화질 줄을 흐리게(§2.3.1)."""
        on = self.image_options()["fmt"] != "png"
        for rb in self.img_q.values():
            rb.setEnabled(on)
        if self.lbl_q is not None:
            self.lbl_q.setEnabled(on)

    def group(self) -> str | None:
        """지금 고른 분류 — "doc" · "image"."""
        r = self.lst_groups.currentRow()
        return self._groups[r] if 0 <= r < len(self._groups) else (self._groups[0] if self._groups else None)

    def format_key(self) -> str | None:
        if self.group() == "image":
            return self._image_key
        for k, b in self._fmt_btn.items():
            if b.isChecked():
                return k
        return None

    def image_options(self) -> dict:
        """이미지 형식·화질·크기 — {"fmt", "quality", "dpi"}(§2.3.1)."""
        pick = lambda d: next((k for k, rb in d.items() if rb.isChecked()), None)   # noqa: E731
        return convert.image_opts({"fmt": pick(self.img_fmt), "quality": pick(self.img_q), "dpi": pick(self.img_dpi)})

    def pages(self):
        """None = 문서 전체, 그 밖에는 0부터 쪽 목록."""
        if self.rb_picked.isChecked() and self._picked:
            return list(self._picked)
        if self.rb_range.isChecked():
            return convert.parse_range(self.ed_range.text(), self._n)
        return None

    def _accept(self):
        if not self.format_key():
            self.lbl_err.setText(tr("형식을 고르세요."))
            return
        try:
            self.pages()
        except ValueError:
            self.lbl_err.setText(tr('쪽 범위는 1~{n} 안에서 3-12 처럼 적어 주세요.').format(n=self._n))
            return
        if self.group() == "image" and self._prefs is not None:
            self._prefs.clear()
            self._prefs.update(self.image_options())       # 다음 창의 처음 값(settings.json `convert_image`)
        self.accept()
