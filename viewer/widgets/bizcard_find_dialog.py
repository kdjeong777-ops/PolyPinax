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

from PyQt6.QtCore import (Qt, QTimer, QSize, QObject, QRectF, QPointF, QDate, pyqtSignal, QAbstractTableModel,
    QModelIndex)
from PyQt6.QtGui import QPixmap, QIcon, QImage, QImageReader, QPainter, QPainterPath, QColor, QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QTableView,
    QAbstractItemView, QHeaderView, QSplitter, QWidget, QFormLayout, QPlainTextEdit, QPushButton,
    QListWidget, QListWidgetItem, QListView, QMessageBox, QFileDialog, QSizePolicy, QCheckBox, QTabBar, QToolButton,
    QMenu, QInputDialog, QApplication, QDateEdit, QDialogButtonBox, QWidgetAction, QScrollArea, QFrame)

from viewer.i18n import tr, tr_noop
from viewer import clipboard_util
from viewer.bizcard import people as P
from viewer.bizcard import phone as PH          # 번호 꼴 한 곳(§5.11 '번호 꼴')
from viewer.bizcard import recognize as R
from viewer.bizcard import vcard as V
from viewer.widgets.page_dots import PageDots   # 쪽 점 표시(디자인 SOT §4.5 '쪽 점', 261117-57)

C_NAME, C_COMP, C_TITLE, C_PHONE, C_MAIL, C_DATE = range(6)   # 전화·메일 열(§5.9 '결과', 사용자 지시 261119)
ROLE = Qt.ItemDataRole.UserRole
FAV_ICON = 56                       # 즐겨찾기 사람 칸 그림(카톡 꼴 둥근 네모)
FAV_ROWS = 2                        # 즐겨찾기 줄 최대 높이(줄 수) — 넘치면 그 칸 안에서 굴림
PHOTO_ICON = 72                     # 인물 사진 썸네일 줄(큰 화면은 그 위 — §5.24 사진창)
DETAIL_BG = {                        # 세부내용 카드·목록 표 — 띠(머리말)·띠 글·테두리 / 본문 / 메모 / 고른 줄 — 회색 톤(디자인 SOT §2.5 '명함 세부 카드', 261120-4)
    "light": {"head": "#e4e4e4", "head_fg": "#1a1a1a", "border": "#c8c8c8", "body": "#f5f5f5", "memo": "#ffffff",
              "sel": "#d8d8d8", "sel_fg": "#1a1a1a"},
    "dark": {"head": "#38383c", "head_fg": "#e6e6e6", "border": "#4a4a50", "body": "#2e2e31", "memo": "#1e1e20",
             "sel": "#424247", "sel_fg": "#ffffff"},
}
DETAIL_W = 330                     # 처음 너비 — 세부 칸(§5.24 '처음 너비': 목록은 네 열 최소 폭, 나머지는 사진창)
FIND_DELAY_MS = 250
RECENT = -1                         # '최근' 탭의 tabData(명함 DB 의 탭 id 와 겹치지 않음, §5.24.2)
FAV_KEY_MS = 120                    # 사람 칸을 키보드로 넘길 때 — 멈춘 뒤 마지막 사람만 그린다(§5.24.2)
RECENT_MS = 3000                    # 세부 칸에 이만큼 넘게 보이면 '최근' 에 넣는다(D27)
FAV_BG = "#cfe2f6"                  # 사진도 명함도 없을 때 — 옅은 파랑
IMG_FILTER = " ".join("*" + e for e in R.IMG_EXTS)
# 칸(키, 화면 이름) — 전화는 종류마다 첫 번호만 고친다(나머지는 그대로 둔다)
FIELDS = (("name", tr_noop("이름")), ("company", tr_noop("회사")), ("dept", tr_noop("부서")), ("title", tr_noop("직함")), ("cell", tr_noop("휴대폰")), ("work", tr_noop("전화")),
          ("fax", tr_noop("팩스")), ("email", tr_noop("메일")), ("address", tr_noop("주소")), ("url", tr_noop("누리집")))
MEMO_LABEL = tr_noop("메모")
PHONE_KEYS = ("cell", "work", "fax")
PHOTO_HANDLE = 9                    # 사진창 구분선 손잡이 높이(가운데 1px 선, §5.24.3 '구분선')
PRELOAD_MS = 1500                  # 창이 뜬 뒤 이만큼 쉬면 [해시태그] 준비(모듈·전체 태그 목록 — §5.24.4 '빠르게')
DROP_TINT, DROP_TINT_HOT = "0.04", "0.14"   # 놓을 자리 틀 바탕(강조색 투명도) — 창 위 / 그 자리 위(§5.24.3 '끌어 놓기')


def _list_phone(c) -> str:
    """목록 '전화' 칸 — 휴대폰, 없으면 첫 전화(§5.9 '결과')."""
    ph = [p for p in (c.get("phones") or []) if isinstance(p, (list, tuple)) and len(p) >= 2]
    return PH.normalize(next((n for k, n in ph if k == "cell"), "") or next((n for k, n in ph if k != "fax"), ""))


def edited_fields(c, g: dict, memo: str, extras=None) -> dict:
    """세부 칸 글 g(칸 → 글)·메모 → 명함 c 에 넣을 값 — 전화는 종류마다 첫 번호만 바꾸고 나머지는 둔다, 번호는 적을 꼴(§5.11).
    명함찾기 [저장]·중복 검토 '명함 고치기'(§5.24.8)가 같이 쓴다."""
    g = {k: (v or "").strip() for k, v in g.items()}
    for k in PHONE_KEYS:
        g[k] = PH.normalize(g.get(k, ""))
    old_ph = [tuple(x) for x in c.get("phones") or []]
    phones, used = [], set()
    for kind in ("cell", "work", "fax"):
        if g[kind]:
            phones.append((kind, g[kind]))
        first = next((i for i, (k, _n) in enumerate(old_ph) if k == kind), None)
        if first is not None:
            used.add(first)
    if extras is None:                                 # 중복 검토 '명함 고치기' — 숨은 둘째 값부터는 그대로
        phones += [p for i, p in enumerate(old_ph) if i not in used]
        emails = ([g["email"]] if g.get("email") else []) + list((c.get("emails") or [])[1:])
        urls = ([g["url"]] if g.get("url") else []) + list((c.get("urls") or [])[1:])
    else:                                              # 명함찾기 — 추가 칸 값으로(261120-35), 다른 종류 전화는 그대로
        phones += [tuple(p) for p in extras.get("phones") or []]
        phones += [p for i, p in enumerate(old_ph) if i not in used and p[0] not in PHONE_KEYS]
        emails = ([g["email"]] if g.get("email") else []) + list(extras.get("emails") or [])
        urls = ([g["url"]] if g.get("url") else []) + list(extras.get("urls") or [])
    name = g.get("name", "")
    name = R.clean_name_ko(name) if R._HANGUL.search(name) and not R._LATIN.search(name) else name
    return {"name": name, "company": R.strip_corp(g.get("company", "")), "dept": g.get("dept", ""),
            "title": g.get("title", ""), "address": g.get("address", ""), "phones": phones, "emails": emails,
            "urls": urls, "memo": memo}


def _list_mail(c) -> str:
    e = (c.get("emails") or [""])[0]
    return str(e[-1] if isinstance(e, (list, tuple)) else e or "")


def _today() -> str:
    import datetime
    return datetime.date.today().isoformat()


# ── 목록 표 — 가상 표(§5.9 '결과': 상한 없이 찾은 명함 전부, 보이는 줄만 그린다) ──
class _Cell:
    """`QTableWidgetItem` 처럼 읽는 칸(text·data) — 표를 부르는 코드·검사가 그대로 쓰게."""
    __slots__ = ("_m", "_r", "_c")

    def __init__(self, model, r, c):
        self._m, self._r, self._c = model, r, c

    def row(self):
        return self._r

    def column(self):
        return self._c

    def text(self):
        return self._m.text(self._r, self._c)

    def data(self, role):
        return self._m.data(self._m.index(self._r, self._c), role)


def _open_url(url: str) -> bool:
    """기본 브라우저로 주소를 연다 — Gmail 보내기(§5.24.1, 앱은 네트워크를 쓰지 않음 §2.1). 검사가 바꿔 받는다."""
    from PyQt6.QtCore import QUrl
    from PyQt6.QtGui import QDesktopServices
    return QDesktopServices.openUrl(QUrl(url))


_BOLD = []


def _bold_font() -> QFont:
    """굵은 글꼴 하나(표가 제 글꼴 크기·글꼴과 합친다 — 굵기만 바꿈)."""
    if not _BOLD:
        f = QFont()
        f.setBold(True)
        _BOLD.append(f)
    return _BOLD[0]


class _CardModel(QAbstractTableModel):
    """명함 행(dict) 목록 — 칸 글은 명함마다 한 번만 만들어 두고, 정렬은 그 글 차례(파이썬 정렬, 같으면 앞 차례 유지)."""

    def __init__(self, headers, parent=None):
        super().__init__(parent)
        self._heads = list(headers)
        self._rows = []
        self._disp = []
        self._at = {}

    @staticmethod
    def _cells(c):
        return (c.get("name") or "", c.get("company") or "", c.get("title") or "", _list_phone(c), _list_mail(c),
                P.shown_date(c))                              # 수정일 — 고친 날, 없으면 스캔일(§5.24.1 '수정일', 261120-25)

    def _reindex(self):
        self._at = {c["id"]: i for i, c in enumerate(self._rows)}

    def _perm(self, col, order):
        n = len(self._rows)
        if not (0 <= col < len(self._heads)):
            return list(range(n))
        d = self._disp
        return sorted(range(n), key=lambda i: d[i][col], reverse=order == Qt.SortOrder.DescendingOrder)

    def set_rows(self, rows, col=-1, order=Qt.SortOrder.AscendingOrder):
        self.beginResetModel()
        self._rows = list(rows)
        self._disp = [self._cells(c) for c in self._rows]
        p = self._perm(col, order)
        self._rows = [self._rows[i] for i in p]
        self._disp = [self._disp[i] for i in p]
        self._reindex()
        self.endResetModel()

    def card(self, r):
        return self._rows[r] if 0 <= r < len(self._rows) else None

    def row_of_id(self, cid) -> int:
        return self._at.get(cid, -1)

    def text(self, r, c):
        return self._disp[r][c] if 0 <= r < len(self._disp) and 0 <= c < len(self._heads) else ""

    def header(self, c):
        return self._heads[c]

    # ── Qt 모델 ──
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._heads)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        r, c = index.row(), index.column()
        if not (0 <= r < len(self._rows)):
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return self._disp[r][c]
        if role == ROLE and c == C_NAME:
            return self._rows[r]["id"]
        if role == Qt.ItemDataRole.FontRole and c == C_NAME:
            return _bold_font()                     # 이름은 굵게(§5.24.1 '이름 굵게', 사용자 지시 261119)
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole and 0 <= section < len(self._heads):
            return self._heads[section]
        return None

    def flags(self, index):
        f = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        return f | Qt.ItemFlag.ItemIsDragEnabled if index.isValid() else f

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        """머리말 정렬 — 고른 줄·현재 줄(영구 색인)이 같은 명함을 따라가게."""
        self.layoutAboutToBeChanged.emit([], QAbstractTableModel.LayoutChangeHint.VerticalSortHint)
        p = self._perm(column, order)
        inv = [0] * len(p)
        for new, old in enumerate(p):
            inv[old] = new
        self._rows = [self._rows[i] for i in p]
        self._disp = [self._disp[i] for i in p]
        self._reindex()
        old = self.persistentIndexList()
        self.changePersistentIndexList(old, [self.index(inv[i.row()], i.column()) if 0 <= i.row() < len(inv) else QModelIndex()
                                             for i in old])
        self.layoutChanged.emit([], QAbstractTableModel.LayoutChangeHint.VerticalSortHint)


class _CardTable(QTableView):
    """명함찾기 목록 표 — `QTableWidget` 의 쓰던 부분(item·setCurrentCell·currentRow·rowCount·신호)만 같은 이름으로."""
    currentCellChanged = pyqtSignal(int, int, int, int)
    cellClicked = pyqtSignal(int, int)

    def __init__(self, headers, parent=None):
        super().__init__(parent)
        self.setModel(_CardModel(headers, self))
        self.selectionModel().currentChanged.connect(
            lambda cur, prev: self.currentCellChanged.emit(cur.row(), cur.column(), prev.row(), prev.column()))
        self.clicked.connect(lambda i: self.cellClicked.emit(i.row(), i.column()))

    def set_cards(self, rows):
        hh = self.horizontalHeader()
        col = hh.sortIndicatorSection() if self.isSortingEnabled() else -1
        self.model().set_rows(rows, col, hh.sortIndicatorOrder())

    def rowCount(self) -> int:
        return self.model().rowCount()

    def columnCount(self) -> int:
        return self.model().columnCount()

    def item(self, r, c):
        m = self.model()
        return _Cell(m, r, c) if 0 <= r < m.rowCount() and 0 <= c < m.columnCount() else None

    def horizontalHeaderItem(self, c):
        class _H:
            def __init__(self, t):
                self._t = t

            def text(self):
                return self._t
        return _H(self.model().header(c)) if 0 <= c < self.model().columnCount() else None

    def itemAt(self, pos):
        i = self.indexAt(pos)
        return self.item(i.row(), i.column()) if i.isValid() else None

    def setCurrentCell(self, r, c):
        self.setCurrentIndex(self.model().index(r, c))

    def currentRow(self) -> int:
        return self.currentIndex().row()

    def scrollToItem(self, it):
        if it is not None:
            self.scrollTo(self.model().index(it.row(), it.column()))


class TodoDialog(QDialog):
    """할 일(D26) — 작업 제목·내용·시작일(기본 오늘)·종료일(체크하지 않으면 계속)."""

    def __init__(self, parent=None, info=None, title=""):
        super().__init__(parent)
        info = info or {}
        self.setWindowTitle(title or tr("할 일"))
        f = QFormLayout(self)
        self.ed_title = QLineEdit(info.get("title", ""))
        self.ed_title.setPlaceholderText(tr("작업 제목 — 즐겨찾기 탭 이름이 됩니다"))
        f.addRow(tr("작업 제목"), self.ed_title)
        self.ed_memo = QPlainTextEdit(info.get("memo", ""))
        self.ed_memo.setFixedHeight(90)
        f.addRow(tr("내용"), self.ed_memo)
        self.d_start = QDateEdit(QDate.fromString(info.get("start") or _today(), "yyyy-MM-dd"))
        self.d_start.setCalendarPopup(True)
        self.d_start.setDisplayFormat("yyyy-MM-dd")
        f.addRow(tr("시작일"), self.d_start)
        erow = QHBoxLayout()
        self.chk_end = QCheckBox(tr("종료일"))
        self.chk_end.setToolTip(tr("체크하지 않으면 시작일부터 계속"))
        self.d_end = QDateEdit(QDate.fromString(info.get("end") or info.get("start") or _today(), "yyyy-MM-dd"))
        self.d_end.setCalendarPopup(True)
        self.d_end.setDisplayFormat("yyyy-MM-dd")
        self.chk_end.toggled.connect(self.d_end.setEnabled)
        self.chk_end.setChecked(bool(info.get("end")))
        self.d_end.setEnabled(bool(info.get("end")))
        erow.addWidget(self.chk_end)
        erow.addWidget(self.d_end, 1)
        f.addRow(erow)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        f.addRow(bb)
        self.resize(380, self.sizeHint().height())

    def _ok(self):
        if not self.ed_title.text().strip():
            self.ed_title.setFocus()
            return
        if self.chk_end.isChecked() and self.d_end.date() < self.d_start.date():
            QMessageBox.information(self, tr("할 일"), tr("종료일이 시작일보다 앞입니다."))
            return
        self.accept()

    def info(self) -> dict:
        return {"title": self.ed_title.text().strip(), "memo": self.ed_memo.toPlainText().strip(),
                "start": self.d_start.date().toString("yyyy-MM-dd"),
                "end": self.d_end.date().toString("yyyy-MM-dd") if self.chk_end.isChecked() else ""}


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


def _virtual_key(card) -> str:
    """그림 없는 명함의 '해시태그 수정' 창 자리 — 디스크에 없는 경로(메모리 사본에만, §5.24.4). 보이는 이름 = 이름_회사."""
    import tempfile
    label = "_".join(x for x in (card.get("name"), card.get("company")) if x) or tr("명함 {n}").format(n=card.get("id"))
    label = "".join(ch if ch not in '\\/:*?"<>|' else " " for ch in str(label)).strip() or "card"
    return os.path.join(tempfile.gettempdir(), "polypinax-bizcard-tags", str(card.get("id")), label)


