# -*- coding: utf-8 -*-
"""261116-5(책갈피창·저장 SOT §4.7.29, 마스터 §11.10.6): '목차 페이지 만들기' 창 — 제목·단계·Word 양식·미리보기.

값만 고른다 — 만들기·저장은 `toc_page_flow` 가 배경 + `_finalize_save` 로.
미리보기(목차 첫 쪽 하나)는 **Qt 로 그린다**(`toc_page` 와 같은 자리값 — 여백·줄 높이·들여쓰기·점선·오른쪽 끝 번호).
fitz 로 그리면 한글 글꼴을 문서에 넣고 글자 폭을 재는 데 메인에서 0.4~1.6초 섰다(실측) — 배경 스레드여도 PyMuPDF 가
GIL 을 쥐어 같다(응답성 SOT §4.4 행). 만드는 것은 그대로 fitz/Word(배경).
"""
from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import QPointF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
                             QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget)

from viewer import toc_page
from viewer.i18n import tr

def paint_preview(rows, w, h, title, width) -> QImage:
    """목차 첫 쪽 미리보기 — `render_fitz` 와 같은 자리값을 Qt 로(pt → 화면 비율 z)."""
    z = width / max(1.0, w)
    img = QImage(int(width), int(h * z), QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    def font(pt, bold):
        f = QFont("Malgun Gothic"); f.setPixelSize(max(1, int(round(pt * z)))); f.setBold(bold)
        return f
    f = font(toc_page.TITLE_FS, True); p.setFont(f)
    fm = QFontMetricsF(f)
    p.setPen(QColor("black"))
    p.drawText(QPointF((width - fm.horizontalAdvance(title)) / 2.0, toc_page.TOP * z), title)
    right = (w - toc_page.MARGIN_X) * z
    y = toc_page.FIRST_ROW
    for lv, name, num in rows:
        if y > h - toc_page.BOTTOM:                     # 첫 쪽만 — 넘김은 render_fitz 와 같은 셈
            break
        lv = max(1, int(lv)); bold = lv == 1
        f = font(toc_page.FS1 if lv == 1 else toc_page.FS2, bold); p.setFont(f); fm = QFontMetricsF(f)
        x0 = (toc_page.MARGIN_X + toc_page.INDENT * (lv - 1)) * z
        num = str(num)
        name = fm.elidedText(str(name), Qt.TextElideMode.ElideRight, max(10.0, right - toc_page.NUM_RESERVE * z - 12 * z - x0))
        p.setPen(QColor("black"))
        p.drawText(QPointF(x0, y * z), name)
        nw = fm.horizontalAdvance(num) if num else 0.0
        if num:
            p.drawText(QPointF(right - nw, y * z), num)
        lx0 = x0 + fm.horizontalAdvance(name) + 6 * z
        lx1 = right - (nw if num else toc_page.NUM_RESERVE * z) - 4 * z
        unit = fm.horizontalAdvance(toc_page.LEADER + " ")
        k = int((lx1 - lx0) // unit) if unit > 0 else 0
        if k > 0:
            dots = (" " + toc_page.LEADER) * k
            p.setPen(QColor(90, 90, 90))
            p.drawText(QPointF(lx1 - fm.horizontalAdvance(dots), y * z), dots)
        y += toc_page.LINE_H
    p.end()
    return img


class TocPageDialog(QDialog):
    PREVIEW_W = 300

    def __init__(self, path, info, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("목차 페이지 만들기"))
        self._path = str(path)
        self._toc = list(info.get("toc") or [])
        self._w, self._h = float(info.get("w") or 595.0), float(info.get("h") or 842.0)
        self._pages = int(info.get("pages") or 0) - int(info.get("old") or 0)
        self._at = int(info.get("at", 1))                 # 261116-15: 옛 목차를 옮겨 둔 자리면 그 자리에 바꿔 넣는다
        mx = max(1, toc_page.max_level(self._toc))
        root = QVBoxLayout(self)
        row = QHBoxLayout(); root.addLayout(row, 1)
        form_w = QWidget(); form = QFormLayout(form_w); row.addWidget(form_w, 1)
        self.ed_title = QLineEdit()
        form.addRow(tr("목차 제목:"), self.ed_title)
        self.cmb_level = QComboBox()
        for lv in range(1, mx + 1):
            self.cmb_level.addItem(toc_page.level_label(lv), lv)
        self.cmb_level.setCurrentIndex(min(2, mx) - 1)
        self.cmb_level.setToolTip(tr("고른 단계 이하를 모두 넣고 단계마다 들여씁니다."))
        form.addRow(tr("목차 단계:"), self.cmb_level)
        self.ed_tpl = QLineEdit()
        self.ed_tpl.setPlaceholderText(tr("비우면 기본 모양"))
        b_pick = QPushButton(tr("양식")); b_pick.clicked.connect(self._pick_template)
        b_sample = QPushButton(tr("샘플 만들기")); b_sample.clicked.connect(self._make_sample)
        b_sample.setToolTip(tr("목차_샘플.docx 를 만들어 엽니다 — 고쳐 저장한 뒤 '양식' 으로 고르세요. 다단 목차와 같은 양식입니다."))
        tr_row = QHBoxLayout(); tr_row.addWidget(self.ed_tpl, 1); tr_row.addWidget(b_pick); tr_row.addWidget(b_sample)
        tw = QWidget(); tw.setLayout(tr_row); tr_row.setContentsMargins(0, 0, 0, 0)
        form.addRow(tr("Word 양식:"), tw)
        if int(info.get("old") or 0) and self._at != 1:
            note = QLabel(tr("옛 목차가 있던 자리({p}쪽부터)에 새 목차를 바꿔 넣어 저장합니다. 쪽 번호는 끼운 뒤의 쪽이고, 목차 줄을 누르면 그 쪽으로 갑니다.").format(p=self._at + 1))
        else:
            note = QLabel(tr("목차는 이 파일의 1쪽(표지) 뒤, 2쪽부터 끼워 저장합니다. 쪽 번호는 끼운 뒤의 쪽이고, 목차 줄을 누르면 그 쪽으로 갑니다."))
        note.setWordWrap(True)
        form.addRow(note)
        self.lbl_preview = QLabel()
        self.lbl_preview.setFixedWidth(self.PREVIEW_W)
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        row.addWidget(self.lbl_preview)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(tr("만들기"))
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        root.addWidget(bb)
        self._timer = QTimer(self); self._timer.setSingleShot(True); self._timer.setInterval(150)
        self._timer.timeout.connect(self._render_preview)
        self.ed_title.textChanged.connect(lambda _t: self._timer.start())
        self.cmb_level.currentIndexChanged.connect(lambda _i: self._on_level())
        self._on_level()

    # ── 값 ──
    def rows(self):
        return toc_page.toc_rows(self._toc, self.levels(), self._pages or None)

    def levels(self) -> int:
        return int(self.cmb_level.currentData() or 1)

    def values(self) -> dict:
        return {"title": self.ed_title.text(), "levels": self.levels(), "template": self.ed_tpl.text().strip()}

    def _on_level(self):
        self.ed_title.setPlaceholderText(toc_page.auto_title([r[1] for r in self.rows()]))   # 비우면 이 제목
        self._timer.start()

    # ── 양식 ──
    def _pick_template(self):
        fn, _ = QFileDialog.getOpenFileName(self, tr("목차 Word 양식"), str(Path(self._path).parent), "Word (*.docx)")
        if fn:
            self.ed_tpl.setText(fn)

    def _make_sample(self):
        fn, _ = QFileDialog.getSaveFileName(self, tr("샘플 만들기"),
                                            str(Path(self._path).parent / tr("목차_샘플.docx")), "Word (*.docx)")
        if not fn:
            return
        if not toc_page.write_sample(fn):
            QMessageBox.warning(self, tr("샘플 만들기"), tr("샘플을 만들지 못했습니다."))
            return
        self.ed_tpl.setText(fn)
        try:
            os.startfile(fn)                                   # noqa: S606 — 사용자가 고친 뒤 이 양식을 쓴다
        except Exception:
            pass

    # ── 미리보기(Qt) ──
    def _render_preview(self):
        rows = self.rows()
        title = self.ed_title.text() if self.ed_title.text().strip() else self.ed_title.placeholderText()
        k = toc_page.fitz_pages(len(rows), self._h)
        img = paint_preview(toc_page.numbered(rows, k, self._at), self._w, self._h, title, self.PREVIEW_W)
        self.lbl_preview.setPixmap(QPixmap.fromImage(img))
        self.lbl_preview.setToolTip(tr("목차 {n}쪽 — 첫 쪽").format(n=k))

    def done(self, r):
        self._timer.stop()                                  # 닫은 뒤 미리보기를 다시 그리지 않는다
        super().done(r)
