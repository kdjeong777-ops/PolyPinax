"""명함찾기 창 (명함 SOT §5.9, P4 · R2·R11·R12).

찾기(낱말 일부·#태그·스캔일 기간) → 결과 표 → 왼쪽 명함 그림(앞면 크게 + 뒷면·인물 사진 작은 그림), 오른쪽 칸·메모 고치기.
이름·회사를 고쳐 저장하면 정리본 이름도 `성명_회사명` 으로 — 앱의 이름 바꾸기 한 길(`_rename_bg` → `_after_rename`).
인물 사진 추가는 배경(JPG·EXIF 뺌). ★ 명함 글은 로그·상태 줄 밖으로 내보내지 않는다(§2.1).
"""
from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QSize, QObject, pyqtSignal
from PyQt6.QtGui import QPixmap, QIcon, QImageReader
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QHeaderView, QSplitter, QWidget, QFormLayout, QPlainTextEdit, QPushButton,
    QListWidget, QListWidgetItem, QListView, QMessageBox, QFileDialog, QSizePolicy)

from viewer.i18n import tr, tr_noop
from viewer.bizcard import people as P
from viewer.bizcard import recognize as R

C_NAME, C_COMP, C_TITLE, C_DATE = range(4)
THUMB = 72
FIND_DELAY_MS = 250
IMG_FILTER = " ".join("*" + e for e in R.IMG_EXTS)
# 칸(키, 화면 이름) — 전화는 종류마다 첫 번호만 고친다(나머지는 그대로 둔다)
FIELDS = (("name", tr_noop("이름")), ("company", tr_noop("회사")), ("dept", tr_noop("부서")), ("title", tr_noop("직함")), ("cell", tr_noop("휴대폰")), ("work", tr_noop("전화")),
          ("fax", tr_noop("팩스")), ("email", tr_noop("메일")), ("address", tr_noop("주소")), ("url", tr_noop("누리집")))


def _scaled(path: str, w: int, h: int) -> QPixmap:
    """큰 사진도 칸 크기로 줄여 읽는다(QImageReader 축소 읽기 — 메모리·시간)."""
    rd = QImageReader(path)
    rd.setAutoTransform(True)
    sz = rd.size()
    if sz.isValid() and (sz.width() > 2 * w or sz.height() > 2 * h):
        rd.setScaledSize(sz.scaled(QSize(2 * w, 2 * h), Qt.AspectRatioMode.KeepAspectRatio))
    im = rd.read()
    if im.isNull():
        return QPixmap()
    return QPixmap.fromImage(im).scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)


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


_KEEP = []


