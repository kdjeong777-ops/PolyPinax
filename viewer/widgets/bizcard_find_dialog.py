"""명함찾기 창 (명함 SOT §5.9 P4, §5.24 개편 · R2·R11·R12).

배치(§5.24): 왼쪽 = 위 즐겨찾기 줄(탭 + 카톡 꼴 사람 칸, 최대 2줄) + 아래 [결과 표 | 세부 칸(체크·메모)],
오른쪽 끝 = 사진창(위 명함 + 앞↔뒤 동그란 단추, 아래 인물 사진 — 끌어 순서 바꾸기 = 파일 이름 차례, 지우기 = 휴지통).
이름·회사를 고쳐 저장하면 정리본 이름도 `성명_회사명` 으로 — 앱의 이름 바꾸기 한 길(`_rename_bg` → `_after_rename`).
목록에서 지우기는 명함 관리 [삭제]와 같은 함수(`trash_paths`, D18). 그림 읽기·인물 사진 넣기는 배경.
★ 명함 글은 로그·상태 줄 밖으로 내보내지 않는다(§2.1).
"""
from __future__ import annotations

import math
import os
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QSize, QObject, QRectF, pyqtSignal
from PyQt6.QtGui import QPixmap, QIcon, QImage, QImageReader, QPainter, QPainterPath, QColor, QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QHeaderView, QSplitter, QWidget, QFormLayout, QPlainTextEdit, QPushButton,
    QListWidget, QListWidgetItem, QListView, QMessageBox, QFileDialog, QSizePolicy, QCheckBox, QTabBar, QToolButton,
    QMenu, QInputDialog, QApplication)

from viewer.i18n import tr, tr_noop
from viewer.bizcard import people as P
from viewer.bizcard import recognize as R
from viewer.bizcard import vcard as V

C_NAME, C_COMP, C_TITLE, C_DATE = range(4)
ROLE = Qt.ItemDataRole.UserRole
FAV_ICON = 56                       # 즐겨찾기 사람 칸 그림(카톡 꼴 둥근 네모)
FAV_ROWS = 2                        # 즐겨찾기 줄 최대 높이(줄 수) — 넘치면 그 칸 안에서 굴림
PHOTO_ICON = 104
DETAIL_W = 330                      # 처음 너비 — 세부 칸(§5.24 '처음 너비': 목록은 네 열 최소 폭, 나머지는 사진창)
FIND_DELAY_MS = 250
FAV_BG = "#cfe2f6"                  # 사진도 명함도 없을 때 — 옅은 파랑
IMG_FILTER = " ".join("*" + e for e in R.IMG_EXTS)
# 칸(키, 화면 이름) — 전화는 종류마다 첫 번호만 고친다(나머지는 그대로 둔다)
FIELDS = (("name", tr_noop("이름")), ("company", tr_noop("회사")), ("dept", tr_noop("부서")), ("title", tr_noop("직함")), ("cell", tr_noop("휴대폰")), ("work", tr_noop("전화")),
          ("fax", tr_noop("팩스")), ("email", tr_noop("메일")), ("address", tr_noop("주소")), ("url", tr_noop("누리집")))
MEMO_LABEL = tr_noop("메모")


def _read(path: str, w: int, h: int) -> QImage:
    """큰 사진도 칸 크기로 줄여 읽는다(QImageReader 축소 읽기 — 메모리·시간). 배경 스레드에서도 쓴다(QImage)."""
    rd = QImageReader(path)
    rd.setAutoTransform(True)
    sz = rd.size()
    if sz.isValid() and (sz.width() > 2 * w or sz.height() > 2 * h):
        rd.setScaledSize(sz.scaled(QSize(2 * w, 2 * h), Qt.AspectRatioMode.KeepAspectRatio))
    return rd.read()


def _scaled(path: str, w: int, h: int) -> QPixmap:
    im = _read(path, w, h)
    if im.isNull():
        return QPixmap()
    return QPixmap.fromImage(im).scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)


