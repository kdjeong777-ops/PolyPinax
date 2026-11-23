"""명함 읽기 — 확인 표 창 (명함 SOT §5.10, P2 · D10·D11·D12 · §5.11 위치 지정·배우기, 261117-9).

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
from viewer.bizcard import phone as PH          # 번호 꼴 한 곳(§5.11 '번호 꼴')
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

    phone_cols = ()            # 휴대폰·전화 열 — 치는 대로 하이픈, 넣을 때 적을 꼴(§5.11 '번호 꼴')

    def paint(self, painter, option, index):
        """지금 칸(←→ 로 옮기는 칸) — 고른 줄 안에서도 고르지 않은 칸처럼(바탕·글 색) 그리고 강조색 2px 테두리.
        고르기는 줄 단위라 칸 색만으로는 어느 칸인지 모른다(§5.10 '지금 칸', 사용자 보고 '좌우로 옮길 때 선택된 셀이 뭔지 모름')."""
        view = self.parent()
        if view is None or not hasattr(view, "currentIndex") or index != view.currentIndex() or not view.hasFocus():
            super().paint(painter, option, index)
            return
        from PyQt6.QtWidgets import QStyle, QStyleOptionViewItem
        from PyQt6.QtGui import QPen
        opt = QStyleOptionViewItem(option)
        opt.state &= ~QStyle.StateFlag.State_Selected     # 고른 줄 색을 빼고(글·'확인 필요' 바탕은 칸 그대로)
        opt.state &= ~QStyle.StateFlag.State_HasFocus     # 스타일의 점선 초점 틀 대신 아래 테두리
        pal = option.palette
        painter.save()
        painter.fillRect(option.rect, pal.color(pal.ColorRole.Base))
        painter.restore()
        super().paint(painter, opt, index)
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(pal.color(pal.ColorRole.Highlight), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(option.rect.adjusted(1, 1, -1, -1), 3, 3)
        painter.restore()

    def createEditor(self, parent, option, index):
        ch = index.data(CHOICES)
        if not ch:
            ed = super().createEditor(parent, option, index)
            if index.column() in self.phone_cols and isinstance(ed, QLineEdit):
                PH.attach(ed)
            return ed
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
        elif index.column() in self.phone_cols and isinstance(editor, QLineEdit):
            model.setData(index, PH.normalize(editor.text()), Qt.ItemDataRole.EditRole)
        else:
            super().setModelData(editor, model, index)
        hook = getattr(self, "on_committed", None)       # 261117-20: 값을 바꾸지 않고 넣어도 '사람이 확인함'
        if hook is not None:
            hook(index.row(), index.column())


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


def trash_paths(parent, mw, targets) -> set:
    """명함 지우기의 파일 쪽 — 한 길(261117-19 §5.20, 261117-4·-6 공용 — 책갈피창 `_trash_files` 와 같은 꼴). 명함 읽기 [삭제]·
    명함찾기 목록 지우기(§5.24 D18)가 함께 쓴다. 열린 PDF 는 먼저 놓고 → 앱 `_trash_bg`(배경·`pathutil.trash_when_free` —
    잠깐 잡히면 다시) → 지운 것은 `fileOpCompleted(경로, "")`, 놓았는데 못 지운 것은 `(경로, 경로)`. 못 지운 것은 공용 문구로 알린다.
    반환 = 못 지운 경로들."""
    from viewer.pathutil import norm_key, trash_when_free
    import viewer.widgets.bookmark_tree as _btm
    bt = getattr(mw, "bookmark_tree", None)
    released = []
    if bt is not None:
        try:
            cur = bt._open_file_now()
        except Exception:
            cur = None
        for p in targets:
            if cur and norm_key(p) == norm_key(cur):
                bt.releaseFileRequested.emit(p)
                released.append(p)
        if released:
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
    runner = getattr(mw, "_trash_bg", None)
    if runner is not None:                      # 앱 — 늘 이 길(배경)
        res = runner(targets, photo=True) or {}
    else:                                       # 앱 밖(검사) — 같은 휴지통 함수·같은 '잠깐 잡히면 다시'
        fn = _btm._trash_fn()
        res = {}
        for p in targets:
            try:
                trash_when_free(p, fn)
                res[p] = None
            except Exception as e:              # noqa: BLE001
                res[p] = e
    failed = [(p, e) for p, e in res.items() if e is not None]
    failed_set = {p for p, _e in failed}
    for p in targets:
        if bt is None:
            break
        if p in failed_set:
            if p in released:
                bt.fileOpCompleted.emit(p, p)    # 못 지움 — 놓았던 원본 다시 열기
        else:
            bt.fileOpCompleted.emit(p, "")       # 지움 — 책갈피창·사진 목록·본문(한 길)
    if failed:
        QMessageBox.warning(parent, tr("휴지통 이동 실패"), _btm._trash_fail_text(failed, photo=True))
    return failed_set


class BizcardImportDialog(QDialog):
    def __init__(self, folder, parent=None, db=None, out_dir=None):
        super().__init__(parent)
        PH.reload()                                    # 환경설정 '전화번호 기본 국가'(§5.11 '번호 꼴')
        self._mw = parent
        self._folder = Path(folder)
        self._db = db
        self._items = scan_folder(self._folder)
        self._worker = None
        self.region_busy = False                  # 고른 자리를 배경에서 읽는 중(§5.16) — 그동안 다른 자리·줄·[적용] 막음
        self.last_region = None
        self._closing = False
        self._loading = False
        self.setWindowTitle(tr("명함 읽기"))
        # 261117-13(사용자 지시 '전체화면으로도'): 최대화 단추 + F11 전체 화면
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowMinimizeButtonHint)
        from PyQt6.QtGui import QShortcut, QKeySequence
        QShortcut(QKeySequence("F11"), self, activated=self.toggle_full)
        self._del_key = (QShortcut, QKeySequence)
        self.resize(1280, 760)
        v = QVBoxLayout(self)

        top = QHBoxLayout()
        self.lbl_folder = QLabel(tr("폴더: {path}  ·  명함 {n}장").format(path=str(self._folder), n=len(self._items)))
        self.lbl_folder.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        top.addWidget(self.lbl_folder, 1)
        self.chk_need = QCheckBox(tr("확인 필요만"))
        self.chk_need.toggled.connect(lambda _c: self._apply_filter())
        top.addWidget(self.chk_need)
        # P5(명함 SOT §5.10 'P5', D17): 새 명함 — 아직 [적용] 하지 않은 줄만 보기 · 창을 연 채 새로 넣은 그림 읽기
        self.chk_new = QCheckBox(tr("새 명함만"))
        self.chk_new.setToolTip(tr("아직 [적용] 하지 않은 명함만 봅니다"))
        self.chk_new.toggled.connect(lambda _c: self._apply_filter())
        top.addWidget(self.chk_new)
        # 261120-31(§5.24.1 '사진에서 읽기'): [새 명함 입력] 창에서 넣은 사진만 — 그 길로 열 때만 보이고 켜진 채
        self._sent = set()
        self.chk_sent = QCheckBox(tr("입력한 명함만"))
        self.chk_sent.setToolTip(tr("[새 명함 입력]의 [사진에서 읽기]로 넣은 사진만 봅니다"))
        self.chk_sent.toggled.connect(lambda _c: self._apply_filter())
        self.chk_sent.setVisible(False)
        top.addWidget(self.chk_sent)
        self.btn_new = QPushButton(tr("새 명함 읽기"))
        self.btn_new.setToolTip(tr("폴더를 다시 훑어 창을 연 뒤에 넣은 명함 그림만 표 끝에 더하고 읽습니다"))
        self.btn_new.clicked.connect(lambda _c=False: self.read_new())
        top.addWidget(self.btn_new)
        self.btn_manual = QPushButton(tr("새 명함 입력"))   # [새 명함 읽기] 오른쪽(명함 SOT §5.24.1 '새 명함 입력', 261120-15)
        self.btn_manual.setToolTip(tr("새 명함이나 새 인물 정보를 손으로 넣습니다 — 명함 그림·인물 사진도 함께"))
        self.btn_manual.clicked.connect(lambda _c=False: self.new_manual())
        top.addWidget(self.btn_manual)
        self._applied_keys = None
        self.ed_date = QLineEdit()
        self.ed_date.setPlaceholderText("YYYY-MM-DD")
        self.ed_date.setFixedWidth(110)
        top.addWidget(self.ed_date)
        self.btn_date = QPushButton(tr("스캔일 일괄"))
        self.btn_date.setToolTip(tr("고른 줄의 스캔일을 왼쪽 날짜로 바꿉니다"))
        self.btn_date.clicked.connect(lambda _c=False: self._set_dates())
        top.addWidget(self.btn_date)
        # 261117-16(사용자 보고 '늘 한 줄만 다시 읽힘' — 표에는 늘 한 줄이 골라져 있다, 사용자 결정 '단추를 둘로'):
        #   [다시 읽기](메뉴) → '고른 줄 다시 읽기 (n장)' · '모두 다시 읽기 (N장)'
        self.btn_reread = QPushButton(tr("다시 읽기"))   # 메뉴 단추 — ▾ 없이 Qt 화살표(디자인 SOT §2.7)
        self.btn_reread.setToolTip(tr("지금의 인식으로 다시 읽습니다 — 고른 줄만 또는 모두. 손으로 고친 칸은 그대로 둡니다"))
        self._reread_menu = QMenu(self)
        self._reread_menu.aboutToShow.connect(self._fill_reread_menu)
        self.btn_reread.setMenu(self._reread_menu)
        top.addWidget(self.btn_reread)
        from viewer.widgets.icons import drop_button
        drop_button(self.btn_reread)
        # 명함 SOT §5.26(D31): 한 사진에 명함 여럿 — 창을 열 때·새 명함 때 저절로 세고, 이 단추는 고른 줄을 손으로
        self.btn_multi = QPushButton(tr("다중 명함 나누기"))
        self.btn_multi.setToolTip(tr("고른 줄의 사진에 명함이 여럿이면 명함마다 잘라 따로 읽습니다 — 찾은 테두리를 고치거나 새로 그릴 수 있습니다"))
        self.btn_multi.clicked.connect(lambda _c=False: self.split_selected())
        top.addWidget(self.btn_multi)
        # P3(명함 SOT §5.8): vCard 내보내기·기존 vCard 에 합치기
        self.btn_vcard = QPushButton("vCard")
        self.btn_vcard.setToolTip(tr("적용한 명함을 vCard(.vcf) 로 내보내거나 기존 vCard 에 합칩니다 — 구글 연락처·휴대폰에서 읽습니다"))
        self._vcard_menu = QMenu(self)
        self._vcard_menu.aboutToShow.connect(self._fill_vcard_menu)
        self.btn_vcard.setMenu(self._vcard_menu)
        top.addWidget(self.btn_vcard)
        drop_button(self.btn_vcard)
        self.last_vcard = None
        self.btn_del = QPushButton(tr("삭제"))
        self.btn_del.setToolTip(tr("고른 명함의 원본 그림·PDF 와 만든 정리본을 휴지통으로 보내고 기록을 지웁니다 (Delete)"))
        self.btn_del.clicked.connect(lambda _c=False: self.delete_selected())
        top.addWidget(self.btn_del)
        self.btn_full = QPushButton(tr("전체 화면"))
        self.btn_full.setToolTip(tr("명함 읽기 창을 화면 가득 — 다시 누르거나 F11·Esc 로 돌아옵니다"))
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
        _dlg = ChoiceDelegate(self.table)
        _dlg.on_committed = self._on_committed
        _dlg.phone_cols = (C_CELL, C_TEL)
        self.table.setItemDelegate(_dlg)
        _QS, _QK = self._del_key
        _dk = _QS(_QK(_QK.StandardKey.Delete), self.table, activated=self.delete_selected)
        _dk.setContext(Qt.ShortcutContext.WidgetShortcut)              # 표에서만(칸을 고치는 중이면 글 칸이 먼저 받는다)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.SelectedClicked
                                   | QAbstractItemView.EditTrigger.EditKeyPressed | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.table.itemChanged.connect(self._on_item_changed)
        self._pending = []                       # 배경에서 온 결과 — 시간 상한 안에서 나눠 채운다
        self._drain = QTimer(self)
        self._drain.setInterval(15)
        self._drain.timeout.connect(self._drain_pending)
        self.table.currentCellChanged.connect(lambda r, *_: self._show_preview(r))
        # 머리말을 눌러 정렬(§5.10 '정렬') — 표 자체 정렬(setSortingEnabled)은 줄 번호 = self._items 차례를 깨므로 쓰지 않고 sort_by 로
        self._sort = (-1, Qt.SortOrder.AscendingOrder)
        hh.setSectionsClickable(True)
        hh.setSortIndicatorShown(False)
        hh.sectionClicked.connect(self._on_head_clicked)
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
        for b in self.findChildren(QPushButton):      # 칸에서 Enter 가 [새 명함 읽기] 를 누르지 않게 — 기본 단추 없음(§5.24.1 'Enter', 261117-59)
            b.setAutoDefault(False)
            b.setDefault(False)

        self._fill_empty_rows()
        self.multi_found = []
        self.multi_dlg = None
        QTimer.singleShot(0, self._start)           # 다 읽은 뒤 아직 안 센 사진을 다중 명함인지 센다(§5.26, _on_done)

    # ── 표 ──
    def _fill_empty_rows(self, start: int = 0):
        self._loading = True
        try:
            for r, it in enumerate(self._items[start:], start):
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
        # 워커가 보낸 r 은 워커를 시작할 때의 줄 번호 — 그사이 정렬했을 수 있어 그 명함 자체로 쌓는다(§5.10 '정렬')
        w = self.sender()
        item = None
        if w is not None and hasattr(w, "_rows") and hasattr(w, "_items"):
            m = getattr(w, "_row_item", None)
            if m is None:
                m = w._row_item = dict(zip(w._rows, w._items))
            item = m.get(r)
        if item is None and 0 <= r < len(self._items):
            item = self._items[r]
        if item is None:
            return
        self._pending.append((item, res, edit))
        if not self._drain.isActive():
            self._drain.start()

    def _row_of(self, item) -> int:
        """명함(_items 의 원소) → 지금 줄 번호, 없으면 -1. 표를 정렬·더하기·지우기 해도 맞게(필요할 때만 다시 셈)."""
        ix = getattr(self, "_row_ix", None) or {}
        r = ix.get(id(item), -1)
        if not (0 <= r < len(self._items) and self._items[r] is item):
            self._row_ix = {id(x): i for i, x in enumerate(self._items)}
            r = self._row_ix.get(id(item), -1)
        return r

    def _on_head_clicked(self, col: int):
        cur_col, order = self._sort
        if col == cur_col:
            order = Qt.SortOrder.DescendingOrder if order == Qt.SortOrder.AscendingOrder else Qt.SortOrder.AscendingOrder
        else:
            order = Qt.SortOrder.AscendingOrder
        self.sort_by(col, order)

    def sort_by(self, col: int, order=Qt.SortOrder.AscendingOrder):
        """그 열로 줄을 정렬 — 칸을 꺼내 새 자리에 끼우고 self._items 도 같은 차례로. 고른 줄·지금 칸·거르기는 그 명함을 따라간다."""
        n = len(self._items)
        if n == 0 or self.region_busy:
            return
        t = self.table
        if col == C_ON:
            keys = [0 if (t.item(r, C_ON) and t.item(r, C_ON).checkState() == Qt.CheckState.Checked) else 1 for r in range(n)]
            keyf = lambda r: keys[r]
        else:
            txt = [(t.item(r, col).text().strip() if t.item(r, col) else "") for r in range(n)]
            keyf = lambda r: (txt[r] == "", txt[r].casefold())
        desc = order == Qt.SortOrder.DescendingOrder
        rows = sorted(range(n), key=keyf, reverse=desc)
        if desc and col != C_ON:                       # 내림차순에서도 빈 칸은 끝
            rows = [r for r in rows if txt[r]] + [r for r in rows if not txt[r]]
        cur_item = self._items[t.currentRow()] if 0 <= t.currentRow() < n else None
        cur_col = max(0, t.currentColumn())
        sel = {id(self._items[i.row()]) for i in t.selectedIndexes() if 0 <= i.row() < n}
        ncol = t.columnCount()
        self._loading = True
        t.setUpdatesEnabled(False)
        t.blockSignals(True)
        try:
            cells = [[t.takeItem(r, c) for c in range(ncol)] for r in range(n)]
            for new_r, old_r in enumerate(rows):
                for c in range(ncol):
                    if cells[old_r][c] is not None:
                        t.setItem(new_r, c, cells[old_r][c])
            self._items = [self._items[r] for r in rows]   # 새 목록 — 도는 워커는 옛 목록을 그대로 쥔다
            self._row_ix = None
            t.clearSelection()
            for r, it in enumerate(self._items):
                if id(it) in sel:
                    t.selectRow(r)
        finally:
            t.blockSignals(False)
            t.setUpdatesEnabled(True)
            self._loading = False
        self._sort = (col, order)
        hh = t.horizontalHeader()
        hh.setSortIndicatorShown(True)
        hh.setSortIndicator(col, order)
        self._apply_filter()
        if cur_item is not None:
            r = self._row_of(cur_item)
            from PyQt6.QtCore import QItemSelectionModel
            t.selectionModel().setCurrentIndex(t.model().index(r, cur_col), QItemSelectionModel.SelectionFlag.NoUpdate)
            t.scrollTo(t.model().index(r, cur_col))

    def _drain_pending(self):
        from PyQt6.QtCore import QElapsedTimer
        clock = QElapsedTimer()
        clock.start()
        self.table.setUpdatesEnabled(False)
        try:
            while self._pending and clock.elapsed() < FILL_BUDGET_MS:
                item, res, edit = self._pending.pop(0)
                r = self._row_of(item)                     # 정렬·지우기 뒤에도 그 명함의 줄(§5.10 '정렬')
                if r >= 0:
                    self._set_row(r, res, edit)
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
            self.table.item(r, C_CELL).setText(PH.normalize(val.get("cell", _first(ph, ("cell",)))))
            self.table.item(r, C_TEL).setText(PH.normalize(val.get("tel", _first(ph, ("work",)))))
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
            it.need_set = need
            self._style_row(r)
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
        cell = PH.normalize(self.table.item(r, C_CELL).text())
        tel = PH.normalize(self.table.item(r, C_TEL).text())
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

    FIELD_COL = None           # (칸 이름, 열) — 확인 표시(261117-20)

    def _field_cols(self):
        return (("name", C_NAME), ("company", C_COMP), ("dept", C_DEPT), ("title", C_TITLE),
                ("cell", C_CELL), ("tel", C_TEL), ("email", C_MAIL))

    def confirmed(self, r) -> set:
        """사람이 확인한 칸 = 손으로 고친 칸 + 값을 바꾸지 않고 넣은 칸·확인 창 [넣기](`_ok`)."""
        ed = self._items[r].edit or {}
        return {k for k, _c in self._field_cols() if k in ed} | set(ed.get("_ok") or [])

    def _style_row(self, r):
        """261117-20(사용자 지시): 사람이 확인한 칸은 **굵게**, 확인한 '확인 필요' 칸은 노란 바탕을 걷고 보통 색으로."""
        it = self._items[r]
        need = getattr(it, "need_set", set())
        ok = self.confirmed(r)
        was = self._loading
        self._loading = True
        try:
            for k, c in self._field_cols():
                itm = self.table.item(r, c)
                if itm is None:
                    continue
                f = itm.font()
                f.setBold(k in ok)
                itm.setFont(f)
                flag = (k in need) or (k in ("cell", "email") and "contact" in need)
                if flag and k not in ok:
                    itm.setBackground(NEED_BG)
                    itm.setForeground(QColor("black"))
                else:
                    itm.setData(Qt.ItemDataRole.BackgroundRole, None)
                    itm.setData(Qt.ItemDataRole.ForegroundRole, None)
        finally:
            self._loading = was
        it.need = bool({k for k in need if k not in ok} - ({"contact"} if {"cell", "email"} & ok else set()))

    def mark_ok(self, r, fld):
        """그 칸을 사람이 확인한 것으로(값은 그대로) — 기록(`_ok`)에 남기고 굵게."""
        it = self._items[r]
        if not it.result or fld not in dict(self._field_cols()):
            return
        ed = dict(it.edit or {})
        ok = list(ed.get("_ok") or [])
        if fld not in ok:
            ok.append(fld)
            ed["_ok"] = ok
            it.edit = ed
            try:
                self._store().edit_put(it.key, ed)
            except Exception:
                pass
        self._style_row(r)
        self._apply_filter_row(r)

    def _on_committed(self, r, c):
        col2f = {c2: k for k, c2 in self._field_cols()}
        if c in col2f and 0 <= r < len(self._items):
            self.mark_ok(r, col2f[c])

    def _on_edit(self, r):
        if self._loading or not self._items[r].result:
            return
        self._loading = True
        try:
            self._update_file(r)
        finally:
            self._loading = False
        v = self._row_values(r)
        edit = self._manual_of(r, v)                # 261117-15: 인식값과 **다른** 칸만 — [다시 읽기] 가 손으로 고친 칸을 가려 지킨다
        ok = (self._items[r].edit or {}).get("_ok")
        if ok:
            edit["_ok"] = list(ok)                  # 확인 표시(261117-20)는 지킨다
        self._items[r].edit = edit
        if self._learn_table_edits(r, edit):         # 261117-17: 표에서 고친 오인식도 교정으로 — 곧바로 쓰이게 다시 불러옴
            self._load_learned()
        try:
            self._store().edit_put(self._items[r].key, edit)
        except Exception:
            pass
        self._style_row(r)
        self._apply_filter_row(r)

    EDIT_KEYS = ("name", "company", "dept", "title", "cell", "tel", "email", "scanned", "on", "keep_back")

    def _auto_values(self, r) -> dict:
        """그 줄의 인식값(사람이 손대지 않았을 때 칸에 들어가는 값)."""
        it = self._items[r]
        res = it.result or {}
        ph = [tuple(x) for x in (res.get("phones") or [])]
        has_back = bool(it.back or (it.pdf and res.get("back_promo") is not None))
        return {"name": res.get("name", ""), "company": R.strip_corp(res.get("company", "")), "dept": res.get("dept", ""),
                "title": res.get("title", ""), "cell": _first(ph, ("cell",)), "tel": _first(ph, ("work",)),
                "email": (res.get("emails") or [""])[0], "scanned": it.scanned, "on": not res.get("error"),
                "keep_back": (not bool(res.get("back_promo"))) if has_back else False}

    def _manual_of(self, r, vals: dict) -> dict:
        """손으로 고친 칸 = 인식값과 다른 칸만."""
        auto = self._auto_values(r)
        return {k: vals[k] for k in self.EDIT_KEYS if k in vals and vals[k] != auto.get(k)}

    LEARN_FIELDS = ("name", "company", "dept", "title")
    LEARN_SIMILAR = 0.5        # 인식값과 이만큼 닮았으면 '오인식을 고친 것' 으로 배운다(아니면 다른 후보를 고른 것)

    def _learn_table_edits(self, r, manual: dict):
        """표에서 직접 고친 칸도 교정으로 배운다(261117-17 사용자 질문 '고친 방법을 학습해 적용하나') — 인식값과 닮은 것만
        (몇 글자 오인식 → 고친 글). 전혀 다른 값은 다른 후보를 고른 것이라 배우지 않는다. 이 PC 의 bizcard.db 에만."""
        import difflib
        auto = self._auto_values(r)
        n = 0
        for k in self.LEARN_FIELDS:
            a, b = (auto.get(k) or "").strip(), (manual.get(k) or "").strip()
            if a and b and a != b and difflib.SequenceMatcher(None, a, b).ratio() >= self.LEARN_SIMILAR                     and R.correction_ok(k, a, b):        # 다른 값을 고른 것(늘이기·다른 직함)은 배우지 않는다(261117-18)
                try:
                    self._store().correction_put(k, a, b)
                    n += 1
                except Exception:
                    pass
        return n

    def delete_selected(self, rows=None, ask: bool = True) -> int:
        """고른 명함 삭제(261117-19 사용자 지시·결정 '원본 파일까지 휴지통') — 원본 그림(앞·뒤)·원본 PDF·만든 정리본을
        **휴지통**으로(앱의 `_trash_bg` — 배경·잠깐 잡히면 다시), 인식 기록·학습 표본·명함 DB 행을 지우고 표에서 뺀다.
        확인 창을 거친다. 읽는 중·자리 읽는 중에는 하지 않는다. 반환 = 지운 명함 수."""
        if (self._worker is not None and not self._worker.done_event.is_set()) or self.region_busy:
            QMessageBox.information(self, tr("삭제"), tr("지금 읽는 중입니다 — 다 읽은 뒤에 다시 하세요."))
            return 0
        rows = sorted(set(rows if rows is not None else self.selected_rows_idx()))
        rows = [r for r in rows if 0 <= r < len(self._items)]
        if not rows:
            return 0
        st = self._store()
        files = []
        outs_of = {}
        for r in rows:
            it = self._items[r]
            files += [p for p in (it.front, it.back, it.pdf) if p and os.path.exists(p)]
            old = st.card_by_src(it.key)
            outs_of[r] = [os.path.realpath(p) for p in ((old or {}).get("front"), (old or {}).get("back")) if p]   # DB 는 소문자 열쇠 — 실제 경로로
        outs = [p for r in rows for p in outs_of[r] if os.path.exists(p)]
        if ask and QMessageBox.question(
                self, tr("삭제"),
                tr("명함 {n}장을 지웁니다 — 원본 파일까지 휴지통으로 보냅니다(원본 {f}개·정리본 {o}개). 인식 기록도 지웁니다.").format(
                    n=len(rows), f=len(files), o=len(outs))) != QMessageBox.StandardButton.Yes:
            return 0
        failed_set = trash_paths(self, self._mw, list(dict.fromkeys(files + outs)))
        gone = []
        for r in rows:                              # 한 파일이라도 못 지운 명함은 기록을 남긴다(일부만 휴지통으로 간 경우)
            it = self._items[r]
            mine = [p for p in (it.front, it.back, it.pdf) if p] + outs_of.get(r, [])
            if any(p in failed_set for p in mine):
                continue
            try:
                st.delete_src(it.key)
            except Exception:
                pass
            gone.append(r)
        for r in sorted(gone, reverse=True):
            self.table.removeRow(r)
            del self._items[r]
        self.lbl_folder.setText(tr("폴더: {path}  ·  명함 {n}장").format(path=str(self._folder), n=len(self._items)))
        self.last_deleted = len(gone)
        return len(gone)

    def selected_rows_idx(self) -> list:
        return sorted({i.row() for i in self.table.selectedIndexes()})

    def _fill_reread_menu(self):
        m = self._reread_menu
        m.clear()
        sel = self.selected_rows_idx()
        busy = self._worker is not None and not self._worker.done_event.is_set()   # 읽는 중에는 둘 다 끔
        a1 = m.addAction(tr("고른 줄 다시 읽기 ({n}장)").format(n=len(sel)))
        a1.setEnabled(bool(sel) and not busy)                                       # 고른 줄이 없으면 끔(숨기지 않음)
        a1.triggered.connect(lambda _c=False, rs=list(sel): self.reread(rs))
        a2 = m.addAction(tr("모두 다시 읽기 ({n}장)").format(n=len(self._items)))
        a2.setEnabled(bool(self._items) and not busy)
        a2.triggered.connect(lambda _c=False: self.reread(list(range(len(self._items)))))

    def reread(self, rows=None, ask: bool = True):
        """[다시 읽기](261117-15 사용자 지시) — 고른 줄(없으면 모두)을 캐시를 건너뛰고 지금의 인식으로 다시 읽는다.
        손으로 고친 칸은 지킨다(옛 기록은 인식값과 같은 칸을 '손대지 않음' 으로 본다). 배경·나눠 채우기는 처음 읽기와 같은 길."""
        if self._worker is not None and not self._worker.done_event.is_set():
            QMessageBox.information(self, tr("다시 읽기"), tr("지금 읽는 중입니다 — 다 읽은 뒤에 다시 하세요."))
            return False
        if rows is None:
            rows = sorted({i.row() for i in self.table.selectedIndexes()})
        rows = [r for r in (rows or range(len(self._items))) if 0 <= r < len(self._items)]
        if not rows:
            return False
        if ask and len(rows) > 20 and QMessageBox.question(
                self, tr("다시 읽기"), tr("명함 {n}장을 다시 읽습니다 — 한 장에 몇 초씩 걸립니다. 손으로 고친 칸은 그대로 둡니다.").format(n=len(rows))) \
                != QMessageBox.StandardButton.Yes:
            return False
        learned_n = 0
        for r in rows:                              # 옛 기록에서도 손으로 고친 칸만 남긴다
            it = self._items[r]
            if it.result and it.edit:
                vals = dict(self._auto_values(r))
                vals.update(it.edit)
                it.edit = self._manual_of(r, vals)
                learned_n += self._learn_table_edits(r, it.edit)   # 지금까지 표에서 고친 것도 배운다(261117-17)
                try:
                    self._store().edit_put(it.key, it.edit)
                except Exception:
                    pass
            self.table.item(r, C_FILE).setText(tr("(다시 읽는 중)"))
        if learned_n:
            self._load_learned()                    # 다시 읽은 결과에 곧바로 쓰이게
        self.reread_learned = learned_n
        self._start(rows)
        return True

    # ── vCard (P3, 명함 SOT §5.8) ──
    def _fill_vcard_menu(self):
        m = self._vcard_menu
        m.clear()
        sel = self.selected_rows_idx()
        alln = list(range(len(self._items)))
        for i, (text, rows, merge) in enumerate((
                (tr("고른 명함 → vCard 파일 ({n}장)"), sel, False),
                (tr("모든 명함 → vCard 파일 ({n}장)"), alln, False),
                (tr("고른 명함을 기존 vCard 에 합치기 ({n}장)"), sel, True),
                (tr("모든 명함을 기존 vCard 에 합치기 ({n}장)"), alln, True))):
            if i == 2:
                m.addSeparator()
            a = m.addAction(text.format(n=len(rows)))
            a.setEnabled(bool(rows))                                  # 고른 줄이 없으면 끔(숨기지 않음)
            a.triggered.connect(lambda _c=False, rs=list(rows), mg=merge: self.export_vcard(rs, merge=mg))

    def vcard_cards(self, rows):
        """(명함 DB 행들, 빠진 수) — [적용] 한 명함만(정리본 파일 이름이 있어야 드라이브 링크를 만든다)."""
        st = self._store()
        cards, skipped = [], 0
        for r in rows:
            if not 0 <= r < len(self._items):
                continue
            c = st.card_by_src(self._items[r].key)
            if c and (c.get("name") or "").strip():
                cards.append(c)
            else:
                skipped += 1
        return cards, skipped

    def export_vcard(self, rows, merge: bool = False, path=None, existing=None, drive=None):
        """vCard 내보내기·합치기. path·existing·drive 를 주면 묻지 않는다(검사). 반환 = 통계(숫자·경로) 또는 None."""
        from viewer.bizcard import vcard as V
        from viewer import bg_write
        quiet = path is not None or existing is not None
        cards, skipped = self.vcard_cards(rows)
        if not cards:
            if not quiet:
                QMessageBox.information(self, "vCard", tr("내보낼 명함이 없습니다 — [적용] 한 명함만 vCard 로 내보냅니다."))
            return None
        st = self._store()
        if drive is None:
            default = st.meta_get("drive_folder", None)
            if default is None:
                default = Path(self.ed_out.text().strip() or str(self._folder)).name
            from PyQt6.QtWidgets import QInputDialog
            drive, ok = QInputDialog.getText(self, "vCard", tr("구글 드라이브의 명함 폴더 이름 — 메모에 '폴더/파일 이름' 과 드라이브 검색 주소를 넣습니다(비우면 넣지 않음):"),
                                             text=default)
            if not ok:
                return None
            drive = drive.strip()
            st.meta_set("drive_folder", drive)
        lang = "en" if str(language()).startswith("en") else "ko"
        word = tr("명함")
        if merge:
            if existing is None:
                existing, _f = QFileDialog.getOpenFileName(self, tr("합칠 기존 vCard"), str(self._folder), "vCard (*.vcf)")
                if not existing:
                    return None
            try:
                old = bg_write.read_text(existing, encoding="utf-8-sig")
            except UnicodeDecodeError:                                # 옛 휴대폰 내보내기(cp949)
                old = Path(existing).read_text(encoding="cp949", errors="replace")
            text, stats = V.merge_text(old, cards, drive, lang, word)
            path = V.merged_path(existing, tr("합침"))
        else:
            if path is None:
                start = Path(self.ed_out.text().strip() or str(self._folder)) / (tr("명함") + ".vcf")
                path, _f = QFileDialog.getSaveFileName(self, tr("vCard 로 내보내기"), str(start), "vCard (*.vcf)")
                if not path:
                    return None
            text = V.export_text(cards, drive, lang, word)
            stats = {"cards": len(cards)}
        bg_write.submit(path, text, delay=0)                          # 드라이브 폴더·백신이 붙들어도 메인은 서지 않는다
        stats.update(skipped=skipped, path=str(path))
        self.last_vcard = stats
        if not quiet:
            if merge:
                msg = tr("기존 vCard 에 합쳤습니다 — 같은 사람 {m}명(더한 줄 {l}), 새 사람 {a}명.").format(
                    m=stats["merged"], l=stats["lines"], a=stats["added"])
            else:
                msg = tr("vCard 에 {n}장을 썼습니다.").format(n=stats["cards"])
            if skipped:
                msg += "\n" + tr("적용하지 않은 {k}장은 빠졌습니다.").format(k=skipped)
            QMessageBox.information(self, "vCard", msg + "\n" + str(path))
        return stats

    # ── 다중 명함 사진 나누기 (명함 SOT §5.26, D31) ──
    def _multi_busy(self) -> bool:
        w = getattr(self, "_multi_worker", None)
        return (w is not None and not w.done_event.is_set()) or getattr(self, "_split_busy", False) \
            or (self.multi_dlg is not None and self.multi_dlg.isVisible())

    def _multi_unseen(self, paths) -> list:
        from viewer.bizcard import multisplit as M
        from viewer.bizcard.store import source_sig
        seen = self._store().meta_get(M.SEEN_KEY) or {}
        return [p for p in paths if seen.get(os.path.normcase(os.path.abspath(p))) != source_sig([p])]

    def _multi_pass(self, paths, after, force: bool = False, show_all: bool = False):
        """사진들(None = 폴더의 세어 볼 사진 중 아직 안 센 것)을 배경에서 세고, 여럿이면 확인 창. 끝나면 after()
        (나눴으면 폴더를 다시 훑은 뒤 모두 읽기)."""
        from viewer.bizcard import multisplit as M
        from viewer.bizcard.importer import MultiWorker
        if paths is None:
            paths = self._multi_unseen(M.candidates(self._folder))
        self._bar_saved = (self.bar.minimum(), self.bar.maximum(), self.bar.value(), self.bar.format())   # 세기 전 막대(_multi_idle 이 되돌림)
        if not paths:
            after()
            return
        self.multi_found = []
        self._multi_after = after
        w = MultiWorker(paths, self._db, force=force, show_all=show_all)
        self._multi_worker = w
        self.bar.setRange(0, max(1, len(paths)))
        self.bar.setValue(0)
        self.bar.setFormat(tr("다중 명함 찾는 중 %v / %m"))
        w.found.connect(self._multi_one)
        w.progressed.connect(self._on_progress)
        w.finishedAll.connect(self._multi_done)
        from viewer.workers import run_in_thread
        keep = getattr(self._mw, "_thread_keep", None)
        run_in_thread(w, keep if keep is not None else _KEEP)

    def _multi_one(self, path, quads, pv):
        self.multi_found.append((path, quads, pv))

    def _multi_done(self, ok):
        after = getattr(self, "_multi_after", None) or (lambda: None)
        if not ok or not self.multi_found or self._closing:
            after()
            return
        from viewer.widgets.bizcard_multi_dialog import MultiSplitDialog
        st = self._store()
        old = {p: 1 for p, _q, _v in self.multi_found if st.card_by_src(p) is not None}
        dlg = MultiSplitDialog(self.multi_found, self, old_counts=old)
        self.multi_dlg = dlg
        dlg.finished.connect(lambda _r: self._multi_chosen(dlg, after))
        dlg.open()                                   # 창 모달 — 닫히면 _multi_chosen

    def _multi_chosen(self, dlg, after):
        from viewer.bizcard import multisplit as M
        from viewer.bizcard.store import source_sig
        st = self._store()
        if dlg.skipped:                              # 나누지 않기로 한 사진 — 다음엔 묻지 않는다
            seen = dict(st.meta_get(M.SEEN_KEY) or {})
            for p in dlg.skipped:
                seen[os.path.normcase(os.path.abspath(p))] = source_sig([p])
            st.meta_set(M.SEEN_KEY, seen)
        if not dlg.jobs:
            after()
            return
        from viewer.bizcard.importer import SplitWorker
        from viewer.workers import run_in_thread
        self._split_busy = True
        self.bar.setFormat(tr("다중 명함 자르는 중"))
        w = SplitWorker(dlg.jobs)
        self._split_worker = w
        w.done.connect(self._split_done)
        keep = getattr(self._mw, "_thread_keep", None)
        run_in_thread(w, keep if keep is not None else _KEEP)

    def _split_done(self, out):
        """잘랐으면 그 원본으로 만든 예전 명함(한 장으로 잘못 읽힌 것)은 지우고(휴지통, D31) 폴더를 다시 훑어 모두 읽는다."""
        from viewer.bizcard import people as P
        if self._closing:
            self._split_busy = False
            return
        st = self._store()
        cut = [p for p, made in out.items() if made]
        for p in cut:                                  # 261120-31: 입력한 사진을 나눴으면 잘라낸 것도 '입력한 명함만' 안에
            if os.path.normcase(os.path.abspath(p)) in self._sent:
                self._sent |= {os.path.normcase(os.path.abspath(m)) for m in out[p]}
        self.multi_split = {p: list(made) for p, made in out.items() if made}
        files, olds = [], []
        for p in cut:
            c = st.card_by_src(p)
            if c is not None:
                olds.append(p)
                files += [x for grp in P.card_files(c)[1:] for x in grp]      # 정리본·인물 사진(원본은 이미 '다중 원본' 으로)
        failed = trash_paths(self, self._mw, files) if files else set()
        for p in olds:
            c = st.card_by_src(p)
            if c is not None and not any(x in failed for grp in P.card_files(c)[1:] for x in grp):
                st.delete_src(p)
        self._split_busy = False
        if self._closing:
            return
        self._items = scan_folder(self._folder)
        self.table.setRowCount(0)
        self.table.setRowCount(len(self._items))
        self._fill_empty_rows(0)
        self._applied_keys = None
        self.lbl_folder.setText(tr("폴더: {path}  ·  명함 {n}장").format(path=str(self._folder), n=len(self._items)))
        self._apply_filter()                           # 261120-31: 다시 훑은 줄에도 거르기(입력한 명함만·새 명함만·확인 필요만)
        self._start()

    def split_selected(self):
        """[다중 명함 나누기] — 고른 줄의 사진을 다시 세어(한 장 미만도) 확인 창에서 테두리를 고치거나 그려 나눈다."""
        if (self._worker is not None and not self._worker.done_event.is_set()) or self._multi_busy():
            QMessageBox.information(self, tr("다중 명함 나누기"), tr("지금 읽는 중입니다 — 다 읽은 뒤에 다시 하세요."))
            return False
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        paths = [self._items[r].front for r in rows if 0 <= r < len(self._items) and self._items[r].front
                 and not self._items[r].back]
        if not paths:
            QMessageBox.information(self, tr("다중 명함 나누기"), tr("나눌 사진 줄을 고르세요(뒷면이 짝지어진 명함은 빼고)."))
            return False
        self._multi_pass(paths, lambda: None, force=True, show_all=True)
        return True

    def _store(self):
        if getattr(self, "_st", None) is None:
            from viewer.bizcard.store import BizcardStore
            self._st = BizcardStore(self._db, ui=True)
        return self._st

    def _apply_filter_row(self, r):
        only = self.chk_need.isChecked()          # 확인한 칸은 '확인 필요' 에서 빠진다(261117-20 — `need` 는 `_style_row` 가 갱신)
        hide = bool(only and not getattr(self._items[r], "need", True))
        if not hide and self.chk_new.isChecked():  # P5: 새 명함만 — 적용한(명함 DB 행이 있는) 줄은 숨김
            hide = os.path.normcase(os.path.abspath(str(self._items[r].key))) in self.applied_keys()
        if not hide and self._sent and self.chk_sent.isChecked():   # 261120-31: 입력한 명함만
            hide = os.path.normcase(os.path.abspath(str(self._items[r].front or self._items[r].key))) not in self._sent
        self.table.setRowHidden(r, hide)

    def applied_keys(self) -> set:
        """적용한 원천(명함 DB 행이 있는 src_key, normcase) — 한 번 읽어 두고 [적용]·[새 명함 읽기] 뒤 다시."""
        if self._applied_keys is None:
            try:
                self._applied_keys = {r[0] for r in self._store().con.execute("SELECT src_key FROM cards") if r[0]}
            except Exception:
                self._applied_keys = set()
        return self._applied_keys

    def _apply_filter(self):
        for r in range(len(self._items)):
            self._apply_filter_row(r)

    def read_new(self, ask: bool = True) -> int:
        """[새 명함 읽기](P5, D17) — 폴더를 다시 훑어 표에 없는 원천만 끝에 더하고 그 줄들만 읽는다. 반환 = 더한 장 수.
        다 읽은 뒤 새 사진이 다중 명함인지 센다(§5.26, _on_done)."""
        if (self._worker is not None and not self._worker.done_event.is_set()) or self.region_busy or self._multi_busy():
            if ask:
                QMessageBox.information(self, tr("새 명함 읽기"), tr("지금 읽는 중입니다 — 다 읽은 뒤에 다시 하세요."))
            return 0
        known = {os.path.normcase(os.path.abspath(str(it.key))) for it in self._items}
        new = [it for it in scan_folder(self._folder) if os.path.normcase(os.path.abspath(str(it.key))) not in known]
        if not new:
            if ask:
                QMessageBox.information(self, tr("새 명함 읽기"), tr("새 명함이 없습니다."))
            return 0
        start = len(self._items)
        self._items.extend(new)
        self.table.setRowCount(len(self._items))
        self._fill_empty_rows(start)
        self.lbl_folder.setText(tr("폴더: {path}  ·  명함 {n}장").format(path=str(self._folder), n=len(self._items)))
        self._applied_keys = None
        rows = list(range(start, len(self._items)))
        lang = "en" if (language() or "ko").lower().startswith("en") else "ko"
        from viewer.workers import run_in_thread
        self._worker = ImportWorker(new, self._db, lang, rows=rows)     # 캐시는 그대로(force 아님)
        self.bar.setRange(0, max(1, len(rows)))
        self.bar.setValue(0)
        self.bar.setFormat(tr("새 명함 읽는 중 %v / %m"))
        self._worker.itemDone.connect(self._on_item_ready)
        self._worker.progressed.connect(self._on_progress)
        self._worker.finishedAll.connect(self._on_done)
        keep = getattr(self._mw, "_thread_keep", None)
        run_in_thread(self._worker, keep if keep is not None else _KEEP)
        self.table.scrollToItem(self.table.item(start, C_NAME))
        return len(new)

    def read_sent(self, paths, _tries: int = 0) -> int:
        """[새 명함 입력]의 [사진에서 읽기](261120-31) — 명함 폴더에 복사한 사진을 '입력한 명함만' 으로 보이고, 표에 없으면 새로 읽는다.
        읽는 중이면 끝난 뒤 다시(0.5초마다, 상한 10분). 반환 = 새로 더한 장 수."""
        if self._closing:
            return 0
        keys = {os.path.normcase(os.path.abspath(str(p))) for p in paths or []}
        if not keys:
            return 0
        self._sent |= keys
        self.chk_sent.setVisible(True)
        self.chk_sent.setChecked(True)
        known = {os.path.normcase(os.path.abspath(str(it.front or it.key))) for it in self._items}
        n = 0
        if not keys <= known:
            busy = (self._worker is not None and not self._worker.done_event.is_set()) or self.region_busy or self._multi_busy()
            if busy:
                if _tries < 1200:
                    QTimer.singleShot(500, lambda: self.read_sent(paths, _tries + 1))
            else:
                n = self.read_new(ask=False)
        self._apply_filter()
        self.raise_()
        self.activateWindow()
        return n

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
        val = corr.get(raw, raw) if R.correction_ok(fld, raw, corr.get(raw, "")) else raw   # 전에 고친 오인식이면 고친 글을 먼저
        self._last_crop = crop
        if confirm:
            got = self._confirm_region(crop if crop is not None else self._source_image(self._items[r]), val, fld)
            if got is None:
                return ""
            if raw and got and got != raw and R.correction_ok(fld, raw, got):
                try:
                    self._store().correction_put(fld, raw, got)       # 교정 배우기(§5.15) — 이 PC 의 bizcard.db 에만
                except Exception:
                    pass
            val = got
        if not val:
            QMessageBox.information(self, tr("명함 읽기"), tr("그 자리에서 글자를 읽지 못했습니다 — 상자를 조금 넓혀 다시 그리세요."))
            return ""
        col = {"name": C_NAME, "company": C_COMP, "dept": C_DEPT, "title": C_TITLE, "cell": C_CELL, "tel": C_TEL, "email": C_MAIL}[fld]
        self.set_cell(r, col, val)
        self._on_edit(r)
        self.mark_ok(r, fld)                        # 확인 창 [넣기] = 사람이 확인함(261117-20)
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
    def _start(self, rows=None):
        if not self._items:
            self.bar.setFormat(tr("명함 그림이 없습니다"))
            return
        lang = "en" if (language() or "ko").lower().startswith("en") else "ko"
        from viewer.workers import run_in_thread
        if rows is None:
            self._worker = ImportWorker(self._items, self._db, lang)
            self.bar.setRange(0, max(1, len(self._items)))   # 다중 명함 세기(§5.26)가 막대를 썼을 수 있다
            self.bar.setValue(0)
            self.bar.setFormat(tr("읽는 중 %v / %m"))
        else:                                       # [다시 읽기] — 그 줄들만, 캐시 건너뜀
            self._worker = ImportWorker([self._items[r] for r in rows], self._db, lang, force=True, rows=rows)
            self.bar.setRange(0, max(1, len(rows)))
            self.bar.setValue(0)
            self.bar.setFormat(tr("다시 읽는 중 %v / %m"))
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
        if ok and not self._closing and not self._multi_busy():
            QTimer.singleShot(0, lambda: self._closing or self._multi_busy() or self._multi_pass(None, self._multi_idle))   # §5.26

    def _multi_idle(self):
        """다중 명함 세기만 하고 나눈 것이 없을 때 — 막대를 세기 전(다 읽음)으로 되돌린다."""
        lo, hi, v, f = getattr(self, "_bar_saved", (0, max(1, len(self._items)), len(self._items), tr("다 읽음 %v / %m")))
        self.bar.setRange(lo, hi)
        self.bar.setValue(v)
        self.bar.setFormat(f)

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
        mw_ = getattr(self, "_multi_worker", None)  # 다중 명함 세기(§5.26) — 신호를 끊고 멈춤
        if mw_ is not None and not mw_.done_event.is_set():
            for sig in (mw_.found, mw_.progressed, mw_.finishedAll):
                try:
                    sig.disconnect()
                except (TypeError, RuntimeError):
                    pass
            mw_.request_cancel()
            mw_.done_event.wait(15)
        sw_ = getattr(self, "_split_worker", None)
        if sw_ is not None and not sw_.done_event.is_set():
            sw_.done_event.wait(30)                # 자르는 중이면 끝날 때까지(파일을 반쯤 옮긴 채 두지 않게)
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
            QMessageBox.information(self, tr("명함 읽기"), tr("적용할 명함이 없습니다 — 이름이 있고 '적용' 이 체크된 줄만 만듭니다."))
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
            res = runner(job, tr("명함 읽기"))
        else:                                   # 앱 밖(검사) — 바로
            job(lambda d, t, l: True)
            res = {"ok": True}
        done = box["done"]
        self._apply_box = box                     # 검사가 본다(배우기 오류 종류)
        self._tag(done)
        self._applied_keys = None                 # P5: 새 명함만 — 방금 적용한 줄을 숨긴다
        self._apply_filter()
        self.learned = box.get("learn")
        self._load_learned()
        self._rescore_others()
        if done:
            QMessageBox.information(self, tr("명함 읽기"),
                                    tr("명함 {n}장을 정리 폴더에 만들었습니다.\n{path}").format(n=len(done), path=str(out)))
        elif not res.get("ok"):
            QMessageBox.warning(self, tr("명함 읽기"), tr("정리본을 만들지 못했습니다."))
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
        from viewer.bizcard.apply import LANG_TAGS
        for front, back, tags in done:
            for p in (front, back):
                if p:
                    old = store.get_manual(p) if hasattr(store, "get_manual") else []
                    old = [t for t in old or [] if t not in LANG_TAGS or t in tags]   # 언어 태그는 하나(D25)
                    store.set(p, list(dict.fromkeys(list(old) + list(tags))))

    def new_manual(self, exec_: bool = True):
        """[새 명함 입력](명함 SOT §5.24.1 '새 명함 입력') — 명함찾기와 같은 창. 같은 사람일 수 있으면 알림만."""
        from viewer.widgets.bizcard_new_dialog import NewCardDialog
        dlg = NewCardDialog(self, db=self._db, folder=str(self._folder))
        self.new_dlg = dlg                                   # 검사가 찾는다
        if not exec_:
            dlg.finished.connect(lambda _r: self._after_manual(dlg))
            dlg.show()
            return dlg
        dlg.exec()
        self._after_manual(dlg)
        return dlg

    def _after_manual(self, dlg):
        if getattr(dlg, "read_files", None):           # 261120-31: [사진에서 읽기] — 이 창에서 읽어 확인
            self.read_sent(dlg.read_files)
            return
        if not getattr(dlg, "new_id", 0):
            return
        from viewer.bizcard import people as P
        from viewer.bizcard.store import BizcardStore
        st = BizcardStore(self._db, ui=True)
        try:
            c = P.card_by_id(st, dlg.new_id)
        finally:
            st.close()
        if c and not str(c.get("front") or "").startswith("contact:"):
            self._tag([(c["front"], c.get("back") or "", list(c.get("tags") or []))])   # 정리본 파일 태그도(§5.5)
        if dlg.dupes:
            QMessageBox.information(self, tr("새 명함 입력"),
                                    tr("같은 휴대폰·메일의 명함이 {n}장 있습니다 — 명함찾기의 [중복 검토]에서 합칠 수 있습니다.").format(n=len(dlg.dupes)))
