"""명함 중복 검토 창 (명함 SOT §5.24.8, D30).

묶기·출처·차례·합친 값은 `people.dupe_groups`·`people.merge_plan`(Qt 없음), 이 창은 보여 주고 적용·되돌리기만.
파일 이름 바꾸기·옮기기는 명함찾기 창의 한 길(`_rename` → 앱 `_rename_bg`·`_after_rename`)로.
★ 명함 글·경로는 로그·예외 메시지에 싣지 않는다(§2.1). 모두 이 PC 안.
"""
from __future__ import annotations

import json
import os
from viewer import dbutil
from pathlib import Path

from PyQt6.QtCore import Qt, QSize, QObject, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QPixmap, QImage
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QListView,
    QAbstractItemView, QPushButton, QSplitter, QTreeWidget, QTreeWidgetItem, QMessageBox, QMenu, QWidget)

from viewer.i18n import tr, tr_noop
from viewer.bizcard import people as P
from viewer.bizcard import vcard as V

ROLE = Qt.ItemDataRole.UserRole
THUMB = 96                          # 명함 그림 썸네일 줄(고른 묶음의 그림 명함 앞·뒷면, §5.24.8 '명함 그림')
SRC_LABEL = {"card": tr_noop("명함"), "remember": tr_noop("리멤버"), "google": tr_noop("구글"), "contact": tr_noop("주소록")}
WHY_LABEL = {"phone": tr_noop("같은 번호"), "namemail": tr_noop("이름·메일 같음(확정)"), "mail": tr_noop("같은 메일"), "typo": tr_noop("번호 오타?"),
             "namecomp": tr_noop("이름·회사 같음")}
SHOW = (("name", tr_noop("이름")), ("company", tr_noop("회사")), ("dept", tr_noop("부서")), ("title", tr_noop("직함")),
        ("phones", tr_noop("전화")), ("emails", tr_noop("메일")), ("urls", tr_noop("누리집")), ("address", tr_noop("주소")),
        ("memo", tr_noop("메모")))


def _phone(c) -> str:
    return ", ".join(n for _k, n in c.get("phones") or [])


def _val(fields, k) -> str:
    v = fields.get(k)
    if k == "phones":
        return ", ".join(n for _k, n in v or [])
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v)
    return str(v or "")


_KEEP = []


class CardEditDialog(QDialog):
    """명함 하나 고치기(§5.24.8 '명함 고치기') — 칸은 명함찾기 세부 칸과 같다, 값은 `edited_fields` 로."""

    def __init__(self, card, parent=None):
        super().__init__(parent)
        from PyQt6.QtWidgets import QFormLayout, QLineEdit, QPlainTextEdit, QDialogButtonBox, QCheckBox
        from viewer.bizcard import phone as PH
        from viewer.widgets import bizcard_find_dialog as FD
        self.card = card
        self.setWindowTitle(tr("명함 고치기"))
        v = QVBoxLayout(self)
        form = QFormLayout()
        ph = card.get("phones") or []
        first = lambda kind: next((n for k, n in ph if k == kind), "")
        vals = {k: card.get(k) or "" for k in ("name", "company", "dept", "title", "address")}
        vals.update(cell=PH.normalize(first("cell")), work=PH.normalize(first("work")), fax=PH.normalize(first("fax")),
                    email=(card.get("emails") or [""])[0], url=(card.get("urls") or [""])[0])
        self.eds, self.checks = {}, {}                  # checks: 칸 열쇠(또는 추가 칸 위젯) → 앞 체크 칸(이름 칸은 없음)

        def row(key, text, ed):
            if key == "name":
                form.addRow(text, ed)
                return
            cb = QCheckBox(text)                        # 칸 앞 체크 — [체크한 칸 비우기](§5.24.8 '명함 고치기')
            self.checks[key] = cb
            form.addRow(cb, ed)
        for k, label in FD.FIELDS:
            ed = QLineEdit(vals.get(k, ""))
            if k in FD.PHONE_KEYS:
                PH.attach(ed)                          # 치는 대로 하이픈(§5.11 '번호 꼴')
            row(k, tr(label), ed)
            self.eds[k] = ed
        # 둘째 값부터도 칸으로(§5.24.8 '명함 고치기', 사용자 결정 261121 — 숨은 번호를 보고 지울 수 있게, 비우면 지움)
        labels = dict(FD.FIELDS)
        self.extra_eds = []
        for kind in FD.PHONE_KEYS:
            for i, n in enumerate([n for k, n in (tuple(x) for x in ph) if k == kind][1:]):
                ed = QLineEdit(PH.normalize(n))
                PH.attach(ed)
                row(ed, "%s %d" % (tr(labels[kind]), i + 2), ed)
                self.extra_eds.append(("phone", kind, ed))
        for group, key, vals_ in (("email", "email", card.get("emails") or []), ("url", "url", card.get("urls") or [])):
            for i, x in enumerate(list(vals_)[1:]):
                ed = QLineEdit(str(x[-1] if isinstance(x, (list, tuple)) else x))
                row(ed, "%s %d" % (tr(labels[key]), i + 2), ed)
                self.extra_eds.append((group, "", ed))
        self.ed_memo = QPlainTextEdit(card.get("memo") or "")
        self.ed_memo.setMinimumHeight(80)
        row("memo", tr(FD.MEMO_LABEL), self.ed_memo)
        v.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Save).setText(tr("저장"))
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("취소"))
        self.btn_clear_checked = bb.addButton(tr("체크한 칸 비우기"), QDialogButtonBox.ButtonRole.ActionRole)
        self.btn_clear_checked.setToolTip(tr("앞에 체크한 칸을 한꺼번에 비웁니다 — [저장] 해야 명함에 반영됩니다"))
        self.btn_clear_checked.clicked.connect(lambda _c=False: self.clear_checked())
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.resize(420, self.sizeHint().height())

    def clear_checked(self) -> int:
        """체크한 칸을 비우고 체크를 푼다(잘못된 병합으로 겹친 값을 여럿 지우기, 사용자 지시 261121). 반환 = 비운 칸 수."""
        n = 0
        for key, cb in self.checks.items():
            if not cb.isChecked():
                continue
            ed = self.ed_memo if key == "memo" else (self.eds.get(key) if isinstance(key, str) else key)
            if ed is not None:
                ed.clear()
                n += 1
            cb.setChecked(False)
        return n

    def values(self) -> dict:
        from viewer.widgets.bizcard_find_dialog import edited_fields
        from viewer.bizcard import phone as PH
        ex = {"phones": [], "emails": [], "urls": []}
        for group, kind, ed in self.extra_eds:
            t = ed.text().strip()
            if not t:
                continue                                   # 비운 칸 = 그 값을 지움
            if group == "phone":
                ex["phones"].append((kind, PH.normalize(t)))
            else:
                ex["emails" if group == "email" else "urls"].append(t)
        return edited_fields(self.card, {k: ed.text() for k, ed in self.eds.items()}, self.ed_memo.toPlainText(), extras=ex)

    def _ok(self):
        if not self.values()["name"]:
            QMessageBox.information(self, tr("명함 고치기"), tr("이름을 비울 수 없습니다."))
            return
        self.accept()


