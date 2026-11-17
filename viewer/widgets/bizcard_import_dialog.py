"""명함 들이기 — 확인 표 창 (명함 SOT §5.10, P2 · D10·D11·D12).

왼쪽 표(이름·회사 후보 풀다운 + 직접 입력), 오른쪽 고른 명함 크게. 인식은 배경(`ImportWorker`), 고친 값은
그때마다 `recog` 캐시에. [적용] 은 정리 폴더에 새 JPG(원본 그대로) — 배경 진행창(`_run_merge_job`).
★ 명함 글은 로그·상태 줄 밖으로 내보내지 않는다(§2.1).
"""
from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPixmap, QImage
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QComboBox, QCheckBox,
    QPushButton, QProgressBar, QSplitter, QWidget, QLineEdit, QFileDialog, QMessageBox, QHeaderView,
    QAbstractItemView, QPlainTextEdit,
)

from viewer.i18n import tr, language
from viewer.bizcard import recognize as R
from viewer.bizcard.importer import scan_folder, ImportWorker, OUT_DIR

# 열 차례
C_ON, C_NAME, C_COMP, C_TITLE, C_CELL, C_TEL, C_MAIL, C_BACK, C_DATE, C_FILE = range(10)
NEED_BG = QColor(255, 244, 200)          # '확인 필요' 칸(디자인 SOT §2.5 의 옅은 노랑 계열)
PREVIEW_W = 460


def _first(phones, kinds):
    for k, n in phones or []:
        if k in kinds:
            return n
    return ""


