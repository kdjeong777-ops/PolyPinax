"""명함 관리 — 확인 표 창 (명함 SOT §5.10, P2 · D10·D11·D12 · §5.11 위치 지정·배우기, 261117-9).

왼쪽 표(이름·회사 후보 풀다운 + 직접 입력), 오른쪽 고른 명함 크게. 인식은 배경(`ImportWorker`), 고친 값은
그때마다 `recog` 캐시에. [적용] 은 정리 폴더에 새 JPG(원본 그대로) — 배경 진행창(`_run_merge_job`).
★ 명함 글은 로그·상태 줄 밖으로 내보내지 않는다(§2.1).
"""
from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QRect, QPoint, QSize, pyqtSignal, QObject
from PyQt6.QtGui import QColor, QPixmap, QImage, QTransform
from PyQt6.QtWidgets import (QRubberBand, QMenu,
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QComboBox, QCheckBox,
    QPushButton, QProgressBar, QSplitter, QWidget, QLineEdit, QFileDialog, QMessageBox, QHeaderView,
    QAbstractItemView, QPlainTextEdit, QSizePolicy, QStyledItemDelegate, QDialog,
)

from viewer.i18n import tr, language
from viewer.bizcard import recognize as R
from viewer.bizcard.importer import scan_folder, ImportWorker, OUT_DIR

# 열 차례
C_ON, C_NAME, C_COMP, C_DEPT, C_TITLE, C_CELL, C_TEL, C_MAIL, C_BACK, C_DATE, C_FILE = range(11)   # 261117-11: 부서
NEED_BG = QColor(255, 244, 200)          # '확인 필요' 칸(디자인 SOT §2.5 의 옅은 노랑 계열)
PREVIEW_W = 460