class PicturePickDialog(QDialog):
    """'명함 사진 삭제'(§5.24.8, 261120-65·-69) — 그 명함의 앞면·뒷면·인물 사진을 썸네일로, 체크한 것만 지운다."""

    def __init__(self, card, photos, parent=None):
        super().__init__(parent)
        from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QDialogButtonBox
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QIcon
        from viewer.widgets.bizcard_find_dialog import _scaled
        self.setWindowTitle(tr("명함 사진 삭제"))
        v = QVBoxLayout(self)
        v.addWidget(QLabel(tr("지울 사진을 체크하세요 — 앞면만 지우면 뒷면이 앞면이 되고, 앞·뒷면을 모두 지우면 원본 스캔까지 휴지통으로 보냅니다.")))
        self.lst = QListWidget()
        self.lst.setIconSize(QSize(120, 90))
        items = []
        for key, label in (("front", tr("명함 앞면")), ("back", tr("명함 뒷면"))):
            path = card.get(key) or ""
            if path and not V.is_contact(card) and os.path.exists(path):
                items.append((key, label, path))
        items += [(p, tr("인물 사진 {n}").format(n=i + 1), p) for i, p in enumerate(photos)]
        for key, label, path in items:
            it = QListWidgetItem(QIcon(_scaled(path, 120, 90)), label)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked)
            it.setData(Qt.ItemDataRole.UserRole, key)
            self.lst.addItem(it)
        v.addWidget(self.lst, 1)
        bb = QDialogButtonBox()
        self.btn_ok = bb.addButton(tr("지우기"), QDialogButtonBox.ButtonRole.AcceptRole)
        b_c = bb.addButton(tr("취소"), QDialogButtonBox.ButtonRole.RejectRole)
        for b in (self.btn_ok, b_c):
            b.setAutoDefault(False)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.resize(460, 420)

    def picks(self) -> list:
        return [self.lst.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.lst.count())
                if self.lst.item(i).checkState() == Qt.CheckState.Checked]


class _ImgWorker(QObject):
    """명함 그림 읽기(배경) — (세대, 큰 그림 세대, 줄 번호(-1 = 큰 그림), 경로, 그림). 명함찾기와 같은 축소 읽기 `_read`."""
    one = pyqtSignal(int, object, int, str, QImage)
    finished = pyqtSignal()

    def __init__(self, gen, big, jobs):
        super().__init__()
        self._gen, self._big, self._jobs = gen, big, list(jobs)

    def run(self):
        from viewer.widgets.bizcard_find_dialog import _read
        for i, path, w, h in self._jobs:
            try:
                im = _read(path, w, h)
            except Exception:
                im = QImage()
            self.one.emit(self._gen, self._big, i, path, im)
        self.finished.emit()


class _FnWorker(QObject):
    """함수 하나를 배경에서 — done(결과, 예외). 중복 검토의 DB 백업·쓰기·되돌리기(§5.24.8 '응답성')."""
    done = pyqtSignal(object, object)
    finished = pyqtSignal()

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            r, err = self._fn(), None
        except Exception as e:                  # noqa: BLE001 — 메인에서 알린다
            r, err = None, e
        self.done.emit(r, err)
        self.finished.emit()


def _copy_db(src, dst) -> None:
    """SQLite 온라인 백업 src → dst(자기 연결 — 배경 스레드에서 부른다)."""
    a = dbutil.connect(src, dbutil.BUSY_MS_BG, row_factory=False)
    b = dbutil.connect(dst, dbutil.BUSY_MS_BG, row_factory=False)
    try:
        a.backup(b)
    finally:
        b.close()
        a.close()


def _unique(folder: Path, name: str) -> Path:
    p, k = folder / name, 2
    stem, ext = os.path.splitext(name)
    while p.exists():
        p, k = folder / ("%s (%d)%s" % (stem, k, ext)), k + 1
    return p