class BizcardImportDialog(QDialog):
    def __init__(self, folder, parent=None, db=None, out_dir=None):
        super().__init__(parent)
        self._mw = parent
        self._folder = Path(folder)
        self._db = db
        self._items = scan_folder(self._folder)
        self._worker = None
        self._loading = False
        self.setWindowTitle(tr("명함 들이기"))
        self.resize(1280, 760)
        v = QVBoxLayout(self)

        top = QHBoxLayout()
        self.lbl_folder = QLabel(tr("폴더: {path}  ·  명함 {n}장").format(path=str(self._folder), n=len(self._items)))
        self.lbl_folder.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        top.addWidget(self.lbl_folder, 1)
        self.chk_need = QCheckBox(tr("확인 필요만"))
        self.chk_need.toggled.connect(lambda _c: self._apply_filter())
        top.addWidget(self.chk_need)
        self.ed_date = QLineEdit()
        self.ed_date.setPlaceholderText("YYYY-MM-DD")
        self.ed_date.setFixedWidth(110)
        top.addWidget(self.ed_date)
        self.btn_date = QPushButton(tr("스캔일 일괄"))
        self.btn_date.setToolTip(tr("고른 줄의 스캔일을 왼쪽 날짜로 바꿉니다"))
        self.btn_date.clicked.connect(lambda _c=False: self._set_dates())
        top.addWidget(self.btn_date)
        v.addLayout(top)
        self.bar = QProgressBar()
        self.bar.setRange(0, max(1, len(self._items)))
        self.bar.setFormat(tr("읽는 중 %v / %m"))
        v.addWidget(self.bar)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.table = QTableWidget(len(self._items), 10)
        self.table.setHorizontalHeaderLabels([tr("적용"), tr("이름"), tr("회사"), tr("직함"), tr("휴대폰"), tr("전화"),
                                              tr("메일"), tr("뒷면"), tr("스캔일"), tr("새 파일 이름")])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hh.setStretchLastSection(True)
        for c, w in ((C_ON, 44), (C_NAME, 110), (C_COMP, 160), (C_TITLE, 80), (C_CELL, 120), (C_TEL, 120),
                     (C_MAIL, 170), (C_BACK, 90), (C_DATE, 90)):
            self.table.setColumnWidth(c, w)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.currentCellChanged.connect(lambda r, *_: self._show_preview(r))
        split.addWidget(self.table)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(6, 0, 0, 0)
        self.pv_front = QLabel()
        self.pv_front.setMinimumSize(PREVIEW_W, int(PREVIEW_W * 0.58))
        self.pv_front.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pv_back = QLabel()
        self.pv_back.setMinimumSize(int(PREVIEW_W * 0.6), int(PREVIEW_W * 0.35))
        self.pv_back.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pv_en = QPlainTextEdit()
        self.pv_en.setReadOnly(True)
        self.pv_en.setMaximumHeight(110)
        self.pv_en.setPlaceholderText(tr("영문 칸 — 뒷면 등에서 읽은 영문"))
        rv.addWidget(self.pv_front, 3)
        rv.addWidget(self.pv_back, 2)
        rv.addWidget(self.pv_en)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        v.addWidget(split, 1)

        bot = QHBoxLayout()
        bot.addWidget(QLabel(tr("정리 폴더:")))
        self.ed_out = QLineEdit(str(out_dir or (self._folder / OUT_DIR)))
        bot.addWidget(self.ed_out, 1)
        b_out = QPushButton(tr("바꾸기..."))
        b_out.clicked.connect(lambda _c=False: self._pick_out())
        bot.addWidget(b_out)
        self.btn_apply = QPushButton(tr("적용"))
        self.btn_apply.setToolTip(tr("체크한 명함을 정리 폴더에 '성명_회사명.jpg' 로 만듭니다 — 원본은 그대로 둡니다"))
        self.btn_apply.clicked.connect(lambda _c=False: self._apply())
        bot.addWidget(self.btn_apply)
        b_close = QPushButton(tr("닫기"))
        b_close.clicked.connect(lambda _c=False: self.close())
        bot.addWidget(b_close)
        v.addLayout(bot)

        self._fill_empty_rows()
        QTimer.singleShot(0, self._start)

    # ── 표 ──
    def _fill_empty_rows(self):
        self._loading = True
        try:
            for r, it in enumerate(self._items):
                on = QTableWidgetItem()
                on.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                on.setCheckState(Qt.CheckState.Unchecked)
                self.table.setItem(r, C_ON, on)
                for c in (C_TITLE, C_CELL, C_TEL, C_MAIL, C_DATE):
                    self.table.setItem(r, c, QTableWidgetItem(""))
                self.table.item(r, C_DATE).setText(it.scanned)
                f = QTableWidgetItem(tr("(읽는 중)"))
                f.setFlags(f.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, C_FILE, f)
        finally:
            self._loading = False

    def _combo(self, cands, cur):
        cb = QComboBox()
        cb.setEditable(True)
        seen = []
        for t in [cur] + [c.get("text", "") for c in cands or []]:
            if t and t not in seen:
                seen.append(t)
        cb.addItems(seen)
        cb.setCurrentText(cur or "")
        return cb

    def _set_row(self, r, res, edit):
        it = self._items[r]
        it.result, it.edit = res, dict(edit or {})
        val = dict(res)
        val.update(it.edit)
        self._loading = True
        try:
            cn = self._combo(res.get("name_cands"), val.get("name", ""))
            cc = self._combo(res.get("company_cands"), R.strip_corp(val.get("company", "")))
            cn.currentTextChanged.connect(lambda _t, row=r: self._on_edit(row))
            cc.currentTextChanged.connect(lambda _t, row=r: self._on_edit(row))
            self.table.setCellWidget(r, C_NAME, cn)
            self.table.setCellWidget(r, C_COMP, cc)
            ph = [tuple(x) for x in (val.get("phones") or [])]
            self.table.item(r, C_TITLE).setText(val.get("title", ""))
            self.table.item(r, C_CELL).setText(val.get("cell", _first(ph, ("cell",))))
            self.table.item(r, C_TEL).setText(val.get("tel", _first(ph, ("work",))))
            self.table.item(r, C_MAIL).setText(val.get("email", (val.get("emails") or [""])[0]))
            if "scanned" in it.edit:
                self.table.item(r, C_DATE).setText(it.edit["scanned"])
            bk = QComboBox()
            if it.back or (it.pdf and res.get("back_promo") is not None):
                bk.addItems([tr("넣음"), tr("넣지 않음")])
                keep = it.edit.get("keep_back", not bool(res.get("back_promo")))
                bk.setCurrentIndex(0 if keep else 1)
            else:
                bk.addItem(tr("없음"))
                bk.setEnabled(False)
            bk.currentIndexChanged.connect(lambda _i, row=r: self._on_edit(row))
            self.table.setCellWidget(r, C_BACK, bk)
            on = self.table.item(r, C_ON)
            on.setCheckState(Qt.CheckState.Checked if it.edit.get("on", not res.get("error")) else Qt.CheckState.Unchecked)
            need = set(res.get("need_check") or [])
            if res.get("error"):
                need |= {"name", "company", "contact"}
            it.need = bool(need)
            for c, k in ((C_NAME, "name"), (C_COMP, "company"), (C_CELL, "contact"), (C_MAIL, "contact")):
                w = self.table.cellWidget(r, c)
                if w is not None:
                    w.setStyleSheet("QComboBox { background: %s; color: black; }" % NEED_BG.name() if k in need else "")
                else:
                    self.table.item(r, c).setBackground(NEED_BG if k in need else QColor(0, 0, 0, 0))
            self._update_file(r)
        finally:
            self._loading = False
        self._apply_filter_row(r)

    def _row_values(self, r) -> dict:
        it = self._items[r]
        res = it.result or {}
        name = self.table.cellWidget(r, C_NAME).currentText().strip() if self.table.cellWidget(r, C_NAME) else ""
        comp = self.table.cellWidget(r, C_COMP).currentText().strip() if self.table.cellWidget(r, C_COMP) else ""
        bk = self.table.cellWidget(r, C_BACK)
        keep = bool(bk is not None and bk.isEnabled() and bk.currentIndex() == 0)
        cell = self.table.item(r, C_CELL).text().strip()
        tel = self.table.item(r, C_TEL).text().strip()
        mail = self.table.item(r, C_MAIL).text().strip()
        phones = [tuple(x) for x in (res.get("phones") or [])]
        fixed = [p for p in phones if p[0] not in ("cell", "work")] + [p for p in phones if p[0] in ("cell", "work")]
        out_ph = []
        if cell:
            out_ph.append(("cell", cell))
        if tel:
            out_ph.append(("work", tel))
        for k, n in fixed:
            if n not in (cell, tel) and not (k in ("cell", "work") and any(o[0] == k for o in out_ph)):
                out_ph.append((k, n))
        emails = [mail] + [e for e in (res.get("emails") or []) if e != mail] if mail else list(res.get("emails") or [])
        cands = res.get("name_cands") or []
        return {"key": it.key, "front": it.front, "back": it.back, "pdf": it.pdf, "keep_back": keep,
                "name": name, "company": comp, "title": self.table.item(r, C_TITLE).text().strip(),
                "phones": out_ph, "emails": emails, "urls": res.get("urls") or [], "address": res.get("address", ""),
                "en": res.get("en") or {}, "langs": res.get("langs") or [], "scanned": self.table.item(r, C_DATE).text().strip(),
                "top1": (bool(cands) and cands[0].get("text") == name) if name else None,
                "on": self.table.item(r, C_ON).checkState() == Qt.CheckState.Checked,
                "cell": cell, "tel": tel, "email": mail}

    def _update_file(self, r):
        v = self._row_values(r)
        self.table.item(r, C_FILE).setText(R.card_filename(v["name"], v["company"]) if v["name"] else tr("(이름 없음)"))

    def _on_item_changed(self, item):
        if not self._loading and self._items[item.row()].result:
            self._on_edit(item.row())

    def _on_edit(self, r):
        if self._loading or not self._items[r].result:
            return
        self._loading = True
        try:
            self._update_file(r)
        finally:
            self._loading = False
        v = self._row_values(r)
        edit = {k: v[k] for k in ("name", "company", "title", "cell", "tel", "email", "scanned", "on")}
        edit["keep_back"] = v["keep_back"]
        self._items[r].edit = edit
        try:
            self._store().edit_put(self._items[r].key, edit)
        except Exception:
            pass

    def _store(self):
        if getattr(self, "_st", None) is None:
            from viewer.bizcard.store import BizcardStore
            self._st = BizcardStore(self._db, ui=True)
        return self._st

    def _apply_filter_row(self, r):
        only = self.chk_need.isChecked()
        self.table.setRowHidden(r, bool(only and not getattr(self._items[r], "need", True)))

    def _apply_filter(self):
        for r in range(len(self._items)):
            self._apply_filter_row(r)

    def _set_dates(self):
        d = self.ed_date.text().strip()
        import re
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
            QMessageBox.information(self, tr("스캔일 일괄"), tr("날짜를 YYYY-MM-DD 꼴로 적으세요."))
            return
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        for r in rows:
            self.table.item(r, C_DATE).setText(d)

    # ── 미리 보기 ──
    def _pix(self, it, back: bool, w: int):
        path = it.back if back else it.front
        img = None
        if it.pdf:
            try:
                import fitz
                doc = fitz.open(it.pdf)
                try:
                    pg = 1 if back else 0
                    if pg < doc.page_count:
                        pm = doc[pg].get_pixmap(dpi=110)
                        img = QImage.fromData(pm.tobytes("png"))
                finally:
                    doc.close()
            except Exception:
                img = None
        if img is None and path:
            img = QImage(path)
        if img is None or img.isNull():
            return QPixmap()
        return QPixmap.fromImage(img).scaledToWidth(w, Qt.TransformationMode.SmoothTransformation)

    def _show_preview(self, r):
        if r < 0 or r >= len(self._items):
            return
        it = self._items[r]
        self.pv_front.setPixmap(self._pix(it, False, max(200, self.pv_front.width() - 8)))
        self.pv_back.setPixmap(self._pix(it, True, max(160, self.pv_back.width() - 8)))
        en = (it.result or {}).get("en") or {}
        self.pv_en.setPlainText("\n".join("%s: %s" % (k, v) for k, v in en.items() if v))

    # ── 읽기 ──
    def _start(self):
        if not self._items:
            self.bar.setFormat(tr("명함 그림이 없습니다"))
            return
        lang = "en" if (language() or "ko").lower().startswith("en") else "ko"
        from viewer.workers import run_in_thread
        self._worker = ImportWorker(self._items, self._db, lang)
        self._worker.itemDone.connect(self._set_row)
        self._worker.progressed.connect(lambda d, t: self.bar.setValue(d))
        self._worker.finishedAll.connect(self._on_done)
        self._keep = []
        run_in_thread(self._worker, self._keep)

    def _on_done(self, ok):
        self.bar.setFormat(tr("다 읽음 %v / %m") if ok else tr("멈춤 %v / %m"))
        if ok and self.table.currentRow() < 0 and self._items:
            self.table.setCurrentCell(0, C_NAME)

    def _stop_worker(self):
        w = self._worker
        if w is not None and not w.done_event.is_set():
            w.request_cancel()
            w.done_event.wait(15)          # 한 장 읽기가 끝나야 멈춘다(최대 몇 초)

    def closeEvent(self, e):
        self._stop_worker()
        st = getattr(self, "_st", None)
        if st is not None:
            st.close()
            self._st = None
        super().closeEvent(e)

    # ── 적용 ──
    def _pick_out(self):
        d = QFileDialog.getExistingDirectory(self, tr("정리 폴더"), self.ed_out.text())
        if d:
            self.ed_out.setText(d)

    def selected_rows(self) -> list:
        out = []
        for r, it in enumerate(self._items):
            if not it.result or it.result.get("error"):
                continue
            v = self._row_values(r)
            if v["on"] and v["name"]:
                out.append(v)
        return out

    def _apply(self):
        rows = self.selected_rows()
        if not rows:
            QMessageBox.information(self, tr("명함 들이기"), tr("적용할 명함이 없습니다 — 이름이 있고 '적용' 이 체크된 줄만 만듭니다."))
            return
        out = Path(self.ed_out.text().strip() or (self._folder / OUT_DIR))
        from viewer.bizcard.apply import apply_cards, ApplyCancelled
        from viewer.twoup import MergeCancelled
        box = {"done": []}

        def job(progress):
            def _p(d, t):
                return progress(d, t, tr("정리본 만드는 중"))
            try:
                box["done"] = apply_cards(rows, out, self._db, _p)
            except ApplyCancelled:
                raise MergeCancelled()

        runner = getattr(self._mw, "_run_merge_job", None)
        if runner is not None:
            res = runner(job, tr("명함 들이기"))
        else:                                   # 앱 밖(검사) — 바로
            job(lambda d, t, l: True)
            res = {"ok": True}
        done = box["done"]
        self._tag(done)
        if done:
            QMessageBox.information(self, tr("명함 들이기"),
                                    tr("명함 {n}장을 정리 폴더에 만들었습니다.\n{path}").format(n=len(done), path=str(out)))
        elif not res.get("ok"):
            QMessageBox.warning(self, tr("명함 들이기"), tr("정리본을 만들지 못했습니다."))
        self.applied = done

    def _tag(self, done):
        """해시태그(§5.5) — 앱의 태그 저장소 하나로(메인). 앱 밖이면 새 저장소."""
        if not done:
            return
        store = None
        bt = getattr(self._mw, "bookmark_tree", None)
        if bt is not None:
            store = getattr(bt, "_tags", None)
        if store is None:
            from viewer.tag_store import TagStore
            store = TagStore()
        ctx = store.bulk() if hasattr(store, "bulk") else None
        if ctx is not None:
            with ctx:
                self._tag_each(store, done)
        else:
            self._tag_each(store, done)

    @staticmethod
    def _tag_each(store, done):
        for front, back, tags in done:
            for p in (front, back):
                if p:
                    old = store.get_manual(p) if hasattr(store, "get_manual") else []
                    store.set(p, list(dict.fromkeys(list(old) + list(tags))))