class BizcardFindDialog(QDialog):
    def __init__(self, parent=None, db=None):
        super().__init__(parent)
        self._mw = parent
        self._db = db
        self._st = None
        self._rows = []
        self._card = None
        self._loading = False
        self._dirty = False
        self.photo_busy = False
        self.setWindowTitle(tr("명함찾기"))
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowMinimizeButtonHint)
        self.setAcceptDrops(True)
        self.resize(1280, 760)
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

        split = QSplitter(Qt.Orientation.Horizontal)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([tr("이름"), tr("회사"), tr("직함"), tr("스캔일")])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        for c, w in ((C_NAME, 90), (C_COMP, 150), (C_TITLE, 80)):
            self.table.setColumnWidth(c, w)
        self.table.currentCellChanged.connect(self._on_current)
        split.addWidget(self.table)

        mid = QWidget()
        mv = QVBoxLayout(mid)
        mv.setContentsMargins(6, 0, 6, 0)
        self.pv = QLabel()
        self.pv.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pv.setMinimumSize(320, 200)
        self.pv.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.pv.setToolTip(tr("인물 사진을 여기에 끌어 놓으면 이 명함의 인물 사진으로 넣습니다"))
        mv.addWidget(self.pv, 1)
        self.thumbs = QListWidget()
        self.thumbs.setViewMode(QListView.ViewMode.IconMode)
        self.thumbs.setFlow(QListView.Flow.LeftToRight)
        self.thumbs.setWrapping(False)
        self.thumbs.setIconSize(QSize(THUMB, THUMB))
        self.thumbs.setFixedHeight(THUMB + 28)
        self.thumbs.currentItemChanged.connect(lambda cur, _p: self._show_big(cur.data(Qt.ItemDataRole.UserRole) if cur else ""))
        mv.addWidget(self.thumbs)
        split.addWidget(mid)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        self.eds = {}
        for k, label in FIELDS:
            ed = QLineEdit()
            ed.textEdited.connect(lambda _t: self._set_dirty(True))
            form.addRow(tr(label), ed)
            self.eds[k] = ed
        rv.addLayout(form)
        rv.addWidget(QLabel(tr("메모")))
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
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 3)
        split.setStretchFactor(2, 2)
        v.addWidget(split, 1)

        bot = QHBoxLayout()
        self.btn_photo = QPushButton(tr("사진 추가..."))
        self.btn_photo.setToolTip(tr("인물 사진을 '인물' 폴더에 정리본과 같은 이름의 JPG 로 넣습니다 — 위치 정보 등 EXIF 는 뺍니다"))
        self.btn_photo.clicked.connect(lambda _c=False: self._pick_photos())
        self.btn_open = QPushButton(tr("사진 모드에서 열기"))
        self.btn_open.clicked.connect(lambda _c=False: self.open_in_photo())
        self.btn_vcard = QPushButton(tr("vCard 로 내보내기..."))
        self.btn_vcard.setToolTip(tr("고른 명함들을 vCard(.vcf) 로 내보냅니다"))
        self.btn_vcard.clicked.connect(lambda _c=False: self.export_vcard())
        b_close = QPushButton(tr("닫기"))
        b_close.clicked.connect(lambda _c=False: self.close())
        for b in (self.btn_photo, self.btn_open, self.btn_vcard):
            bot.addWidget(b)
        bot.addStretch(1)
        bot.addWidget(b_close)
        v.addLayout(bot)
        self._enable_card_buttons(False)
        QTimer.singleShot(0, self.refresh)

    # ── 저장소 ──
    def _store(self):
        if self._st is None:
            from viewer.bizcard.store import BizcardStore
            self._st = BizcardStore(self._db, ui=True)
        return self._st

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
        keep = self._card["id"] if self._card else None
        self._loading = True
        try:
            self.table.setRowCount(len(self._rows))
            pick = 0 if self._rows else -1
            for r, c in enumerate(self._rows):
                for col, val in ((C_NAME, c.get("name")), (C_COMP, c.get("company")), (C_TITLE, c.get("title")),
                                 (C_DATE, c.get("scanned"))):
                    self.table.setItem(r, col, QTableWidgetItem(val or ""))
                if c["id"] == keep:
                    pick = r
        finally:
            self._loading = False
        self.lbl_count.setText((tr("처음 {n}장") if more else tr("{n}장")).format(n=len(self._rows)))
        if pick >= 0:
            self.table.setCurrentCell(pick, 0)
            self._load(self._rows[pick])
        else:
            self._load(None)

    def _on_current(self, r, _c, pr, _pc):
        if self._loading or r == pr:
            return
        if self._dirty and not self._ask_save():
            self._loading = True
            self.table.setCurrentCell(pr, 0)
            self._loading = False
            return
        self._load(self._rows[r] if 0 <= r < len(self._rows) else None)

    def selected_cards(self) -> list:
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self._rows[r] for r in rows if 0 <= r < len(self._rows)]

    # ── 한 명함 ──
    def _load(self, card):
        self._card = card
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
            self.lbl_file.setText(os.path.basename(card["front"]) if card else "")
        finally:
            self._loading = False
        self._set_dirty(False)
        self._enable_card_buttons(card is not None)
        self._fill_thumbs()

    def _fill_thumbs(self, select: str = ""):
        self.thumbs.clear()
        c = self._card
        if not c:
            self.pv.clear()
            return
        paths = [c["front"]] + ([c["back"]] if c.get("back") else []) + P.person_photos(c["front"])
        for p in paths:
            if not os.path.exists(p):
                continue
            it = QListWidgetItem(QIcon(_scaled(p, THUMB, THUMB)), "")
            it.setData(Qt.ItemDataRole.UserRole, p)
            it.setToolTip(os.path.basename(p))
            self.thumbs.addItem(it)
        if self.thumbs.count():
            idx = next((i for i in range(self.thumbs.count())
                        if select and os.path.normcase(self.thumbs.item(i).data(Qt.ItemDataRole.UserRole)) == os.path.normcase(select)), 0)
            self.thumbs.setCurrentRow(idx)
        else:
            self.pv.setText(tr("(그림 파일이 없습니다)"))

    def _show_big(self, path):
        self.shown = path
        if not path:
            self.pv.clear()
            return
        pm = _scaled(path, max(200, self.pv.width()), max(150, self.pv.height()))
        self.pv.setPixmap(pm)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        cur = self.thumbs.currentItem()
        if cur is not None:
            QTimer.singleShot(0, lambda: self._show_big(getattr(self, "shown", "")))

    def _set_dirty(self, on: bool):
        if self._loading:
            return
        self._dirty = bool(on and self._card)
        self.btn_save.setEnabled(self._dirty)

    def _enable_card_buttons(self, on: bool):
        for b in (self.btn_photo, self.btn_open, self.btn_vcard):
            b.setEnabled(on)

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
        old_auto = set(c.get("tags") or [])
        new_tags = tags_for({"company": new["company"], "langs": [t for t in old_auto if t in ("한글", "영어")]})
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
                stem = p.stem if i == 0 else "%s (%d)" % (p.stem, i + 1)
                dst = Path(ph).with_name(stem + os.path.splitext(ph)[1])
                if os.path.normcase(str(dst)) != os.path.normcase(ph) and not dst.exists():
                    self._rename(ph, str(dst))
        fields = dict(new, front=nf, back=nb, tags=new_tags)
        P.update_card(st, c["id"], fields)
        self._retag([x for x in (nf, nb) if x], old_auto, new_tags)
        self._dirty = False
        self.btn_save.setEnabled(False)
        self._card = dict(c, **fields)
        self.saved = {"renamed": nf != front}
        self.refresh()
        return True

    def _rename(self, src: str, dst: str) -> bool:
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

    # ── 인물 사진 ──
    def _pick_photos(self):
        files, _f = QFileDialog.getOpenFileNames(self, tr("인물 사진"), "", tr("그림") + " (%s)" % IMG_FILTER)
        if files:
            self.add_photos(files)

    def dragEnterEvent(self, e):
        if self._card and e.mimeData().hasUrls() and any(self._is_img(u.toLocalFile()) for u in e.mimeData().urls()):
            e.acceptProposedAction()

    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls() if self._is_img(u.toLocalFile())]
        if files:
            e.acceptProposedAction()
            self.add_photos(files)

    @staticmethod
    def _is_img(p) -> bool:
        return bool(p) and os.path.splitext(p)[1].lower() in R.IMG_EXTS

    def add_photos(self, files):
        if not self._card or self.photo_busy:
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
                self._fill_thumbs(select=made[-1] if made else "")
            if bad:
                QMessageBox.warning(self, tr("인물 사진"), tr("그림 {n}개를 넣지 못했습니다.").format(n=bad))
        w.done.connect(_done)
        keep = getattr(self._mw, "_thread_keep", None)
        run_in_thread(w, keep if isinstance(keep, list) else _KEEP)

    # ── 단추 ──
    def open_in_photo(self):
        c = self._card
        if not c or self._mw is None or not hasattr(self._mw, "_photo_open_arg"):
            return
        if not self._mw._photo_open_arg(c["front"]):
            QMessageBox.information(self, tr("명함찾기"), tr("사진 모드로 열지 못했습니다."))

    def export_vcard(self, path=None, drive=None):
        """고른 명함들 → vCard(§5.8 모듈). path·drive 를 주면 묻지 않는다(검사). 반환 = 장 수 또는 None."""
        from viewer.bizcard import vcard as V
        from viewer import bg_write
        from viewer.i18n import language
        cards = self.selected_cards() or ([self._card] if self._card else [])
        if not cards:
            return None
        st = self._store()
        if drive is None:
            from PyQt6.QtWidgets import QInputDialog
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
            start = Path(cards[0]["front"]).parent / (tr("명함") + ".vcf")
            path, _f = QFileDialog.getSaveFileName(self, tr("vCard 로 내보내기"), str(start), "vCard (*.vcf)")
            if not path:
                return None
        lang = "en" if str(language()).startswith("en") else "ko"
        bg_write.submit(path, V.export_text(cards, drive, lang, tr("명함")), delay=0)
        if not quiet:
            QMessageBox.information(self, "vCard", tr("vCard 에 {n}장을 썼습니다.").format(n=len(cards)) + "\n" + str(path))
        return len(cards)

    def closeEvent(self, e):
        if self._dirty and not self._ask_save():
            e.ignore()
            return
        if self._st is not None:
            self._st.close()
            self._st = None
        super().closeEvent(e)