class RegionLabel(QLabel):
    """미리 보기 — 끌어서 상자를 그리면 `regionPicked(그림 비율 x0, y0, x1, y1, 전역 위치)`(§5.11 위치 지정)."""
    regionPicked = pyqtSignal(float, float, float, float, QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._band = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self._org = None
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setToolTip(tr("명함 위를 끌어 이름·회사 등의 자리를 지정하면 그 자리만 다시 읽어 칸을 채우고, 같은 회사 명함에 기억합니다"))

    def _pix_rect(self) -> QRect:
        pm = self.pixmap()
        if pm is None or pm.isNull():
            return QRect()
        r = QRect(QPoint(0, 0), pm.size())
        r.moveCenter(self.rect().center())
        return r

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._pix_rect().contains(e.position().toPoint()):
            self._org = e.position().toPoint()
            self._band.setGeometry(QRect(self._org, QSize()))
            self._band.show()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._org is not None:
            self._band.setGeometry(QRect(self._org, e.position().toPoint()).normalized())
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._org is not None:
            box = QRect(self._org, e.position().toPoint()).normalized().intersected(self._pix_rect())
            self._org = None
            self._band.hide()
            pr = self._pix_rect()
            if box.width() > 4 and box.height() > 4 and pr.width() > 0:
                self.regionPicked.emit((box.left() - pr.left()) / pr.width(), (box.top() - pr.top()) / pr.height(),
                                       (box.right() - pr.left()) / pr.width(), (box.bottom() - pr.top()) / pr.height(),
                                       self.mapToGlobal(box.bottomLeft()))
        super().mouseReleaseEvent(e)


_KEEP = []                 # 앱 밖(검사)에서 쓸 때의 스레드 참조 보관


def pil_to_qimage(im) -> QImage:
    """PIL → QImage(**복사본**). 261117-14 사용자 보고: `ImageQt(RGB)` 는 폭이 4의 배수가 아니면 줄 바이트 수가 어긋나 사선 무늬로
    보였고, 바탕 버퍼를 빌려 쓰는 QImage 라 창이 '응답 없음' 이 될 수 있었다 — 줄 바이트 수를 밝히고 곧바로 `copy()` 한다."""
    rgb = im.convert("RGB")
    w, h = rgb.size
    data = rgb.tobytes("raw", "RGB")
    return QImage(data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
CHOICES = Qt.ItemDataRole.UserRole + 1     # 칸의 고르기 후보(이름·회사 후보, 뒷면 넣음/넣지 않음)
FREE = Qt.ItemDataRole.UserRole + 2        # 후보 밖 글을 직접 쓸 수 있나
FILL_BUDGET_MS = 40        # 한 번에 표를 채우는 시간 상한 — 남은 것은 다음 틱(응답성 SOT §4 ④, 메인 정지 < 1초)


class ChoiceDelegate(QStyledItemDelegate):
    """후보 풀다운은 **고칠 때만** 만든다 — 종전에는 줄마다 QComboBox 위젯 3개(1000장 = 3000개)를 만들고 스타일시트로
    칠해 표를 채우는 동안 메인이 1초 넘게 섰다('응답 없음', 사용자 보고 261117-12)."""

    def createEditor(self, parent, option, index):
        ch = index.data(CHOICES)
        if not ch:
            return super().createEditor(parent, option, index)
        cb = QComboBox(parent)
        cb.setEditable(bool(index.data(FREE)))
        cb.addItems([str(x) for x in ch])
        return cb

    def setEditorData(self, editor, index):
        if isinstance(editor, QComboBox):
            editor.setCurrentText(str(index.data(Qt.ItemDataRole.DisplayRole) or ""))
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if isinstance(editor, QComboBox):
            model.setData(index, editor.currentText().strip(), Qt.ItemDataRole.EditRole)
        else:
            super().setModelData(editor, model, index)


class RegionWorker(QObject):
    """고른 자리 읽기(§5.16) — 원천 그림 그리기·OCR 을 배경에서, 끝나면 `done({val, crop})`(run_in_thread)."""
    done = pyqtSignal(dict)
    finished = pyqtSignal()

    def __init__(self, source_fn, item, box, fld):
        super().__init__()
        self._src, self._it, self._box, self._fld = source_fn, item, box, fld

    def run(self):
        out = {}
        try:
            im = self._src(self._it)
            if im is not None:
                out["val"], out["crop"] = R.read_box(im, self._box, self._fld)
        except Exception as e:                     # 명함 글은 싣지 않는다 — 종류만
            out["err"] = type(e).__name__
        self.done.emit(out)
        self.finished.emit()


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
        self.region_busy = False                  # 고른 자리를 배경에서 읽는 중(§5.16) — 그동안 다른 자리·줄·[적용] 막음
        self.last_region = None
        self._closing = False
        self._loading = False
        self.setWindowTitle(tr("명함 관리"))
        # 261117-13(사용자 지시 '전체화면으로도'): 최대화 단추 + F11 전체 화면
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowMinimizeButtonHint)
        from PyQt6.QtGui import QShortcut, QKeySequence
        QShortcut(QKeySequence("F11"), self, activated=self.toggle_full)
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
        self.btn_full = QPushButton(tr("전체 화면"))
        self.btn_full.setToolTip(tr("명함 관리 창을 화면 가득 — 다시 누르거나 F11·Esc 로 돌아옵니다"))
        self.btn_full.clicked.connect(lambda _c=False: self.toggle_full())
        top.addWidget(self.btn_full)
        v.addLayout(top)
        self.bar = QProgressBar()
        self.bar.setRange(0, max(1, len(self._items)))
        self.bar.setFormat(tr("읽는 중 %v / %m"))
        v.addWidget(self.bar)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.splitterMoved.connect(lambda *_: QTimer.singleShot(0, self._refit))   # 칸 폭을 바꿔도 다시 맞춤
        self.table = QTableWidget(len(self._items), 11)
        self.table.setHorizontalHeaderLabels([tr("적용"), tr("이름"), tr("회사"), tr("부서"), tr("직함"), tr("휴대폰"), tr("전화"),
                                              tr("메일"), tr("뒷면"), tr("스캔일"), tr("새 파일 이름")])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hh.setStretchLastSection(True)
        for c, w in ((C_ON, 44), (C_NAME, 110), (C_COMP, 160), (C_DEPT, 110), (C_TITLE, 80), (C_CELL, 120), (C_TEL, 120),
                     (C_MAIL, 170), (C_BACK, 90), (C_DATE, 90)):
            self.table.setColumnWidth(c, w)
        self.table.setItemDelegate(ChoiceDelegate(self.table))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.SelectedClicked
                                   | QAbstractItemView.EditTrigger.EditKeyPressed | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.table.itemChanged.connect(self._on_item_changed)
        self._pending = []                       # 배경에서 온 결과 — 시간 상한 안에서 나눠 채운다
        self._drain = QTimer(self)
        self._drain.setInterval(15)
        self._drain.timeout.connect(self._drain_pending)
        self.table.currentCellChanged.connect(lambda r, *_: self._show_preview(r))
        split.addWidget(self.table)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(6, 0, 0, 0)
        self.pv_front = RegionLabel()
        self.pv_front.regionPicked.connect(self._on_region)
        self.pv_front.setMinimumSize(int(PREVIEW_W * 0.6), int(PREVIEW_W * 0.4))
        self.pv_front.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)   # 그림 크기가 칸을 키우지 않게
        self.pv_front.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pv_back = QLabel()
        self.pv_back.setMinimumSize(int(PREVIEW_W * 0.4), int(PREVIEW_W * 0.25))
        self.pv_back.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
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
        b_out = QPushButton(tr("바꾸기"))
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
                for c in (C_NAME, C_COMP, C_DEPT, C_TITLE, C_CELL, C_TEL, C_MAIL, C_BACK, C_DATE):
                    self.table.setItem(r, c, QTableWidgetItem(""))
                self.table.item(r, C_DATE).setText(it.scanned)
                f = QTableWidgetItem(tr("(읽는 중)"))
                f.setFlags(f.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, C_FILE, f)
        finally:
            self._loading = False

    @staticmethod
    def _choices(cands, cur):
        seen = []
        for t in [cur] + [c.get("text", "") for c in cands or []]:
            if t and t not in seen:
                seen.append(t)
        return seen

    def choices(self, r, col) -> list:
        """그 칸의 고르기 후보(검사·위치 지정이 본다)."""
        it = self.table.item(r, col)
        return list(it.data(CHOICES) or []) if it is not None else []

    def cell(self, r, col) -> str:
        it = self.table.item(r, col)
        return it.text().strip() if it is not None else ""

    def set_cell(self, r, col, text):
        """칸 값을 바꾼다 — 사람이 고친 것과 같은 길(itemChanged → `_on_edit`)."""
        it = self.table.item(r, col)
        if it is not None:
            it.setText(text)

    def _on_item_ready(self, r, res, edit):
        self._pending.append((r, res, edit))
        if not self._drain.isActive():
            self._drain.start()

    def _drain_pending(self):
        from PyQt6.QtCore import QElapsedTimer
        clock = QElapsedTimer()
        clock.start()
        self.table.setUpdatesEnabled(False)
        try:
            while self._pending and clock.elapsed() < FILL_BUDGET_MS:
                self._set_row(*self._pending.pop(0))
        finally:
            self.table.setUpdatesEnabled(True)
        if not self._pending:
            self._drain.stop()

    def _load_learned(self):
        """배운 것(§5.11) — 이름 가중치·양식 위치·도메인 표. 메인에서 짧게 읽는다(UI 대기 상한)."""
        try:
            from viewer.bizcard.learn import weights_of
            st = self._store()
            self._learned = {"weights": weights_of(st), "layouts": st.layouts(), "domains": st.domain_map(),
                             "corrections": st.corrections()}
        except Exception:
            self._learned = {"weights": None, "layouts": {}, "domains": {}, "corrections": {}}

    def _rescore(self, res):
        lr = getattr(self, "_learned", None)
        if lr is None:
            self._load_learned()
            lr = self._learned
        if not res or res.get("error"):
            return res
        return R.rescore(res, lr["weights"], lr["layouts"], lr["domains"], lr.get("corrections"))

    def _set_row(self, r, res, edit):
        it = self._items[r]
        it.raw = res
        res = self._rescore(res)
        it.result, it.edit = res, dict(edit or {})
        val = dict(res)
        val.update(it.edit)
        self._loading = True
        try:
            for col, cands, cur in ((C_NAME, res.get("name_cands"), val.get("name", "")),
                                    (C_COMP, res.get("company_cands"), R.strip_corp(val.get("company", "")))):
                itm = self.table.item(r, col)
                itm.setText(cur or "")
                itm.setData(CHOICES, self._choices(cands, cur))
                itm.setData(FREE, True)
            ph = [tuple(x) for x in (val.get("phones") or [])]
            self.table.item(r, C_DEPT).setText(val.get("dept", ""))
            self.table.item(r, C_TITLE).setText(val.get("title", ""))
            self.table.item(r, C_CELL).setText(val.get("cell", _first(ph, ("cell",))))
            self.table.item(r, C_TEL).setText(val.get("tel", _first(ph, ("work",))))
            self.table.item(r, C_MAIL).setText(val.get("email", (val.get("emails") or [""])[0]))
            if "scanned" in it.edit:
                self.table.item(r, C_DATE).setText(it.edit["scanned"])
            bk = self.table.item(r, C_BACK)
            if it.back or (it.pdf and res.get("back_promo") is not None):
                keep = it.edit.get("keep_back", not bool(res.get("back_promo")))
                bk.setText(tr("넣음") if keep else tr("넣지 않음"))
                bk.setData(CHOICES, [tr("넣음"), tr("넣지 않음")])
                bk.setFlags(bk.flags() | Qt.ItemFlag.ItemIsEditable)
            else:
                bk.setText(tr("없음"))
                bk.setData(CHOICES, [])
                bk.setFlags(bk.flags() & ~Qt.ItemFlag.ItemIsEditable)
            on = self.table.item(r, C_ON)
            on.setCheckState(Qt.CheckState.Checked if it.edit.get("on", not res.get("error")) else Qt.CheckState.Unchecked)
            need = set(res.get("need_check") or [])
            if res.get("error"):
                need |= {"name", "company", "contact"}
            it.need = bool(need)
            for c, k in ((C_NAME, "name"), (C_COMP, "company"), (C_CELL, "contact"), (C_MAIL, "contact")):
                itm = self.table.item(r, c)
                itm.setBackground(NEED_BG if k in need else QColor(0, 0, 0, 0))
                itm.setForeground(QColor("black") if k in need else self.table.palette().text().color())
            self._update_file(r)
        finally:
            self._loading = False
        self._apply_filter_row(r)

    def _row_values(self, r) -> dict:
        it = self._items[r]
        res = it.result or {}
        name = self.cell(r, C_NAME)
        comp = self.cell(r, C_COMP)
        keep = self.cell(r, C_BACK) == tr("넣음")
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
                "name": name, "company": comp, "dept": self.table.item(r, C_DEPT).text().strip(),
                "title": self.table.item(r, C_TITLE).text().strip(),
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
        edit = {k: v[k] for k in ("name", "company", "dept", "title", "cell", "tel", "email", "scanned", "on")}
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
        ang = int((it.result or {}).get("rotated") or 0) if not back else 0
        if ang:                                            # 돌려 읽은 명함은 돌린 그대로 보인다(PIL rotate = 반시계)
            img = img.transformed(QTransform().rotate(-ang))
        return QPixmap.fromImage(img)

    @staticmethod
    def _fit(lbl, pm):
        """칸 안에 비율 그대로 맞춘다 — 큰 그림·세로 명함도 넘치지 않게(사용자 보고 261117-10, 종전엔 폭에만 맞춰 세로가 넘쳤다)."""
        if pm is None or pm.isNull():
            lbl.setPixmap(QPixmap())
            return
        sz = lbl.contentsRect().size()
        w, h = max(80, sz.width() - 4), max(60, sz.height() - 4)
        lbl.setPixmap(pm.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    # ── 위치 지정(§5.11) ──

    def _source_image(self, it):
        """다시 읽을 앞면 그림(PIL) — PDF 는 300 dpi, 작은 그림은 3배, 돌려 읽었으면 같은 각도로."""
        from PIL import Image
        import io
        im = None
        if it.pdf:
            import fitz
            doc = fitz.open(it.pdf)
            try:
                im = Image.open(io.BytesIO(doc[0].get_pixmap(dpi=R.CONTACT_DPI).tobytes("png")))
            finally:
                doc.close()
        elif it.front:
            im = Image.open(it.front)
            im.load()
            if max(im.size) < R.SMALL_SIDE:
                im = R._upscale(im, R.NAME_UPSCALE)
        ang = int((it.result or {}).get("rotated") or 0)
        if im is not None and ang:
            im = im.rotate(ang, expand=True)
        return im

    def read_region(self, r, box, fld):
        """시험·도구용 — 같은 스레드에서 바로 읽는다(창에서는 `set_region` 이 배경에서 부른다). (칸 값, 자른 그림)."""
        im = self._source_image(self._items[r])
        return R.read_box(im, box, fld) if im is not None else ("", None)

    def _on_region(self, x0, y0, x1, y1, gpos):
        if self.region_busy:
            return                                 # 읽는 중에는 새 자리를 받지 않는다
        r = self.table.currentRow()
        if r < 0 or not self._items[r].result:
            return
        m = QMenu(self)
        labels = (("name", tr("이름")), ("company", tr("회사")), ("dept", tr("부서")), ("title", tr("직함")), ("cell", tr("휴대폰")),
                  ("tel", tr("전화")), ("email", tr("메일")))
        acts = {m.addAction(label): fld for fld, label in labels}
        a = m.exec(gpos)
        if a is None:
            return
        self.set_region(r, (x0, y0, x1, y1), acts[a])

    def _confirm_region(self, crop, text, fld):
        """고른 자리 그림과 읽은 글을 보여 주고 고치게 한다(261117-13 사용자 지시) — 넣을 글 또는 None(취소)."""
        dlg, ed = self.region_dialog(crop, text)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return ed.text().strip()

    def region_dialog(self, crop, text):
        """확인 창 만들기(검사가 안을 본다) — (창, 글 칸)."""
        from PyQt6.QtWidgets import QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("고른 자리"))
        v = QVBoxLayout(dlg)
        pic = QLabel()
        pm = QPixmap.fromImage(pil_to_qimage(crop))
        pic.setPixmap(pm.scaled(min(720, max(240, pm.width())), min(260, max(60, pm.height())),
                                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        pic.setFrameShape(QLabel.Shape.Box)
        v.addWidget(QLabel(tr("이 자리를 읽었습니다:")))
        v.addWidget(pic)
        ed = QLineEdit(text)
        ed.setPlaceholderText(tr("읽지 못했습니다 — 직접 적으세요"))
        v.addWidget(QLabel(tr("넣을 글 (틀리면 고치세요 — 고친 것은 이 PC 에서 배웁니다):")))
        v.addWidget(ed)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(tr("넣기"))
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        ed.selectAll()
        ed.setFocus()
        dlg._pic, dlg._edit = pic, ed
        return dlg, ed

    def set_region(self, r, box, fld, confirm: bool = True):
        """지정한 자리를 **배경에서** 읽기 시작한다 — 끝나면 신호로 `_region_done` 이 확인 창·칸 채우기를 잇는다
        (261117-14: 지역 루프로 기다리지 않는다 — 응답성 SOT '루프로 버티기' 금지). 읽는 동안은 다른 자리·줄·[적용] 을 막고,
        창을 닫으면 결과를 버린다. 끝난 값은 `last_region`(검사가 본다)."""
        if self.region_busy:
            return
        from viewer.workers import run_in_thread
        self.region_busy = True
        self.last_region = None
        self._region_ctx = (r, box, fld, confirm)
        for w in (self.table, self.pv_front, self.btn_apply):
            w.setEnabled(False)
        self.setCursor(Qt.CursorShape.BusyCursor)
        wk = RegionWorker(self._source_image, self._items[r], box, fld)
        wk.done.connect(self._region_done)         # 창의 메서드 — 창이 지워지면 Qt 가 연결을 끊는다
        keep = getattr(self._mw, "_thread_keep", None)
        run_in_thread(wk, keep if keep is not None else _KEEP)
        self._region_worker = wk

    def _region_done(self, out: dict):
        self.region_busy = False
        for w in (self.table, self.pv_front, self.btn_apply):
            w.setEnabled(True)
        self.unsetCursor()
        if self._closing:
            return                                  # 닫는 중이면 버린다
        r, box, fld, confirm = self._region_ctx
        self.last_region = self._finish_region(r, box, fld, confirm, out.get("val", ""), out.get("crop"))

    def _finish_region(self, r, box, fld, confirm, raw, crop):
        """읽은 글 → 확인 창(고쳐서 넣기) → 칸 채우기 → 교정·양식 배우기. 넣은 값(또는 "")."""
        corr = (getattr(self, "_learned", None) or {}).get("corrections", {}).get(fld, {})
        val = corr.get(raw, raw)                  # 전에 고친 적이 있는 오인식이면 고친 글을 먼저
        self._last_crop = crop
        if confirm:
            got = self._confirm_region(crop if crop is not None else self._source_image(self._items[r]), val, fld)
            if got is None:
                return ""
            if raw and got and got != raw:
                try:
                    self._store().correction_put(fld, raw, got)       # 교정 배우기(§5.15) — 이 PC 의 bizcard.db 에만
                except Exception:
                    pass
            val = got
        if not val:
            QMessageBox.information(self, tr("명함 관리"), tr("그 자리에서 글자를 읽지 못했습니다 — 상자를 조금 넓혀 다시 그리세요."))
            return ""
        col = {"name": C_NAME, "company": C_COMP, "dept": C_DEPT, "title": C_TITLE, "cell": C_CELL, "tel": C_TEL, "email": C_MAIL}[fld]
        self.set_cell(r, col, val)
        self._on_edit(r)
        if fld in ("name", "company", "title"):         # 부서 자리는 칸만 채운다 — 다시 매기기가 쓰는 양식은 이름·회사(§5.13)
            v = self._row_values(r)
            key = R.layout_key(v["emails"], v["urls"], v["company"])
            if key:
                try:
                    self._store().layout_put(key, fld, box, manual=True)
                except Exception:
                    pass
                self._load_learned()
                self._rescore_others(r)
        return val

    def _rescore_others(self, skip=-1):
        """배운 것이 바뀌면 사람이 아직 고치지 않은 줄을 다시 매긴다(OCR 없이)."""
        for i, it in enumerate(self._items):
            if i == skip or not getattr(it, "raw", None) or it.edit.get("name"):
                continue
            self._set_row(i, it.raw, it.edit)

    def _show_preview(self, r):
        if r < 0 or r >= len(self._items):
            return
        it = self._items[r]
        self._pv_src = (self._pix(it, False, 0), self._pix(it, True, 0))      # 원본 크기 — 창 크기가 바뀌면 다시 맞춘다
        self._fit(self.pv_front, self._pv_src[0])
        self._fit(self.pv_back, self._pv_src[1])
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
        self._worker.itemDone.connect(self._on_item_ready)    # 바로 채우지 않고 쌓아 두었다가 시간 상한 안에서(§5.14)
        self._worker.progressed.connect(self._on_progress)    # ★ 창의 메서드로 — 창이 지워지면 Qt 가 연결을 끊는다(람다는 남아 죽었다)
        self._worker.finishedAll.connect(self._on_done)
        # ★ 스레드 참조는 창이 아니라 앱(오래 사는 쪽)에 둔다 — 읽는 도중 창을 닫으면(WA_DeleteOnClose) 창과 함께
        #   아직 끝나는 중인 QThread 가 지워져 프로세스가 죽었다(261117-10 검사가 잡음, 종료 코드 127)
        keep = getattr(self._mw, "_thread_keep", None)
        if keep is None:
            keep = _KEEP
        run_in_thread(self._worker, keep)

    def _on_progress(self, d, t):
        self.bar.setValue(d)

    def _on_done(self, ok):
        self.bar.setFormat(tr("다 읽음 %v / %m") if ok else tr("멈춤 %v / %m"))
        if ok and self.table.currentRow() < 0 and self._items:
            self.table.setCurrentCell(0, C_NAME)

    def _stop_worker(self):
        w = self._worker
        if w is None or w.done_event.is_set():
            return                         # 끝난 워커는 이미 지워졌을 수 있다(deleteLater) — 건드리지 않는다
        for sig in (w.itemDone, w.progressed, w.finishedAll):   # 아직 도는 워커 — 닫기 전에 신호부터 끊는다(261117-10)
            try:
                sig.disconnect()
            except (TypeError, RuntimeError):
                pass
        w.request_cancel()
        w.done_event.wait(15)              # 한 장 읽기가 끝나야 멈춘다(최대 몇 초)

    def toggle_full(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
        QTimer.singleShot(0, self._refit)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.toggle_full()                 # 전체 화면에서 Esc 는 창을 닫지 않고 돌아온다
            return
        super().keyPressEvent(e)

    def _refit(self):
        src = getattr(self, "_pv_src", None)
        if src:
            self._fit(self.pv_front, src[0])
            self._fit(self.pv_back, src[1])

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._refit()

    def closeEvent(self, e):
        self._closing = True                       # 자리 읽기가 돌고 있으면 결과를 버린다(§5.16)
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
            QMessageBox.information(self, tr("명함 관리"), tr("적용할 명함이 없습니다 — 이름이 있고 '적용' 이 체크된 줄만 만듭니다."))
            return
        out = Path(self.ed_out.text().strip() or (self._folder / OUT_DIR))
        from viewer.bizcard.apply import apply_cards, ApplyCancelled
        from viewer.twoup import MergeCancelled
        box = {"done": []}
        results = {it.key: it.result for it in self._items if it.result}

        def job(progress):
            def _p(d, t):
                return progress(d, t, tr("정리본 만드는 중"))
            try:
                box["done"] = apply_cards(rows, out, self._db, _p)
            except ApplyCancelled:
                raise MergeCancelled()
            # 배우기(§5.11) — 이 PC 의 bizcard.db 에만. 배경 스레드에서 자기 연결로
            try:
                from viewer.bizcard.learn import learn_from
                from viewer.bizcard.store import BizcardStore
                st = BizcardStore(self._db)
                try:
                    box["learn"] = learn_from(st, rows, results)
                finally:
                    st.close()
            except Exception as e:                 # 명함 글은 싣지 않는다 — 종류만
                box["learn_err"] = type(e).__name__

        runner = getattr(self._mw, "_run_merge_job", None)
        if runner is not None:
            res = runner(job, tr("명함 관리"))
        else:                                   # 앱 밖(검사) — 바로
            job(lambda d, t, l: True)
            res = {"ok": True}
        done = box["done"]
        self._apply_box = box                     # 검사가 본다(배우기 오류 종류)
        self._tag(done)
        self.learned = box.get("learn")
        self._load_learned()
        self._rescore_others()
        if done:
            QMessageBox.information(self, tr("명함 관리"),
                                    tr("명함 {n}장을 정리 폴더에 만들었습니다.\n{path}").format(n=len(done), path=str(out)))
        elif not res.get("ok"):
            QMessageBox.warning(self, tr("명함 관리"), tr("정리본을 만들지 못했습니다."))
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