def _card_tag_store(real):
    """태그 저장소의 메모리 사본 — 창이 고치는 동안 디스크에 쓰지 않는다(그림 없는 명함의 가상 경로가 실제 저장소에 남지 않게).
    기존 태그 목록·등록 차례는 실제 저장소 것 그대로."""
    import json
    from viewer.tag_store import TagStore

    class _CardTagStore(TagStore):
        def __init__(self):
            self._path = Path(os.devnull)
            self._data = json.loads(json.dumps(real._data, ensure_ascii=False))
            self._bulk_depth = 0
            self._dirty = False

        def _save(self):
            self._dirty = False

        def backup(self) -> bool:
            return False
    return _CardTagStore()


from PyQt6.QtWidgets import QSplitterHandle   # noqa: E402 — 사진창 손잡이(261120-22)


class _LineHandle(QSplitterHandle):
    """사진창 위 명함·아래 인물 사진 사이 손잡이 — 가운데 1px 선(카드 테 색)이 곧 손잡이(§5.24.3 '구분선', 261120-22).
    집을 수 있게 높이 `PHOTO_HANDLE`, 가리키면 선이 강조색 2px. 종전엔 선이 인물 사진 칸 안의 그림이고 손잡이는 그 위 빈 틈이라
    선을 끌면 크기가 바뀌지 않았다(사용자 보고 '사진사이의 바 위에서 끌어서 옮길 수 있어. 바를 집어서 크기 조절하도록')."""

    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._hot = False

    def enterEvent(self, e):
        self._hot = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hot = False
        self.update()
        super().leaveEvent(e)

    def line_color(self) -> QColor:
        pal = self.palette()
        if self._hot:
            return pal.color(pal.ColorRole.Highlight)
        c = DETAIL_BG["dark" if pal.color(pal.ColorRole.Window).lightness() < 128 else "light"]
        return QColor(c["border"])

    def paintEvent(self, e):
        p = QPainter(self)
        w = 2 if self._hot else 1
        y = self.height() // 2
        p.fillRect(6, y - (w // 2), max(0, self.width() - 6), w, self.line_color())   # 왼쪽 6 = 사진창 안쪽 여백과 같게
        p.end()


class _LineSplitter(QSplitter):
    def createHandle(self):
        return _LineHandle(self.orientation(), self)


class _MemoTypeWatch(QObject):
    """메모 칸에 글을 치기 시작하는 순간(글자 키·한글 입력) — 칸이 받기 전에 부른다(§5.9 '메모 날짜', 261120-27)."""

    def __init__(self, edit, before):
        super().__init__(edit)
        self._before = before
        edit.installEventFilter(self)

    def eventFilter(self, obj, ev):
        from PyQt6.QtCore import QEvent
        t = ev.type()
        if t == QEvent.Type.KeyPress and ev.text() and ev.text().isprintable() \
                and not (ev.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)):
            self._before()
        elif t == QEvent.Type.InputMethod and (ev.commitString() or ev.preeditString()):
            self._before()
        return False


class _TodoXlsxWorker(QObject):
    """할 일 엑셀 만들기·쓰기(배경, 261120-21) — done(성공, 실패 까닭 종류). ★ 명함 값은 신호·로그에 싣지 않는다(§2.1)."""
    done = pyqtSignal(bool, str)
    finished = pyqtSignal()

    def __init__(self, path, rows, heads, sheet, ongoing):
        super().__init__()
        self._a = (path, rows, heads, sheet, ongoing)

    def run(self):
        try:
            from viewer.bizcard.todo_xlsx import write_todos
            write_todos(*self._a)
            self.done.emit(True, "")
        except Exception as e:
            self.done.emit(False, type(e).__name__)
        finally:
            self.finished.emit()


class _KnownWorker(QObject):
    """저장소 사본의 전체 태그 목록을 배경에서 센다(`known_tags_of`, 261120-20) — done(실제 저장소, 목록, 센 때 세대, 센 때 데이터)."""
    done = pyqtSignal(object, list, int, object)
    finished = pyqtSignal()

    def __init__(self, snap, real, gen, data):
        super().__init__()
        self._snap, self._real, self._gen, self._data = snap, real, gen, data

    def run(self):
        try:
            from viewer.tag_store import known_tags_of
            out = known_tags_of(self._snap, list(self._snap._data.keys()))
            self.done.emit(self._real, out, self._gen, self._data)   # 실패하면 넘기지 않는다(창이 열 때 센다)
        except Exception:
            pass
        finally:
            self.finished.emit()


def _menu_act(m: QMenu, text: str, fn):
    a = m.addAction(text)
    a.triggered.connect(lambda _c=False: fn())
    return a


def _menu_act_help(m: QMenu, text: str, fn, help_text: str, parent=None):
    """오른쪽에 [?] 가 붙은 메뉴 항목 — 글을 누르면 실행, [?] 를 누르면 설명만(실행하지 않는다, §5.24.2 '탭 메뉴')."""
    w = QWidget(m)
    h = QHBoxLayout(w)
    h.setContentsMargins(4, 0, 4, 0)
    h.setSpacing(2)
    b = QToolButton(w)
    b.setText(text)
    b.setAutoRaise(True)
    b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    b.setStyleSheet("QToolButton{text-align:left; padding:3px 18px;}")
    q = QToolButton(w)
    q.setText("?")
    q.setAutoRaise(True)
    q.setToolTip(help_text)
    h.addWidget(b, 1)
    h.addWidget(q)

    def run():
        m.close()
        fn()
    b.clicked.connect(lambda _c=False: run())
    q.clicked.connect(lambda _c=False: QMessageBox.information(parent or m, text, help_text))
    act = QWidgetAction(m)
    act.setDefaultWidget(w)
    act.setText(text)
    m.addAction(act)
    return act


def _tab_icon(kind: str, pal) -> QIcon:
    """탭 아이콘(그려서 만든 그림) — 'todo' = 체크된 동그라미, 'recent' = 시계(§5.24.2 '탭 줄')."""
    pm = QPixmap(16, 16)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    from PyQt6.QtGui import QPen
    if kind == "todo":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.highlight().color())
        p.drawEllipse(1, 1, 14, 14)
        pen = QPen(pal.highlightedText().color(), 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawPolyline(*[QPointF(x, y) for x, y in ((4.5, 8.2), (7.0, 10.8), (11.5, 5.5))])
    else:
        pen = QPen(pal.text().color(), 1.6)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(1.5, 1.5, 13, 13))
        p.drawLine(QPointF(8, 8), QPointF(8, 4))
        p.drawLine(QPointF(8, 8), QPointF(11, 9.5))
    p.end()
    return QIcon(pm)


class _DropTabBar(QTabBar):
    """사람 칸·표에서 끌어 온 명함을 탭 위에 놓으면 그 탭에 복사(§5.24.2 '넣기·복사')."""
    dropped = pyqtSignal(int, object)                  # (탭 번호, 끌어 온 곳)

    def __init__(self, accepts):
        super().__init__()
        self._accepts = accepts
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e):
        e.acceptProposedAction() if self._accepts(e) else e.ignore()

    def dragMoveEvent(self, e):
        e.acceptProposedAction() if self._accepts(e) and self.tabAt(e.position().toPoint()) >= 0 else e.ignore()

    def dropEvent(self, e):
        i = self.tabAt(e.position().toPoint())
        if not self._accepts(e) or i < 0:
            e.ignore()
            return
        e.setDropAction(Qt.DropAction.CopyAction)
        e.accept()
        self.dropped.emit(i, e.source())


class _DropButton(QToolButton):
    """'+' — 끌어 놓으면 새 탭·새 할 일 메뉴(끈 사람들이 들어간다)."""
    dropped = pyqtSignal(object)

    def __init__(self, accepts):
        super().__init__()
        self._accepts = accepts
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e):
        e.acceptProposedAction() if self._accepts(e) else e.ignore()

    def dropEvent(self, e):
        if not self._accepts(e):
            e.ignore()
            return
        e.setDropAction(Qt.DropAction.CopyAction)
        e.accept()
        src = e.source()
        QTimer.singleShot(0, lambda: self.dropped.emit(src))


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

    drag_hint = None           # 바깥 파일을 끄는 동안 알림(e, 떠나거나 놓으면 None) — 놓을 자리 표시(§5.24.3)

    def _hint(self, e):
        if self.drag_hint is not None and (e is None or e.source() is not self):
            self.drag_hint(e)

    def dragEnterEvent(self, e):
        if self._ok(e):
            e.acceptProposedAction()
        else:
            e.ignore()
        self._hint(e)

    def dragMoveEvent(self, e):
        if self._ok(e):
            e.acceptProposedAction()
        else:
            e.ignore()
        self._hint(e)

    def dragLeaveEvent(self, e):
        super().dragLeaveEvent(e)
        self._hint(None)

    def dropEvent(self, e):
        self._hint(None)
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


class _FitScroll(QScrollArea):
    """세부 칸 영역(§5.24.1 '추가 칸', 261120-35) — 바라는 높이 = 안의 칸 높이(늘 다 보이게), 창이 낮으면 줄고 스크롤."""

    def sizeHint(self):
        w = self.widget()
        h = (w.sizeHint().height() if w is not None else 0) + 2 * self.frameWidth()
        return QSize(super().sizeHint().width(), h)

    def minimumSizeHint(self):
        return QSize(super().minimumSizeHint().width(), 3 * self.fontMetrics().height())