class BizcardDupeDialog(QDialog):
    def __init__(self, find_dlg):
        super().__init__(find_dlg)
        self.fd = find_dlg
        self.setWindowTitle(tr("중복 검토"))
        self.resize(1100, 640)
        # 크게 보기(사용자 지시 261119) — 명함 관리 창과 같이 최대화 단추 + F11 전체 화면(Esc 로 돌아옴)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowMinimizeButtonHint)
        from PyQt6.QtGui import QShortcut, QKeySequence
        QShortcut(QKeySequence("F11"), self, activated=self.toggle_full)
        st = self.fd._store()
        self.bak = st.path.with_name(st.path.name + ".dupe_bak")
        self.log_path = st.path.with_suffix(".dupe_undo.json")
        self.groups, self.rep, self.chk, self.gchk = [], {}, {}, {}
        self.edits = {}                                  # {묶음: {칸: 값}} — '적용 후' 에서 고친 값
        self._busy = False
        self.working, self._bg_then = False, None        # 배경 DB 일(`_bg`) 중 — 창은 꺼져 있고 닫히지 않는다
        v = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel(tr("병합 우선순위(끌어 순서 바꾸기):")))
        self.order = QListWidget()
        self.order.setFlow(QListView.Flow.LeftToRight)
        self.order.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.order.setMaximumHeight(34)
        self.order.setToolTip(tr("왼쪽이 1순위 — 1순위에 있는 값은 그대로, 없는 칸만 다음 순위 값으로 채웁니다"))
        for s in P.dupe_order(st):
            it = QListWidgetItem(tr(SRC_LABEL[s]))
            it.setData(ROLE, s)
            self.order.addItem(it)
        self.order.model().rowsMoved.connect(lambda *a: self._order_changed())
        top.addWidget(self.order, 1)
        b_find = QPushButton(tr("다시 찾기"))
        b_find.clicked.connect(lambda _c=False: self.reload())
        top.addWidget(b_find)
        # 명함 SOT §5.26 '이미 들어간 명함'(사용자 지시 261119): 한 장으로 잘못 들어간 다중 명함 사진 찾기
        self.btn_multi = QPushButton(tr("다중 명함 찾기"))
        self.btn_multi.setToolTip(tr("이미 들어간 명함 중 한 사진에 명함이 여럿인 것(한 장으로 잘못 읽힌 것)을 찾아 명함마다 나눕니다"))
        self.btn_multi.clicked.connect(lambda _c=False: self.find_multi())
        top.addWidget(self.btn_multi)
        v.addLayout(top)

        split = QSplitter(Qt.Orientation.Horizontal)
        lw, rw = QWidget(), QWidget()
        lv, rv = QVBoxLayout(lw), QVBoxLayout(rw)
        lv.setContentsMargins(0, 0, 0, 0)
        rv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(QLabel(tr("적용 전 — 대표와 그 아래 유사한 명함(체크한 것만 합침)")))
        self.before = QTreeWidget()
        self.before.setHeaderLabels([tr("이름"), tr("회사"), tr("전화"), tr("메일"), tr("출처"), tr("이유")])
        self.before.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.before.customContextMenuRequested.connect(self._menu)
        self.before.itemChanged.connect(self._checked)
        lv.addWidget(self.before)
        rv.addWidget(QLabel(tr("적용 후 — 합친 결과(대표에서 바뀐 칸은 굵게)")))
        self.after = QTreeWidget()
        self.after.setHeaderLabels([tr("칸"), tr("값"), tr("출처")])
        self.after.setToolTip(tr("값을 두 번 눌러 고치면 그 값으로 합칩니다 — 전화·메일·누리집은 쉼표로 나눕니다"))
        self.after.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.after.itemDoubleClicked.connect(self._edit_start)
        self.after.itemChanged.connect(self._edited)
        rv.addWidget(self.after)
        split.addWidget(lw)
        split.addWidget(rw)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        # 아래: 고른 묶음의 명함 그림 — 썸네일 줄(여럿이면 골라) + 큰 그림 (사용자 지시 261119)
        #   명함찾기 사진창과 같은 꼴(위 큰 그림 + 아래 썸네일 한 줄, 같은 격자), 읽기는 같은 `_read` 를 배경에서(세대로 앞 읽기 버림)
        pw = QWidget()
        ph = QVBoxLayout(pw)
        ph.setContentsMargins(0, 0, 0, 0)
        self.big = QLabel(tr("(명함 그림 없음)"))
        self.big.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.big.setMinimumHeight(140)
        self.big_path = ""
        self.thumbs = QListWidget()
        self.thumbs.setViewMode(QListView.ViewMode.IconMode)
        self.thumbs.setFlow(QListView.Flow.LeftToRight)
        self.thumbs.setWrapping(False)
        self.thumbs.setMovement(QListView.Movement.Static)
        self.thumbs.setIconSize(QSize(THUMB, THUMB))
        self.thumbs.setGridSize(QSize(THUMB + 12, THUMB + 12))
        self.thumbs.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.thumbs.setFixedHeight(THUMB + 16 + self.thumbs.horizontalScrollBar().sizeHint().height())
        self.thumbs.currentItemChanged.connect(lambda cur, _p: self._show_big(cur.data(ROLE) if cur else ""))
        self._img_gen = 0
        self.imgs_pending = 0
        ph.addWidget(self.big, 1)
        ph.addWidget(self.thumbs)
        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.addWidget(split)
        vsplit.addWidget(pw)
        vsplit.setStretchFactor(0, 3)
        vsplit.setStretchFactor(1, 2)
        v.addWidget(vsplit, 1)
        self.before.currentItemChanged.connect(lambda cur, _p: (self._sync(cur, self.after), self._preview(cur)))
        self.after.currentItemChanged.connect(lambda cur, _p: (self._sync(cur, self.before), self._preview(cur)))

        bot = QHBoxLayout()
        self.lbl = QLabel()
        bot.addWidget(self.lbl, 1)
        self.btn_apply = QPushButton(tr("적용"))   # 미리보기 → [적용] 공통(디자인 SOT §2.7, 261120-69)
        self.btn_apply.clicked.connect(lambda _c=False: self.apply())
        self.btn_undo = QPushButton(tr("마지막 합치기 되돌리기"))
        self.btn_undo.clicked.connect(lambda _c=False: self.undo())
        b_close = QPushButton(tr("닫기"))
        b_close.clicked.connect(lambda _c=False: self.accept())
        bot.insertWidget(0, self.btn_undo)                    # 되돌리기는 왼쪽에 떼고 [적용][닫기]는 오른쪽 끝(디자인 SOT §2.7, 261120-78)
        for b in (self.btn_apply, b_close):
            bot.addWidget(b)
        v.addLayout(bot)
        for b in self.findChildren(QPushButton):          # Enter 가 칸 고치기를 마치지 않고 단추를 누르지 않게 — 아래 줄을 붙인
            b.setAutoDefault(False)                       # 뒤에(그 전엔 아래 줄 단추가 창의 자식이 아니라 빠져 [적용] 이 기본 단추였다, 261120-69)
            b.setDefault(False)
        self.reload()

    # ── 묶음 ──
    def order_keys(self) -> list:
        return [self.order.item(i).data(ROLE) for i in range(self.order.count())]

    def _order_changed(self):
        self.fd._store().meta_set(P.DUPE_ORDER_KEY, self.order_keys())
        self.reload()

    def set_order(self, keys):
        """출처 순서를 정함(검사·끌기와 같은 결과)."""
        self.order.clear()
        for s in keys:
            it = QListWidgetItem(tr(SRC_LABEL[s]))
            it.setData(ROLE, s)
            self.order.addItem(it)
        self._order_changed()

    def reload(self):
        self.groups = P.dupe_groups(self.fd._store(), self.order_keys())
        self.rep, self.chk, self.gchk, self.edits = {}, {}, {}, {}
        for gi, g in enumerate(self.groups):
            rep = g["cards"][0]["id"]
            self.rep[gi] = rep
            for c in g["cards"][1:]:
                self.chk[(gi, c["id"])] = g["sure_root"][c["id"]] == g["sure_root"][rep]
            self.gchk[gi] = any(self.chk[(gi, c["id"])] for c in g["cards"][1:])
        self.fill()
        self.btn_undo.setEnabled(self.log_path.exists() and self.bak.exists())

    def group_cards(self, gi) -> list:
        """대표 먼저, 나머지는 묶음 차례(출처 순서) — 체크 안 한 것은 뺌."""
        g = self.groups[gi]
        rep = next(c for c in g["cards"] if c["id"] == self.rep[gi])
        return [rep] + [c for c in g["cards"] if c["id"] != rep["id"] and self.chk.get((gi, c["id"]))]

    def plan(self, gi):
        cards = self.group_cards(gi)
        if not (self.gchk.get(gi) and len(cards) >= 2):
            return None
        p = P.merge_plan(cards, self.groups[gi].get("manual"))
        for k, v in (self.edits.get(gi) or {}).items():   # '적용 후' 에서 손으로 고친 값이 이긴다(§5.24.8 '고치기')
            p["fields"][k] = v
            p["frm"].pop(k, None)                          # 출처 없음 = 손으로 고친 칸(주소록이 덮지 않음, D24)
        edited = self.edits.get(gi) or {}
        if ("name" in edited or "company" in edited) and "tags" not in edited:   # 고친 이름·회사로 자동 태그도(261120-53)
            p["fields"]["tags"] = P.auto_retag(p["fields"]["tags"], cards, p["fields"].get("name") or "",
                                               p["fields"].get("company") or "")[0]
        return p

    def fill(self):
        self._busy = True
        self.before.clear()
        for gi, g in enumerate(self.groups):
            cards = [next(c for c in g["cards"] if c["id"] == self.rep[gi])] + [c for c in g["cards"] if c["id"] != self.rep[gi]]
            top = None
            for c in cards:
                is_rep = c["id"] == self.rep[gi]
                cols = [c.get("name") or "", c.get("company") or "", _phone(c), ", ".join(c.get("emails") or []),
                        tr(SRC_LABEL[g["src"][c["id"]]]), tr("대표") if is_rep else tr(WHY_LABEL[g["why"][c["id"]]])]
                it = QTreeWidgetItem(cols)
                it.setData(0, ROLE, (gi, c["id"]))
                mk = (g.get("match") or {}).get(c["id"])
                if mk:                                     # 어느 휴대폰으로 묶였는지(§5.24.8 '묶기', 261120-55 — 이 PC 화면에만)
                    from viewer.bizcard import phone as PH
                    it.setToolTip(len(cols) - 1, tr("묶인 휴대폰: {n}").format(n=PH.format_kr(mk) or mk))
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                if is_rep:
                    it.setCheckState(0, Qt.CheckState.Checked if self.gchk[gi] else Qt.CheckState.Unchecked)
                    f = it.font(0)
                    f.setBold(True)
                    it.setFont(0, f)
                    self.before.addTopLevelItem(it)
                    top = it
                else:
                    it.setCheckState(0, Qt.CheckState.Checked if self.chk[(gi, c["id"])] else Qt.CheckState.Unchecked)
                    top.addChild(it)
            top.setExpanded(True)
        for i in range(self.before.columnCount()):
            self.before.resizeColumnToContents(i)
        self._busy = False
        self.fill_after()

    def fill_after(self):
        self._busy = True
        try:
            self._fill_after()
        finally:
            self._busy = False

    def _fill_after(self):
        self.after.clear()
        n_g = n_d = 0
        for gi, g in enumerate(self.groups):
            p = self.plan(gi)
            rep = next(c for c in g["cards"] if c["id"] == self.rep[gi])
            top = QTreeWidgetItem([rep.get("name") or "", "", ""])
            top.setData(0, ROLE, (gi, None))
            self.after.addTopLevelItem(top)
            if p is None:
                top.setText(1, tr("(합치지 않음)"))
                top.setForeground(1, self.palette().placeholderText())
                continue
            n_g += 1
            n_d += len(p["drop"])
            top.setText(0, p["fields"]["name"])
            top.setText(1, p["fields"]["company"])
            top.setText(2, tr(SRC_LABEL[g["src"][p["keeper"]]]))
            mine = self.edits.get(gi) or {}
            for k, label in SHOW:                          # 빈 칸도 보인다 — 고쳐 채울 수 있게
                val = _val(p["fields"], k)
                frm = p["frm"].get(k)
                src = tr("직접") if k in mine else (tr(SRC_LABEL[g["src"][frm]]) if frm else
                                                   (tr("모두") if val and k in ("phones", "emails", "urls", "memo") else ""))
                it = QTreeWidgetItem([tr(label), val.replace("\n", " ⏎ "), src])
                it.setData(0, ROLE, (gi, k))
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsEditable)
                if val != _val(rep, k) or k in mine:
                    f = it.font(1)
                    f.setBold(True)
                    it.setFont(1, f)
                top.addChild(it)
            top.setExpanded(True)
        for i in range(self.after.columnCount()):
            self.after.resizeColumnToContents(i)
        self.lbl.setText(tr("묶음 {g}개 · 합칠 묶음 {n}개 · 지울 명함 {d}장").format(g=len(self.groups), n=n_g, d=n_d))
        self.btn_apply.setEnabled(n_g > 0)

    # ── '적용 후' 값 고치기 (§5.24.8 '고치기', 사용자 지시 261119) ──
    def _edit_start(self, it, col):
        d = it.data(0, ROLE)
        if it.parent() is None or not d or not isinstance(d[1], str):
            return
        self._busy = True
        it.setText(1, _val(self.plan(d[0])["fields"], d[1]))       # 고칠 때는 여러 줄 메모도 원래 글로
        self._busy = False
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self.after.editItem(it, 1))   # 누름으로 바뀐 고른 줄·사진 정리가 끝난 뒤에 연다

    def _edited(self, it, col):
        if self._busy or col != 1 or it.parent() is None:
            return
        gi, k = it.data(0, ROLE)
        self.set_edit(gi, k, it.text(1))

    def set_edit(self, gi, k, text):
        """묶음 gi 의 칸 k 를 text 로(전화·메일·누리집은 쉼표로 나눔, 메모의 ' ⏎ ' 는 줄바꿈)."""
        g = self.groups[gi]
        text = (text or "").replace(" ⏎ ", "\n").strip()
        if k == "phones":
            kinds = {}
            for c in g["cards"]:
                for kind, num in c.get("phones") or []:
                    kinds.setdefault(P._phone_key(num) or num, kind)
            val = []
            for num in [x.strip() for x in text.split(",") if x.strip()]:
                key = P._phone_key(num) or num
                val.append((kinds.get(key) or ("cell" if key.startswith(P.MOBILE_PREFIX) else "work"), num))
        elif k in ("emails", "urls"):
            val = [x.strip() for x in text.split(",") if x.strip()]
        else:
            val = text
        self.edits.setdefault(gi, {})[k] = val
        self.fill_after()

    def _checked(self, it, col):
        if self._busy or col != 0:
            return
        gi, cid = it.data(0, ROLE)
        on = it.checkState(0) == Qt.CheckState.Checked
        if cid == self.rep[gi]:
            self.gchk[gi] = on
        else:
            self.chk[(gi, cid)] = on
        self.fill_after()

    def _sync(self, cur, other):
        if cur is None:
            return
        while cur.parent() is not None:
            cur = cur.parent()
        gi = cur.data(0, ROLE)[0]
        top = other.topLevelItem(gi)
        if top is not None and other.currentItem() is not top and (other.currentItem() is None
                                                                   or self._top_gi(other.currentItem()) != gi):
            other.setCurrentItem(top)

    # ── 명함 그림 (§5.24.8 '명함 그림') ──
    def _preview(self, cur):
        """고른 줄의 묶음 — 그림 명함의 앞·뒷면을 썸네일 줄에, 고른 명함의 앞면을 크게. 그림이 없으면 글만."""
        self.thumbs.blockSignals(True)
        self.thumbs.clear()
        self.thumbs.blockSignals(False)
        if cur is None:
            self._show_big("")
            return
        gi, cid = cur.data(0, ROLE)
        if not isinstance(cid, int) or cid not in {c["id"] for c in self.groups[gi]["cards"]}:
            p = self.plan(gi)
            cid = p["keeper"] if p else self.rep[gi]
        pick, jobs = None, []
        self.thumbs.blockSignals(True)
        for c in self.group_cards_all(gi):
            if V.is_contact(c):
                continue
            for side in (c.get("front"), c.get("back")):
                if not side or not os.path.exists(side):
                    continue
                it = QListWidgetItem(c.get("name") or "")
                it.setData(ROLE, side)
                jobs.append((self.thumbs.count(), side, THUMB, THUMB))
                it.setToolTip(os.path.basename(side))
                self.thumbs.addItem(it)
                if pick is None and c["id"] == cid:
                    pick = it
        self.thumbs.blockSignals(False)
        self._img_gen += 1
        self._load_imgs(jobs)
        pick = pick or self.thumbs.item(0)
        if pick is not None:
            self.thumbs.blockSignals(True)
            self.thumbs.setCurrentItem(pick)
            self.thumbs.blockSignals(False)
        self._show_big(pick.data(ROLE) if pick is not None else "")

    def group_cards_all(self, gi) -> list:
        g = self.groups[gi]
        return [next(c for c in g["cards"] if c["id"] == self.rep[gi])] + [c for c in g["cards"] if c["id"] != self.rep[gi]]

    def _show_big(self, path):
        self.big_path = path or ""
        self._big_gen = getattr(self, "_big_gen", 0) + 1
        if not path:
            self.big.setPixmap(QPixmap())
            self.big.setText(tr("(명함 그림 없음)"))
            return
        self._load_imgs([(-1, path, max(200, self.big.width()), max(120, self.big.height()))], big=self._big_gen)

    def _load_imgs(self, jobs, big=None):
        """그림 읽기는 배경(응답성 SOT) — 명함찾기와 같은 `_read`(축소 읽기). 세대가 바뀌면 늦게 온 그림은 버린다."""
        if not jobs:
            return
        from viewer.workers import run_in_thread
        w = _ImgWorker(self._img_gen, big, jobs)
        w.one.connect(self._img_ready)
        self.imgs_pending += len(jobs)
        keep = getattr(self.fd._mw, "_thread_keep", None) if self.fd._mw is not None else None
        run_in_thread(w, keep if isinstance(keep, list) else _KEEP)

    def _img_ready(self, gen, big, i, path, img):
        self.imgs_pending = max(0, self.imgs_pending - 1)
        if img.isNull():
            return
        if i < 0:
            if big == getattr(self, "_big_gen", 0) and path == self.big_path:
                self.big.setPixmap(QPixmap.fromImage(img).scaled(max(200, self.big.width()), max(120, self.big.height()),
                                   Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            return
        it = self.thumbs.item(i) if gen == self._img_gen else None  # noqa: E501
        if it is not None and it.data(ROLE) == path:
            it.setIcon(QIcon(QPixmap.fromImage(img).scaled(THUMB, THUMB, Qt.AspectRatioMode.KeepAspectRatio,
                                                            Qt.TransformationMode.SmoothTransformation)))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.big_path:
            self._show_big(self.big_path)

    @staticmethod
    def _top_gi(it):
        while it.parent() is not None:
            it = it.parent()
        return it.data(0, ROLE)[0]

    def set_rep(self, gi, cid):
        """묶음의 대표를 바꿈(오른쪽 메뉴 '대표로') — 옛 대표는 체크한 유사 명함으로."""
        old = self.rep[gi]
        if old == cid:
            return
        self.chk.pop((gi, cid), None)
        self.chk[(gi, old)] = True
        self.rep[gi] = cid
        self.gchk[gi] = True
        self.fill()

    def _menu(self, pos):
        it = self.before.itemAt(pos)
        if it is None:
            return
        gi, cid = it.data(0, ROLE)
        m = QMenu(self)
        if it.parent() is not None:
            m.addAction(tr("대표로"), lambda: self.set_rep(gi, cid))
        m.addAction(tr("명함 고치기"), lambda: self.edit_card(gi, cid))   # 그 명함 자체(§5.24.8 '명함 고치기')
        c = next((x for x in self.groups[gi]["cards"] if x["id"] == cid), None)
        if c is not None and (not V.is_contact(c) or self.fd._photo_front(c) and P.person_photos(self.fd._photo_front(c))):
            m.addAction(tr("명함 사진 삭제"), lambda: self.delete_pictures(cid))   # 고른 앞면·뒷면·인물 사진만(§5.24.8, 261120-65)
        self._last_menu = m
        m.exec(self.before.viewport().mapToGlobal(pos))

    def edit_card(self, gi, cid, dlg=None) -> bool:
        """'적용 전' 명함 하나를 고쳐 명함 DB 에 — 명함찾기 [저장] 과 같은 길(`store_card_edit`). 묶음은 그대로, 그 줄·합친 결과만 새로.
        dlg = 검사용(이미 값을 넣은 CardEditDialog — 실행하지 않고 그 값으로)."""
        g = self.groups[gi]
        c = next((x for x in g["cards"] if x["id"] == cid), None)
        if c is None:
            return False
        if dlg is None:
            dlg = CardEditDialog(c, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return False
        fields = self.fd.store_card_edit(c, dlg.values())
        if fields is None:
            return False
        self.reload()                                    # 고친 값으로 다시 묶는다 — 지운 번호로 이어졌던 명함은 빠진다(사용자 결정 261121)
        if not getattr(self.fd, "_dirty", False):
            self.fd.refresh()                            # 명함찾기 목록도 고친 값으로(보던 고침이 있으면 건드리지 않음)
        return True

    def detach_image(self, cid, ask: bool = True) -> bool:
        """'명함 그림 떼기'(§5.24.8, 사용자 결정 261121) — 잘못 붙은 다른 사람의 명함 그림만 뗀다: 정리본 앞·뒷면을 휴지통으로,
        이 명함은 그림 없는 명함(연락처·메모·태그 그대로), 인물 사진은 새 자리로 옮김. 원본 스캔은 그대로라 명함 관리에서 다시 읽을 수 있다."""
        c = P.card_by_id(self.fd._store(), cid)
        if not c or V.is_contact(c) or self.working:
            return False
        if ask and QMessageBox.question(self, tr("중복 검토"), tr(
                "'{n}' 에 붙은 명함 그림(정리본 앞·뒷면)을 휴지통으로 보내고 그림 없는 명함으로 둡니다 — 연락처·메모는 그대로, "
                "원본 스캔은 남아 명함 관리에서 다시 읽을 수 있습니다.").format(n=c.get("name") or "")) != QMessageBox.StandardButton.Yes:
            return False
        ok = self.fd.detach_card_image(c, originals=True)   # 앞·뒷면 모두 — 원본 스캔도(사용자 결정 261121, 261120-65)
        self.reload()
        return ok

    def delete_pictures(self, cid, ask: bool = True) -> bool:
        """'명함 사진 삭제'(§5.24.8, 261120-65·-69) — 창에서 고른 앞면·뒷면·인물 사진만 휴지통으로, 지운 뒤 다시 묶는다."""
        c = P.card_by_id(self.fd._store(), cid)
        if not c or self.working:
            return False
        pf = self.fd._photo_front(c)
        dlg = PicturePickDialog(c, P.person_photos(pf) if pf else [], self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return False
        picks = dlg.picks()
        if not picks:
            return False
        if ask and QMessageBox.question(self, tr("중복 검토"), tr("고른 사진 {n}개를 휴지통으로 보냅니다.").format(n=len(picks))) \
                != QMessageBox.StandardButton.Yes:
            return False
        ok = self.fd.delete_card_pictures(c, picks)
        self.reload()
        return ok

    def toggle_full(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.toggle_full()                          # 전체 화면에서 Esc 는 창을 닫지 않고 돌아온다
            return
        super().keyPressEvent(e)

    # ── 이미 들어간 다중 명함 사진 (§5.26 '이미 들어간 명함') ──
    def multi_targets(self) -> dict:
        """{셀 사진: (명함 행, 잘라낸 것을 둘 폴더)} — 원본 그림이 있으면 원본(그 옆), 없으면 정리본(정리 폴더 위 = 원천 폴더)."""
        from viewer.bizcard import multisplit as M
        out = {}
        for r in self.fd._store().con.execute("SELECT * FROM cards").fetchall():
            c = self.fd._store()._row(r)
            if V.is_contact(c):
                continue
            src = P._real(c.get("src_key") or "")
            if src and os.path.isfile(src) and Path(src).suffix.lower() in M.img_exts() \
                    and Path(src).parent.name != M.MULTI_DIR:
                out[src] = (c, None)
                continue
            f = P._real(c.get("front") or "")
            if f and os.path.isfile(f):
                out[f] = (c, str(Path(f).parent.parent))
        return out

    def find_multi(self, ask: bool = True):
        """[다중 명함 찾기] — 이미 들어간 그림 명함의 사진을 배경에서 세어(이미 센 것은 건너뜀) 여럿이면 확인 창.
        세는 동안 단추는 [멈춤](중간 취소), 글로 'n / m' 진행."""
        if getattr(self, "_mw_multi", None) is not None and not self._mw_multi.done_event.is_set():
            self._mw_multi.request_cancel()            # 두 번째 누름 = 멈춤
            return None
        from viewer.bizcard.importer import MultiWorker
        from viewer.workers import run_in_thread
        self._multi_targets = self.multi_targets()
        self.multi_found = []
        self._multi_ask = ask
        w = MultiWorker(list(self._multi_targets), self.fd._db)
        self._mw_multi = w
        self.btn_multi.setText(tr("멈춤"))
        self.lbl.setText(tr("다중 명함 찾는 중 — 사진 {n}장").format(n=len(self._multi_targets)))
        w.found.connect(lambda p, q, pv: self.multi_found.append((p, q, pv)))
        w.progressed.connect(lambda d, t: self.lbl.setText(tr("다중 명함 찾는 중 {d} / {t}").format(d=d, t=t)))
        w.finishedAll.connect(self._multi_counted)
        keep = getattr(self.fd._mw, "_thread_keep", None) if self.fd._mw is not None else None
        run_in_thread(w, keep if isinstance(keep, list) else _KEEP)
        return w

    def _multi_counted(self, ok):
        self.btn_multi.setText(tr("다중 명함 찾기"))
        self.fill_after()
        if not ok:
            return
        if not self.multi_found:
            if self._multi_ask:
                QMessageBox.information(self, tr("다중 명함 찾기"), tr("한 사진에 명함이 여럿인 것을 찾지 못했습니다."))
            return
        from viewer.widgets.bizcard_multi_dialog import MultiSplitDialog
        dlg = MultiSplitDialog(self.multi_found, self, old_counts={p: 1 for p, _q, _v in self.multi_found})
        self.multi_dlg = dlg
        dlg.finished.connect(lambda _r: self._multi_chosen(dlg))
        dlg.open()

    def _multi_chosen(self, dlg):
        from viewer.bizcard import multisplit as M
        from viewer.bizcard.store import source_sig
        st = self.fd._store()
        if dlg.skipped:
            seen = dict(st.meta_get(M.SEEN_KEY) or {})
            for p in dlg.skipped:
                seen[os.path.normcase(os.path.abspath(p))] = source_sig([p])
            st.meta_set(M.SEEN_KEY, seen)
        if not dlg.jobs:
            return
        if self.working:
            return
        self._drop_old_hold()                           # 되돌리기는 마지막 하나 — 합치기와 같은 길(§5.24.8 '되돌리기')
        dbp, bak = st.path, self.bak
        jobs = [(p, q, self._multi_targets[p][1]) for p, q in dlg.jobs]
        self._bg(lambda: _copy_db(dbp, bak), lambda _r: self._multi_split_start(jobs))   # 예전 명함을 지우기 전 DB 백업

    def _multi_split_start(self, jobs):
        from viewer.bizcard.importer import SplitWorker
        from viewer.workers import run_in_thread
        self._bg_end()
        w = SplitWorker(jobs)
        self._split_worker = w
        w.done.connect(self._multi_split_done)
        keep = getattr(self.fd._mw, "_thread_keep", None) if self.fd._mw is not None else None
        run_in_thread(w, keep if isinstance(keep, list) else _KEEP)

    def _multi_split_done(self, out):
        """나눴으면 예전 한 장짜리 명함은 지우고(정리본·인물 사진 휴지통, D31) 묶음을 다시 — 잘라낸 것은 명함 관리로 읽는다."""
        st = self.fd._store()
        self.multi_split = {p: made for p, made in out.items() if made}
        moves = list(getattr(self._split_worker, "moved", []))
        folders = []
        for p in self.multi_split:
            c, outd = self._multi_targets[p]
            ok = True
            for f in [x for grp in P.card_files(c)[1:] for x in grp if os.path.exists(x)]:   # 정리본·인물 사진 → '병합 보관'(되돌리기)
                hd = P.hold_dir(f)
                try:
                    hd.mkdir(parents=True, exist_ok=True)
                except OSError:
                    ok = False
                    continue
                to = str(_unique(hd, os.path.basename(f)))
                if self.fd._rename(f, to, quiet=True):
                    moves.append((f, to))
                else:
                    ok = False
            if not ok:
                continue
            if c.get("src_key"):
                st.delete_src(c["src_key"])
            else:
                st.delete_card(c["id"])
            folders.append(outd or str(Path(p).parent))
        made = [x for v in self.multi_split.values() for x in v]
        with open(self.log_path, "w", encoding="utf-8") as fp:
            json.dump({"moves": moves, "made": made}, fp, ensure_ascii=False)
        self.reload()
        if folders and self.fd._mw is not None and hasattr(self.fd._mw, "_action_bizcard_import") and (
                not self._multi_ask or QMessageBox.question(
                    self, tr("다중 명함 찾기"),
                    tr("명함 {n}장으로 나눴습니다 — 명함 관리를 열어 읽을까요?").format(
                        n=sum(len(v) for v in self.multi_split.values()))) == QMessageBox.StandardButton.Yes):
            from PyQt6.QtCore import QTimer
            mw, f = self.fd._mw, folders[0]
            self.accept()                              # 이 창(모달)을 닫아야 명함 관리 창을 쓸 수 있다
            QTimer.singleShot(0, lambda: mw._action_bizcard_import(f))

    # ── 적용·되돌리기 ──
    def apply(self, ask: bool = True) -> int:
        plans = [(gi, p) for gi, p in ((gi, self.plan(gi)) for gi in range(len(self.groups))) if p]
        if not plans:
            return 0
        n_d = sum(len(p["drop"]) for _gi, p in plans)
        if ask and QMessageBox.question(
                self, tr("중복 검토"),
                tr("묶음 {n}개를 합칩니다 — 대표가 아닌 명함 {d}장은 지웁니다(그림 파일은 '병합 보관' 폴더로). [마지막 합치기 되돌리기] 로 되돌릴 수 있습니다.").format(
                    n=len(plans), d=n_d)) != QMessageBox.StandardButton.Yes:
            return 0
        if self.working:
            return 0
        st = self.fd._store()
        self._drop_old_hold()
        dbp, bak = st.path, self.bak
        self._bg(lambda: _copy_db(dbp, bak), lambda _r: self._apply(st, plans, ask))   # 적용 전 DB 백업(되돌리기)
        return len(plans)                                     # 끝은 배경 쓰기 뒤 `_applied` — 그동안 `working`

    def _apply(self, st, plans, ask) -> None:
        dbp = st.path
        moves, failed, jobs = [], 0, []
        for gi, p in plans:
            byid = {c["id"]: c for c in self.groups[gi]["cards"]}
            keeper = byid[p["keeper"]]
            if p["photo_from"] is not None:                   # 남길 행에 인물 사진이 없으면 옮긴다
                for ph in P.person_photos(P._real(byid[p["photo_from"]]["front"])):
                    to = str(P.next_photo_path(keeper["front"]))
                    if self.fd._rename(ph, to, quiet=True):
                        moves.append((ph, to))
                    else:
                        failed += 1
            extra = {}
            if not V.is_contact(keeper):
                got = self.fd.rename_card_files(keeper, p["fields"]["name"], p["fields"]["company"], moves)
                if got and got != (keeper["front"], keeper.get("back") or ""):
                    extra = {"front": got[0], "back": got[1]}
            for cid in p["drop"]:
                c = byid[cid]
                if V.is_contact(c):
                    continue
                hd = P.hold_dir(P._real(c["front"]))
                for f in [x for grp in P.card_files(c) for x in grp]:
                    try:
                        hd.mkdir(parents=True, exist_ok=True)
                    except OSError:
                        failed += 1
                        continue
                    to = str(_unique(hd, os.path.basename(f)))
                    if self.fd._rename(f, to, quiet=True):
                        moves.append((f, to))
                    else:
                        failed += 1
            jobs.append((p, extra))
            nf = extra.get("front") or keeper["front"]
            nb = extra.get("back", keeper.get("back") or "")
            paths = [x for x in (nf, nb) if x and os.path.exists(x)]
            if paths:
                old_auto = P.auto_retag(p["fields"]["tags"], list(byid.values()), p["fields"].get("name") or "",
                                        p["fields"].get("company") or "")[1]   # 합친 명함들의 옛 회사 태그를 파일에서도 걷음(261120-53)
                self.fd._retag(paths, old_auto, p["fields"]["tags"])
        log = self.log_path

        def write():                                          # 명함 DB 쓰기·되돌리기 기록 — 배경, 자기 연결로
            from viewer.bizcard.store import BizcardStore
            s2 = BizcardStore(dbp)
            try:
                for p, extra in jobs:
                    P.merge_db(s2, p, extra)
            finally:
                s2.close()
            with open(log, "w", encoding="utf-8") as fp:
                json.dump({"moves": moves}, fp, ensure_ascii=False)
        self.last_failed = failed
        self._bg(write, lambda _r: self._applied(failed, ask))

    def _applied(self, failed, ask):
        self._bg_end()
        if failed and ask:
            QMessageBox.warning(self, tr("중복 검토"), tr("파일 {n}개를 옮기지 못했습니다 — 다른 프로그램이 열고 있는지 확인하세요.").format(n=failed))
        self.reload()

    def _drop_old_hold(self):
        """앞 합치기의 '병합 보관' 파일은 휴지통으로, 앞 백업·기록은 지운다(되돌리기는 하나만)."""
        if self.log_path.exists():
            try:
                moves = json.load(open(self.log_path, encoding="utf-8")).get("moves") or []
            except (OSError, ValueError):
                moves = []
            held = [b for _a, b in moves if os.path.exists(b) and Path(b).parent.name == P.HOLD_DIR]
            if held:
                from viewer.widgets.bizcard_import_dialog import trash_paths
                trash_paths(self, self.fd._mw, held)
        for f in (self.log_path, self.bak):
            try:
                f.unlink()
            except OSError:
                pass

    def undo(self, ask: bool = True) -> bool:
        if self.working or not (self.log_path.exists() and self.bak.exists()):
            return False
        if ask and QMessageBox.question(self, tr("중복 검토"), tr("마지막 합치기를 되돌립니다 — 옮긴 파일을 제자리로, 명함 DB 를 합치기 전으로.")) \
                != QMessageBox.StandardButton.Yes:
            return False
        try:
            log_ = json.load(open(self.log_path, encoding="utf-8"))
        except (OSError, ValueError):
            log_ = {}
        moves = log_.get("moves") or []
        made = [x for x in (log_.get("made") or []) if os.path.exists(x)]
        if made:                                          # 다중 명함 나누기(§5.26)로 만든 그림은 휴지통으로
            from viewer.widgets.bizcard_import_dialog import trash_paths
            trash_paths(self, self.fd._mw, made)
        for a, b in reversed(moves):
            if os.path.exists(b) and not os.path.exists(a):
                try:
                    Path(a).parent.mkdir(parents=True, exist_ok=True)
                except OSError:
                    pass
                self.fd._rename(b, a, quiet=True)
        dbp, bak, log = self.fd._store().path, self.bak, self.log_path

        def restore():                                        # 백업 → 명함 DB — 배경(응답성 SOT)
            _copy_db(bak, dbp)
            for f in (log, bak):
                try:
                    f.unlink()
                except OSError:
                    pass
        self._bg(restore, lambda _r: (self._bg_end(), self.reload()))
        return True                                       # 끝은 배경 복사 뒤 — 그동안 `working`

    def _bg(self, fn, then):
        """배경 스레드에서 fn, 끝나면 메인에서 then(결과) — 신호로 잇고 지역 루프로 기다리지 않는다(응답성 SOT §6 금지 목록).
        그동안 `working` 이고 창은 꺼져 있으며 닫히지 않는다. then 이 `_bg_end` 를 부른다. 실패하면 알리고 창을 켠다."""
        from viewer.workers import run_in_thread
        self.working, self._bg_then = True, then
        self.setEnabled(False)
        w = _FnWorker(fn)
        w.done.connect(self._bg_done)
        keep = getattr(self.fd._mw, "_thread_keep", None) if self.fd._mw is not None else None
        run_in_thread(w, keep if isinstance(keep, list) else _KEEP)

    def _bg_done(self, r, err):
        then, self._bg_then = self._bg_then, None
        if err is not None:
            self._bg_end()
            QMessageBox.warning(self, tr("중복 검토"), tr("명함 DB 를 쓰지 못했습니다({err}).").format(err=type(err).__name__))
            self.reload()
            return
        if then is not None:
            try:
                then(r)
            except Exception as e:              # noqa: BLE001 — 뒤이은 일(파일 옮기기 등)이 실패해도 창이 꺼진 채 남지 않게
                self._bg_end()
                QMessageBox.warning(self, tr("중복 검토"), tr("명함 DB 를 쓰지 못했습니다({err}).").format(err=type(e).__name__))
                self.reload()

    def _bg_end(self):
        self.working = False
        self.setEnabled(True)

    def reject(self):
        if self.working:                                  # 배경 DB 일이 끝나기 전엔 닫지 않는다(Esc 포함)
            return
        super().reject()

    def closeEvent(self, e):
        if self.working:
            e.ignore()
            return
        super().closeEvent(e)