def _fav_image(path: str, from_card: bool) -> QImage:
    """즐겨찾기 그림 원재료 — 인물 사진은 그대로, 명함은 가운데 정사각(명함 일부). 배경에서."""
    im = _read(path, FAV_ICON * 3, FAV_ICON * 3)
    if im.isNull():
        return im
    if from_card:
        s = min(im.width(), im.height())
        im = im.copy((im.width() - s) // 2, (im.height() - s) // 2, s, s)
    return im


def _rounded(img, name: str) -> QPixmap:
    """둥근 네모 그림 — 그림이 없으면 옅은 파란 바탕에 이름 첫 글자."""
    s = FAV_ICON
    pm = QPixmap(s, s)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, s, s), s * 0.32, s * 0.32)
    p.setClipPath(path)
    if img is not None and not img.isNull():
        sc = img.scaled(s, s, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        p.drawImage(-(sc.width() - s) // 2, -(sc.height() - s) // 2, sc)
    else:
        p.fillRect(0, 0, s, s, QColor(FAV_BG))
        f = QFont()
        f.setPixelSize(int(s * 0.42))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#4a6f96"))
        p.drawText(QRectF(0, 0, s, s), Qt.AlignmentFlag.AlignCenter, (name or "?").strip()[:1])
    p.end()
    return pm


class PhotoWorker(QObject):
    """인물 사진 넣기(배경) — 그림마다 JPG·EXIF 뺌. done(만든 경로들, 실패 수)."""
    done = pyqtSignal(list, int)
    finished = pyqtSignal()

    def __init__(self, front, srcs):
        super().__init__()
        self._front, self._srcs = front, list(srcs)

    def run(self):
        made, bad = [], 0
        for s in self._srcs:
            try:
                dst = P.next_photo_path(self._front)
                P.save_person_photo(s, dst)
                made.append(str(dst))
            except Exception:
                bad += 1
        self.done.emit(made, bad)
        self.finished.emit()


class FavIconWorker(QObject):
    """즐겨찾기 그림 읽기(배경) — (세대, 명함 id, 그림). 세대가 바뀌면 부르는 쪽이 버린다."""
    one = pyqtSignal(int, int, QImage)
    finished = pyqtSignal()

    def __init__(self, gen, jobs):
        super().__init__()
        self._gen, self._jobs = gen, list(jobs)

    def run(self):
        for cid, path, from_card in self._jobs:
            try:
                im = _fav_image(path, from_card)
            except Exception:
                im = QImage()
            if not im.isNull():
                self.one.emit(self._gen, cid, im)
        self.finished.emit()


_KEEP = []


def _menu_act(m: QMenu, text: str, fn):
    a = m.addAction(text)
    a.triggered.connect(lambda _c=False: fn())
    return a


def _move_rows(lw: QListWidget, rows, to: int) -> None:
    """고른 줄들을 to 앞으로(차례 지킴) — IconMode 의 '자유 위치' 끌기 대신 차례 바꾸기."""
    rows = sorted(set(rows))
    items = [lw.item(r) for r in rows]
    to -= sum(1 for r in rows if r < to)
    for r in reversed(rows):
        lw.takeItem(r)
    for i, it in enumerate(items):
        lw.insertItem(max(0, min(to + i, lw.count())), it)
    for it in items:
        it.setSelected(True)


class _OrderList(QListWidget):
    """끌어 차례를 바꾸는 그림 칸(즐겨찾기 사람 칸·인물 사진). 바깥에서 끌어 온 것은 `external(event)` 로 넘긴다."""
    reordered = pyqtSignal()
    deleteRequested = pyqtSignal()

    def __init__(self, external=None, accepts=None):
        super().__init__()
        self._external, self._accepts = external, accepts
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Snap)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

    def _ok(self, e) -> bool:
        return e.source() is self or bool(self._accepts and self._accepts(e))

    def dragEnterEvent(self, e):
        if self._ok(e):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if self._ok(e):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dropEvent(self, e):
        if e.source() is self:
            idx = self.indexAt(e.position().toPoint())
            to = idx.row() if idx.isValid() else self.count()
            if idx.isValid() and e.position().x() > self.visualRect(idx).center().x():
                to += 1
            _move_rows(self, [i.row() for i in self.selectedIndexes()], to)
            e.setDropAction(Qt.DropAction.CopyAction)     # 모델이 지우지 않게 — 옮김은 위에서 끝남
            e.accept()
            self.reordered.emit()
            return
        if self._external is not None and self._ok(e):
            e.acceptProposedAction()
            self._external(e)
            return
        e.ignore()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Delete and self.selectedItems():
            self.deleteRequested.emit()
            return
        super().keyPressEvent(e)


class BizcardFindDialog(QDialog):
    def __init__(self, parent=None, db=None):
        super().__init__(parent)
        self._mw = parent
        self._db = db
        self._st = None
        self._rows = []
        self._by_id = {}
        self._card = None
        self._side = "front"
        self._loading = False
        self._dirty = False
        self.photo_busy = False
        self._fav_gen = 0
        self.setWindowTitle(tr("명함찾기"))
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowMinimizeButtonHint)
        self.setAcceptDrops(True)
        self.resize(1360, 800)
        v = QVBoxLayout(self)

        top = QHBoxLayout()
        self.ed_find = QLineEdit()
        self.ed_find.setPlaceholderText(tr("이름·회사·메모 등 — 낱말 여럿은 모두 들어 있는 명함, #낱말은 해시태그"))
        self.ed_find.setClearButtonEnabled(True)
        top.addWidget(self.ed_find, 1)
        self.cb_period = QComboBox()
        for key, label in (("all", tr("전체")), ("1m", tr("최근 1개월")), ("3m", tr("최근 3개월")), ("1y", tr("최근 1년")),
                           ("custom", tr("직접"))):
            self.cb_period.addItem(label, key)
        top.addWidget(QLabel(tr("스캔일")))
        top.addWidget(self.cb_period)
        self.ed_from, self.ed_to = QLineEdit(), QLineEdit()
        for ed in (self.ed_from, self.ed_to):
            ed.setPlaceholderText("YYYY-MM-DD")
            ed.setFixedWidth(100)
            ed.setVisible(False)
            ed.textChanged.connect(lambda _t: self._find_timer.start())
        self.lbl_tilde = QLabel("~")
        self.lbl_tilde.setVisible(False)
        top.addWidget(self.ed_from)
        top.addWidget(self.lbl_tilde)
        top.addWidget(self.ed_to)
        self.lbl_count = QLabel("")
        top.addWidget(self.lbl_count)
        v.addLayout(top)
        self._find_timer = QTimer(self)
        self._find_timer.setSingleShot(True)
        self._find_timer.setInterval(FIND_DELAY_MS)
        self._find_timer.timeout.connect(self.refresh)
        self.ed_find.textChanged.connect(lambda _t: self._find_timer.start())
        self.cb_period.currentIndexChanged.connect(self._on_period)

        # ── 왼쪽: 즐겨찾기 줄 + [표 | 세부] ──
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        tabs_row = QHBoxLayout()
        self.fav_tabs = QTabBar()
        self.fav_tabs.setMovable(True)
        self.fav_tabs.setExpanding(False)
        self.fav_tabs.setDrawBase(False)
        self.fav_tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.fav_tabs.customContextMenuRequested.connect(self._fav_tab_menu)
        self.fav_tabs.tabBarDoubleClicked.connect(lambda i: self.fav_rename_tab(i))
        self.fav_tabs.tabMoved.connect(lambda _a, _b: self._fav_save_tab_order())
        self.fav_tabs.currentChanged.connect(lambda _i: self._fav_tab_changed())
        tabs_row.addWidget(self.fav_tabs)
        self.btn_fav_tab = QToolButton()
        self.btn_fav_tab.setText("+")
        self.btn_fav_tab.setAutoRaise(True)
        self.btn_fav_tab.setToolTip(tr("새 즐겨찾기 탭"))
        self.btn_fav_tab.clicked.connect(lambda _c=False: self.fav_new_tab())
        tabs_row.addWidget(self.btn_fav_tab)
        tabs_row.addStretch(1)
        lv.addLayout(tabs_row)
        self.fav = _OrderList(external=lambda _e: self.fav_add_selected(),
                              accepts=lambda e: e.source() is self.table)
        self.fav.setIconSize(QSize(FAV_ICON, FAV_ICON))
        self.fav.setGridSize(QSize(FAV_ICON + 22, FAV_ICON + 24))
        self.fav.setUniformItemSizes(True)
        self.fav.setWordWrap(False)
        self.fav.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.fav.setToolTip(tr("표의 줄을 끌어 놓으면 이 탭에 넣습니다 — 끌어 차례 바꾸기, Delete 로 빼기"))
        self.fav.reordered.connect(self._fav_save_order)
        self.fav.deleteRequested.connect(lambda: self.fav_remove_selected())
        self.fav.itemClicked.connect(lambda it: self._show_card_id(it.data(ROLE)))
        self.fav.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.fav.customContextMenuRequested.connect(self._fav_menu)
        lv.addWidget(self.fav)

        mid = self.mid = QSplitter(Qt.Orientation.Horizontal)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([tr("이름"), tr("회사"), tr("직함"), tr("스캔일")])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setDragEnabled(True)
        self.table.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.table.verticalHeader().setVisible(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hh.setStretchLastSection(True)
        hh.setSortIndicatorShown(True)
        for c, w in ((C_NAME, 90), (C_COMP, 150), (C_TITLE, 80)):
            self.table.setColumnWidth(c, w)
        self.table.setSortingEnabled(True)                   # 머리말을 누르면 정렬, 다시 누르면 반대(§5.24)
        self.table.sortByColumn(C_DATE, Qt.SortOrder.DescendingOrder)
        self.table.currentCellChanged.connect(self._on_current)
        self.table.cellClicked.connect(lambda r, _c: self._on_clicked(r))
        for seq, fn in ((QKeySequence(QKeySequence.StandardKey.Copy), lambda: self.copy_selected()),
                        (QKeySequence(Qt.Key.Key_Delete), lambda: self.delete_cards())):
            sc = QShortcut(seq, self.table)
            sc.setContext(Qt.ShortcutContext.WidgetShortcut)
            sc.activated.connect(fn)
        mid.addWidget(self.table)

        detail = QWidget()
        rv = QVBoxLayout(detail)
        rv.setContentsMargins(6, 0, 0, 0)
        form = QFormLayout()
        self.eds, self.chk = {}, {}
        for k, label in FIELDS:
            ed = QLineEdit()
            ed.textEdited.connect(lambda _t: self._set_dirty(True))
            cb = QCheckBox(tr(label))
            cb.setToolTip(tr("체크한 칸을 [내용 복사] 로 글로 복사합니다 — 체크는 다음에도 그대로"))
            cb.toggled.connect(lambda _on: self._save_copy_fields())
            form.addRow(cb, ed)
            self.eds[k], self.chk[k] = ed, cb
        rv.addLayout(form)
        self.chk["memo"] = QCheckBox(tr(MEMO_LABEL))
        self.chk["memo"].toggled.connect(lambda _on: self._save_copy_fields())
        rv.addWidget(self.chk["memo"])
        self.ed_memo = QPlainTextEdit()
        self.ed_memo.textChanged.connect(lambda: self._set_dirty(True) if not self._loading else None)
        rv.addWidget(self.ed_memo, 1)
        self.lbl_file = QLabel("")
        self.lbl_file.setWordWrap(True)
        self.lbl_file.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        rv.addWidget(self.lbl_file)
        self.btn_save = QPushButton(tr("저장"))
        self.btn_save.setToolTip(tr("고친 칸·메모를 명함 DB 에 저장합니다 — 이름·회사를 바꾸면 정리본 파일 이름도 '성명_회사명' 으로"))
        self.btn_save.clicked.connect(lambda _c=False: self.save())
        self.btn_save.setEnabled(False)
        rv.addWidget(self.btn_save)
        mid.addWidget(detail)
        mid.setStretchFactor(0, 3)
        mid.setStretchFactor(1, 2)
        lv.addWidget(mid, 1)

        # ── 오른쪽 끝: 사진창(위 명함 + 앞↔뒤, 아래 인물 사진) ──
        self.photo_split = QSplitter(Qt.Orientation.Vertical)
        cardw = QWidget()
        cv = QVBoxLayout(cardw)
        cv.setContentsMargins(6, 0, 0, 0)
        self.pv = QLabel()
        self.pv.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pv.setMinimumSize(260, 150)
        self.pv.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.pv.setToolTip(tr("인물 사진을 여기에 끌어 놓으면 이 명함의 인물 사진으로 넣습니다"))
        cv.addWidget(self.pv, 1)
        self.btn_flip = QToolButton()
        self.btn_flip.setFixedSize(16, 16)
        self.btn_flip.setStyleSheet("QToolButton{border-radius:8px;border:1px solid palette(mid);background:palette(button);}"
                                    "QToolButton:checked{background:palette(highlight);}"
                                    "QToolButton:disabled{background:transparent;}")
        self.btn_flip.setCheckable(True)
        self.btn_flip.setToolTip(tr("명함 앞면 ↔ 뒷면"))
        self.btn_flip.toggled.connect(lambda on: self._flip(on))
        cv.addWidget(self.btn_flip, 0, Qt.AlignmentFlag.AlignHCenter)
        self.photo_split.addWidget(cardw)
        photow = QWidget()
        pvl = QVBoxLayout(photow)
        pvl.setContentsMargins(6, 0, 0, 0)
        pvl.addWidget(QLabel(tr("인물 사진")))
        self.photos = _OrderList(external=self._drop_files, accepts=lambda e: e.mimeData().hasUrls())
        self.photos.setIconSize(QSize(PHOTO_ICON, PHOTO_ICON))
        self.photos.setGridSize(QSize(PHOTO_ICON + 12, PHOTO_ICON + 12))
        self.photos.setToolTip(tr("끌어 차례를 바꿉니다(첫 사진이 즐겨찾기 그림) — Delete 로 지우기(휴지통)"))
        self.photos.reordered.connect(self._photo_reordered)
        self.photos.deleteRequested.connect(lambda: self.delete_photos())
        self.photos.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.photos.customContextMenuRequested.connect(self._photo_menu)
        pvl.addWidget(self.photos, 1)
        self.photo_split.addWidget(photow)
        self.photo_split.setStretchFactor(0, 3)
        self.photo_split.setStretchFactor(1, 2)
        self.photo_split.splitterMoved.connect(lambda _p, _i: QTimer.singleShot(0, self._show_card))

        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.split.addWidget(left)
        self.split.addWidget(self.photo_split)
        self.split.setStretchFactor(0, 5)
        self.split.setStretchFactor(1, 2)
        self.split.splitterMoved.connect(lambda _p, _i: QTimer.singleShot(0, self._show_card))
        v.addWidget(self.split, 1)

        bot = QHBoxLayout()
        self.btn_photo = QPushButton(tr("사진 추가..."))
        self.btn_photo.setToolTip(tr("인물 사진을 '인물' 폴더에 정리본과 같은 이름의 JPG 로 넣습니다 — 위치 정보 등 EXIF 는 뺍니다"))
        self.btn_photo.clicked.connect(lambda _c=False: self._pick_photos())
        self.btn_open = QPushButton(tr("명함 보기"))                     # D19: 종전 '사진 모드에서 열기' — 동작 그대로
        self.btn_open.setToolTip(tr("이 명함을 사진 모드에서 엽니다"))
        self.btn_open.clicked.connect(lambda _c=False: self.open_in_photo())
        self.btn_vcard = QPushButton(tr("주소록 ▾"))                    # §5.24 D22·D23 — 구글 주소록·리멤버 명함첩(vCard)
        self.btn_vcard.setToolTip(tr("주소록 vCard(.vcf) 가져오기·내보내기 — 구글 주소록·리멤버"))
        bm = QMenu(self.btn_vcard)
        _menu_act(bm, tr("리멤버 vCard 가져오기..."), lambda: self.import_contacts(source="remember"))
        _menu_act(bm, tr("구글 주소록 vCard 가져오기..."), lambda: self.import_contacts(source="google"))
        bm.addSeparator()
        _menu_act(bm, tr("구글 주소록용 vCard 로 내보내기..."), lambda: self.export_vcard(style="google"))
        _menu_act(bm, tr("리멤버용 vCard 로 내보내기..."), lambda: self.export_vcard(style="remember"))
        self.btn_vcard.setMenu(bm)
        self.btn_tags = QPushButton(tr("해시태그..."))
        self.btn_tags.setToolTip(tr("고른 명함들에 해시태그를 붙이거나 뗍니다 — 정리본 파일에도 같이, 찾기 칸에서 #낱말로 찾습니다"))
        self.btn_tags.clicked.connect(lambda _c=False: self.edit_tags())
        self.btn_copy = QPushButton(tr("내용 복사"))
        self.btn_copy.setToolTip(tr("고른 명함들의 체크한 칸을 '항목: 값' 글로 복사합니다"))
        self.btn_copy.clicked.connect(lambda _c=False: self.copy_selected())
        self.btn_fav_add = QPushButton(tr("즐겨찾기에 넣기"))
        self.btn_fav_add.setToolTip(tr("표에서 고른 명함 모두를 지금 즐겨찾기 탭에 넣습니다"))
        self.btn_fav_add.clicked.connect(lambda _c=False: self.fav_add_selected())
        self.btn_del = QPushButton(tr("삭제"))
        self.btn_del.setToolTip(tr("고른 명함을 지웁니다 — 원본·정리본·인물 사진을 휴지통으로"))
        self.btn_del.clicked.connect(lambda _c=False: self.delete_cards())
        b_close = QPushButton(tr("닫기"))
        b_close.clicked.connect(lambda _c=False: self.close())
        for b in (self.btn_photo, self.btn_open, self.btn_tags, self.btn_copy, self.btn_fav_add, self.btn_vcard, self.btn_del):
            bot.addWidget(b)
        bot.addStretch(1)
        bot.addWidget(b_close)
        v.addLayout(bot)
        self._enable_card_buttons(False)
        self._init_store_bits()
        QTimer.singleShot(0, self.refresh)

    # ── 저장소 ──
    def _store(self):
        if self._st is None:
            from viewer.bizcard.store import BizcardStore
            self._st = BizcardStore(self._db, ui=True)
            P.fav_init(self._st, tr("즐겨찾기"))
        return self._st

    def _init_store_bits(self):
        st = self._store()
        on = set(st.meta_get("copy_fields", list(P.COPY_DEFAULT)) or [])
        for k, cb in self.chk.items():
            cb.blockSignals(True)
            cb.setChecked(k in on)
            cb.blockSignals(False)
        self._fav_fill_tabs(st.meta_get("fav_tab", None))

    def _save_copy_fields(self):
        self._store().meta_set("copy_fields", [k for k in P.COPY_FIELDS if self.chk[k].isChecked()])

    # ── 찾기 ──
    def _on_period(self, _i=0):
        custom = self.cb_period.currentData() == "custom"
        for w in (self.ed_from, self.lbl_tilde, self.ed_to):
            w.setVisible(custom)
        self.refresh()

    def _range(self):
        key = self.cb_period.currentData()
        if key == "custom":
            return self.ed_from.text().strip(), self.ed_to.text().strip()
        return P.since_for(key), ""

    def refresh(self):
        if self._dirty and not self._ask_save():
            return
        since, until = self._range()
        rows = P.find(self._store(), self.ed_find.text(), since, until)
        more = len(rows) > P.SEARCH_LIMIT
        self._rows = rows[:P.SEARCH_LIMIT]
        self._by_id = {c["id"]: c for c in self._rows}
        keep = self._card["id"] if self._card else None
        self._loading = True
        try:
            self.table.setSortingEnabled(False)             # 채우는 동안 줄이 움직이지 않게
            self.table.clearContents()
            self.table.setRowCount(len(self._rows))
            for r, c in enumerate(self._rows):
                for col, val in ((C_NAME, c.get("name")), (C_COMP, c.get("company")), (C_TITLE, c.get("title")),
                                 (C_DATE, c.get("scanned"))):
                    it = QTableWidgetItem(val or "")
                    if col == C_NAME:
                        it.setData(ROLE, c["id"])
                    self.table.setItem(r, col, it)
            self.table.setSortingEnabled(True)              # 지금 머리말 기준으로 다시 정렬
        finally:
            self._loading = False
        self.lbl_count.setText((tr("처음 {n}장") if more else tr("{n}장")).format(n=len(self._rows)))
        pick = self.row_of_id(keep) if keep in self._by_id else (0 if self._rows else -1)
        if pick >= 0:
            self._loading = True
            self.table.setCurrentCell(pick, 0)
            self._loading = False
            self._load(self._card_at(pick))
        else:
            self._load(None)

    def row_of_id(self, cid) -> int:
        for r in range(self.table.rowCount()):
            it = self.table.item(r, C_NAME)
            if it is not None and it.data(ROLE) == cid:
                return r
        return -1

    def _card_at(self, r):
        it = self.table.item(r, C_NAME) if 0 <= r < self.table.rowCount() else None
        return self._by_id.get(it.data(ROLE)) if it is not None else None

    def _on_current(self, r, _c, pr, _pc):
        if self._loading or r == pr:
            return
        if self._dirty and not self._ask_save():
            self._loading = True
            self.table.setCurrentCell(pr, 0)
            self._loading = False
            return
        self._load(self._card_at(r))

    def _on_clicked(self, r):
        """즐겨찾기에서 표 밖 명함을 보고 있다가 같은 줄을 다시 누를 때(현재 줄이 그대로라 위 신호가 안 옴)."""
        c = self._card_at(r)
        if c is not None and (self._card is None or self._card["id"] != c["id"]):
            if self._dirty and not self._ask_save():
                return
            self._load(c)

    def selected_cards(self) -> list:
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [c for c in (self._card_at(r) for r in rows) if c is not None]

    def _show_card_id(self, cid):
        """즐겨찾기 사람을 누름 — 표에 있으면 그 줄, 없으면 표는 그대로 두고 그 명함을 보인다."""
        if self._card is not None and self._card["id"] == cid:
            return
        r = self.row_of_id(cid)
        if r >= 0:
            self.table.setCurrentCell(r, 0)
            return
        if self._dirty and not self._ask_save():
            return
        c = P.card_by_id(self._store(), cid)
        if c is not None:
            self._loading = True
            self.table.clearSelection()
            self._loading = False
            self._load(c)

    # ── 한 명함 ──
    def _load(self, card):
        self._card = card
        self._side = "front"
        self._loading = True
        try:
            ph = card.get("phones") if card else []
            first = lambda kind: next((n for k, n in ph or [] if k == kind), "")
            vals = {"name": "", "company": "", "dept": "", "title": "", "cell": "", "work": "", "fax": "", "email": "",
                    "address": "", "url": ""}
            if card:
                vals.update({k: card.get(k) or "" for k in ("name", "company", "dept", "title", "address")})
                vals.update(cell=first("cell"), work=first("work"), fax=first("fax"),
                            email=(card.get("emails") or [""])[0], url=(card.get("urls") or [""])[0])
            for k, ed in self.eds.items():
                ed.setText(vals[k])
                ed.setEnabled(card is not None)
            self.ed_memo.setPlainText((card or {}).get("memo") or "")
            self.ed_memo.setEnabled(card is not None)
            if card and V.is_contact(card):
                self.lbl_file.setText(tr("(주소록에서 가져온 명함 — 그림 없음)"))
            else:
                self.lbl_file.setText(os.path.basename(card["front"]) if card else "")
            has_back = bool(card and card.get("back") and os.path.exists(card["back"]))
            self.btn_flip.setChecked(False)
            self.btn_flip.setEnabled(has_back)
        finally:
            self._loading = False
        self._set_dirty(False)
        self._enable_card_buttons(card is not None)
        self._show_card()
        self._fill_photos()

    def _flip(self, on: bool):
        if self._loading:
            return
        self._side = "back" if on else "front"
        self._show_card()

    def _show_card(self):
        c = self._card
        path = (c.get("back") if self._side == "back" else c.get("front")) if c else ""
        self.shown = path or ""
        if not path or not os.path.exists(path):
            self.pv.clear()
            if c:
                self.pv.setText(tr("(그림 파일이 없습니다)"))
            return
        self.pv.setPixmap(_scaled(path, max(200, self.pv.width()), max(120, self.pv.height())))

    def _fill_photos(self, select: str = ""):
        self.photos.clear()
        c = self._card
        if not c or V.is_contact(c):
            return
        for p in P.person_photos(c["front"]):
            it = QListWidgetItem(QIcon(_scaled(p, PHOTO_ICON, PHOTO_ICON)), "")
            it.setData(ROLE, p)
            it.setToolTip(os.path.basename(p))
            self.photos.addItem(it)
            if select and os.path.normcase(p) == os.path.normcase(select):
                self.photos.setCurrentItem(it)

    def photo_paths(self) -> list:
        return [self.photos.item(i).data(ROLE) for i in range(self.photos.count())]

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self._show_card)
        QTimer.singleShot(0, self._fav_fit)

    def showEvent(self, e):
        super().showEvent(e)
        if not getattr(self, "_sized", False):
            self._sized = True
            self._init_sizes()

    def table_min_width(self) -> int:
        """네 열(이름·회사·직함·스캔일)이 다 보이는 표 폭."""
        t = self.table
        date_w = t.fontMetrics().horizontalAdvance("0000-00-00") + 24     # 마지막 열은 늘어나므로 글자 폭으로 센다
        return (sum(t.columnWidth(c) for c in range(t.columnCount() - 1)) + date_w
                + t.verticalScrollBar().sizeHint().width() + 2 * t.frameWidth() + 4)

    def _init_sizes(self):
        """처음 너비(§5.24, 사용자 지시 261118) — 목록은 스캔일까지 보이는 최소 폭, 세부는 DETAIL_W, 나머지는 사진창.
        창을 열 때 한 번만 — 그 뒤는 사용자가 끌어 바꾼다."""
        tw = self.table_min_width()
        self.mid.setSizes([tw, DETAIL_W])
        total = max(self.split.width(), self.width() - 24)
        left = tw + DETAIL_W + self.mid.handleWidth() + 6
        self.split.setSizes([left, max(300, total - left)])
        QTimer.singleShot(0, self._show_card)

    def _set_dirty(self, on: bool):
        if self._loading:
            return
        self._dirty = bool(on and self._card)
        self.btn_save.setEnabled(self._dirty)

    def _enable_card_buttons(self, on: bool):
        img = on and not V.is_contact(self._card)            # 주소록에서 가져온 명함 — 그림·인물 사진 없음
        for b in (self.btn_tags, self.btn_copy, self.btn_fav_add, self.btn_del):
            b.setEnabled(on)
        for b in (self.btn_photo, self.btn_open):
            b.setEnabled(img)
        self.photos.setEnabled(img)

    def _ask_save(self) -> bool:
        """저장 안 한 고침 — 저장·버리기·취소. True = 넘어가도 됨."""
        b = QMessageBox.question(self, tr("명함찾기"), tr("고친 내용을 저장할까요?"),
                                 QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                 QMessageBox.StandardButton.Save)
        if b == QMessageBox.StandardButton.Cancel:
            return False
        if b == QMessageBox.StandardButton.Save:
            return self.save()
        self._set_dirty(False)
        return True

    # ── 저장 ──
    def _edited(self) -> dict:
        c = self._card
        g = {k: ed.text().strip() for k, ed in self.eds.items()}
        old_ph = [tuple(x) for x in c.get("phones") or []]
        phones, used = [], set()
        for kind in ("cell", "work", "fax"):
            if g[kind]:
                phones.append((kind, g[kind]))
            first = next((i for i, (k, _n) in enumerate(old_ph) if k == kind), None)
            if first is not None:
                used.add(first)
        phones += [p for i, p in enumerate(old_ph) if i not in used]
        emails = ([g["email"]] if g["email"] else []) + list((c.get("emails") or [])[1:])
        urls = ([g["url"]] if g["url"] else []) + list((c.get("urls") or [])[1:])
        name = R.clean_name_ko(g["name"]) if R._HANGUL.search(g["name"]) and not R._LATIN.search(g["name"]) else g["name"]
        return {"name": name, "company": R.strip_corp(g["company"]), "dept": g["dept"], "title": g["title"],
                "address": g["address"], "phones": phones, "emails": emails, "urls": urls,
                "memo": self.ed_memo.toPlainText()}

    def save(self) -> bool:
        """고친 칸·메모 저장. 이름·회사가 바뀌면 정리본·뒷면·인물 사진 이름도(한 길). True = 저장함."""
        c = self._card
        if not c or not self._dirty:
            return True
        if self.photo_busy:
            QMessageBox.information(self, tr("명함찾기"), tr("인물 사진을 넣는 중입니다 — 끝난 뒤에 다시 하세요."))
            return False
        new = self._edited()
        if not new["name"]:
            QMessageBox.information(self, tr("명함찾기"), tr("이름을 비울 수 없습니다."))
            return False
        from viewer.bizcard.apply import tags_for, unique_path, BACK_SUFFIX
        st = self._store()
        old_tags = list(c.get("tags") or [])
        langs = [t for t in old_tags if t in ("한글", "영어")]
        old_auto = set(tags_for({"company": c.get("company") or "", "langs": langs}))   # 앱이 붙인 것만 바꾼다
        new_tags = list(dict.fromkeys(tags_for({"company": new["company"], "langs": langs})
                                      + [t for t in old_tags if t not in old_auto]))     # 사람이 붙인 해시태그는 그대로
        front, back = c["front"], c.get("back") or ""
        nf, nb = front, back
        want = R.card_filename(new["name"], new["company"], os.path.splitext(front)[1] or ".jpg")
        if (new["name"], new["company"]) != (c.get("name") or "", c.get("company") or "") and os.path.exists(front) \
                and os.path.normcase(Path(front).stem.split(" (")[0]) != os.path.normcase(Path(want).stem):
            folder = Path(front).parent
            same = folder / want
            p = same if os.path.normcase(str(same)) == os.path.normcase(front) else unique_path(folder, want, set())
            photos = P.person_photos(front)
            if not self._rename(front, str(p)):
                return False
            nf = str(p)
            if back and os.path.exists(back):
                pb = unique_path(folder, p.stem + BACK_SUFFIX + os.path.splitext(back)[1], set())
                if self._rename(back, str(pb)):
                    nb = str(pb)
            for i, ph in enumerate(photos):          # 인물 사진도 새 이름으로(차례 지킴)
                dst = Path(ph).with_name(P.photo_name(p, i, os.path.splitext(ph)[1]))
                if os.path.normcase(str(dst)) != os.path.normcase(ph) and not dst.exists():
                    self._rename(ph, str(dst))
        fields = dict(new, front=nf, back=nb, tags=new_tags)
        P.update_card(st, c["id"], fields)
        P.forget_srcs(st, c["id"], [k for k in ("name", "company", "dept", "title", "address", "memo")
                                    if (new.get(k) or "") != (c.get(k) or "")])   # 손으로 고친 칸 — 주소록이 덮어쓰지 않게(D24)
        self._retag([x for x in (nf, nb) if x and os.path.exists(x)], old_auto, new_tags)
        self._dirty = False
        self.btn_save.setEnabled(False)
        self._card = dict(c, **fields)
        self.saved = {"renamed": nf != front}
        self.refresh()
        self._fav_fill()
        return True

    def _rename(self, src: str, dst: str, quiet: bool = False) -> bool:
        """앱의 이름 바꾸기 한 길(배경 + `_after_rename` → 태그·색인·명함 DB 가 따라감). 앱 밖이면 그 자리에서."""
        bt = getattr(self._mw, "bookmark_tree", None)
        if bt is not None and hasattr(bt, "_rename_bg"):
            err = bt._rename_bg(src, dst, tr("명함 이름 바꾸기"))
            if err is None:
                bt._after_rename(None, Path(src), Path(dst))
                return True
        else:
            from viewer.pathutil import rename_when_free
            try:
                rename_when_free(src, dst, wait_s=0)
                return True
            except Exception as e:
                err = e
        if not quiet:
            QMessageBox.warning(self, tr("명함찾기"), tr("파일 이름을 바꾸지 못했습니다 — 다른 프로그램이 열고 있는지 확인하세요.")
                                + "\n" + type(err).__name__)
        return False

    def _retag(self, paths, old_auto, new_tags):
        """해시태그(§5.5) — 옛 자동 태그(#회사 등)를 새 것으로, 사람이 붙인 다른 태그는 둔다. 앱의 태그 저장소 하나로."""
        bt = getattr(self._mw, "bookmark_tree", None)
        store = getattr(bt, "_tags", None) if bt is not None else None
        if store is None:
            from viewer.tag_store import TagStore
            store = TagStore()
        for p in paths:
            cur = [t for t in (store.get_manual(p) or []) if t not in old_auto]
            store.set(p, list(dict.fromkeys(cur + list(new_tags))))

    # ── 체크한 칸 복사 (§5.24, D21) ──
    def copy_text(self) -> str:
        cards = self.selected_cards() or ([self._card] if self._card else [])
        fields = {k for k, cb in self.chk.items() if cb.isChecked()}
        labels = dict({k: tr(lb) for k, lb in FIELDS}, memo=tr(MEMO_LABEL))
        vals = []
        for c in cards:
            v = P.field_values(c)
            if self._card is not None and c["id"] == self._card["id"]:   # 지금 보는 명함은 화면 칸(저장 전 고침 포함)
                v.update({k: ed.text().strip() for k, ed in self.eds.items()})
                v["memo"] = self.ed_memo.toPlainText()
            vals.append(v)
        return P.copy_text(vals, fields, labels)

    def copy_selected(self) -> str:
        t = self.copy_text()
        if t:
            QApplication.clipboard().setText(t)
        return t

    # ── 즐겨찾기 탭 (§5.24) ──
    def _fav_gid(self):
        i = self.fav_tabs.currentIndex()
        return self.fav_tabs.tabData(i) if i >= 0 else None

    def _fav_fill_tabs(self, select=None):
        self.fav_tabs.blockSignals(True)
        while self.fav_tabs.count():
            self.fav_tabs.removeTab(0)
        pick = 0
        for i, (gid, name) in enumerate(P.fav_groups(self._store())):
            self.fav_tabs.addTab(name)
            self.fav_tabs.setTabData(i, gid)
            if gid == select:
                pick = i
        self.fav_tabs.setCurrentIndex(pick)
        self.fav_tabs.blockSignals(False)
        self._fav_fill()

    def _fav_tab_changed(self):
        gid = self._fav_gid()
        if gid is not None:
            self._store().meta_set("fav_tab", gid)
        self._fav_fill()

    def _fav_save_tab_order(self):
        P.fav_order_groups(self._store(), [self.fav_tabs.tabData(i) for i in range(self.fav_tabs.count())])

    def fav_new_tab(self, name=None):
        if name is None:
            name, ok = QInputDialog.getText(self, tr("즐겨찾기"), tr("새 탭 이름(예: 가족·친구):"))
            if not ok:
                return None
        name = (name or "").strip()
        if not name:
            return None
        gid = P.fav_add_group(self._store(), name)
        self._fav_fill_tabs(gid)
        return gid

    def fav_rename_tab(self, i, name=None):
        if i < 0:
            return
        if name is None:
            name, ok = QInputDialog.getText(self, tr("즐겨찾기"), tr("탭 이름:"), text=self.fav_tabs.tabText(i))
            if not ok:
                return
        name = (name or "").strip()
        if name:
            P.fav_rename_group(self._store(), self.fav_tabs.tabData(i), name)
            self.fav_tabs.setTabText(i, name)

    def fav_delete_tab(self, i, ask: bool = True) -> bool:
        if i < 0 or self.fav_tabs.count() <= 1:
            return False
        gid = self.fav_tabs.tabData(i)
        n = len(P.fav_members(self._store(), gid))
        if ask and n and QMessageBox.question(
                self, tr("즐겨찾기"), tr("'{tab}' 탭을 지웁니다 — 탭의 {n}명은 빠지고 명함은 그대로입니다.").format(
                    tab=self.fav_tabs.tabText(i), n=n)) != QMessageBox.StandardButton.Yes:
            return False
        if P.fav_delete_group(self._store(), gid):
            self._fav_fill_tabs(self._fav_gid() if i != self.fav_tabs.currentIndex() else None)
            return True
        return False

    def _fav_tab_menu(self, pos):
        i = self.fav_tabs.tabAt(pos)
        if i < 0:
            return
        m = QMenu(self)
        _menu_act(m, tr("이름 바꾸기..."), lambda: self.fav_rename_tab(i))
        _menu_act(m, tr("탭 지우기"), lambda: self.fav_delete_tab(i)).setEnabled(self.fav_tabs.count() > 1)
        _menu_act(m, tr("새 탭..."), lambda: self.fav_new_tab())
        m.exec(self.fav_tabs.mapToGlobal(pos))

    def _fav_fill(self):
        """지금 탭의 사람 칸 — 우선 옅은 파랑 + 첫 글자, 그림은 배경에서 읽어 바꾼다."""
        self.fav.clear()
        gid = self._fav_gid()
        self._fav_gen += 1
        if gid is None:
            self._fav_fit()
            return
        jobs = []
        for c in P.fav_members(self._store(), gid):
            it = QListWidgetItem(QIcon(_rounded(None, c.get("name") or "")), c.get("name") or "")
            it.setData(ROLE, c["id"])
            it.setToolTip(" · ".join(x for x in (c.get("name"), c.get("company"), c.get("title")) if x))
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.fav.addItem(it)
            photos = P.person_photos(c["front"]) if c.get("front") and not V.is_contact(c) else []
            if photos:
                jobs.append((c["id"], photos[0], False))
            elif c.get("front") and os.path.exists(c["front"]):
                jobs.append((c["id"], c["front"], True))
        self._fav_fit()
        self.fav_icons_pending = len(jobs)
        if jobs:
            from viewer.workers import run_in_thread
            w = FavIconWorker(self._fav_gen, jobs)
            w.one.connect(self._fav_icon)
            keep = getattr(self._mw, "_thread_keep", None)
            run_in_thread(w, keep if isinstance(keep, list) else _KEEP)

    def _fav_icon(self, gen, cid, img):
        if gen != self._fav_gen:
            return
        for i in range(self.fav.count()):
            it = self.fav.item(i)
            if it.data(ROLE) == cid:
                it.setIcon(QIcon(_rounded(img, it.text())))
                it.setData(ROLE + 1, True)             # 그림 바꿈(검사가 본다)
        self.fav_icons_pending = max(0, getattr(self, "fav_icons_pending", 1) - 1)

    def _fav_fit(self):
        """높이 — 사람 수에 맞춰 1~2줄, 넘치면 그 칸 안에서 굴림."""
        g = self.fav.gridSize()
        per = max(1, (self.fav.viewport().width() or self.width()) // max(1, g.width()))
        rows = min(FAV_ROWS, max(1, math.ceil(self.fav.count() / per)))
        self.fav.setFixedHeight(rows * g.height() + 2 * self.fav.frameWidth() + 4)

    def fav_ids(self) -> list:
        return [self.fav.item(i).data(ROLE) for i in range(self.fav.count())]

    def fav_add_selected(self, cards=None) -> int:
        gid = self._fav_gid()
        cards = cards if cards is not None else (self.selected_cards() or ([self._card] if self._card else []))
        if gid is None or not cards:
            return 0
        n = P.fav_add(self._store(), gid, [c["id"] for c in cards])
        self._fav_fill()
        return n

    def fav_remove_selected(self):
        gid = self._fav_gid()
        ids = [it.data(ROLE) for it in self.fav.selectedItems()]
        if gid is None or not ids:
            return
        P.fav_remove(self._store(), gid, ids)
        self._fav_fill()

    def _fav_save_order(self):
        gid = self._fav_gid()
        if gid is not None:
            P.fav_order(self._store(), gid, self.fav_ids())

    def _fav_menu(self, pos):
        if self.fav.itemAt(pos) is None:
            return
        m = QMenu(self)
        _menu_act(m, tr("탭에서 빼기"), lambda: self.fav_remove_selected())
        m.exec(self.fav.mapToGlobal(pos))

    # ── 인물 사진 ──
    def _pick_photos(self):
        files, _f = QFileDialog.getOpenFileNames(self, tr("인물 사진"), "", tr("그림") + " (%s)" % IMG_FILTER)
        if files:
            self.add_photos(files)

    def dragEnterEvent(self, e):
        if self._card and not V.is_contact(self._card) and e.mimeData().hasUrls() and any(self._is_img(u.toLocalFile()) for u in e.mimeData().urls()):
            e.acceptProposedAction()

    def dropEvent(self, e):
        self._drop_files(e)

    def _drop_files(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls() if self._is_img(u.toLocalFile())]
        if files:
            e.acceptProposedAction()
            self.add_photos(files)

    @staticmethod
    def _is_img(p) -> bool:
        return bool(p) and os.path.splitext(p)[1].lower() in R.IMG_EXTS

    def add_photos(self, files):
        if not self._card or self.photo_busy or V.is_contact(self._card):
            return
        from viewer.workers import run_in_thread
        self.photo_busy = True
        self.btn_photo.setEnabled(False)
        w = PhotoWorker(self._card["front"], files)
        card_id = self._card["id"]

        def _done(made, bad):
            self.photo_busy = False
            self.btn_photo.setEnabled(self._card is not None)
            self.last_photos = made
            if self._card and self._card["id"] == card_id:
                self._fill_photos(select=made[-1] if made else "")
            if card_id in self.fav_ids():
                self._fav_fill()
            if bad:
                QMessageBox.warning(self, tr("인물 사진"), tr("그림 {n}개를 넣지 못했습니다.").format(n=bad))
        w.done.connect(_done)
        keep = getattr(self._mw, "_thread_keep", None)
        run_in_thread(w, keep if isinstance(keep, list) else _KEEP)

    def _photo_reordered(self):
        self.apply_photo_order(self.photo_paths())

    def apply_photo_order(self, ordered) -> bool:
        """D20 — 사진 차례 = 파일 이름 차례. 임시 이름을 거쳐 두 번(서로 겹치지 않게), 앱 이름 바꾸기 한 길로."""
        c = self._card
        if not c or self.photo_busy:
            self._fill_photos()
            return False
        plan = P.photo_renames(c["front"], ordered)
        ok = True
        done = []
        for src, tmp, _final in plan:
            if self._rename(src, tmp, quiet=True):
                done.append((tmp, _final))
            else:
                ok = False
        for tmp, final in done:
            if not self._rename(tmp, final, quiet=True):
                ok = False
        if not ok:
            QMessageBox.warning(self, tr("인물 사진"), tr("사진 이름을 다 바꾸지 못했습니다 — 다른 프로그램이 열고 있는지 확인하세요."))
        self._fill_photos()
        if c["id"] in self.fav_ids():
            self._fav_fill()
        return ok

    def delete_photos(self, paths=None, ask: bool = True) -> int:
        """고른 인물 사진 → 휴지통(앱 `_trash_bg` 한 길), 남은 사진은 이름을 다시 차례대로."""
        c = self._card
        paths = paths if paths is not None else [it.data(ROLE) for it in self.photos.selectedItems()]
        if not c or not paths or self.photo_busy:
            return 0
        if ask and QMessageBox.question(self, tr("인물 사진"), tr("인물 사진 {n}개를 휴지통으로 보냅니다.").format(n=len(paths))) \
                != QMessageBox.StandardButton.Yes:
            return 0
        from viewer.widgets.bizcard_import_dialog import trash_paths
        failed = trash_paths(self, self._mw, list(paths))
        rest = [p for p in self.photo_paths() if p not in paths or p in failed]
        self.apply_photo_order([p for p in rest if os.path.exists(p)])
        return len([p for p in paths if p not in failed])

    def _photo_menu(self, pos):
        if self.photos.itemAt(pos) is None:
            return
        m = QMenu(self)
        _menu_act(m, tr("지우기"), lambda: self.delete_photos())
        m.exec(self.photos.mapToGlobal(pos))

    # ── 목록에서 지우기 (§5.24 D18 — 명함 관리 [삭제] 와 같은 길) ──
    def delete_cards(self, cards=None, ask: bool = True) -> int:
        cards = cards if cards is not None else (self.selected_cards() or ([self._card] if self._card else []))
        if not cards:
            return 0
        if self.photo_busy:
            QMessageBox.information(self, tr("명함찾기"), tr("인물 사진을 넣는 중입니다 — 끝난 뒤에 다시 하세요."))
            return 0
        files = {c["id"]: P.card_files(c) for c in cards}
        n_o = sum(len(f[0]) for f in files.values())
        n_c = sum(len(f[1]) for f in files.values())
        n_p = sum(len(f[2]) for f in files.values())
        if ask and QMessageBox.question(
                self, tr("삭제"),
                tr("명함 {n}장을 지웁니다 — 원본 파일까지 휴지통으로 보냅니다(원본 {f}개·정리본 {o}개·인물 사진 {p}개). 인식 기록도 지웁니다.").format(
                    n=len(cards), f=n_o, o=n_c, p=n_p)) != QMessageBox.StandardButton.Yes:
            return 0
        from viewer.widgets.bizcard_import_dialog import trash_paths
        targets = list(dict.fromkeys(p for f in files.values() for grp in f for p in grp))
        failed = trash_paths(self, self._mw, targets)
        st = self._store()
        gone = 0
        for c in cards:
            if any(p in failed for grp in files[c["id"]] for p in grp):
                continue                                # 일부만 휴지통으로 간 명함은 기록을 남긴다(§5.20)
            if c.get("src_key"):
                st.delete_src(c["src_key"])
            else:
                st.delete_card(c["id"])
            gone += 1
        self.last_deleted = gone
        if not gone:
            return 0
        rows = [r for r in (self.row_of_id(c["id"]) for c in cards) if r >= 0]
        at = min(rows) if rows else 0                  # 지운 줄의 자리 — 지운 뒤 그 자리 = 바로 아래 명함(사용자 지시 261118)
        self._dirty = False
        self._card = None
        self.refresh()
        n = self.table.rowCount()
        if n:
            r = min(at, n - 1)                          # 맨 끝을 지웠으면 새 끝 줄
            self.table.clearSelection()
            self.table.setCurrentCell(r, 0)
            self.table.selectRow(r)
            if self._card is None or self._card["id"] != (self._card_at(r) or {}).get("id"):
                self._load(self._card_at(r))
        self._fav_fill()
        return gone

    # ── 단추 ──
    def open_in_photo(self):
        c = self._card
        if not c or V.is_contact(c) or self._mw is None or not hasattr(self._mw, "_photo_open_arg"):
            return
        if not self._mw._photo_open_arg(c["front"]):
            QMessageBox.information(self, tr("명함찾기"), tr("사진 모드로 열지 못했습니다."))

    def export_vcard(self, path=None, drive=None, style: str = "google"):
        """고른 명함들 → vCard(§5.8 모듈). style = 'google'(드라이브 줄) · 'remember'(리멤버 명함첩 꼴, §5.24 D23).
        path·drive 를 주면 묻지 않는다(검사). 반환 = 장 수 또는 None."""
        from viewer import bg_write
        from viewer.i18n import language
        cards = self.selected_cards() or ([self._card] if self._card else [])
        if not cards:
            return None
        st = self._store()
        if style == "remember":
            drive = ""
        if drive is None:
            default = st.meta_get("drive_folder", None)
            if default is None:
                default = Path(cards[0]["front"]).parent.name
            drive, ok = QInputDialog.getText(self, "vCard", tr("구글 드라이브의 명함 폴더 이름 — 메모에 '폴더/파일 이름' 과 드라이브 검색 주소를 넣습니다(비우면 넣지 않음):"),
                                             text=default)
            if not ok:
                return None
            drive = drive.strip()
            st.meta_set("drive_folder", drive)
        quiet = path is not None
        if path is None:
            base = Path(cards[0]["front"]).parent if not V.is_contact(cards[0]) else Path.home()
            start = base / (tr("명함") + ("_" + tr("리멤버") if style == "remember" else "") + ".vcf")
            path, _f = QFileDialog.getSaveFileName(self, tr("vCard 로 내보내기"), str(start), "vCard (*.vcf)")
            if not path:
                return None
        lang = "en" if str(language()).startswith("en") else "ko"
        bg_write.submit(path, V.export_text(cards, drive, lang, tr("명함"), style), delay=0)
        if not quiet:
            QMessageBox.information(self, "vCard", tr("vCard 에 {n}장을 썼습니다.").format(n=len(cards)) + "\n" + str(path))
        return len(cards)

    # ── 해시태그 (§5.24) — 명함 DB 태그 칸 + 정리본 파일 태그(앱 태그 저장소 하나) ──
    def _tagstore(self):
        bt = getattr(self._mw, "bookmark_tree", None)
        store = getattr(bt, "_tags", None) if bt is not None else None
        if store is None:
            from viewer.tag_store import TagStore
            store = TagStore()
        return store

    def edit_tags(self, text=None):
        """고른 명함들(없으면 지금 명함) — 함께 붙은 태그를 보여 주고, 더한 것은 모두에 붙이고 뗀 것은 모두에서 뗀다.
        text 를 주면 창 없이(검사). 반환 = 바꾼 명함 수 또는 None(취소)."""
        cards = self.selected_cards() or ([self._card] if self._card else [])
        if not cards:
            return None
        if self._dirty and not self._ask_save():
            return None
        from viewer.tag_store import normalize_tags
        if text is None:
            files = [c for c in cards if c.get("front") and not V.is_contact(c) and os.path.exists(c["front"])]
            if files:                                   # 책갈피창 '해시태그 수정' 창과 같은 길(§5.24, 사용자 지시 261118)
                return self.tag_apply(files)
        init = P.common_tags(cards)
        store = self._tagstore()
        if text is None:                                # 그림 없는 주소록 명함만 — 명함 DB 태그 칸만
            from viewer.widgets.tag_edit_dialog import TagEditDialog
            existing = sorted(set(store.all_tags()) | {t for c in self._rows for t in c.get("tags") or []})
            title = (cards[0].get("name") or "") if len(cards) == 1 else tr("명함 {n}장").format(n=len(cards))
            dlg = TagEditDialog(title, init, existing, self)
            if not dlg.exec():
                return None
            text = dlg.tags()
        new = normalize_tags(text)
        added = [t for t in new if t not in init]
        removed = [t for t in init if t not in new]
        if not added and not removed:
            return 0
        P.retag_cards(self._store(), cards, added, removed)
        for c in cards:
            for f in (c.get("front"), c.get("back")):
                if f and os.path.exists(f):
                    f = os.path.realpath(f)
                    cur = [t for t in (store.get_manual(f) or []) if t not in removed]
                    store.set(f, list(dict.fromkeys(cur + added)))
        self.refresh()
        return len(cards)

    def tag_apply(self, cards) -> int:
        """책갈피창 '해시태그 수정' 창(`TagApplyDialog`, 태그 SOT §8.7)에 명함들의 정리본 앞면을 썸네일로 넘긴다.
        창을 닫으면 명함마다 앞면에서 더하고 뗀 사람 태그를 명함 DB 태그 칸·뒷면 파일에 같게. 반환 = 바뀐 명함 수."""
        from viewer.widgets.tag_apply_dialog import TagApplyDialog
        store = self._tagstore()
        fronts = [os.path.realpath(c["front"]) for c in cards]
        before = {f: list(store.get_manual(f) or []) for f in fronts}
        mw = self._mw
        prefs = getattr(mw, "_prefs", None) if mw is not None else None
        keep = mw.__dict__.setdefault("_thread_keep", []) if mw is not None else _KEEP
        state = prefs.get("tag_apply_window") if isinstance(prefs, dict) else None
        dlg = TagApplyDialog(store, fronts, fronts, self, keep=keep, state=state)
        self._tag_apply_dialog = dlg                   # 검사용
        dlg.exec()
        if isinstance(prefs, dict) and dlg.state_out != (prefs.get("tag_apply_window") or {}):
            prefs["tag_apply_window"] = dict(dlg.state_out)   # 크기·최대화·정렬 기억 — 책갈피창과 같은 설정
            try:
                mw._save_settings_now()
            except Exception:
                pass
        st = self._store()
        n = 0
        # 여러 장이어도 메인을 오래 세우지 않게 — 태그 저장소는 한 번에 모아 저장(bulk), 명함 DB 는 마지막에 한 번 커밋
        with store.bulk():
            for c, f in zip(cards, fronts):
                after = list(store.get_manual(f) or [])
                add = [t for t in after if t not in before[f]]
                rem = [t for t in before[f] if t not in after]
                if not add and not rem:
                    continue
                b = c.get("back")
                if b and os.path.exists(b):
                    b = os.path.realpath(b)
                    cur = [t for t in (store.get_manual(b) or []) if t not in rem]
                    store.set(b, list(dict.fromkeys(cur + add)))
                row = P.card_by_id(st, c["id"]) or c            # 대화상자 뒤 — 명함은 id 로 다시 읽는다
                P.update_card(st, c["id"], {"tags": list(dict.fromkeys([t for t in row.get("tags") or [] if t not in rem] + add))},
                              commit=False)
                n += 1
        st.con.commit()
        try:
            mw.bookmark_tree.refresh_tag_labels()
        except Exception:
            pass
        if n:
            self.refresh()
        return n

    # ── 주소록 가져오기 (§5.24 D22·D23 — 구글 주소록·리멤버 명함첩 vCard) ──
    def import_contacts(self, path=None, ask: bool = True, source: str = "google"):
        """vCard → 같은 사람(번호·메일)은 빈 칸만 채우고, 없는 사람은 그림 없는 명함으로 더한다. 반환 = (합침, 더함) 또는 None.
        source = 'remember'·'google' — 두 주소록 값이 다르면 리멤버가 이긴다(D24). 명함을 읽은 값·손으로 고친 값은 덮어쓰지 않는다."""
        if path is None:
            path, _f = QFileDialog.getOpenFileName(self, tr("주소록 가져오기"), "", "vCard (*.vcf)")
            if not path:
                return None
        try:
            raw = Path(path).read_bytes()
        except OSError as e:
            QMessageBox.warning(self, tr("주소록 가져오기"), tr("파일을 읽지 못했습니다.") + "\n" + type(e).__name__)
            return None
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp949", "replace")
        persons = V.people_from_vcf(text, (tr("명함"), tr_noop("명함")))   # 화면 언어 낱말 + 한국어 낱말(옛 내보내기)
        if not persons:
            QMessageBox.information(self, tr("주소록 가져오기"), tr("이 파일에서 연락처를 찾지 못했습니다."))
            return None
        if self._dirty and not self._ask_save():
            return None
        st = self._store()
        plan = P.import_plan(st, persons)
        m, a = P.import_counts(plan)
        if ask and QMessageBox.question(
                self, tr("주소록 가져오기"),
                tr("연락처 {n}명을 읽었습니다 — 이미 있는 {m}명은 빈 칸만 채우고, 새 {a}명은 그림 없는 명함으로 더합니다.").format(
                    n=len(persons), m=m, a=a)) != QMessageBox.StandardButton.Yes:
            return None
        res = P.apply_import(st, plan, tr("주소록"), source)
        self.last_import = res
        self.refresh()
        return res

    def closeEvent(self, e):
        if self._dirty and not self._ask_save():
            e.ignore()
            return
        self._fav_gen += 1                               # 늦게 오는 그림은 버림
        if self._st is not None:
            self._st.close()
            self._st = None
        super().closeEvent(e)