class BizcardFindDialog(QDialog):
    def __init__(self, parent=None, db=None, host=None):
        """host = 본 뷰어 대신 일을 하는 객체(별도 명함 프로그램 — `standalone.Host`, §5.27 '경계'). 없으면 parent(MainWindow)."""
        super().__init__(parent)
        PH.reload()                                    # 환경설정 '전화번호 기본 국가'(§5.11 '번호 꼴')
        self._mw = host if host is not None else parent
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
        self._peek = None                              # '마감한 탭 ▸ 보기' 로 잠시 보이는 탭(D28)
        self._table_tab = None                         # 목록 표가 보이는 탭(None = 찾기 결과, §5.24.2 '탭 줄')
        self._recent_id = None
        self._ghost_all = False                        # 흐린 찾기 글을 다시 골라 전체 목록을 보는 중(§5.24.1 '찾기 칸 흐린 글')
        self.setWindowTitle(tr("명함찾기"))
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowMinimizeButtonHint)
        self.setAcceptDrops(True)
        self.resize(1360, 800)
        v = QVBoxLayout(self)

        top = QHBoxLayout()
        self.cb_kind = QComboBox()                     # 찾기 칸 앞 구분(§5.24.1 '위 줄', 사용자 지시 261119)
        kind_label = dict(zip(P.KINDS, (tr("전체"), tr("한글"), tr("영어"), tr("명함 있음"), tr("명함 없음"),
                                        tr("사진 있음"), tr("사진 없음"))))
        for gi, grp in enumerate(P.KIND_GROUPS):        # 언어 / 명함 / 사진 묶음 사이 구분선(261120-24)
            if gi:
                self.cb_kind.insertSeparator(self.cb_kind.count())
            for key in grp:
                self.cb_kind.addItem(kind_label[key], key)
        self.cb_kind.setToolTip(tr("한글·영어 = 이름 글자, 명함 있음·없음 = 명함 그림(없음 = 주소록에서 들인 명함), "
                                   "사진 있음·없음 = 인물 사진"))
        self.cb_kind.currentIndexChanged.connect(lambda _i: self._on_kind())
        from viewer.widgets.icons import themed_icon as _ti
        self.btn_menu = QToolButton()                  # 맨 왼쪽 ≡ 메뉴 — 아래 단추와 같은 항목 + 종료(§5.24.1 '≡ 메뉴', 261120-37)
        self.btn_menu.setIcon(_ti("menu", size=18))
        self.btn_menu.setIconSize(QSize(18, 18))
        self.btn_menu.setAutoRaise(True)
        self.btn_menu.setToolTip(tr("메뉴"))
        self.main_menu = QMenu(self.btn_menu)
        self.main_menu.aboutToShow.connect(self._fill_main_menu)
        # 메뉴 화살표(작은 v) 없이 — setMenu 대신 누르면 단추 아래에 띄운다(261120-40, 디자인 SOT §2.7 예외)
        self.btn_menu.clicked.connect(
            lambda: self.main_menu.popup(self.btn_menu.mapToGlobal(self.btn_menu.rect().bottomLeft())))
        top.addWidget(self.btn_menu)
        top.addWidget(self.cb_kind)
        self.ed_find = QLineEdit()
        from viewer.widgets.search_ghost import SearchGhost   # 261117-42(검색창 SOT §6.1): 찾은 글은 떠나면 흐리게
        SearchGhost(self.ed_find, instant=True)
        self.ed_find.setPlaceholderText(tr("이름·회사·메모 등 — 낱말 여럿은 모두 들어 있는 명함, #낱말은 해시태그"))
        self.ed_find.setClearButtonEnabled(True)
        top.addWidget(self.ed_find, 1)
        self.btn_tags = QPushButton(tr("해시태그"))       # 찾기 칸 바로 오른쪽(§5.24.1 '위 줄', 사용자 지시 261119)
        self.btn_tags.setToolTip(tr("고른 명함들에 해시태그를 붙이거나 뗍니다 — 정리본 파일에도 같이, 찾기 칸에서 #낱말로 찾습니다"))
        self.btn_tags.clicked.connect(lambda _c=False: self.edit_tags())
        top.addWidget(self.btn_tags)
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
        from viewer.widgets.icons import themed_icon
        self.btn_settings = QToolButton()               # 찾기 줄 오른쪽 끝 톱니 = 명함 환경설정(§5.24.9, 261120-17)
        self.btn_settings.setIcon(themed_icon("gear", size=18))
        self.btn_settings.setIconSize(QSize(18, 18))
        self.btn_settings.setAutoRaise(True)
        self.btn_settings.setToolTip(tr("명함 환경설정 — 명함 폴더·전화번호 기본 국가·'최근' 항목 제한"))
        self.btn_settings.clicked.connect(lambda _c=False: self.open_settings())
        top.addWidget(self.btn_settings)
        v.addLayout(top)
        self._find_timer = QTimer(self)
        self._find_timer.setSingleShot(True)
        self._find_timer.setInterval(FIND_DELAY_MS)
        self._find_timer.timeout.connect(self.refresh)
        self.ed_find.textChanged.connect(lambda _t: self._search_mode())
        self.ed_find.installEventFilter(self)                   # 찾기 칸을 고르면 찾기 결과로(§5.24.2 '탭 줄')
        self.cb_period.currentIndexChanged.connect(self._on_period)
        self._recent_timer = QTimer(self)
        self._recent_timer.setSingleShot(True)
        self._recent_timer.setInterval(RECENT_MS)
        self._recent_timer.timeout.connect(self._recent_hit)
        self._fav_key_timer = QTimer(self)
        self._fav_key_timer.setSingleShot(True)
        self._fav_key_timer.setInterval(FAV_KEY_MS)
        self._fav_key_timer.timeout.connect(self._fav_key_show)
        self._fav_key_id = None

        # ── 위 띠: [탭 줄 + 사람 칸 | 할 일 칸] (§5.24.10 '배치', 261120-34) · 아래 왼쪽: [표 | 세부] ──
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        self.top_band = QWidget()
        tbl = QHBoxLayout(self.top_band)
        tbl.setContentsMargins(0, 0, 0, 0)
        favw = QWidget()
        fvl = QVBoxLayout(favw)
        fvl.setContentsMargins(0, 0, 0, 0)
        tbl.addWidget(favw, 1)
        from viewer.widgets.bizcard_todo_panel import TodoPanel
        self.todo_panel = TodoPanel(self._store, self)
        self.todo_panel.changed.connect(lambda: self._fav_fill_tabs(self._fav_gid()))
        self.todo_panel.setVisible(False)
        tbl.addWidget(self.todo_panel)
        tabs_row = QHBoxLayout()
        self.fav_tabs = _DropTabBar(accepts=lambda e: e.source() in (self.fav, self.table))
        self.fav_tabs.dropped.connect(self._drop_on_tab)
        self.fav_tabs.tabBarClicked.connect(self._tab_clicked)
        self.fav_tabs.setMovable(True)
        self.fav_tabs.setExpanding(False)
        self.fav_tabs.setDrawBase(False)
        self.fav_tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.fav_tabs.customContextMenuRequested.connect(self._fav_tab_menu)
        self.fav_tabs.tabBarDoubleClicked.connect(lambda i: self.fav_rename_tab(i))
        self.fav_tabs.tabMoved.connect(self._tab_moved)
        self.fav_tabs.currentChanged.connect(lambda _i: self._fav_tab_changed())
        tabs_row.addWidget(self.fav_tabs)
        self.btn_fav_tab = _DropButton(accepts=lambda e: e.source() in (self.fav, self.table))
        self.btn_fav_tab.setText("+")
        self.btn_fav_tab.setAutoRaise(True)
        self.btn_fav_tab.setToolTip(tr("새 즐겨찾기 탭·새 할 일 — 표에서 고른 명단이 들어갑니다(사람 칸에서 끌어 놓아도)"))
        self.btn_fav_tab.clicked.connect(lambda _c=False: self.plus_menu())
        self.btn_fav_tab.dropped.connect(lambda src: self.plus_menu(self._drag_cards(src)))
        tabs_row.addWidget(self.btn_fav_tab)
        tabs_row.addStretch(1)
        self.cb_recent = QComboBox()                       # '최근' 탭 기간(D27)
        for key, label in (("1w", tr("1주")), ("1m", tr("1개월")), ("3m", tr("3개월")), ("custom", tr("지정"))):
            self.cb_recent.addItem(label, key)
        self.cb_recent.setToolTip(tr("최근 탭 — 이 기간에 본 명함"))
        self.d_recent_from = QDateEdit(QDate.currentDate().addDays(-7))
        self.d_recent_to = QDateEdit(QDate.currentDate())
        for d in (self.d_recent_from, self.d_recent_to):
            d.setCalendarPopup(True)
            d.setDisplayFormat("yyyy-MM-dd")
            d.dateChanged.connect(lambda _d: self._recent_changed())
        self.cb_recent.currentIndexChanged.connect(lambda _i: self._recent_changed())
        for w in (self.cb_recent, self.d_recent_from, self.d_recent_to):
            w.setVisible(False)
            tabs_row.addWidget(w)
        fvl.addLayout(tabs_row)
        self.fav = _OrderList(external=lambda _e: self.fav_add_selected(),
                              accepts=lambda e: e.source() is self.table and self._fav_gid() != RECENT)
        self.fav.setIconSize(QSize(FAV_ICON, FAV_ICON))
        self.fav.setGridSize(QSize(FAV_ICON + 22, FAV_ICON + 24))
        self.fav.setUniformItemSizes(True)
        self.fav.setWordWrap(False)
        self.fav.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.fav.setToolTip(tr("표의 줄을 끌어 놓으면 이 탭에 넣습니다 — 끌어 차례 바꾸기, 다른 탭에 끌어 놓으면 복사, Delete 로 빼기"))
        self.fav.reordered.connect(self._fav_save_order)
        self.fav.deleteRequested.connect(lambda: self.fav_remove_selected())
        self.fav.itemClicked.connect(lambda it: self._show_card_id(it.data(ROLE)))
        self.fav.currentItemChanged.connect(self._fav_current)    # 키보드로 옮겨도 그 명함(§5.24.2)
        self.fav.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.fav.customContextMenuRequested.connect(self._fav_menu)
        fvl.addWidget(self.fav)
        fvl.addStretch(1)

        mid = self.mid = QSplitter(Qt.Orientation.Horizontal)
        self.table = _CardTable([tr("이름"), tr("회사"), tr("직함"), tr("전화"), tr("메일"), tr("수정일")])   # 가상 표(§5.9 '결과'), 끝 열 = 수정일(261120-25)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setDragEnabled(True)
        self.table.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)            # 줄 번갈아 색·세로 선 없음(§5.24.1 '목록 표 꾸밈')
        self.table.setShowGrid(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hh.setStretchLastSection(True)
        hh.setSortIndicatorShown(True)
        phone_w = self.table.fontMetrics().horizontalAdvance("010-0000-0000") + 20
        for c, w in ((C_NAME, 90), (C_COMP, 150), (C_TITLE, 80), (C_PHONE, phone_w), (C_MAIL, 170)):
            self.table.setColumnWidth(c, w)
        self.table.setSortingEnabled(True)                   # 머리말을 누르면 정렬, 다시 누르면 반대(§5.24)
        self.table.sortByColumn(C_NAME, Qt.SortOrder.AscendingOrder)   # 처음은 이름 차례(§5.24.1, 사용자 지시 261119)
        self.table.currentCellChanged.connect(self._on_current)
        self.table.cellClicked.connect(lambda r, _c: self._on_clicked(r))
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_menu)
        for seq, fn in ((QKeySequence(QKeySequence.StandardKey.Copy), lambda: self.copy_selected()),
                        (QKeySequence(Qt.Key.Key_Delete), lambda: self.delete_cards())):
            sc = QShortcut(seq, self.table)
            sc.setContext(Qt.ShortcutContext.WidgetShortcut)
            sc.activated.connect(fn)
        mid.addWidget(self.table)

        detail = QWidget()
        dv = QVBoxLayout(detail)
        dv.setContentsMargins(6, 0, 0, 0)
        self.detail_box = QWidget()                    # 세부내용 카드 — 제목 띠·옅은 본문·더 옅은 메모(§5.24.1 '세부내용 묶음', 261120-4)
        self.detail_box.setObjectName("bizDetailBox")
        self.detail_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        cardv = QVBoxLayout(self.detail_box)
        cardv.setContentsMargins(1, 1, 1, 1)           # 테두리 1px 안쪽
        cardv.setSpacing(0)
        self.detail_head = QLabel(tr("세부내용"))       # 가운데 굵은 제목 띠
        self.detail_head.setObjectName("bizDetailHead")
        self.detail_head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tf = self.detail_head.font()
        tf.setBold(True)
        self.detail_head.setFont(tf)
        cardv.addWidget(self.detail_head)
        body = QWidget()
        body.setObjectName("bizDetailBody")
        body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        cardv.addWidget(body, 1)
        rv = QVBoxLayout(body)
        rv.setContentsMargins(10, 8, 10, 8)
        form = QFormLayout()
        self.eds, self.chk = {}, {}
        for k, label in FIELDS:
            ed = QLineEdit()
            if k in ("name", "cell"):                  # 이름·휴대폰은 굵게(§5.24.1 '이름 굵게', 261117-61·261120-4)
                bf = ed.font()
                bf.setBold(True)
                ed.setFont(bf)
            ed.textEdited.connect(lambda _t: self._set_dirty(True))
            if k in PHONE_KEYS:
                PH.attach(ed)                          # 치는 대로 하이픈·떠날 때 적을 꼴(§5.11 '번호 꼴')
            cb = QCheckBox(tr(label))
            cb.setToolTip(tr("체크한 칸을 [내용 복사] 로 글로 복사합니다 — 체크는 다음에도 그대로"))
            cb.toggled.connect(lambda _on: self._save_copy_fields())
            form.addRow(cb, ed)
            self.eds[k], self.chk[k] = ed, cb
        # 메모 위 칸 영역 — 추가 메일·전화·누리집 줄까지, 넘치면 스크롤(§5.24.1 '추가 칸', 261120-35)
        fields_w = QWidget()
        fields_w.setObjectName("bizDetailFields")
        fl = QVBoxLayout(fields_w)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.addLayout(form)
        self.form_extra = QFormLayout()
        fl.addLayout(self.form_extra)
        self.extra_eds = []                            # [(갈래 email|phone|url, 전화 종류, 칸)]
        self.fields_scroll = _FitScroll()
        self.fields_scroll.setWidget(fields_w)
        self.fields_scroll.setWidgetResizable(True)
        self.fields_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.fields_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.fields_scroll.setStyleSheet("QScrollArea, QWidget#bizDetailFields{background:transparent;}")
        self.fields_scroll.viewport().setAutoFillBackground(False)
        self.fields_scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)   # 내용 높이까지만, 남는 높이는 메모
        rv.addWidget(self.fields_scroll)
        self.chk["memo"] = QCheckBox(tr(MEMO_LABEL))
        self.chk["memo"].toggled.connect(lambda _on: self._save_copy_fields())
        rv.addWidget(self.chk["memo"])
        self.ed_memo = QPlainTextEdit()
        self.ed_memo.textChanged.connect(lambda: self._set_dirty(True) if not self._loading else None)
        self._memo_watch = _MemoTypeWatch(self.ed_memo, self._memo_date_before_typing)   # 쓰기 시작하면 오늘 날짜(261120-27)
        self._memo_view = 0                                # 메모 칸을 명함 값으로 새로 채울 때마다 +1 — 날짜는 한 보기에 한 번
        self.ed_memo.textChanged.connect(lambda: setattr(self, "_memo_view", self._memo_view + 1) if self._loading else None)
        rv.addWidget(self.ed_memo, 1)
        self.lbl_file = QLabel("")
        self.lbl_file.setWordWrap(True)
        self.lbl_file.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        rv.addWidget(self.lbl_file)
        dv.addWidget(self.detail_box, 1)
        self._detail_css = ""
        self._style_detail()
        self.btn_save = QPushButton(tr("저장"))
        self.btn_save.setToolTip(tr("고친 칸·메모를 명함 DB 에 저장합니다 — 이름·회사를 바꾸면 정리본 파일 이름도 '성명_회사명' 으로"))
        self.btn_save.clicked.connect(lambda _c=False: self.save())
        self.btn_save.setEnabled(False)
        self.btn_copy = QPushButton(tr("내용 복사"))
        self.btn_copy.setToolTip(tr("고른 명함들의 체크한 칸을 '항목: 값' 글로 복사합니다"))
        self.btn_copy.clicked.connect(lambda _c=False: self.copy_selected())
        srow = QHBoxLayout()                               # [저장] 오른쪽에 [내용 복사](§5.24, 사용자 지시 261119)
        srow.addWidget(self.btn_save, 1)
        srow.addWidget(self.btn_copy, 1)
        dv.addLayout(srow)                             # [저장]·[내용 복사] 는 묶음 밖 아래
        mid.addWidget(detail)
        mid.setStretchFactor(0, 3)
        mid.setStretchFactor(1, 2)
        lv.addWidget(mid, 1)

        # ── 오른쪽 끝: 사진창(위 명함 + 앞↔뒤, 아래 인물 사진) ──
        self.photo_split = _LineSplitter(Qt.Orientation.Vertical)   # 위 명함과 아래 인물 사진 사이 구분선 = 손잡이(§5.24.3 '구분선', 261120-22)
        self.photo_split.setHandleWidth(PHOTO_HANDLE)
        self.photo_split.setChildrenCollapsible(False)
        cardw = QWidget()
        cv = QVBoxLayout(cardw)
        cv.setContentsMargins(6, 0, 0, 0)
        self.pv = QLabel()
        self.pv.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pv.setMinimumSize(260, 150)
        self.pv.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.pv.setToolTip(tr("인물 사진을 여기에 끌어 놓으면 이 명함의 인물 사진으로 넣습니다"))
        cv.addWidget(self.pv, 1)
        self.dots = PageDots()                         # 쪽 점 표시 — 앞·뒷면(사용자 지시 261119, 종전 앞↔뒤 동그란 단추)
        self.dots.setToolTip(tr("명함 앞면 ↔ 뒷면"))
        self.dots.picked.connect(lambda i: self._flip(i == 1))
        cv.addWidget(self.dots, 0, Qt.AlignmentFlag.AlignHCenter)
        self.photo_split.addWidget(cardw)
        photow = QWidget()
        pvl = QVBoxLayout(photow)
        pvl.setContentsMargins(6, 0, 0, 0)
        # 위 = 큰 화면, 아래 = 썸네일 한 줄(§5.24 사진창, 사용자 지시 261119)
        self.photo_view = QLabel()
        self.photo_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.photo_view.setMinimumSize(160, 120)
        self.photo_view.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.photo_shown = ""
        pvl.addWidget(self.photo_view, 1)
        self.photos = _OrderList(external=self._drop_files, accepts=lambda e: e.mimeData().hasUrls())
        self.photos.setWrapping(False)                     # 한 줄 — 넘치면 가로 스크롤
        self.photos.setIconSize(QSize(PHOTO_ICON, PHOTO_ICON))
        self.photos.setGridSize(QSize(PHOTO_ICON + 12, PHOTO_ICON + 12))
        self.photos.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.photos.setFixedHeight(PHOTO_ICON + 16 + self.photos.horizontalScrollBar().sizeHint().height())
        self.photos.currentItemChanged.connect(lambda _c, _p: self._show_photo())
        self.photos.setToolTip(tr("끌어 차례를 바꿉니다(첫 사진이 즐겨찾기 그림) — Delete 로 지우기(휴지통)"))
        self.photos.reordered.connect(self._photo_reordered)
        self.photos.drag_hint = self._photos_drag          # 썸네일 줄 위에서도 놓을 자리 표시(§5.24.3 '끌어 놓기')
        self.photos.deleteRequested.connect(lambda: self.delete_photos())
        self.photos.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.photos.customContextMenuRequested.connect(self._photo_menu)
        pvl.addWidget(self.photos)
        prow = QHBoxLayout()                               # 인물 사진 칸 아래 단추(§5.24 '단추', 사용자 지시 261119)
        self.btn_photo = QPushButton(tr("사진 추가"))
        self.btn_photo.setToolTip(tr("인물 사진을 '인물' 폴더에 정리본과 같은 이름의 JPG 로 넣습니다 — 위치 정보 등 EXIF 는 뺍니다"))
        self.btn_photo.clicked.connect(lambda _c=False: self._pick_photos())
        self.btn_photo_del = QPushButton(tr("사진 삭제"))
        self.btn_photo_del.setToolTip(tr("썸네일 줄에서 고른 인물 사진(없으면 큰 화면의 사진)을 휴지통으로"))
        self.btn_photo_del.clicked.connect(lambda _c=False: self.delete_shown_photos())
        prow.addWidget(self.btn_photo)
        prow.addWidget(self.btn_photo_del)
        prow.addStretch(1)
        pvl.addLayout(prow)
        self.photo_split.addWidget(photow)
        self.photo_split.setStretchFactor(0, 2)
        self.photo_split.setStretchFactor(1, 3)
        self.photo_split.splitterMoved.connect(lambda _p, _i: QTimer.singleShot(0, self._show_card))
        self._detail_css = ""
        self._style_detail()                           # 사진창 구분선까지 한 번 더(세부 카드보다 늦게 만든다)

        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.split.addWidget(left)
        self.split.addWidget(self.photo_split)
        self.split.setStretchFactor(0, 5)
        self.split.setStretchFactor(1, 2)
        self.split.splitterMoved.connect(lambda _p, _i: QTimer.singleShot(0, self._show_card))
        self.split.splitterMoved.connect(lambda _p, _i: self._sync_todo_width())   # 할 일 칸 폭 = 사진창 폭(§5.24.10)
        tbl.setSpacing(self.split.handleWidth())
        self.top_band.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        v.addWidget(self.top_band)
        v.addWidget(self.split, 1)

        bot = QHBoxLayout()
        self.btn_open = QPushButton(tr("명함 보기"))                     # D19: 종전 '사진 모드에서 열기' — 동작 그대로
        self.btn_open.setToolTip(tr("이 명함을 사진 모드에서 엽니다"))
        self.btn_open.clicked.connect(lambda _c=False: self.open_in_photo())
        self.btn_vcard = QPushButton(tr("주소록"))       # 메뉴 단추 — 글자에 ▾ 없이 Qt 화살표 하나(디자인 SOT §2.7)                    # §5.24 D22·D23 — 구글 주소록·리멤버 명함첩(vCard)
        self.btn_vcard.setToolTip(tr("주소록 vCard(.vcf) 가져오기·내보내기 — 구글 주소록·리멤버"))
        bm = QMenu(self.btn_vcard)
        _menu_act(bm, tr("리멤버 vCard 가져오기"), lambda: self.import_contacts(source="remember"))
        _menu_act(bm, tr("구글 주소록 vCard 가져오기"), lambda: self.import_contacts(source="google"))
        bm.addSeparator()
        _menu_act(bm, tr("구글 주소록용 vCard 로 내보내기"), lambda: self.export_vcard(style="google"))
        _menu_act(bm, tr("리멤버용 vCard 로 내보내기"), lambda: self.export_vcard(style="remember"))
        bm.addSeparator()
        _menu_act(bm, tr("구글 주소록과 싱크"), lambda: self.open_gsync())     # 261120-36(§5.29) — 구글 계정 연결은 명함 환경설정
        self.btn_vcard.setMenu(bm)
        from viewer.widgets.icons import drop_button
        drop_button(self.btn_vcard)
        self.btn_manage = QPushButton(tr("명함 관리"))      # 메뉴 '명함 관리' 와 같은 길(§5.24.1 '단추', 사용자 지시 261119)
        self.btn_manage.setToolTip(tr("명함 폴더의 확인 표 창(명함 관리)을 엽니다"))
        self.btn_manage.clicked.connect(lambda _c=False: self.open_manage())
        self.btn_manage.setVisible(callable(getattr(self._mw, "_action_bizcard_import", None)))
        self.btn_dupe = QPushButton(tr("중복 검토"))        # §5.24.8 D30 — 번호·메일 등으로 같은 사람 묶어 합치기
        self.btn_dupe.setToolTip(tr("같은 사람으로 보이는 명함(같은 번호·메일, 번호 오타, 같은 이름·회사)을 묶어 우선순위대로 합칩니다"))
        self.btn_dupe.clicked.connect(lambda _c=False: self.open_dupes())
        self.btn_new_card = QPushButton(tr("새 명함 입력"))  # 맨 앞(§5.24.1 '새 명함 입력', 261120-15)
        self.btn_new_card.setToolTip(tr("새 명함이나 새 인물 정보를 손으로 넣습니다 — 명함 그림·인물 사진도 함께"))
        self.btn_new_card.clicked.connect(lambda _c=False: self.new_card())
        for b in (self.btn_new_card, self.btn_manage, self.btn_dupe, self.btn_vcard, self.btn_open):   # [새 명함 입력] → [명함 관리] → [주소록] → [명함 보기](§5.24.1 '단추')
            bot.addWidget(b)
        bot.addStretch(1)                              # [닫기] 단추 없음 — 제목 줄 X·Alt+F4·Esc·≡ 메뉴 '종료'(261120-38)
        v.addLayout(bot)
        for b in self.findChildren(QPushButton):      # Enter 가 [해시태그] 등을 누르지 않게 — 기본 단추 없음(사용자 보고 261119)
            b.setAutoDefault(False)
            b.setDefault(False)
        self._enable_card_buttons(False)
        self._init_store_bits()
        QTimer.singleShot(0, self.refresh)

    def new_card(self, exec_: bool = True):
        """[새 명함 입력](§5.24.1 '새 명함 입력') — 저장되면 목록을 다시 채워 새 명함을 고르고, 같은 사람일 수 있으면 [중복 검토]를 묻는다."""
        if self._dirty and not self._ask_save():
            return None
        from viewer.widgets.bizcard_new_dialog import NewCardDialog
        dlg = NewCardDialog(self, db=self._db, folder=self._bizcard_folder())
        self.new_dlg = dlg                                   # 검사가 찾는다
        if not exec_:
            dlg.finished.connect(lambda _r: self.after_new_card(dlg))
            dlg.show()
            return dlg
        dlg.exec()
        self.after_new_card(dlg)
        return dlg

    def after_new_card(self, dlg):
        if getattr(dlg, "read_files", None):           # 261120-31: [사진에서 읽기] — 명함 관리(명함 폴더)에서 읽어 확인
            fn = getattr(self._mw, "_action_bizcard_import", None)
            if callable(fn):
                fn(self._bizcard_folder())
                imp = getattr(self._mw, "_bizcard_dlg", None)
                if imp is not None and hasattr(imp, "read_sent"):
                    imp.read_sent(dlg.read_files)
            return
        if not getattr(dlg, "new_id", 0):
            return
        c = P.card_by_id(self._store(), dlg.new_id)
        if c and not V.is_contact(c):                    # 그림 명함 — 정리본 파일 태그도(§5.5, 명함 관리 [적용]과 같게)
            self._retag([x for x in (c["front"], c.get("back") or "") if x and os.path.exists(x)], set(), c.get("tags") or [])
        self._table_tab = None
        self.ed_find.clear()
        self.refresh()
        r = self.row_of_id(dlg.new_id)
        if r >= 0:
            self.table.setCurrentCell(r, 0)
        if dlg.dupes and QMessageBox.question(
                self, tr("새 명함 입력"),
                tr("같은 휴대폰·메일의 명함이 {n}장 있습니다 — 같은 사람일 수 있습니다. [중복 검토]를 열까요?").format(n=len(dlg.dupes))) \
                == QMessageBox.StandardButton.Yes:
            self.open_dupes()

    def open_manage(self):
        """[명함 관리] — 메뉴 '명함 관리' 와 같은 함수(MainWindow._action_bizcard_import, 대상 폴더 규칙도 같음 §5.12)."""
        fn = getattr(self._mw, "_action_bizcard_import", None)
        if callable(fn):
            fn()

    def _fill_main_menu(self):
        """≡ 메뉴를 열 때마다 — 아래 단추 줄과 같은 항목·차례, 단추의 보임·켜짐을 그대로, 누르면 그 단추와 같은 길. 끝에 '종료'."""
        m = self.main_menu
        m.clear()
        for b in (self.btn_new_card, self.btn_manage, self.btn_dupe, self.btn_vcard, self.btn_open):
            if not b.isVisible() and not b.isVisibleTo(self):
                continue
            if b.menu() is not None:                   # [주소록] — 그 단추의 메뉴 항목 그대로
                sub = m.addMenu(b.text())
                for a in b.menu().actions():
                    sub.addAction(a) if not a.isSeparator() else sub.addSeparator()
                sub.setEnabled(b.isEnabled())
                continue
            act = m.addAction(b.text())
            act.setEnabled(b.isEnabled())
            act.triggered.connect(lambda _c=False, btn=b: btn.click())
        m.addSeparator()
        quit_act = m.addAction(tr("종료"))
        quit_act.triggered.connect(lambda _c=False: self.close())   # 따로 실행이면 프로그램이 끝나고, 본 뷰어 안이면 창만 닫힘

    def open_gsync(self, exec_: bool = True):
        """[구글 주소록과 싱크](명함 SOT §5.29, 261120-36) — 미리보기 창. 반영 뒤 목록을 다시 채우고, 구글에서 지워져
        '명함도 지움' 을 고른 명함은 목록 지우기와 같은 휴지통 길(§5.20)로."""
        from viewer.bizcard import gsync as G
        from viewer.bizcard import gsync_auth as A
        from viewer.widgets.bizcard_gsync_dialog import GSyncDialog
        if self._dirty and not self._ask_save():
            return None
        st = self._store()
        if not A.connected() or not A.client(st)[0]:
            QMessageBox.information(self, tr("구글 주소록과 싱크"),
                                    tr("먼저 명함 환경설정(톱니)의 '구글 주소록' 에서 구글 계정을 연결하세요."))
            return None
        drive = bool(st.meta_get(G.OPT_DRIVE, False)) and A.granted_drive()
        dlg = GSyncDialog(self, db=self._db, folder=self._bizcard_folder(), photos=bool(st.meta_get(G.OPT_PHOTOS, False)),
                          drive=drive, drive_folder=str(st.meta_get(G.OPT_FOLDER, "") or G.DRIVE_FOLDER_DEFAULT))
        self.gsync_dlg = dlg                                 # 검사가 찾는다
        if not exec_:
            dlg.finished.connect(lambda _r: self._after_gsync(dlg))
            dlg.show()
            return dlg
        dlg.exec()
        self._after_gsync(dlg)
        return dlg

    def _after_gsync(self, dlg):
        res = getattr(dlg, "result", None)
        if not res:
            return
        gone = [c for c in (P.card_by_id(self._store(), i) for i in res.get("delete_cards") or []) if c]
        if gone:
            self.delete_cards(gone, ask=False)
        self.refresh()

    def open_settings(self, exec_: bool = True):
        """톱니 — 명함 환경설정(§5.24.9). 닫으면 '최근' 탭·번호 꼴을 다시."""
        from viewer.widgets.bizcard_settings_dialog import BizcardSettingsDialog
        dlg = BizcardSettingsDialog(self, host=self._mw, store=self._store())
        self.settings_dlg = dlg                              # 검사가 찾는다
        if not exec_:
            dlg.show()
            return dlg
        if dlg.exec():
            self._bz_folder = None                           # 명함 폴더를 바꿨을 수 있다(인물 사진 자리)
            if self._fav_gid() == RECENT:
                self._fav_fill()
        return dlg

    def recent_clear(self, ask: bool = True) -> int:
        """'최근' 탭 메뉴 '모두 삭제'(§5.24.2, 261120-19) — 확인 창 뒤 기록을 모두 지운다(명함은 그대로)."""
        if ask and QMessageBox.question(
                self, tr("모두 삭제"), tr("'최근' 기록을 모두 지웁니다 — 되돌릴 수 없습니다(명함은 그대로)."),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return 0
        n = P.recent_clear(self._store())
        if self._fav_gid() == RECENT:
            self._fav_fill()
            self._sync_table(RECENT)
        return n

    def open_dupes(self, exec_: bool = True):
        """[중복 검토](§5.24.8) — 고치던 칸은 먼저 저장을 묻고, 창을 닫으면 목록·즐겨찾기를 다시."""
        if self._dirty and not self._ask_save():
            return None
        if self.photo_busy:
            QMessageBox.information(self, tr("명함찾기"), tr("인물 사진을 넣는 중입니다 — 끝난 뒤에 다시 하세요."))
            return None
        from viewer.widgets.bizcard_dupe_dialog import BizcardDupeDialog
        dlg = BizcardDupeDialog(self)
        self.dupe_dlg = dlg                                  # 검사가 찾는다
        if not exec_:
            dlg.show()
            return dlg
        dlg.exec()
        self.after_dupes()
        return dlg

    def after_dupes(self):
        self._card = None
        self._dirty = False
        self.refresh()
        self._fav_fill()

    # ── 저장소 ──
    def _store(self):
        if self._st is None:
            from viewer.bizcard.store import BizcardStore
            self._st = BizcardStore(self._db, ui=True)
            P.fav_init(self._st, tr("즐겨찾기"))
        return self._st

    def _init_store_bits(self):
        st = self._store()
        try:
            P.fix_lang_tags(st, self._tagstore())         # 종전 '#한글·#영어 둘 다' → 하나(D25, 한 번만)
        except Exception:
            pass
        P.recent_prune(st)                                # '최근' 항목 제한(§5.24.2, 261120-18)
        on = set(st.meta_get("copy_fields", list(P.COPY_DEFAULT)) or [])
        for k, cb in self.chk.items():
            cb.blockSignals(True)
            cb.setChecked(k in on)
            cb.blockSignals(False)
        self._fav_fill_tabs(st.meta_get("fav_tab", None))
        i = self.cb_kind.findData(st.meta_get("find_kind", "all"))   # 구분 기억(§5.24.1 '구분', 사용자 지시 261120)
        self.cb_kind.blockSignals(True)
        self.cb_kind.setCurrentIndex(max(0, i))
        self.cb_kind.blockSignals(False)

    def _save_copy_fields(self):
        self._store().meta_set("copy_fields", [k for k in P.COPY_FIELDS if self.chk[k].isChecked()])

    def _on_kind(self):
        """구분을 바꿈 — 기억하고(명함 DB meta) 찾기 결과로."""
        self._store().meta_set("find_kind", self.cb_kind.currentData() or "all")
        self._on_period()

    # ── 찾기 ──
    def _search_mode(self):
        """찾기 칸·기간을 바꾸면 목록 표는 찾기 결과로(탭 명단 보기를 끝냄)."""
        self._table_tab = None
        self._ghost_all = False                        # 칸 글이 바뀜 — 흐린 글 전체 보기 끝
        self._find_timer.start()

    def _on_period(self, _i=0):
        custom = self.cb_period.currentData() == "custom"
        for w in (self.ed_from, self.lbl_tilde, self.ed_to):
            w.setVisible(custom)
        self._table_tab = None
        self.refresh()

    def _range(self):
        key = self.cb_period.currentData()
        if key == "custom":
            return self.ed_from.text().strip(), self.ed_to.text().strip()
        return P.since_for(key), ""

    def refresh(self):
        if self._dirty and not self._ask_save():
            return
        if self._table_tab is not None:                # 탭 명단 보기(§5.24.2 '탭 줄')
            rows = self._tab_members(self._table_tab)
        else:
            since, until = self._range()
            q = "" if self._ghost_all else self.ed_find.text()   # 흐린 글을 다시 고름 = 전체(§5.24.1 '찾기 칸 흐린 글')
            rows = P.find(self._store(), q, since, until)   # 상한 없이 전부(§5.9 '결과')
            kind = self.cb_kind.currentData()
            if kind and kind != "all":
                ph = P.photo_ids(rows, self._bizcard_folder()) if kind in ("photo", "nophoto") else None   # 사진 있음·없음(261120-24)
                rows = [c for c in rows if P.kind_ok(c, kind, ph)]
        self._rows = rows
        self._by_id = {c["id"]: c for c in self._rows}
        keep = self._card["id"] if self._card else None
        self._loading = True
        try:
            self.table.set_cards(self._rows)                # 지금 머리말 기준으로 정렬해 넣는다(가상 표 — 보이는 줄만 그림)
        finally:
            self._loading = False
        if self._table_tab is not None:
            self.lbl_count.setText(tr("'{tab}' {n}명").format(tab=self._tab_name(self._table_tab), n=len(self._rows)))
        else:
            self.lbl_count.setText(tr("{n}장").format(n=len(self._rows)))
        pick = self.row_of_id(keep) if keep in self._by_id else (0 if self._rows else -1)
        if pick >= 0:
            self._loading = True
            self.table.setCurrentCell(pick, 0)
            self._loading = False
            self._load(self._card_at(pick))
        else:
            self._load(None)

    def row_of_id(self, cid) -> int:
        return self.table.model().row_of_id(cid)

    def _card_at(self, r):
        return self.table.model().card(r)

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
        """즐겨찾기 사람을 고름(누름·키보드) — 늘 목록 표에서 그 줄을 골라 보인다(§5.24.2 '즐겨찾기 줄').
        목록에 없으면(다른 찾기 결과·다른 탭 명단) 목록을 지금 탭 명단으로 바꾼 뒤 고른다. 이미 보던 명함이어도 줄을 다시 고른다."""
        r = self.row_of_id(cid)
        if r < 0:
            gid = self._fav_gid()
            if gid is not None and self._table_tab != gid:
                if self._dirty and not self._ask_save():
                    return
                self._table_tab = gid                      # 목록을 지금 탭 명단으로
                self.refresh()
                r = self.row_of_id(cid)
        if r >= 0:
            self._loading = True
            self.table.clearSelection()
            self.table.setCurrentCell(r, 0)
            self.table.selectRow(r)
            self._loading = False
            self.table.scrollToItem(self.table.item(r, 0))
            if self._card is None or self._card["id"] != cid:
                if self._dirty and not self._ask_save():
                    return
                self._load(self._card_at(r))
            return
        if self._card is not None and self._card["id"] == cid:
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
        self._fav_key_timer.stop()                         # 다른 길로 명함을 보이면 키보드 대기는 버린다
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
                vals.update(cell=PH.normalize(first("cell")), work=PH.normalize(first("work")), fax=PH.normalize(first("fax")),
                            email=(card.get("emails") or [""])[0], url=(card.get("urls") or [""])[0])
            for k, ed in self.eds.items():
                ed.setText(vals[k])
                ed.setEnabled(card is not None)
            self._fill_extra_rows(card)                    # 추가 메일·전화·누리집 줄(261120-35)
            self.ed_memo.setPlainText((card or {}).get("memo") or "")
            self.ed_memo.setEnabled(card is not None)
            if card and V.is_contact(card):
                self.lbl_file.setText(tr("(주소록에서 가져온 명함 — 그림 없음)"))
            else:
                self.lbl_file.setText(os.path.basename(card["front"]) if card else "")
            has_back = bool(card and card.get("back") and os.path.exists(card["back"]))
            self.dots.set_state(2 if has_back else 1, 0)
        finally:
            self._loading = False
        self._set_dirty(False)
        self._enable_card_buttons(card is not None)
        self._show_card()
        self._fill_photos()
        self._recent_id = card["id"] if card else None     # RECENT_MS 넘게 보이면 '최근' 에(D27)
        if card:
            self._recent_timer.start()
        else:
            self._recent_timer.stop()

    def _flip(self, on: bool):
        if self._loading:
            return
        self._side = "back" if on else "front"
        self.dots.set_state(self.dots.count, 1 if on else 0)
        self._show_card()

    def _show_card(self):
        self._show_photo()                                # 크기가 바뀌면 인물 사진 큰 화면도
        c = self._card
        path = (c.get("back") if self._side == "back" else c.get("front")) if c else ""
        self.shown = path or ""
        if not path or not os.path.exists(path):
            self.pv.clear()
            if c:
                self.pv.setText(tr("(그림 파일이 없습니다)"))
            return
        self.pv.setPixmap(_scaled(path, max(200, self.pv.width()), max(120, self.pv.height())))

    def _show_photo(self):
        """썸네일 줄에서 고른 인물 사진(없으면 첫 사진)을 위 큰 화면에."""
        it = self.photos.currentItem() or (self.photos.item(0) if self.photos.count() else None)
        path = it.data(ROLE) if it is not None else ""
        self.photo_shown = path or ""
        if not path or not os.path.exists(path):
            self.photo_view.clear()
            if self._photo_front():
                self.photo_view.setText(tr("(인물 사진 없음 — 끌어 놓거나 [사진 추가])"))
            return
        self.photo_view.setPixmap(_scaled(path, max(120, self.photo_view.width()), max(90, self.photo_view.height())))

    def _bizcard_folder(self) -> str:
        """명함 폴더(환경설정 picture.bizcard_folder) — 그림 없는 주소록 명함의 인물 사진 자리(§5.24.3). 창마다 한 번 읽는다."""
        if getattr(self, "_bz_folder", None) is None:
            from viewer.bizcard.standalone import bizcard_folder
            self._bz_folder = bizcard_folder()
        return self._bz_folder

    def _photo_front(self, c=None) -> str:
        """인물 사진 기준 경로(`people.photo_front`) — 그림 없는 주소록 명함도 명함 폴더가 있으면 자리가 있다."""
        c = self._card if c is None else c
        return P.photo_front(c, self._bizcard_folder()) if c else ""

    def _fill_photos(self, select: str = ""):
        self.photos.blockSignals(True)
        try:
            self.photos.clear()
            c = self._card
            pf = self._photo_front()
            if pf:
                cur = None
                for p in P.person_photos(pf):
                    it = QListWidgetItem(QIcon(_scaled(p, PHOTO_ICON, PHOTO_ICON)), "")
                    it.setData(ROLE, p)
                    it.setToolTip(os.path.basename(p))
                    self.photos.addItem(it)
                    if select and os.path.normcase(p) == os.path.normcase(select):
                        cur = it
                if cur is None and self.photos.count():
                    cur = self.photos.item(0)         # 명함을 고르면 첫 사진
                if cur is not None:
                    self.photos.setCurrentItem(cur)
        finally:
            self.photos.blockSignals(False)
        self._show_photo()
        if hasattr(self, "btn_photo_del"):
            self.btn_photo_del.setEnabled(bool(self._photo_front()) and self.photos.count() > 0)

    def photo_paths(self) -> list:
        return [self.photos.item(i).data(ROLE) for i in range(self.photos.count())]

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self._show_card)
        QTimer.singleShot(0, self._fav_fit)
        QTimer.singleShot(0, self._sync_todo_width)

    # ── 할 일 칸 (§5.24.10, 261120-34) ──
    def _sync_todo_width(self):
        """할 일 칸 폭 = 사진창 폭 — 그래서 위 띠의 칸 경계가 아래 띠(세부내용 | 사진창)와 맞는다."""
        if getattr(self, "todo_panel", None) is not None and self.photo_split.width() > 0:
            self.todo_panel.setFixedWidth(self.photo_split.width())

    def _todo_show(self, gid):
        """할 일 탭이면 칸에 그 기록, 아니면 칸을 숨기고 사람 칸이 위 띠 끝까지(사용자 지시)."""
        on = self.todo_panel.set_group(gid) if gid not in (None, RECENT) else self.todo_panel.set_group(None)
        self.todo_panel.setVisible(bool(on))
        self._sync_todo_width()
        QTimer.singleShot(0, self._fav_fit)

    def _style_detail(self):
        """세부내용 카드 꾸밈 — 색은 DETAIL_BG(테마별): 제목 띠·테두리 head, 본문 body, 메모 memo.
        본문 칸은 테두리·바탕 없이, 가리킴 = 옅은 입력 바탕, 초점 = 입력 바탕 + 강조 밑줄."""
        pal = QApplication.palette()
        c = DETAIL_BG["dark" if pal.color(pal.ColorRole.Window).lightness() < 128 else "light"]
        b = pal.color(pal.ColorRole.Base)
        ed = "QWidget#bizDetailBox QLineEdit"
        css = ("QWidget#bizDetailBox{background:%(body)s;border:1px solid %(border)s;border-radius:8px;}"
               "QLabel#bizDetailHead{background:%(head)s;color:%(head_fg)s;padding:6px;border-bottom:1px solid %(border)s;"
               "border-top-left-radius:7px;border-top-right-radius:7px;}"
               "QWidget#bizDetailBody{background:%(body)s;border-bottom-left-radius:7px;border-bottom-right-radius:7px;}"
               "%(ed)s{border:none;background:transparent;padding:2px 4px;}"
               "%(ed)s:hover{background:rgba(%(r)d,%(g)d,%(b)d,0.55);}"
               "QWidget#bizDetailBox QPlainTextEdit{border:none;background:%(memo)s;border-radius:6px;padding:2px;}"
               "%(ed)s:focus, QWidget#bizDetailBox QPlainTextEdit:focus"
               "{background:palette(base);border-bottom:1px solid palette(highlight);}") % dict(
            c, ed=ed, r=b.red(), g=b.green(), b=b.blue())
        if css != self._detail_css:                    # 같은 값이면 다시 넣지 않는다(스타일 바뀜이 되돌아오지 않게)
            self._detail_css = css
            self.detail_box.setStyleSheet(css)
            # 목록 표 = 세부내용 카드와 한 벌(§5.24.1 '목록 표 꾸밈', 261120-7·-8, 사용자 지시 261120 '전반적으로 어울리게'):
            #   머리말 = 띠 색, 테두리 = 카드 테, 줄은 메모 바탕·본문 바탕 번갈아, 세로 선 없음, 고른 줄 = 고른 줄 색(회색 톤 — 사용자 결정 261120)
            self.table.setStyleSheet(
                "QTableView{background:%(memo)s;alternate-background-color:%(body)s;border:1px solid %(border)s;"
                "gridline-color:%(border)s;selection-background-color:%(sel)s;selection-color:%(sel_fg)s;outline:0;}"
                "QTableView::item{padding:2px 4px;border:none;}"
                "QTableView::item:selected{background:%(sel)s;color:%(sel_fg)s;}"   # 창이 뒤로 가도 같은 고른 줄
                "QTableView QHeaderView::section{background:%(head)s;color:%(head_fg)s;border:none;"
                "border-right:1px solid %(border)s;border-bottom:1px solid %(border)s;padding:4px 6px;}"
                # 정렬 화살표는 글 오른쪽(windows11 스타일은 글 위에 그려 머리말이 높아진다)
                "QTableView QHeaderView::up-arrow, QTableView QHeaderView::down-arrow"
                "{subcontrol-origin:padding;subcontrol-position:center right;width:9px;height:9px;}" % c)
            self.fav.setStyleSheet("QListWidget{border:1px solid %(border)s;}" % c)   # 즐겨찾기 칸 테두리도 같은 테
            if getattr(self, "photo_split", None) is not None and self.photo_split.count() > 1:
                self.photo_split.handle(1).update()     # 사진창 구분선(손잡이가 그림 — 테마가 바뀌면 다시, §5.24.3)
            if getattr(self, "btn_settings", None) is not None:
                from viewer.widgets.icons import themed_icon
                self.btn_settings.setIcon(themed_icon("gear", size=18))   # 테마 글자색 톱니(§5.24.9)
                self.btn_menu.setIcon(themed_icon("menu", size=18))        # ≡ 메뉴(261120-37)
        self._match_head()

    def _match_head(self):
        """목록 표 머리말 높이 = 세부내용 제목 띠 높이(§5.24.1 '목록 표 꾸밈', 사용자 지시 261120) — 위 끝·아래 끝이 나란히."""
        self.detail_head.ensurePolished()
        self.table.horizontalHeader().setFixedHeight(self.detail_head.sizeHint().height())

    def changeEvent(self, e):
        from PyQt6.QtCore import QEvent
        if e.type() in (QEvent.Type.PaletteChange, QEvent.Type.ApplicationPaletteChange, QEvent.Type.StyleChange) \
                and getattr(self, "detail_box", None) is not None:
            self._style_detail()                       # 테마를 바꾸면 묶음 바탕도(디자인 SOT §2.5 '명함 세부 카드')
        super().changeEvent(e)

    def showEvent(self, e):
        super().showEvent(e)
        if not getattr(self, "_sized", False):
            self._sized = True
            self._init_sizes()
            QTimer.singleShot(PRELOAD_MS, self._preload_tags)   # 쉬는 동안 [해시태그] 준비(261120-20)
            QTimer.singleShot(0, lambda: self._todo_show(self._fav_gid()))   # 처음 탭이 할 일이면 칸(§5.24.10)

    def table_min_width(self) -> int:
        """이름·회사·직함·전화가 다 보이는 표 폭(§5.24.1 '처음 너비' — 메일·스캔일은 끌어 넓히면)."""
        t = self.table
        return (sum(t.columnWidth(c) for c in range(C_PHONE + 1))
                + t.verticalScrollBar().sizeHint().width() + 2 * t.frameWidth() + 4)

    def _init_sizes(self):
        """처음 너비(§5.24.1) — 목록은 전화까지 보이는 최소 폭, 세부는 DETAIL_W, 나머지는 사진창.
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
        img = on and not V.is_contact(self._card)            # 주소록에서 가져온 명함 — 명함 그림 없음
        ph = on and bool(self._photo_front())                 # 인물 사진은 그림 없는 명함도(명함 폴더가 있으면, §5.24.3)
        for b in (self.btn_tags, self.btn_copy):
            b.setEnabled(on)
        self.btn_open.setEnabled(img)
        self.btn_photo.setEnabled(ph and not self.photo_busy)
        self.photos.setEnabled(ph)
        self.btn_photo_del.setEnabled(ph and self.photos.count() > 0)

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
        return edited_fields(self._card, {k: ed.text() for k, ed in self.eds.items()}, self.ed_memo.toPlainText(),
                             extras=self._extra_values())

    # ── 추가 칸(§5.24.1 '추가 칸', 261120-35) — 두 번째 메일부터·같은 종류 둘째 전화부터·둘째 누리집부터 ──
    def _fill_extra_rows(self, card):
        while self.form_extra.rowCount():
            self.form_extra.removeRow(0)
        self.extra_eds = []
        if not card:
            return
        labels = dict(FIELDS)

        def add(group, kind, label_key, n, value):
            ed = QLineEdit(str(value or ""))
            ed.textEdited.connect(lambda _t: self._set_dirty(True))
            if group == "phone":
                PH.attach(ed)
            lab = QLabel("%s %d" % (tr(labels[label_key]), n))
            lab.setContentsMargins(22, 0, 0, 0)        # 체크 칸 자리만큼 들여 위 칸 이름과 줄을 맞춘다
            self.form_extra.addRow(lab, ed)
            self.extra_eds.append((group, kind, ed))
        for i, e in enumerate((card.get("emails") or [])[1:]):
            add("email", "", "email", i + 2, e[-1] if isinstance(e, (list, tuple)) else e)
        for kind in PHONE_KEYS:
            nums = [n for k, n in (tuple(x) for x in card.get("phones") or []) if k == kind]
            for i, n in enumerate(nums[1:]):
                add("phone", kind, kind, i + 2, PH.normalize(n))
        for i, u in enumerate((card.get("urls") or [])[1:]):
            add("url", "", "url", i + 2, u)
        self.fields_scroll.updateGeometry()            # 줄이 늘면 칸 영역도 내용 높이까지(남는 높이는 메모)

    def _extra_values(self) -> dict:
        out = {"emails": [], "phones": [], "urls": []}
        for group, kind, ed in self.extra_eds:
            t = ed.text().strip()
            if not t:
                continue                               # 비운 줄 = 그 값을 지움
            if group == "email":
                out["emails"].append(t)
            elif group == "url":
                out["urls"].append(t)
            else:
                out["phones"].append((kind, PH.normalize(t)))
        return out

    def store_card_edit(self, c, new):
        """고친 값 new(`edited_fields`)를 명함 c 에 — 이름·회사가 바뀌면 정리본·뒷면·인물 사진 이름, 앱이 붙인 해시태그만 바꿈,
        손으로 고친 칸은 주소록 출처를 지움. [저장]·중복 검토 '명함 고치기'(§5.24.8)가 같은 길. 반환 = 바뀐 칸들(실패면 None)."""
        from viewer.bizcard.apply import tags_for, LANG_TAGS
        st = self._store()
        old_tags = list(c.get("tags") or [])
        langs = [t for t in old_tags if t in LANG_TAGS]
        old_auto = set(tags_for({"name": c.get("name") or "", "company": c.get("company") or "", "langs": langs,
                                 "langs_ordered": False})) | set(langs)     # 앱이 붙인 것만 바꾼다(언어는 다시 하나로 — D25)
        new_tags = list(dict.fromkeys(tags_for({"name": new["name"], "company": new["company"], "langs": langs,
                                                "langs_ordered": False})
                                      + [t for t in old_tags if t not in old_auto]))     # 사람이 붙인 해시태그는 그대로
        got = self.rename_card_files(c, new["name"], new["company"])
        if got is None:
            return None
        nf, nb = got
        fields = dict(new, front=nf, back=nb, tags=new_tags)
        # 수정일·메모 기록(§5.24.1 '수정일'·§5.9 '메모 기록', 261120-25·-26) — 메모 밖 칸이 바뀌었을 때만
        keys = P.changed_keys(c, new)
        if keys:
            P.edited_init(st)
            fields["edited"] = _today()
            if P.memo_opt(st, P.MEMO_LOG_KEY):
                labels = dict({k: tr(lb) for k, lb in FIELDS})
                fields["memo"] = P.memo_with_log(fields.get("memo") or "", _today(), [labels.get(k, k) for k in keys],
                                                 tr("수정"))
        P.update_card(st, c["id"], fields)
        P.forget_srcs(st, c["id"], [k for k in ("name", "company", "dept", "title", "address", "memo")
                                    if (new.get(k) or "") != (c.get(k) or "")])   # 손으로 고친 칸 — 주소록이 덮어쓰지 않게(D24)
        self._retag([x for x in (nf, nb) if x and os.path.exists(x)], old_auto, new_tags)
        return fields

    def _memo_date_before_typing(self):
        """메모를 쓰기 시작할 때 맨 위에 '오늘 ' 을 넣고 그 뒤에 쓰게 한다(§5.9 '메모 날짜', 261120-27 — 명함 환경설정에서 끔).
        메모가 비었거나 커서가 맨 앞일 때만(가운데를 고치는 것은 그대로), 맨 윗줄이 이미 오늘 날짜면 넣지 않고,
        한 명함을 보는 동안 한 번만(지운 날짜를 다시 넣지 않는다)."""
        c = self._card
        view = (c.get("id"), getattr(self, "_memo_view", 0)) if c else None
        if not c or self._loading or getattr(self, "_memo_dated_view", None) == view:
            return
        self._memo_dated_view = view
        try:
            if not P.memo_opt(self._store(), P.MEMO_DATE_KEY):
                return
        except Exception:
            return
        ed = self.ed_memo
        text = ed.toPlainText()
        cur = ed.textCursor()
        if text.strip() and cur.position() != 0:
            return
        today = _today()
        if text.split("\n", 1)[0].startswith(today):
            return
        cur.movePosition(cur.MoveOperation.Start)
        cur.insertText(today + " " + ("\n" if text.strip() else ""))
        cur.setPosition(len(today) + 1)
        ed.setTextCursor(cur)

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
        front = c["front"]
        fields = self.store_card_edit(c, new)
        if fields is None:
            return False
        nf = fields["front"]
        if fields.get("memo") != new.get("memo"):         # 메모에 고친 기록이 들어갔으면 칸에도 보인다(다음 저장이 지우지 않게)
            self._loading = True
            try:
                self.ed_memo.setPlainText(fields["memo"])
            finally:
                self._loading = False
        self._dirty = False
        self.btn_save.setEnabled(False)
        self._card = dict(c, **fields)
        self.saved = {"renamed": nf != front}
        self.refresh()
        self._fav_fill()
        return True

    def rename_card_files(self, c, name: str, company: str, log=None):
        """이름·회사가 바뀌면 정리본·뒷면·인물 사진 이름을 `성명_회사명` 으로(한 길) — 반환 (새 앞면, 새 뒷면), 실패면 None.
        [저장]·중복 검토(§5.24.8) 가 같이 쓴다. log = [(원래, 새)] 를 모을 목록(되돌리기용)."""
        from viewer.bizcard.apply import unique_path, BACK_SUFFIX
        front, back = c["front"], c.get("back") or ""
        nf, nb = front, back
        if V.is_contact(c):                            # 그림 없는 주소록 명함 — 인물 사진 이름만 새 `성명_회사명` 으로(§5.24.3)
            old_pf = self._photo_front(c)
            new_pf = P.contact_photo_front(name, company, self._bizcard_folder())
            if old_pf and new_pf and os.path.normcase(old_pf) != os.path.normcase(new_pf):
                for i, ph in enumerate(P.person_photos(old_pf)):
                    dst = Path(ph).with_name(P.photo_name(new_pf, i, os.path.splitext(ph)[1]))
                    if not dst.exists() and self._rename(ph, str(dst)):
                        log is not None and log.append((ph, str(dst)))
            return nf, nb
        want = R.card_filename(name, company, os.path.splitext(front)[1] or ".jpg")
        if (name, company) != (c.get("name") or "", c.get("company") or "") and os.path.exists(front) \
                and os.path.normcase(Path(front).stem.split(" (")[0]) != os.path.normcase(Path(want).stem):
            front = P._real(front)
            folder = Path(front).parent
            same = folder / want
            p = same if os.path.normcase(str(same)) == os.path.normcase(front) else unique_path(folder, want, set())
            photos = P.person_photos(front)
            if not self._rename(front, str(p)):
                return None
            log is not None and log.append((front, str(p)))
            nf = str(p)
            if back and os.path.exists(back):
                back = P._real(back)
                pb = unique_path(folder, p.stem + BACK_SUFFIX + os.path.splitext(back)[1], set())
                if self._rename(back, str(pb)):
                    nb = str(pb)
                    log is not None and log.append((back, str(pb)))
            for i, ph in enumerate(photos):          # 인물 사진도 새 이름으로(차례 지킴)
                dst = Path(ph).with_name(P.photo_name(p, i, os.path.splitext(ph)[1]))
                if os.path.normcase(str(dst)) != os.path.normcase(ph) and not dst.exists():
                    if self._rename(ph, str(dst)):
                        log is not None and log.append((ph, str(dst)))
        return nf, nb

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
    def copy_text(self, cards=None) -> str:
        if cards is None:
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
            clipboard_util.set_text(t)                # 클립보드는 한 길(스크린샷 SOT §8.4 — 261117-26 덧고침)
        return t

    # ── 즐겨찾기 탭 (§5.24.2) — 맨 앞 '최근'(RECENT), 즐겨찾기·할 일 탭 ──
    def _fav_gid(self):
        i = self.fav_tabs.currentIndex()
        return self.fav_tabs.tabData(i) if i >= 0 else None

    def _tab_name(self, gid) -> str:
        for i in range(self.fav_tabs.count()):
            if self.fav_tabs.tabData(i) == gid:
                return self.fav_tabs.tabText(i)
        r = self._store().con.execute("SELECT name FROM fav_groups WHERE id=?", (gid,)).fetchone() if gid != RECENT else None
        return r["name"] if r else tr("최근")

    def _fav_fill_tabs(self, select=None):
        self.fav_tabs.blockSignals(True)
        while self.fav_tabs.count():
            self.fav_tabs.removeTab(0)
        st = self._store()
        pal = self.palette()
        self.fav_tabs.addTab(_tab_icon("recent", pal), tr("최근"))
        self.fav_tabs.setTabData(0, RECENT)
        self.fav_tabs.setTabToolTip(0, tr("세부 칸에서 {s}초 넘게 본 명함 — 저절로 들어오고, 빼기만 합니다").format(s=RECENT_MS // 1000))
        pick = 0 if select == RECENT else None
        groups = P.fav_groups(st, _today())                       # 마감한 탭·기간 밖 할 일은 숨김(D26·D28)
        if self._peek is not None and all(g != self._peek for g, _n in groups):
            r = st.con.execute("SELECT name FROM fav_groups WHERE id=?", (self._peek,)).fetchone()
            if r is not None:
                groups = groups + [(self._peek, r["name"])]
            else:
                self._peek = None
        for gid, name in groups:
            info = P.todo_info(st, gid)
            i = self.fav_tabs.addTab(_tab_icon("todo", pal), name) if info else self.fav_tabs.addTab(name)
            self.fav_tabs.setTabData(i, gid)
            tip = self._todo_tip(info) if info else ""
            if gid == self._peek:
                tip = (tip + "\n" if tip else "") + tr("(마감한 탭 — 다른 탭을 고르면 다시 숨습니다)")
            self.fav_tabs.setTabToolTip(i, tip)
            if gid == select:
                pick = i
        if pick is None:
            pick = 1 if self.fav_tabs.count() > 1 else 0
        self.fav_tabs.setCurrentIndex(pick)
        self.fav_tabs.blockSignals(False)
        self._recent_bar(self._fav_gid() == RECENT)
        self._fav_fill()

    def _fav_tab_changed(self):
        gid = self._fav_gid()
        if self._peek is not None and gid != self._peek:  # 잠시 보던 마감한 탭은 다시 숨김
            self._peek = None
            QTimer.singleShot(0, lambda g=gid: self._fav_fill_tabs(g))
        if gid is not None:
            self._store().meta_set("fav_tab", gid)
        self._recent_bar(gid == RECENT)
        self._fav_fill()
        tp = getattr(self, "todo_panel", None)
        if tp is not None:
            if tp.dirty and tp.gid not in (None, gid):
                tp._ask_leave()                          # 고친 할 일 기록 — 저장·버리기(탭은 이미 바뀜, 취소는 버리기)
            self._todo_show(gid)                         # 할 일 칸(§5.24.10)

    def _tab_clicked(self, i):
        """탭을 누르면 목록 표에 그 탭 사람들을 모두(사용자 지시 261119) — 찾기 칸·기간을 바꾸면 찾기 결과로."""
        if i < 0:
            return
        self._table_tab = self.fav_tabs.tabData(i)
        QTimer.singleShot(0, self.refresh)

    def _tab_moved(self, _a, _b):
        if self.fav_tabs.tabData(0) != RECENT:            # '최근' 은 맨 앞 고정
            QTimer.singleShot(0, lambda: self._fav_fill_tabs(self._fav_gid()))
        self._fav_save_tab_order()

    def _fav_save_tab_order(self):
        P.fav_order_groups(self._store(), [g for g in (self.fav_tabs.tabData(i) for i in range(self.fav_tabs.count()))
                                           if g != RECENT])

    def _recent_bar(self, on: bool):
        self.cb_recent.setVisible(on)
        custom = on and self.cb_recent.currentData() == "custom"
        for w in (self.d_recent_from, self.d_recent_to):
            w.setVisible(custom)

    def _recent_range(self):
        key = self.cb_recent.currentData()
        if key == "custom":
            return self.d_recent_from.date().toString("yyyy-MM-dd"), self.d_recent_to.date().toString("yyyy-MM-dd")
        import datetime
        days = {"1w": 7, "1m": 31, "3m": 92}.get(key, 7)
        return (datetime.date.today() - datetime.timedelta(days=days)).isoformat(), ""

    def _recent_changed(self):
        self._recent_bar(self._fav_gid() == RECENT)
        if self._fav_gid() == RECENT:
            self._fav_fill()
        self._sync_table(RECENT)

    def _recent_hit(self):
        """세부 칸에 RECENT_MS 넘게 보인 명함 → '최근'(D27). 표는 다시 채우지 않는다(보던 줄이 움직이지 않게)."""
        c = self._card
        if c is None or c["id"] != self._recent_id:
            return
        P.recent_add(self._store(), c["id"])
        if self._fav_gid() == RECENT:
            self._fav_fill()

    def _tab_members(self, gid) -> list:
        if gid == RECENT:
            return P.recent_list(self._store(), *self._recent_range())
        return P.fav_members(self._store(), gid)

    def _sync_table(self, gid):
        """목록 표가 그 탭 명단을 보이고 있으면 다시 채운다."""
        if self._table_tab is not None and self._table_tab == gid:
            self.refresh()

    def _reload_card(self):
        """메모가 바뀌었을 수 있다(할 일 넣기·탭 삭제) — 지금 명함 다시 읽기."""
        if self._card is not None:
            c = P.card_by_id(self._store(), self._card["id"])
            if c is not None:
                self._load(c)

    def fav_new_tab(self, name=None, cards=None):
        if name is None:
            name, ok = QInputDialog.getText(self, tr("즐겨찾기"), tr("새 탭 이름(예: 가족·친구):"))
            if not ok:
                return None
        name = (name or "").strip()
        if not name:
            return None
        st = self._store()
        gid = P.fav_add_group(st, name)
        if cards:
            P.fav_add(st, gid, [c["id"] for c in cards], ongoing=tr("계속"))
        self._fav_fill_tabs(gid)
        return gid

    def fav_rename_tab(self, i, name=None):
        if i < 0 or self.fav_tabs.tabData(i) == RECENT:
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
        return i >= 0 and self.tab_delete(self.fav_tabs.tabData(i), ask=ask)

    def tab_delete(self, gid, ask: bool = True) -> bool:
        """탭 삭제(D29) — 탭과 그 사람 칸을 지우고, 할 일로 메모에 적은 글도 빼낸다. 명함은 그대로."""
        if gid is None or gid == RECENT:
            return False
        st = self._store()
        n = len(P.fav_members(st, gid))
        if ask and QMessageBox.question(self, tr("탭 삭제"), tr(
                "'{tab}' 탭을 삭제합니다 — 탭과 그 {n}명 칸이 완전히 지워지고, 할 일로 메모에 적은 글도 지웁니다. "
                "되돌릴 수 없습니다. 명함과 파일은 그대로입니다.").format(tab=self._tab_name(gid), n=n)) != QMessageBox.StandardButton.Yes:
            return False
        if not P.fav_delete_group(st, gid, tr("계속")):
            if ask:
                QMessageBox.information(self, tr("탭 삭제"), tr("할 일이 아닌 마지막 탭은 삭제할 수 없습니다."))
            return False
        if self._peek == gid:
            self._peek = None
        cur = self._fav_gid()
        if self._table_tab == gid:
            self._table_tab = None
            self.refresh()
        self._fav_fill_tabs(cur if cur != gid else None)
        self._reload_card()
        return True

    def tab_close(self, gid, ask: bool = True) -> bool:
        """탭 마감(D28) — 탭 줄에서 숨기고 지우지 않는다('마감한 탭 ▸' 에서 다시)."""
        if gid is None or gid == RECENT:
            return False
        if not P.fav_close(self._store(), gid, True):
            if ask:
                QMessageBox.information(self, tr("탭 마감"), tr("할 일이 아닌 마지막 탭은 마감할 수 없습니다."))
            return False
        if self._peek == gid:
            self._peek = None
        if self._table_tab == gid:
            self._table_tab = None
            self.refresh()
        cur = self._fav_gid()
        self._fav_fill_tabs(cur if cur != gid else None)
        return True

    def tab_reopen(self, gid) -> bool:
        P.fav_close(self._store(), gid, False)
        self._peek = None
        self._fav_fill_tabs(gid)
        return True

    def tab_peek(self, gid):
        """'마감한 탭 ▸ 보기' — 그 탭을 잠시 탭 줄 끝에(다른 탭을 고르면 다시 숨음)."""
        self._peek = gid
        self._fav_fill_tabs(gid)

    def _is_closed(self, gid) -> bool:
        r = self._store().con.execute("SELECT closed FROM fav_groups WHERE id=?", (gid,)).fetchone()
        return bool(r and r["closed"])

    def plus_menu(self, cards=None):
        """'+' — 새 즐겨찾기 탭·새 할 일(표에서 고른 명단, 끌어 놓았으면 끈 사람들)."""
        cards = self.selected_cards() if cards is None else cards
        m = QMenu(self)
        _menu_act(m, tr("새 즐겨찾기 탭 ({n}명)").format(n=len(cards)), lambda: self.fav_new_tab(cards=cards))
        _menu_act(m, tr("새 할 일 ({n}명)").format(n=len(cards)), lambda: self.todo_new(cards=cards))
        self._plus_menu_obj = m                        # 검사용
        m.exec(self.btn_fav_tab.mapToGlobal(self.btn_fav_tab.rect().bottomLeft()))

    def _drag_cards(self, src) -> list:
        if src is self.fav:
            return self._fav_selected_cards()
        if src is self.table:
            return self.selected_cards()
        return []

    def _drop_on_tab(self, i, src):
        """사람 칸·표에서 끌어 탭에 놓음 — 그 탭에 복사(지금 탭에서는 빠지지 않는다)."""
        gid = self.fav_tabs.tabData(i)
        if gid == RECENT or (src is self.fav and gid == self._fav_gid()):
            return 0
        return self.fav_add_selected(self._drag_cards(src), gid=gid)

    def copy_emails(self, cards) -> str:
        """이메일 복사(§5.24.1) — 쉼표로 이어 클립보드에."""
        t = P.emails_text(cards)
        if t:
            clipboard_util.set_text(t)                # 클립보드는 한 길(스크린샷 SOT §8.4 — 261117-26 덧고침)
        return t

    # ── Gmail 보내기 (§5.24.1 'Gmail 보내기', 사용자 결정 261120) ──
    def _gmail_menu(self, m, cards):
        """메일 보내기 세 줄 — 누르면 바로(받는 칸·보낼 계정은 명함 환경설정, 고른 적 없으면 한 번 묻기 — §5.24.1, 261120-33).
        차례: Gmail 보내기 → 네이버 메일 보내기(Gmail 바로 아래) → 기본 메일 앱으로 보내기. 탭 메뉴·사람 메뉴가 같이 쓴다."""
        _menu_act(m, tr("Gmail 보내기"), lambda: self.gmail_send(cards))
        _menu_act(m, tr("네이버 메일 보내기"), lambda: self.mail_naver(cards))   # 주소 복사 + 메일 화면(받는 사람을 채울 수 없음)
        _menu_act(m, tr("기본 메일 앱으로 보내기"), lambda: self.mail_default(cards))   # mailto(261120-23)

    def mail_field(self, ask: bool = False):
        """받는 칸('to'·'bcc') — 명함 환경설정에서 고른 것(meta). 고른 적이 없거나 ask 면 한 번 묻고 기억. 물음을 닫으면 None."""
        st = self._store()
        cur = st.meta_get(P.MAIL_FIELD_KEY, None)
        if cur in ("to", "bcc") and not ask:
            return cur
        items = [tr("받는 사람"), tr("숨은 참조")]
        txt, ok = QInputDialog.getItem(self, tr("메일 보내기"), tr("메일 주소를 넣을 칸 — 명함 환경설정에서 바꿀 수 있습니다:"),
                                       items, 1 if cur == "bcc" else 0, False)
        if not ok:
            return None
        field = "bcc" if txt == items[1] else "to"
        st.meta_set(P.MAIL_FIELD_KEY, field)
        return field

    def _mail_targets(self, cards, title):
        """보낼 주소들 — 없으면 알리고 None, 메일 없는 사람 수와 함께."""
        emails, missing = P.email_list(cards)
        if not emails:
            QMessageBox.information(self, title, tr("메일 주소가 있는 사람이 없습니다."))
            return None, 0
        return emails, missing

    def mail_default(self, cards, field: str = None) -> int:
        """기본 메일 앱(mailto)의 쓰기 창 — 받는 칸은 명함 환경설정, 길면 여러 창(§5.24.1 '다른 메일로 보내기', 261120-23·-33). 연 창 수."""
        title = tr("기본 메일 앱으로 보내기")
        emails, missing = self._mail_targets(cards, title)
        if not emails:
            return 0
        field = field or self.mail_field()
        if field is None:
            return 0
        urls = P.mailto_urls(emails, field)
        if len(urls) > 1 and QMessageBox.question(
                self, title,
                tr("주소가 {n}개라 쓰기 창 {w}개로 나눠 엽니다.").format(n=len(emails), w=len(urls))) != QMessageBox.StandardButton.Yes:
            return 0
        for u in urls:
            _open_url(u)
        if missing:
            QMessageBox.information(self, title, tr("메일 없는 {n}명은 뺐습니다.").format(n=missing))
        return len(urls)

    def mail_naver(self, cards) -> str:
        """네이버 메일 — 받는 사람을 채운 쓰기 창 주소가 공개돼 있지 않아 주소를 클립보드에 넣고 메일 화면만 연다(261120-23)."""
        title = tr("네이버 메일 보내기")
        emails, missing = self._mail_targets(cards, title)
        if not emails:
            return ""
        t = ", ".join(emails)
        clipboard_util.set_text(t)
        _open_url(P.NAVER_MAIL)
        msg = tr("메일 주소 {n}개를 복사했습니다 — 네이버 메일에서 [메일 쓰기]를 누르고 받는 사람 칸에 붙여 넣으세요.").format(n=len(emails))
        if missing:
            msg += "\n" + tr("메일 없는 {n}명은 뺐습니다.").format(n=missing)
        QMessageBox.information(self, title, msg)
        return t

    def gmail_account(self, ask: bool = False):
        """보낼 구글 계정 — 처음 한 번(또는 ask) 묻고 명함 DB meta 에 기억. 빈 값 = 브라우저 기본 계정. 물음을 닫으면 None."""
        st = self._store()
        cur = st.meta_get("gmail_account", None)
        if cur is not None and not ask:
            return cur
        text, ok = QInputDialog.getText(self, tr("Gmail 보내기"),
                                        tr("보낼 Gmail 주소 — 브라우저에 구글 계정이 여럿이면 이 계정으로 엽니다(비우면 기본 계정):"),
                                        text=cur or "")
        if not ok:
            return None
        text = (text or "").strip()
        st.meta_set("gmail_account", text)
        return text

    def gmail_send(self, cards, field: str = None) -> int:
        """고른 사람들의 메일 주소(사람마다 첫 메일)를 Gmail 쓰기 창(브라우저)의 받는 칸에 — 길면 여러 창. 연 창 수."""
        emails, missing = P.email_list(cards)
        if not emails:
            QMessageBox.information(self, tr("Gmail 보내기"), tr("메일 주소가 있는 사람이 없습니다."))
            return 0
        field = field or self.mail_field()
        if field is None:
            return 0
        acct = self.gmail_account()
        if acct is None:
            return 0
        urls = P.gmail_urls(emails, field, acct)
        if len(urls) > 1 and QMessageBox.question(
                self, tr("Gmail 보내기"),
                tr("주소가 {n}개라 쓰기 창 {w}개로 나눠 엽니다.").format(n=len(emails), w=len(urls))) != QMessageBox.StandardButton.Yes:
            return 0
        for u in urls:
            _open_url(u)
        if missing:
            QMessageBox.information(self, tr("Gmail 보내기"), tr("메일 없는 {n}명은 뺐습니다.").format(n=missing))
        return len(urls)

    def _tab_menu_groups(self, menu, cards, exclude=None, todo=None):
        """탭 고르기 메뉴 — todo None 이면 모두(할 일은 아이콘), True/False 면 그 갈래만."""
        st = self._store()
        pal = self.palette()
        for g, name in P.fav_groups(st, _today()):
            if g == exclude:
                continue
            is_t = P.is_todo(st, g)
            if todo is not None and is_t != todo:
                continue
            a = _menu_act(menu, name, lambda g=g: self.fav_add_selected(cards, gid=g))
            if is_t:
                a.setIcon(_tab_icon("todo", pal))

    def _table_menu(self, pos):
        """목록 오른쪽 메뉴(§5.24.1) — 즐겨찾기·할 일에 넣기·이메일 복사·삭제."""
        if self.table.itemAt(pos) is None:
            return
        cards = self.selected_cards() or ([self._card] if self._card else [])
        if not cards:
            return
        m = QMenu(self)
        fm = m.addMenu(tr("즐겨찾기 탭에 넣기"))
        self._tab_menu_groups(fm, cards, todo=False)
        fm.addSeparator()
        _menu_act(fm, tr("새 즐겨찾기 탭"), lambda: self.fav_new_tab(cards=cards))
        tm = m.addMenu(tr("할 일에 넣기"))
        tm.setIcon(_tab_icon("todo", self.palette()))
        self._tab_menu_groups(tm, cards, todo=True)
        tm.addSeparator()
        _menu_act(tm, tr("새 할 일"), lambda: self.todo_new(cards=cards))
        _menu_act(m, tr("이메일 복사"), lambda: self.copy_emails(cards))
        m.addSeparator()
        _menu_act(m, tr("삭제"), lambda: self.delete_cards())
        self._table_menu_obj = m                       # 검사용
        m.exec(self.table.viewport().mapToGlobal(pos))

    def _fav_tab_menu(self, pos):
        """탭 메뉴(§5.24.2) — 할 일 고치기·이름 바꾸기·이메일 복사·탭 마감 [?]·탭 삭제 [?]·마감한 탭 ▸."""
        i = self.fav_tabs.tabAt(pos)
        if i < 0:
            return
        st = self._store()
        gid = self.fav_tabs.tabData(i)
        m = QMenu(self)
        m.setToolTipsVisible(True)
        if gid == RECENT:
            _menu_act(m, tr("이메일 복사"), lambda: self.copy_emails(self._tab_members(RECENT)))
            self._gmail_menu(m, self._tab_members(RECENT))
            m.addSeparator()
            _menu_act(m, tr("모두 삭제"), lambda: self.recent_clear())   # §5.24.2 '최근 탭'(261120-19)
        else:
            if P.todo_info(st, gid) is not None:
                _menu_act(m, tr("할 일 고치기"), lambda: self.todo_edit(gid))
            _menu_act(m, tr("이름 바꾸기"), lambda: self.fav_rename_tab(i))
            _menu_act(m, tr("이메일 복사"), lambda: self.copy_emails(self._tab_members(gid)))
            self._gmail_menu(m, self._tab_members(gid))
            m.addSeparator()
            if self._is_closed(gid):
                _menu_act(m, tr("다시 열기"), lambda: self.tab_reopen(gid))
            else:
                _menu_act_help(m, tr("탭 마감"), lambda: self.tab_close(gid), tr(
                    "탭 줄에서 보이지 않게 합니다. 지우지 않으므로 탭 메뉴 '마감한 탭'에서 언제든 다시 보거나 다시 열 수 있습니다."), self)
            _menu_act_help(m, tr("탭 삭제"), lambda: self.tab_delete(gid), tr(
                "탭과 그 사람 칸을 완전히 지웁니다. 할 일로 사람 메모에 적은 글도 함께 지웁니다(직접 고친 글은 그대로). "
                "명함은 지우지 않습니다."), self)
        closed = P.closed_tabs(st, _today())
        if closed:
            m.addSeparator()
            cm = m.addMenu(tr("마감한 탭"))
            pal = self.palette()
            for cid, name, todo in closed:
                sm = cm.addMenu(name)
                if todo:
                    sm.setIcon(_tab_icon("todo", pal))
                _menu_act(sm, tr("보기"), lambda c=cid: self.tab_peek(c))
                if self._is_closed(cid):
                    _menu_act(sm, tr("다시 열기"), lambda c=cid: self.tab_reopen(c))
                if todo:
                    _menu_act(sm, tr("할 일 고치기"), lambda c=cid: self.todo_edit(c))
                _menu_act(sm, tr("탭 삭제"), lambda c=cid: self.tab_delete(c))
        if st.con.execute("SELECT 1 FROM fav_groups WHERE todo=1 LIMIT 1").fetchone():   # 할 일이 있을 때만(§5.24.2 '할 일 엑셀')
            m.addSeparator()
            _menu_act(m, tr("할 일 엑셀로 내보내기"), lambda: self.export_todos())
        self._tab_menu_obj = m                         # 검사용
        m.exec(self.fav_tabs.mapToGlobal(pos))

    # ── 할 일 엑셀로 내보내기 (§5.24.2 '할 일 엑셀', 261120-21) ──
    def export_todos(self, path=None):
        """모든 할 일(마감·기간 밖 포함)을 기간 차례로 .xlsx 에 — 할 일마다 제목·내용·기간·상태와 명단(이름·회사·직함·휴대폰·메일).
        파일 만들기·쓰기는 배경(응답성 SOT §6). path 를 주면 묻지 않고(검사). 반환 = 맡긴 할 일 수(없으면 0, 취소면 None)."""
        st = self._store()
        rows = P.todo_rows(st, _today())
        if not rows:
            QMessageBox.information(self, tr("할 일 엑셀로 내보내기"), tr("할 일이 없습니다."))
            return 0
        quiet = path is not None
        if path is None:
            start = Path.home() / "Documents" / ("%s_%s.xlsx" % (tr("할 일"), _today()))
            if not start.parent.is_dir():
                start = Path.home() / start.name
            path, _f = QFileDialog.getSaveFileName(self, tr("할 일 엑셀로 내보내기"), str(start), "Excel (*.xlsx)")
            if not path:
                return None
            if not path.lower().endswith(".xlsx"):
                path += ".xlsx"
        labels = {"live": tr("진행"), "soon": tr("예정"), "past": tr("기간 지남"), "closed": tr("마감")}
        for t in rows:
            t["state_label"] = labels.get(t["state"], "")
        heads = [tr("시작일"), tr("종료일"), tr("상태"), tr("제목"), tr("내용"), tr("해시태그"),
                 tr("이름"), tr("회사"), tr("직함"), tr("휴대폰"), tr("메일")]
        from viewer.workers import run_in_thread
        w = _TodoXlsxWorker(path, rows, heads, tr("할 일"), tr("계속"))
        w.done.connect(lambda ok, msg, p=path, n=len(rows), q=quiet: self._todos_written(ok, msg, p, n, q))
        keep = getattr(self._mw, "_thread_keep", None)
        self.todo_export_busy = True
        run_in_thread(w, keep if isinstance(keep, list) else _KEEP)
        self._todo_worker = w
        return len(rows)

    def _todos_written(self, ok, msg, path, n, quiet):
        self.todo_export_busy = False
        self.last_todo_export = (ok, path)               # 검사용
        if quiet:
            return
        if not ok:
            QMessageBox.warning(self, tr("할 일 엑셀로 내보내기"), tr("엑셀 파일을 쓰지 못했습니다 — 다른 프로그램이 열고 있는지 확인하세요."))
            return
        b = QMessageBox(QMessageBox.Icon.Information, tr("할 일 엑셀로 내보내기"),
                        tr("할 일 {n}개를 엑셀로 썼습니다.").format(n=n) + "\n" + str(path), parent=self)
        b_open = b.addButton(tr("폴더 열기"), QMessageBox.ButtonRole.ActionRole)
        b.addButton(tr("닫기"), QMessageBox.ButtonRole.RejectRole)
        b.exec()
        if b.clickedButton() is b_open:
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))

    # ── 할 일(todo) — 즐겨찾기 탭 + 기간(D26) ──
    @staticmethod
    def _todo_tip(info) -> str:
        period = "%s ~ %s" % (info["start"], info["end"] or tr("계속"))
        return "%s\n%s" % (period, info["memo"]) if info["memo"] else period

    def todo_new(self, info=None, cards=None) -> int:
        """새 할 일 — cards(없으면 표에서 고른 명함들·지금 명함)로 할 일 탭을 만든다. info 를 주면 창 없이(검사). 반환 = 탭 id 또는 0."""
        if cards is None:
            cards = self.selected_cards() or ([self._card] if self._card else [])
        if info is None:
            dlg = TodoDialog(self, title=tr("할 일 — {n}명").format(n=len(cards)))
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return 0
            info = dlg.info()
        if not (info.get("title") or "").strip():
            return 0
        if self._dirty and not self._ask_save():
            return 0
        gid = P.todo_add(self._store(), info, [c["id"] for c in cards], tr("계속"))
        self._fav_fill_tabs(gid)
        if self._card is not None:                    # 메모가 바뀌었을 수 있다 — 지금 명함 다시 읽기
            c = P.card_by_id(self._store(), self._card["id"])
            if c is not None:
                self._load(c)
        return gid

    def todo_edit(self, gid, info=None) -> bool:
        st = self._store()
        cur = P.todo_info(st, gid)
        if cur is None:
            return False
        if info is None:
            dlg = TodoDialog(self, cur, title=tr("할 일 고치기"))
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return False
            info = dlg.info()
        if not (info.get("title") or "").strip():
            return False
        P.todo_update(st, gid, info)
        self._fav_fill_tabs(self._fav_gid())
        if getattr(self, "todo_panel", None) is not None and self.todo_panel.gid == gid:
            self._todo_show(gid)                         # 제목·기간·내용(새 기록)을 할 일 칸에도(§5.24.10)
        return True

    def todo_delete(self, gid, ask: bool = True) -> bool:
        return P.todo_info(self._store(), gid) is not None and self.tab_delete(gid, ask=ask)

    def _fav_current(self, cur, _prev):
        """키보드로 옮김 — 빠르게 넘겨도 멈춘 뒤 마지막 사람만 보인다(메인을 세우지 않게, FAV_KEY_MS)."""
        if cur is not None and not getattr(self, "_fav_filling", False):
            self._fav_key_id = cur.data(ROLE)
            self._fav_key_timer.start()

    def _fav_key_show(self):
        if self._fav_key_id is not None:
            self._show_card_id(self._fav_key_id)

    def eventFilter(self, obj, e):
        from PyQt6.QtCore import QEvent
        if obj is getattr(self, "ed_find", None):
            t = e.type()
            if t in (QEvent.Type.FocusIn, QEvent.Type.MouseButtonPress):
                go = False
                if self._table_tab is not None:
                    self._table_tab = None                 # 탭 명단 보기 → 찾기 결과(비었으면 전체)
                    go = True
                # 흐린 글을 다시 고름(흐린 글 거르개보다 먼저 받는다 — 아직 흐림) → 커서 맨 앞·전체 목록(사용자 지시 261120)
                if obj.property("searchGhostDim") and not self._ghost_all:
                    self._ghost_all = True
                    go = True
                if go:
                    QTimer.singleShot(0, self.refresh)
            elif self._ghost_all and t in (QEvent.Type.KeyPress, QEvent.Type.ContextMenu, QEvent.Type.InputMethod):
                QTimer.singleShot(0, self._ghost_check)    # →·Ctrl 조합·메뉴로 흐린 글을 되살렸나(그 뒤에 본다)
        return super().eventFilter(obj, e)

    def _ghost_check(self):
        """흐린 글이 되살아났거나 바뀌었으면 칸 글의 결과로 돌아간다."""
        if self._ghost_all and not self.ed_find.property("searchGhostDim"):
            self._ghost_all = False
            self._find_timer.stop()
            self.refresh()

    def _fav_fill(self):
        """지금 탭의 사람 칸 — 우선 옅은 파랑 + 첫 글자, 그림은 배경에서 읽어 바꾼다."""
        self._fav_filling = True
        try:
            self._fav_fill_items()
        finally:
            self._fav_filling = False

    def _fav_fill_items(self):
        self.fav.clear()
        gid = self._fav_gid()
        self._fav_gen += 1
        if gid is None:
            self._fav_fit()
            return
        jobs = []
        bold = QFont(self.fav.font())                  # 이름은 굵게 — 사람 칸 글꼴에 굵기만(§5.24.2 '즐겨찾기 줄', 사용자 지시 261120)
        bold.setBold(True)
        for c in self._tab_members(gid):
            it = QListWidgetItem(QIcon(_rounded(None, c.get("name") or "")), c.get("name") or "")
            it.setFont(bold)
            it.setData(ROLE, c["id"])
            it.setToolTip(self._fav_tip(c))
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.fav.addItem(it)
            pf = self._photo_front(c)
            photos = P.person_photos(pf) if pf else []
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
        h = rows * g.height() + 2 * self.fav.frameWidth() + 4
        tp = getattr(self, "todo_panel", None)
        if tp is not None and tp.isVisible():            # 할 일 칸이 보이면 사람 칸도 그 높이까지(§5.24.10 '배치')
            h = max(h, tp.minimumHeight() - self.fav_tabs.sizeHint().height())
        self.fav.setFixedHeight(h)

    def fav_ids(self) -> list:
        return [self.fav.item(i).data(ROLE) for i in range(self.fav.count())]

    def fav_add_selected(self, cards=None, gid=None) -> int:
        """넣는 길 하나 — gid(없으면 지금 탭)에 cards(없으면 표에서 고른 명함들). '최근' 에는 넣지 않는다(D27)."""
        gid = self._fav_gid() if gid is None else gid
        cards = cards if cards is not None else (self.selected_cards() or ([self._card] if self._card else []))
        if gid is None or gid == RECENT or not cards:
            return 0
        todo = P.is_todo(self._store(), gid)
        if todo and self._dirty and not self._ask_save():
            return 0
        n = P.fav_add(self._store(), gid, [c["id"] for c in cards], ongoing=tr("계속"))
        if gid == self._fav_gid():
            self._fav_fill()
        self._sync_table(gid)
        if todo and n:                                 # 할 일 탭 — 메모 맨 위에 기록됐다(D26)
            self._reload_card()
        return n

    def fav_remove_selected(self):
        gid = self._fav_gid()
        ids = [it.data(ROLE) for it in self.fav.selectedItems()]
        if gid is None or not ids:
            return
        if gid == RECENT:
            P.recent_remove(self._store(), ids)
        else:
            P.fav_remove(self._store(), gid, ids)
        self._fav_fill()
        self._sync_table(gid)

    def _fav_selected_cards(self) -> list:
        st = self._store()
        return [c for c in (P.card_by_id(st, it.data(ROLE)) for it in self.fav.selectedItems()) if c]

    def _fav_save_order(self):
        gid = self._fav_gid()
        if gid is not None:
            P.fav_order(self._store(), gid, self.fav_ids())

    @staticmethod
    def _fav_tip(c) -> str:
        """즐겨찾기 사람 위 — 이름·회사·직함 + 휴대폰·메일(§5.24, 사용자 지시 261119)."""
        lines = [" · ".join(x for x in (c.get("name"), c.get("company"), c.get("title")) if x)]
        cells = [p[1] for p in (c.get("phones") or []) if isinstance(p, (list, tuple)) and len(p) >= 2 and p[0] == "cell"]
        if cells:
            lines.append(tr("휴대폰") + ": " + ", ".join(cells))
        mails = [str(e[-1] if isinstance(e, (list, tuple)) else e) for e in (c.get("emails") or []) if e]
        if mails:
            lines.append(tr("메일") + ": " + ", ".join(mails))
        return "\n".join(x for x in lines if x)

    def fav_copy_selected(self) -> str:
        """즐겨찾기 사람 메뉴 '내용 복사' — 고른 사람들의 체크한 칸([내용 복사]와 같은 글)."""
        t = self.copy_text(self._fav_selected_cards())
        if t:
            clipboard_util.set_text(t)                # 클립보드는 한 길(스크린샷 SOT §8.4 — 261117-26 덧고침)
        return t

    def _fav_menu(self, pos):
        """사람 메뉴(§5.24.2) — 내용 복사·이메일 복사·다른 탭에 복사·새 탭/할 일로·빼기."""
        if self.fav.itemAt(pos) is None:
            return
        gid = self._fav_gid()
        cards = self._fav_selected_cards()
        m = QMenu(self)
        _menu_act(m, tr("내용 복사"), lambda: self.fav_copy_selected())
        _menu_act(m, tr("이메일 복사"), lambda: self.copy_emails(cards))
        self._gmail_menu(m, cards)
        cm = m.addMenu(tr("다른 탭에 복사"))
        self._tab_menu_groups(cm, cards, exclude=gid)
        _menu_act(m, tr("새 즐겨찾기 탭으로"), lambda: self.fav_new_tab(cards=cards))
        _menu_act(m, tr("새 할 일로"), lambda: self.todo_new(cards=cards))
        m.addSeparator()
        _menu_act(m, tr("최근에서 빼기") if gid == RECENT else tr("탭에서 빼기"), lambda: self.fav_remove_selected())
        self._fav_menu_obj = m                         # 검사용
        m.exec(self.fav.mapToGlobal(pos))

    # ── 인물 사진 ──
    def _pick_photos(self):
        files, _f = QFileDialog.getOpenFileNames(self, tr("인물 사진"), "", tr("그림") + " (%s)" % IMG_FILTER)
        if files:
            self.add_photos(files)

    # 끌어 놓기(§5.24.3 '끌어 놓기') — 놓는 자리는 사진창(photo_split) 하나, 끄는 동안 그 자리를 점선 틀로 보인다.
    #   종전엔 창이 들어오기(enter)만 받고 움직이기(move)를 받지 않아 Windows 에서 '놓을 수 없음' 이 되어 놓아지지 않았다.
    def _drop_ok(self, e) -> bool:
        md = e.mimeData()
        return bool(self._photo_front()) and md.hasUrls() and any(self._is_img(u.toLocalFile()) for u in md.urls())

    def _in_drop_zone(self, pos) -> bool:
        from PyQt6.QtCore import QRect, QPoint
        z = self.photo_split
        return z.isVisible() and QRect(z.mapTo(self, QPoint(0, 0)), z.size()).contains(pos)

    def _show_drop_zone(self, on: bool, hot: bool = False):
        """놓을 자리 표시 — 사진창 위에 겹친 틀(마우스·끌기를 받지 않는다). hot = 그 안에 올림(바탕도 칠함)."""
        from PyQt6.QtCore import QRect, QPoint
        z = getattr(self, "drop_zone", None)
        if not on:
            if z is not None:
                z.hide()
            return
        if z is None:
            z = self.drop_zone = QLabel(tr("여기에 놓으면 인물 사진으로 넣습니다"), self)
            z.setObjectName("bizDropZone")
            z.setAlignment(Qt.AlignmentFlag.AlignCenter)
            z.setWordWrap(True)
            z.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        h = self.palette().color(self.palette().ColorRole.Highlight)
        z.setStyleSheet("QLabel#bizDropZone{border:2px dashed %s;border-radius:8px;background:rgba(%d,%d,%d,%s);"
                        "color:%s;font-weight:bold;}" % (h.name(), h.red(), h.green(), h.blue(),
                                                         DROP_TINT_HOT if hot else DROP_TINT, h.name()))
        z.setGeometry(QRect(self.photo_split.mapTo(self, QPoint(0, 0)), self.photo_split.size()))
        z.raise_()
        z.show()

    def dragEnterEvent(self, e):
        if self._drop_ok(e):
            e.acceptProposedAction()                   # 창 어디로 들어와도 받아 두고 — 놓는 것은 사진창 안에서만(move)
            self._show_drop_zone(True, self._in_drop_zone(e.position().toPoint()))
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        hot = self._drop_ok(e) and self._in_drop_zone(e.position().toPoint())
        if hot:
            e.acceptProposedAction()
        else:
            e.ignore()
        self._show_drop_zone(self._drop_ok(e), hot)

    def dragLeaveEvent(self, e):
        self._show_drop_zone(False)

    def dropEvent(self, e):
        self._show_drop_zone(False)
        if self._drop_ok(e) and self._in_drop_zone(e.position().toPoint()):
            self._drop_files(e)
        else:
            e.ignore()

    def _photos_drag(self, e):
        """썸네일 줄 위(그 줄이 직접 받는다)에서도 같은 틀 — e = 끌기 이벤트, None = 떠남·놓음."""
        self._show_drop_zone(e is not None and self._drop_ok(e), True)

    def _drop_files(self, e):
        self._show_drop_zone(False)
        files = [u.toLocalFile() for u in e.mimeData().urls() if self._is_img(u.toLocalFile())]
        if files:
            e.acceptProposedAction()
            self.add_photos(files)

    @staticmethod
    def _is_img(p) -> bool:
        return bool(p) and os.path.splitext(p)[1].lower() in R.IMG_EXTS

    def add_photos(self, files):
        pf = self._photo_front()
        if not self._card or self.photo_busy or not pf:
            return
        from viewer.workers import run_in_thread
        self.photo_busy = True
        self.btn_photo.setEnabled(False)
        w = PhotoWorker(pf, files)
        card_id = self._card["id"]

        def _done(made, bad):
            self.photo_busy = False
            self.btn_photo.setEnabled(bool(self._photo_front()))
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
        plan = P.photo_renames(self._photo_front(c), ordered)
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

    def delete_shown_photos(self, ask: bool = True) -> int:
        """[사진 삭제] — 썸네일 줄에서 고른 사진, 없으면 큰 화면의 사진(Delete 와 같은 길)."""
        paths = [it.data(ROLE) for it in self.photos.selectedItems()] or ([self.photo_shown] if self.photo_shown else [])
        return self.delete_photos(paths, ask=ask)

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
        files = {c["id"]: P.card_files(c, self._bizcard_folder()) for c in cards}
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
            store = self._own_tagstore()
        return store

    def _own_tagstore(self):
        """본 뷰어 없이(PolyCardex) — 태그 파일을 누를 때마다 새로 읽지 않고, 파일이 바뀌었을 때만(크기·고친 시각) 다시 연다.
        다른 프로그램(본 뷰어)이 고쳐 쓰면 다음 누름에 새로 읽는다(§5.24.4 '빠르게', 261120-20)."""
        from viewer.tag_store import TagStore
        st = getattr(self, "_own_tags", None)
        try:
            from viewer.settings_store import settings_dir
            fp = Path(settings_dir()) / "file_tags.json"
            sig = (fp.stat().st_size, fp.stat().st_mtime_ns) if fp.exists() else None
        except Exception:
            sig = object()                              # 알 수 없으면 늘 새로
        if st is None or getattr(self, "_own_tags_sig", None) != sig:
            st = self._own_tags = TagStore()
            self._own_tags_sig = sig
        return st

    def _preload_tags(self):
        """창이 뜬 뒤 쉬는 동안 — '해시태그 수정' 창 모듈을 미리 불러오고, 저장소의 전체 태그 목록을 배경에서 세어 둔다
        (첫 [해시태그] 누름이 늦던 원인 둘, 261120-20). 사본을 떠서 배경이 세고, 그사이 저장소가 바뀌었으면 버린다."""
        if getattr(self, "_tags_preloaded", False):
            return
        self._tags_preloaded = True
        try:
            import viewer.widgets.tag_apply_dialog          # noqa: F401 — 첫 누름의 모듈 불러오기(workers·indexer·pymupdf)
            real = self._tagstore()
            kc = getattr(real, "_known_cache", None)
            if kc is not None and kc[0] == real._gen and kc[1] is real._data:
                return                                      # 이미 지금 세대로 세어 둠
            snap = _card_tag_store(real)
            w = _KnownWorker(snap, real, real._gen, real._data)
            w.done.connect(self._known_ready)
            from viewer.workers import run_in_thread
            keep = getattr(self._mw, "_thread_keep", None)
            run_in_thread(w, keep if isinstance(keep, list) else _KEEP)
            self._known_worker = w
        except Exception:
            pass

    def _known_ready(self, real, tags, gen, data):
        try:
            real.seed_known(tags, gen=gen, data=data)      # 그사이 저장소가 바뀌었으면 받지 않는다
        except Exception:
            pass
        self.known_preloaded = True                        # 검사용

    def edit_tags(self, text=None):
        """고른 명함들(없으면 지금 명함) — 함께 붙은 태그를 보여 주고, 더한 것은 모두에 붙이고 뗀 것은 모두에서 뗀다.
        text 를 주면 창 없이(검사). 반환 = 바꾼 명함 수 또는 None(취소)."""
        cards = self.selected_cards() or ([self._card] if self._card else [])
        if not cards:
            return None
        if self._dirty and not self._ask_save():
            return None
        from viewer.tag_store import normalize_tags
        if text is None:                                # 늘 책갈피창 '해시태그 수정' 창 하나(§5.24.4, 사용자 지시 261118·261119)
            return self.tag_apply(cards)
        init = P.common_tags(cards)
        store = self._tagstore()
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
        """책갈피창 '해시태그 수정' 창(`TagApplyDialog`, 태그 SOT §8.7)에 명함들의 정리본 앞면을 썸네일로 넘긴다(그림 없는 명함은
        이름만). 창을 닫으면 명함마다 앞면에서 더하고 뗀 사람 태그를 명함 DB 태그 칸·뒷면 파일에 같게. 반환 = 바뀐 명함 수."""
        from viewer.widgets.tag_apply_dialog import TagApplyDialog
        real = self._tagstore()
        # 창은 태그 저장소의 메모리 사본(_card_tag_store)에서 — 그림 없는 주소록 명함(D22)도 같은 창에 '파일' 하나로 넣는다(가상 경로,
        # 썸네일 없음). 닫은 뒤 바뀐 그림 파일 기록만 실제 저장소로, 명함마다 더하고 뗀 사람 태그를 명함 DB·뒷면 파일에(§5.24.4).
        store = _card_tag_store(real)
        fronts, files, virt = [], set(), {}
        for c in cards:
            f = c.get("front")
            if f and not V.is_contact(c) and os.path.exists(f):
                f = os.path.realpath(f)
                files.add(f)
            else:
                f = _virtual_key(c)
                store.set(f, list(c.get("tags") or []))
                virt[f] = c
            fronts.append(f)
        before = {f: list(store.get_manual(f) or []) for f in fronts}
        # 전체 태그 목록은 실제 저장소가 세어 둔 것(세대 캐시 — 미리 센 것이면 바로) + 그림 없는 명함의 태그 — 사본에서 다시 세지 않는다(261120-20)
        try:
            known = real.known_tags()
            low = {t.lower() for t in known}
            for f in virt:
                known += [t for t in store.get(f) if t.lower() not in low and not low.add(t.lower())]
            store.seed_known(known)
        except Exception:
            pass
        mw = self._mw
        prefs = getattr(mw, "_prefs", None) if mw is not None else None
        keep = mw.__dict__.setdefault("_thread_keep", []) if mw is not None else _KEEP
        state = prefs.get("tag_apply_window") if isinstance(prefs, dict) else None
        dlg = TagApplyDialog(store, fronts, fronts, self, keep=keep, state=state)
        for i in range(dlg.lst_files.count()):          # 가상 경로는 보이지 않게
            it = dlg.lst_files.item(i)
            if it.data(Qt.ItemDataRole.UserRole) in virt:
                it.setToolTip(tr("그림 없는 주소록 명함 — 명함 DB 태그 칸에만"))
        self._tag_apply_dialog = dlg                   # 검사용
        dlg.exec()
        after = {f: list(store.get_manual(f) or []) for f in fronts}
        if isinstance(prefs, dict) and dlg.state_out != (prefs.get("tag_apply_window") or {}):
            prefs["tag_apply_window"] = dict(dlg.state_out)   # 크기·최대화·정렬 기억 — 책갈피창과 같은 설정
            try:
                mw._save_settings_now()
            except Exception:
                pass
        st = self._store()
        n = 0
        # 여러 장이어도 메인을 오래 세우지 않게 — 태그 저장소는 한 번에 모아 저장(bulk), 명함 DB 는 마지막에 한 번 커밋
        with real.bulk():
            for f in files:                             # 바뀐 그림 파일 기록(자동 태그 거절 포함)을 실제 저장소로
                rec = store.record(f)
                if rec != real.record(f):
                    real.put_record(f, rec)
            for c, f in zip(cards, fronts):
                add = [t for t in after[f] if t not in before[f]]
                rem = [t for t in before[f] if t not in after[f]]
                if not add and not rem:
                    continue
                b = c.get("back")
                if b and os.path.exists(b):
                    b = os.path.realpath(b)
                    cur = [t for t in (real.get_manual(b) or []) if t not in rem]
                    real.set(b, list(dict.fromkeys(cur + add)))
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
        if getattr(real, "_known_cache", (None,))[0] != getattr(real, "_gen", 0):   # 태그를 바꿨으면 쉬는 동안 다시 세어 둔다
            self._tags_preloaded = False
            QTimer.singleShot(PRELOAD_MS, self._preload_tags)
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
        if ask and QMessageBox.question(
                self, tr("주소록 가져오기"),
                tr("연락처 {n}명을 읽었습니다 — 모두 그림 없는 명함으로 넣은 뒤 [중복 검토] 창에서 이미 있는 명함과 합칠 것을 고릅니다.").format(
                    n=len(persons))) != QMessageBox.StandardButton.Yes:
            return None
        res = P.apply_import(st, persons, tr("주소록"), source)
        self.last_import = res
        self.refresh()
        self.open_dupes(exec_=ask)              # 가져온 뒤에는 늘 병합 창(§5.24.8, 사용자 지시 261119) — 검사(ask=False)는 모달 없이
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
