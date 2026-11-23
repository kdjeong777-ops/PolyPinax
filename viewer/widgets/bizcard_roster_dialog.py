"""명단 관리 창 (명함 SOT §5.32, 261122-1·-2) — 명함이 있든 없든 모든 명단, 010 둘 이상, vcf 비교, 나누기.

계산은 Qt 없는 `viewer.bizcard.roster`·`people.split_card`. 고치기·지우기·사진 지우기는 명함찾기와 같은 길(`store_card_edit`·
`delete_cards`·`delete_card_pictures`), 파일 옮김은 앱 이름 바꾸기 한 길(`_rename`). 목록·vcf 읽기는 배경(`_RosterWorker`).
★ 명함 글·경로는 로그·예외 메시지에 싣지 않는다(§2.1). 받은 vcf 는 읽기만(복사하지 않음). 모두 이 PC 안.
"""
from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import Qt, QSize, QObject, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QListView, QPushButton,
    QSplitter, QTreeWidget, QTreeWidgetItem, QMessageBox, QMenu, QComboBox, QLineEdit, QCheckBox, QFileDialog, QFormLayout,
    QDialogButtonBox, QWidget)

from viewer.i18n import tr, tr_noop
from viewer.bizcard import people as P
from viewer.bizcard import roster as RS
from viewer.bizcard import vcard as V

ROLE = Qt.ItemDataRole.UserRole
THUMB = 96
VIEWS = (("all", tr_noop("전체")), ("multi", tr_noop("010 둘 이상")), ("many", tr_noop("명함 3장 이상")), ("vcf", tr_noop("vcf 비교")))
MANY_WHY = {"name": tr_noop("이름 같음 {n}장"), "010": tr_noop("010 같음 {n}장")}   # '명함 3장 이상' 이유 칸(§5.32, 261122-5)
KIND_LABEL = {RS.MERGED: tr_noop("잘못 합쳐짐?"), RS.RENAMED: tr_noop("이름 바뀜?"), RS.NEW: tr_noop("새 사람"),
              RS.SAME_NAME: tr_noop("같은 이름·번호 다름")}
_KEEP = []


def _other_phones(c) -> str:
    keys = set(P.mobiles_010(c))
    from viewer.bizcard import phone as PH
    return ", ".join(n for k, n in (tuple(x) for x in c.get("phones") or [])
                     if (PH.mobile_key(k, n) or "") not in keys)


def _m010(c) -> str:
    from viewer.bizcard import phone as PH
    return ", ".join(PH.format_kr(k) or k for k in P.mobiles_010(c))


class _RosterWorker(QObject):
    """목록 읽기·vcf 읽기·비교(배경, 자기 연결) — done(세대, 결과 dict)."""
    done = pyqtSignal(int, object)
    finished = pyqtSignal()

    def __init__(self, gen, db, mode, text, vcf_path, persons, show_new, frozen=None):
        super().__init__()
        self._a = (gen, db, mode, text, vcf_path, persons, show_new, frozen)

    def run(self):
        gen, db, mode, text, vcf_path, persons, show_new, frozen = self._a
        out = {"mode": mode, "cards": [], "groups": [], "persons": persons, "error": "", "frozen": None}
        stage = "db"
        try:
            import sqlite3
            from viewer.bizcard.store import BizcardStore
            st = BizcardStore(db)
            try:
                cards = RS.all_cards(st)
            finally:
                st.close()
            if mode == "vcf":
                if frozen is None:                       # 처음(또는 [새로 비교]) — 한 번 견줘 작업 목록으로 고정(261122-4)
                    stage = "vcf"
                    if persons is None and vcf_path:
                        persons = RS.read_vcf(vcf_path)
                        out["persons"] = persons
                    stage = "compare"
                    frozen = RS.freeze(RS.vcf_compare(cards, persons or [], show_new=True))
                    out["frozen"] = frozen
                stage = "status"
                by_id = {c["id"]: c for c in cards}
                groups = []
                for gi, g in enumerate(frozen):           # 고정한 목록 그대로 — 줄은 사라지지 않고 상태만(지운 명단은 '(지움)')
                    subs = []
                    for s in g["subs"]:
                        c = by_id.get(s["id"])
                        subs.append({"card": c if c is not None else {"id": s["id"], "name": s.get("name") or "", "phones": [],
                                                                       "emails": [], "front": "contact:gone", "_gone": True},
                                     "kind": s["kind"], "key": s.get("key") or "", "auto": RS.sub_resolved(g, s, c)})
                    groups.append({"gi": gi, "person": g["person"], "keys": g["keys"], "kind": g["kind"], "subs": subs,
                                   "auto": RS.person_resolved(g, cards)})
                out["groups"] = [g for g in groups if (show_new or g["kind"] != RS.NEW)
                                 and (RS.text_match(g["person"], text) or any(RS.text_match(s["card"], text) for s in g["subs"]))]
            else:
                if mode == "multi":
                    cards = RS.multi_mobile(cards)
                elif mode == "many":                      # 같은 사람 명함 3장 이상(261122-5) — 묶음끼리 모아
                    many = RS.many_cards(cards)
                    out["why"] = {c["id"]: (k, n) for c, k, n in many}
                    cards = [c for c, _k, _n in many]
                out["cards"] = [c for c in cards if RS.text_match(c, text)]
        except Exception as e:                  # noqa: BLE001 — 메인에서 알린다(글·경로는 싣지 않음)
            # 어느 단계인지·SQLite 오류 글(명함 글 없음)까지 — 사용자 보고 261123 'DatabaseError' 만으로는 까닭을 몰랐다
            detail = str(e)[:120] if isinstance(e, sqlite3.Error) else ""
            out["error"] = "%s · %s%s" % (stage, type(e).__name__, (": " + detail) if detail else "")
            import traceback
            traceback.print_exc()                # 코드 줄만(명함 글 없음) — 개발 실행 창에
        self.done.emit(gen, out)
        self.finished.emit()


class SplitDialog(QDialog):
    """나누기(§5.32) — 새 사람의 이름·회사·부서·직함, 뗄 번호·메일·명함 그림·인물 사진을 체크."""

    def __init__(self, card, photos, parent=None, preset=None):
        super().__init__(parent)
        from viewer.bizcard import phone as PH
        from viewer.widgets.bizcard_find_dialog import _scaled
        preset = preset or {}
        self.card = card
        self.setWindowTitle(tr("나누기"))
        v = QVBoxLayout(self)
        lbl = QLabel(tr("'{n}' 에서 다른 사람의 것을 골라 새 사람으로 떼어 냅니다 — 뗀 번호·메일은 이 명단에서 빠집니다.").format(
            n=card.get("name") or ""))
        lbl.setWordWrap(True)
        v.addWidget(lbl)
        form = QFormLayout()
        self.eds = {}
        for k, label in (("name", tr_noop("이름")), ("company", tr_noop("회사")), ("dept", tr_noop("부서")), ("title", tr_noop("직함"))):
            ed = QLineEdit(str(preset.get(k) or ""))
            form.addRow(tr(label), ed)
            self.eds[k] = ed
        v.addLayout(form)
        v.addWidget(QLabel(tr("새 사람에게 줄 것:")))
        self.lst = QListWidget()
        self.lst.setIconSize(QSize(80, 60))
        want = set(preset.get("keys") or [])
        for x in card.get("phones") or []:
            kind, num = tuple(x)[0], tuple(x)[-1]
            it = QListWidgetItem(tr("전화 {n}").format(n=num))
            it.setData(ROLE, ("phone", (kind, num)))
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if (PH.mobile_key(kind, num) or "-") in want else Qt.CheckState.Unchecked)
            self.lst.addItem(it)
        for e in card.get("emails") or []:
            it = QListWidgetItem(tr("메일 {m}").format(m=e))
            it.setData(ROLE, ("email", e))
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked)
            self.lst.addItem(it)
        if not V.is_contact(card) and card.get("front") and os.path.exists(P._real(card["front"])):
            it = QListWidgetItem(QIcon(_scaled(P._real(card["front"]), 80, 60)), tr("명함 그림(앞·뒷면)"))
            it.setData(ROLE, ("image", True))
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked)
            self.lst.addItem(it)
        for i, p in enumerate(photos or []):
            it = QListWidgetItem(QIcon(_scaled(p, 80, 60)), tr("인물 사진 {n}").format(n=i + 1))
            it.setData(ROLE, ("photo", p))
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked)
            self.lst.addItem(it)
        v.addWidget(self.lst, 1)
        bb = QDialogButtonBox()
        self.btn_ok = bb.addButton(tr("나누기"), QDialogButtonBox.ButtonRole.AcceptRole)
        b_c = bb.addButton(tr("취소"), QDialogButtonBox.ButtonRole.RejectRole)
        for b in (self.btn_ok, b_c):
            b.setAutoDefault(False)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.resize(480, 520)

    def check(self, kind, value=None, on=True) -> int:
        """kind('phone'·'email'·'image'·'photo') 줄을 체크(value 를 주면 그 값만 — 번호는 숫자로 견줌). 반환 = 바꾼 줄 수(검사·미리 채움)."""
        import re
        n = 0
        dig = lambda s: re.sub(r"\D", "", str(s or ""))          # noqa: E731
        for i in range(self.lst.count()):
            it = self.lst.item(i)
            k, val = it.data(ROLE)
            if k != kind:
                continue
            if value is not None and (dig(val[-1]) != dig(value) if k == "phone" else val != value):
                continue
            it.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
            n += 1
        return n

    def values(self) -> dict:
        out = {"fields": {k: ed.text().strip() for k, ed in self.eds.items()}, "phones": [], "emails": [], "image": False, "photos": []}
        for i in range(self.lst.count()):
            it = self.lst.item(i)
            if it.checkState() != Qt.CheckState.Checked:
                continue
            k, val = it.data(ROLE)
            if k == "phone":
                out["phones"].append(val)
            elif k == "email":
                out["emails"].append(val)
            elif k == "image":
                out["image"] = True
            else:
                out["photos"].append(val)
        return out

    def _ok(self):
        v = self.values()
        if not v["fields"]["name"]:
            QMessageBox.information(self, tr("나누기"), tr("새 사람의 이름을 넣으세요."))
            return
        if not (v["phones"] or v["emails"] or v["image"] or v["photos"]):
            QMessageBox.information(self, tr("나누기"), tr("새 사람에게 줄 것을 하나 이상 체크하세요."))
            return
        self.accept()


def run_split(parent, fd, cid, preset=None, dlg=None) -> int:
    """나누기 한 길(명단 관리·중복 검토 '잘못 합쳐짐 의심' — §5.32). dlg = 검사용(값을 넣은 SplitDialog — 실행하지 않음).
    파일(명함 그림·인물 사진)은 앱 이름 바꾸기 한 길로 먼저, DB 는 `people.split_card`. 반환 = 새 id(안 했으면 0)."""
    from viewer.bizcard.apply import unique_path, BACK_SUFFIX
    from viewer.bizcard import recognize as R
    st = fd._store()
    c = P.card_by_id(st, cid)
    if not c:
        return 0
    old_pf = fd._photo_front(c)
    photos = P.person_photos(old_pf) if old_pf else []
    if dlg is None:
        dlg = SplitDialog(c, photos, parent, preset)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return 0
    v = dlg.values()
    f = v["fields"]
    image = None
    if v["image"] and not V.is_contact(c):
        front = P._real(c["front"])
        folder = Path(front).parent
        p = unique_path(folder, R.card_filename(f["name"], f.get("company") or "", os.path.splitext(front)[1] or ".jpg"), set())
        if not fd._rename(front, str(p)):
            return 0
        nb = ""
        back = P._real(c.get("back") or "") if c.get("back") else ""
        if back and os.path.exists(back):
            pb = unique_path(folder, p.stem + BACK_SUFFIX + os.path.splitext(back)[1], set())
            if fd._rename(back, str(pb)):
                nb = str(pb)
        image = (str(p), nb)
    try:
        nid = P.split_card(st, cid, v["phones"], v["emails"], f, image=image)
    except Exception as e:                      # noqa: BLE001 — 글·경로는 싣지 않음
        QMessageBox.warning(parent, tr("나누기"), tr("나누지 못했습니다({err}).").format(err=type(e).__name__))
        return 0
    new = P.card_by_id(st, nid)
    if image:                                   # 정리본 파일 태그도 새 사람의 것으로(§5.5)
        old_auto = P.auto_retag(list(c.get("tags") or []), [c], f["name"], f.get("company") or "")[1]
        fd._retag([x for x in image if x and os.path.exists(x)], old_auto, new.get("tags") or [])
    new_pf = fd._photo_front(new)
    for ph in v["photos"]:                      # 고른 인물 사진은 새 사람 자리로
        if new_pf and os.path.exists(ph):
            dst = P.next_photo_path(new_pf)
            dst.parent.mkdir(parents=True, exist_ok=True)
            fd._rename(ph, str(dst), quiet=True)
    a = P.card_by_id(st, cid)
    a_pf = fd._photo_front(a) if a else ""
    if image and a_pf and old_pf and os.path.normcase(a_pf) != os.path.normcase(old_pf):
        for ph in [x for x in photos if x not in v["photos"] and os.path.exists(x)]:   # 남는 쪽의 사진은 그림 없는 명함 자리로(§5.24.3)
            dst = P.next_photo_path(a_pf)
            dst.parent.mkdir(parents=True, exist_ok=True)
            fd._rename(ph, str(dst), quiet=True)
    if not getattr(fd, "_dirty", False):
        fd._card = None
        fd.refresh()
    return nid


class RosterDialog(QDialog):
    def __init__(self, find_dlg):
        super().__init__(find_dlg)
        self.fd = find_dlg
        self.setWindowTitle(tr("명단 관리"))
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowMinimizeButtonHint)
        self.resize(1100, 680)
        self.vcf_path, self.persons = "", None
        self.cards, self.groups = [], []
        self._gen, self.loading = 0, False
        self._img_gen, self.imgs_pending = 0, 0
        # vcf 작업 목록(고정)·사람이 정한 체크 — 명함 DB meta 에 남겨 다시 열면 이어서(§5.32 '작업 목록', 261122-4)
        self.frozen, self.checks, self.added = None, {}, {}
        saved = self.fd._store().meta_get(RS.META_KEY) or {}
        if isinstance(saved, dict) and saved.get("groups") is not None:
            self.vcf_path, self.frozen, self.checks = saved.get("path") or "", saved["groups"], dict(saved.get("checks") or {})
            self.added = dict(saved.get("added") or {})     # [추가] 한 vcf 사람 줄 {gi: 새 명단 id}(261122-7)
        self.undo_stack, self.redo_stack = [], []      # 창 안 작업 단위 되돌리기(§5.32 '되돌리기', 261122-4)
        self._filling = False
        v = QVBoxLayout(self)
        top = QHBoxLayout()
        self.cmb_view = QComboBox()
        for key, label in VIEWS:
            self.cmb_view.addItem(tr(label), key)
        self.cmb_view.currentIndexChanged.connect(lambda _i: self._view_changed())
        top.addWidget(self.cmb_view)
        self.ed_find = QLineEdit()
        self.ed_find.setPlaceholderText(tr("이름·회사·번호·메일로 거르기"))
        self.ed_find.textChanged.connect(lambda _t: self.reload())
        top.addWidget(self.ed_find, 1)
        self.btn_vcf = QPushButton(tr("vcf 열기…"))
        self.btn_vcf.setToolTip(tr("휴대폰 주소록 등에서 내보낸 vcf 와 견줍니다 — 파일은 읽기만 합니다"))
        self.btn_vcf.clicked.connect(lambda _c=False: self.open_vcf())
        top.addWidget(self.btn_vcf)
        self.btn_recompare = QPushButton(tr("새로 비교"))
        self.btn_recompare.setToolTip(tr("vcf 를 다시 읽어 처음부터 견줍니다 — 지금 작업 목록과 체크는 지웁니다"))
        self.btn_recompare.clicked.connect(lambda _c=False: self.recompare())
        top.addWidget(self.btn_recompare)
        self.chk_new = QCheckBox(tr("번호 없는 새 사람도 보기"))
        self.chk_new.toggled.connect(lambda _on: self.reload())
        top.addWidget(self.chk_new)
        v.addLayout(top)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr("이름"), tr("회사"), tr("010 번호"), tr("다른 전화"), tr("메일"), tr("명함"), tr("이유")])
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        self.tree.currentItemChanged.connect(lambda cur, _p: (self._enable(), self._preview()))
        self.tree.itemChanged.connect(self._checked)
        self.tree.itemDoubleClicked.connect(self._double)        # 하위 줄 두 번 누름 = 고치기(261122-4)
        split.addWidget(self.tree)
        # 오른쪽 = 위 큰 그림(칸에 맞춰) + 아래 썸네일 한 줄 — 중복 검토 '명함 그림' 과 같은 꼴(사용자 보고 261123 '명함이 너무 작게')
        pw = QWidget()
        pv = QVBoxLayout(pw)
        pv.setContentsMargins(0, 0, 0, 0)
        self.big = QLabel(tr("(명함 그림 없음)"))
        self.big.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.big.setMinimumSize(200, 140)
        self.big_path = ""
        self._big_gen = 0
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
        pv.addWidget(self.big, 1)
        pv.addWidget(self.thumbs)
        split.addWidget(pw)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([640, 440])
        v.addWidget(split, 1)
        self.lbl_help = QLabel(tr("바로잡는 차례: ① 잘못 합쳐지기 전에 구글 주소록에서 내보내 둔 vcf 를 [vcf 비교] 로 열어 그것을 바른 기준으로 "
                                  "나누기·vcf 번호로·vcf 이름으로 ② 변경 기록이 남은 합치기는 주소록 ▸ 변경 기록·되살리기에서 출처 '합치기' 로 되살릴 수도 "
                                  "③ 그 뒤 구글 주소록과 싱크 미리보기 [적용] 으로 구글·휴대폰에 올립니다."))
        self.lbl_help.setWordWrap(True)
        v.addWidget(self.lbl_help)
        bot = QHBoxLayout()
        self.btn_undo = QPushButton(tr("되돌리기"))           # 되돌리기 단추는 왼쪽 끝(디자인 SOT §2.7)
        self.btn_undo.clicked.connect(lambda _c=False: self.undo())
        self.btn_redo = QPushButton(tr("다시 실행"))
        self.btn_redo.clicked.connect(lambda _c=False: self.redo())
        bot.addWidget(self.btn_undo)
        bot.addWidget(self.btn_redo)
        self.lbl = QLabel()
        bot.addWidget(self.lbl, 1)
        self.btn_edit = QPushButton(tr("고치기"))
        self.btn_edit.clicked.connect(lambda _c=False: self.edit())
        self.btn_split = QPushButton(tr("나누기"))
        self.btn_split.setToolTip(tr("고른 번호·메일·명함 그림·인물 사진을 새 사람으로 떼어 냅니다"))
        self.btn_split.clicked.connect(lambda _c=False: self.split())
        self.btn_pics = QPushButton(tr("명함 사진 삭제"))
        self.btn_pics.clicked.connect(lambda _c=False: self.delete_pictures())
        self.btn_del = QPushButton(tr("명단 삭제"))
        self.btn_del.clicked.connect(lambda _c=False: self.delete())
        self.btn_add = QPushButton(tr("추가"))
        self.btn_add.setToolTip(tr("vcf 의 이 사람을 명단에 더합니다(그림 없는 명함)"))
        self.btn_add.clicked.connect(lambda _c=False: self.add())
        self.btn_rename = QPushButton(tr("vcf 이름으로"))
        self.btn_rename.setToolTip(tr("이 명단의 이름을 vcf 의 이름으로 바꿉니다"))
        self.btn_rename.clicked.connect(lambda _c=False: self.vcf_name())
        self.btn_nums = QPushButton(tr("vcf 번호로"))
        self.btn_nums.setToolTip(tr("이 명단의 010 번호를 vcf(예전 구글 백업)의 번호로 맞춥니다 — 뺄 번호가 다른 사람 것이면 [나누기] 로 새 사람에게 주세요"))
        self.btn_nums.clicked.connect(lambda _c=False: self.vcf_numbers())
        b_close = QPushButton(tr("닫기"))
        b_close.clicked.connect(lambda _c=False: self.accept())
        for b in (self.btn_edit, self.btn_split, self.btn_pics, self.btn_del, self.btn_add, self.btn_rename, self.btn_nums, b_close):
            bot.addWidget(b)
        v.addLayout(bot)
        for b in self.findChildren(QPushButton):        # Enter 가 단추를 누르지 않게 — 기본 단추 없음(§5.24.1 'Enter')
            b.setAutoDefault(False)
            b.setDefault(False)
        self._view_changed()

    # ── 읽기 ──
    def view(self) -> str:
        return self.cmb_view.currentData()

    def set_view(self, key: str):
        self.cmb_view.setCurrentIndex(next(i for i, (k, _l) in enumerate(VIEWS) if k == key))

    def _view_changed(self):
        vcf = self.view() == "vcf"
        self.btn_vcf.setVisible(vcf)
        self.chk_new.setVisible(vcf)
        self.btn_recompare.setVisible(vcf)
        self.reload()

    def open_vcf(self, path=None) -> bool:
        if path is None:
            path, _f = QFileDialog.getOpenFileName(self, tr("vcf 열기"), "", tr("vCard (*.vcf)"))
        if not path:
            return False
        self.vcf_path, self.persons = path, None
        # 같은 파일이어도 다시 읽으면 옛 작업 목록을 버리고 지금 DB 로 새로 비교(261122-7 — 고친 것이 잘 됐는지 보려고).
        # 창만 다시 열면 이어서(meta, 261122-4). 되돌리기 쌓임은 그대로(DB 되돌림은 목록과 상관없이 맞다)
        self.frozen, self.checks, self.added = None, {}, {}
        if self.view() != "vcf":
            self.set_view("vcf")
        else:
            self.reload()
        return True

    def recompare(self) -> bool:
        """[새로 비교] — vcf 를 다시 읽어 처음부터(작업 목록·체크를 지움)."""
        if not self.vcf_path:
            return False
        self.persons, self.frozen, self.checks, self.added = None, None, {}, {}
        self.reload()
        return True

    def _save_state(self):
        """작업 목록·체크를 명함 DB meta 에(다시 열면 이어서) — 작은 JSON 한 줄."""
        try:
            self.fd._store().meta_set(RS.META_KEY, {"path": self.vcf_path, "groups": self.frozen, "checks": self.checks,
                                                    "added": self.added})
        except Exception:
            pass

    def reload(self):
        from viewer.workers import run_in_thread
        self._gen += 1
        if self.view() == "vcf" and not self.vcf_path:
            self.tree.clear()
            self.cards, self.groups = [], []
            self.lbl.setText(tr("[vcf 열기…] 로 견줄 vcf 를 고르세요."))
            self._enable()
            return
        self.loading = True
        self.lbl.setText(tr("읽는 중…"))
        w = _RosterWorker(self._gen, str(self.fd._store().path), self.view(), self.ed_find.text(), self.vcf_path, self.persons,
                          self.chk_new.isChecked(), self.frozen)
        w.done.connect(self._loaded)
        keep = getattr(self.fd._mw, "_thread_keep", None) if self.fd._mw is not None else None
        run_in_thread(w, keep if isinstance(keep, list) else _KEEP)

    def _loaded(self, gen, out):
        if gen != self._gen:
            return                                      # 늦게 끝난 옛 읽기는 버린다
        self.loading = False
        if out.get("error"):
            self.tree.clear()
            self.lbl.setText(tr("읽지 못했습니다({err}).").format(err=out["error"]))
            return
        if out.get("persons") is not None:
            self.persons = out["persons"]
        if out.get("frozen") is not None:                   # 새로 고정한 작업 목록
            self.frozen, self.checks, self.added = out["frozen"], {}, {}
            self._save_state()
        self.cards, self.groups = out["cards"], out["groups"]
        self._prune_added()
        for g in self.groups or []:                         # [추가] 한 줄은 저절로 체크(261122-7)
            if str(g.get("gi")) in self.added:
                g["auto"] = True
        self.why = out.get("why") or {}
        self.fill()

    def _card_item(self, c, why="", data=None):
        it = QTreeWidgetItem([c.get("name") or "", c.get("company") or "", _m010(c), _other_phones(c),
                              ", ".join(c.get("emails") or []), "" if V.is_contact(c) else tr("명함"), why])
        it.setData(0, ROLE, data or ("card", c["id"]))
        return it

    @staticmethod
    def line_key(d) -> str:
        """줄 열쇠 — 대표 'p:묶음', 하위 'c:묶음:명함 id'(체크를 남기는 열쇠)."""
        return ("p:%d" % d[1]) if d[0] == "vcf" else ("c:%d:%d" % (d[2], d[1]))

    def is_checked(self, d, auto: bool) -> bool:
        return bool(self.checks.get(self.line_key(d), auto))

    def _paint(self, it, on: bool):
        """해결된(체크한) 줄은 회색 글 — 고칠 수는 있다."""
        col = self.palette().placeholderText() if on else self.palette().text()
        for i in range(self.tree.columnCount()):
            it.setForeground(i, col)

    def _set_check(self, it, d, auto):
        on = self.is_checked(d, auto)
        it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        it.setCheckState(0, Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
        it.setData(0, ROLE + 1, auto)
        self._paint(it, on)

    def fill(self):
        from viewer.bizcard import phone as PH
        self._filling = True
        try:
            self._fill(PH)
        finally:
            self._filling = False
        self._enable()

    def _fill(self, PH):
        cur = self._sel()
        self.tree.clear()
        if self.view() == "vcf":
            for g in self.groups:
                gi, p = g["gi"], g["person"]
                top = QTreeWidgetItem([p.get("name") or "", p.get("company") or "", ", ".join(PH.format_kr(k) or k for k in g["keys"]),
                                       "", ", ".join(p.get("emails") or []), "", tr("vcf") if g["kind"] != RS.NEW else tr(KIND_LABEL[RS.NEW])])
                top.setData(0, ROLE, ("vcf", gi))
                f = top.font(0)
                f.setBold(True)
                top.setFont(0, f)
                self.tree.addTopLevelItem(top)
                self._set_check(top, ("vcf", gi), g["auto"])
                for s in g["subs"]:
                    c = s["card"]
                    why = tr(KIND_LABEL[s["kind"]]) + ("" if not c.get("_gone") else " · " + tr("(지움)"))
                    it = self._card_item(c, why, ("card", c["id"], gi, s["kind"]))
                    top.addChild(it)
                    self._set_check(it, ("card", c["id"], gi, s["kind"]), s["auto"])
                top.setExpanded(True)
            done = sum(1 for g in self.groups if self.is_checked(("vcf", g["gi"]), g["auto"]))
            self.lbl.setText(tr("vcf 사람 {n}명 · 대표 해결 {d}명").format(n=len(self.groups), d=done))
            if cur:
                if cur[0] == "card" and len(cur) > 2:
                    self.select_card(cur[1], gi=cur[2])
                elif cur[0] == "vcf":
                    self.select_person(cur[1])
        else:
            why = tr("010 {n}개") if self.view() == "multi" else ""
            many = getattr(self, "why", {}) if self.view() == "many" else {}
            for c in self.cards:
                if c["id"] in many:
                    k, n = many[c["id"]]
                    w = tr(MANY_WHY[k]).format(n=n)
                else:
                    w = why.format(n=len(P.mobiles_010(c))) if why else ""
                self.tree.addTopLevelItem(self._card_item(c, w))
            self.lbl.setText(tr("명단 {n}명").format(n=len(self.cards)))
        for i in range(self.tree.columnCount()):
            self.tree.resizeColumnToContents(i)
        self._enable()

    # ── 고른 줄 ──
    def _sel(self):
        it = self.tree.currentItem()
        return it.data(0, ROLE) if it is not None else None

    def current_card(self):
        d = self._sel()
        if not d or d[0] != "card":
            return None
        return P.card_by_id(self.fd._store(), d[1])

    def current_person(self):
        """고른 줄의 vcf 사람(vcf 줄이나 그 아래 명단 줄)과 그 묶음."""
        d = self._sel()
        if not d:
            return None, None
        gi = d[1] if d[0] == "vcf" else (d[2] if len(d) > 2 else None)
        g = next((x for x in self.groups if x.get("gi") == gi), None) if gi is not None else None
        if g is None:
            return None, None
        return g["person"], g

    def _checked(self, it, col):
        """사람이 체크를 켜거나 끄면 그것이 이긴다(저절로 체크와 다를 때만 남김) — 회색도 따라."""
        if self._filling or col != 0:
            return
        d = it.data(0, ROLE)
        if not d or self.view() != "vcf":
            return
        on = it.checkState(0) == Qt.CheckState.Checked
        auto = bool(it.data(0, ROLE + 1))
        k = self.line_key(d)
        if on == auto:
            self.checks.pop(k, None)
        else:
            self.checks[k] = on
        self._save_state()
        self._filling = True
        try:
            self._paint(it, on)
        finally:
            self._filling = False

    def _double(self, it, _col):
        d = it.data(0, ROLE) if it is not None else None
        if d and d[0] == "card":
            self.tree.setCurrentItem(it)
            self.edit()

    def select_card(self, cid, gi=None) -> bool:
        """그 명함 줄을 고른다(검사·되돌아오기). gi = vcf 묶음 번호(한 명단이 여러 vcf 사람 아래에 있을 때)."""
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            if gi is not None and top.data(0, ROLE) != ("vcf", gi):
                continue
            for it in [top] + [top.child(j) for j in range(top.childCount())]:
                d = it.data(0, ROLE)
                if d and d[0] == "card" and d[1] == cid:
                    self.tree.setCurrentItem(it)
                    return True
        return False

    def select_person(self, gi) -> bool:
        for i in range(self.tree.topLevelItemCount()):
            if self.tree.topLevelItem(i).data(0, ROLE) == ("vcf", gi):
                self.tree.setCurrentItem(self.tree.topLevelItem(i))
                return True
        return False

    def _enable(self):
        d = self._sel()
        card = bool(d) and d[0] == "card"
        for b in (self.btn_edit, self.btn_split, self.btn_pics, self.btn_del):
            b.setEnabled(card)
        self.btn_add.setVisible(self.view() == "vcf")
        self.btn_rename.setVisible(self.view() == "vcf")
        self.btn_add.setEnabled(bool(d) and d[0] == "vcf")
        self.btn_rename.setEnabled(card and len(d) > 3 and d[3] == RS.RENAMED)
        self.btn_nums.setVisible(self.view() == "vcf")
        self.btn_nums.setEnabled(card and len(d) > 3 and d[3] == RS.SAME_NAME)
        self.btn_undo.setEnabled(bool(self.undo_stack))
        self.btn_redo.setEnabled(bool(self.redo_stack))
        self.btn_recompare.setEnabled(bool(self.vcf_path))

    def _preview(self):
        """고른 명단의 명함 앞·뒷면·인물 사진 — 썸네일 줄, 첫 그림(앞면)을 크게(배경 읽기 — 중복 검토와 같은 `_ImgWorker`)."""
        self.thumbs.blockSignals(True)
        self.thumbs.clear()
        self.thumbs.blockSignals(False)
        self._img_gen += 1
        c = self.current_card()
        paths = []
        if c:
            if not V.is_contact(c):
                paths += [P._real(x) for x in (c.get("front"), c.get("back")) if x and os.path.exists(P._real(x))]
            pf = self.fd._photo_front(c)
            paths += P.person_photos(pf) if pf else []
        jobs = []
        self.thumbs.blockSignals(True)
        for p in paths:
            it = QListWidgetItem("")
            it.setData(ROLE, p)
            it.setToolTip(os.path.basename(p))
            jobs.append((self.thumbs.count(), p, THUMB, THUMB))
            self.thumbs.addItem(it)
        if self.thumbs.count():
            self.thumbs.setCurrentRow(0)
        self.thumbs.blockSignals(False)
        self._load(jobs)
        self._show_big(paths[0] if paths else "")

    def _load(self, jobs, big=None):
        from viewer.widgets.bizcard_dupe_dialog import _ImgWorker
        from viewer.workers import run_in_thread
        if not jobs:
            return
        w = _ImgWorker(self._img_gen, big, jobs)
        w.one.connect(self._img_ready)
        self.imgs_pending += len(jobs)
        keep = getattr(self.fd._mw, "_thread_keep", None) if self.fd._mw is not None else None
        run_in_thread(w, keep if isinstance(keep, list) else _KEEP)

    def _show_big(self, path):
        """큰 그림 — 칸 크기에 맞춰 줄여 읽기(배경). 그림이 없으면 글."""
        self.big_path = path or ""
        self._big_gen += 1
        if not path:
            self.big.setPixmap(QPixmap())
            self.big.setText(tr("(명함 그림 없음)"))
            return
        self._load([(-1, path, max(200, self.big.width()), max(140, self.big.height()))], big=self._big_gen)

    def _img_ready(self, gen, big, i, path, img):
        self.imgs_pending = max(0, self.imgs_pending - 1)
        if img.isNull():
            return
        if i < 0:
            if big == self._big_gen and path == self.big_path:
                self.big.setPixmap(QPixmap.fromImage(img).scaled(max(200, self.big.width()), max(140, self.big.height()),
                                   Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            return
        it = self.thumbs.item(i) if gen == self._img_gen else None
        if it is not None and it.data(ROLE) == path:
            it.setIcon(QIcon(QPixmap.fromImage(img).scaled(THUMB, THUMB, Qt.AspectRatioMode.KeepAspectRatio,
                                                            Qt.TransformationMode.SmoothTransformation)))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if getattr(self, "big_path", ""):
            self._show_big(self.big_path)             # 창 크기를 바꾸면 큰 그림도 칸에 맞춰 다시

    def _menu(self, pos):
        it = self.tree.itemAt(pos)
        if it is None:
            return
        self.tree.setCurrentItem(it)
        d = it.data(0, ROLE)
        m = QMenu(self)
        if d[0] == "vcf":
            m.addAction(tr("추가"), self.add)
        else:
            m.addAction(tr("고치기"), self.edit)
            m.addAction(tr("나누기"), self.split)
            m.addAction(tr("명함 사진 삭제"), self.delete_pictures)
            m.addAction(tr("명단 삭제"), self.delete)
            if len(d) > 3 and d[3] == RS.RENAMED:
                m.addAction(tr("vcf 이름으로"), self.vcf_name)
            if len(d) > 3 and d[3] == RS.SAME_NAME:
                m.addAction(tr("vcf 번호로"), self.vcf_numbers)
        self._last_menu = m
        m.exec(self.tree.viewport().mapToGlobal(pos))

    # ── 일 ──
    def _after(self, cid=None):
        self.reload()

    # 되돌리기·다시 실행(§5.32 '되돌리기', 261122-4) — 일마다 앞뒤 DB 모습 + 그 일이 옮긴 파일
    def _record(self, ids, fn):
        """fn 을 하면서 관련 명단의 앞뒤 모습과 옮긴 파일을 적는다(지우는 파일은 휴지통 대신 `병합 보관` 으로). 반환 = fn 의 결과."""
        st = self.fd._store()
        top = st.con.execute("SELECT COALESCE(max(id), 0) FROM cards").fetchone()[0]
        ids = {int(i) for i in ids}
        before = P.snapshot(st, ids)
        self.fd.move_log, self.fd.hold_on = [], True
        try:
            res = fn()
        finally:
            moves = list(self.fd.move_log or [])
            self.fd.move_log, self.fd.hold_on = None, False
        new_ids = {r[0] for r in st.con.execute("SELECT id FROM cards WHERE id > ?", (top,))}
        for i in new_ids:
            before["cards"].setdefault(i, None)            # 새로 생긴 명단 — 되돌리면 지움
        after = P.snapshot(st, ids | new_ids)
        if moves or before["cards"] != after["cards"] or before["side"] != after["side"] or before["not_same"] != after["not_same"]:
            self.undo_stack.append({"moves": moves, "before": before, "after": after})
            self.redo_stack.clear()
        return res

    def _replay(self, moves, back: bool):
        for a, b in (reversed(moves) if back else moves):
            src, dst = (b, a) if back else (a, b)
            if os.path.exists(src) and not os.path.exists(dst):
                try:
                    Path(dst).parent.mkdir(parents=True, exist_ok=True)
                except OSError:
                    pass
                self.fd._rename(src, dst, quiet=True)

    def undo(self) -> bool:
        """[되돌리기] — 마지막 일: 옮긴 파일을 거꾸로, 관련 명단을 앞 모습으로."""
        if not self.undo_stack:
            return False
        rec = self.undo_stack.pop()
        self._replay(rec["moves"], back=True)
        P.restore_snapshot(self.fd._store(), rec["before"])
        self.redo_stack.append(rec)
        self._refresh_fd()
        self._after()
        return True

    def redo(self) -> bool:
        """[다시 실행] — 되돌린 일을 다시: 파일을 다시 옮기고 관련 명단을 뒤 모습으로."""
        if not self.redo_stack:
            return False
        rec = self.redo_stack.pop()
        self._replay(rec["moves"], back=False)
        P.restore_snapshot(self.fd._store(), rec["after"])
        self.undo_stack.append(rec)
        self._refresh_fd()
        self._after()
        return True

    def _refresh_fd(self):
        if not getattr(self.fd, "_dirty", False):
            self.fd._card = None
            self.fd.refresh()

    def held_files(self) -> list:
        """되돌릴 수 있게 `병합 보관` 에 둔 파일 중 아직 있는 것(창을 닫을 때 휴지통으로)."""
        return [b for rec in self.undo_stack for _a, b in rec["moves"] if Path(b).parent.name == P.HOLD_DIR and os.path.exists(b)]

    def done(self, r):
        held = self.held_files()
        if held:
            from viewer.widgets.bizcard_import_dialog import trash_paths
            trash_paths(self, self.fd._mw, held)
        self.undo_stack.clear()
        self.redo_stack.clear()
        super().done(r)

    def edit(self, dlg=None) -> bool:
        from viewer.widgets.bizcard_dupe_dialog import CardEditDialog
        c = self.current_card()
        if not c:
            return False
        if dlg is None:
            dlg = CardEditDialog(c, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return False
        vals = dlg.values()
        if not self._record([c["id"]], lambda: self.fd.store_card_edit(c, vals) is not None):
            return False
        self._after()
        return True

    def split(self, dlg=None) -> int:
        c = self.current_card()
        if not c:
            return 0
        person, g = self.current_person()
        preset = None
        if person is not None:
            preset = {"name": person.get("name") or "", "company": person.get("company") or "",
                      "dept": person.get("dept") or "", "title": person.get("title") or "", "keys": g["keys"]}
        preset = self._preset(c, preset)
        nid = self._record([c["id"]], lambda: run_split(self, self.fd, c["id"], preset=preset, dlg=dlg))
        if nid:
            self._after()
        return nid

    def split_dialog(self) -> SplitDialog:
        """검사·미리 채움 — 지금 고른 명단으로 SplitDialog 를 만든다(실행하지 않음)."""
        c = self.current_card()
        person, g = self.current_person()
        preset = None
        if person is not None:
            preset = {"name": person.get("name") or "", "company": person.get("company") or "", "keys": g["keys"]}
        pf = self.fd._photo_front(c)
        return SplitDialog(c, P.person_photos(pf) if pf else [], self, self._preset(c, preset))

    def _preset(self, c, preset):
        """같은 이름·번호 다름 줄 — 새 사람은 vcf 에 없는 010 을 가진 다른 사람(이름은 사람이 넣음)."""
        d = self._sel()
        if preset is not None and d and len(d) > 3 and d[3] == RS.SAME_NAME:
            _p, g = self.current_person()
            return {"keys": [k for k in P.mobiles_010(c) if k not in set(g["keys"])]}
        return preset

    def delete_pictures(self) -> bool:
        from viewer.widgets.bizcard_dupe_dialog import PicturePickDialog
        c = self.current_card()
        if not c:
            return False
        pf = self.fd._photo_front(c)
        dlg = PicturePickDialog(c, P.person_photos(pf) if pf else [], self)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.picks():
            return False
        return self.delete_picks(c, dlg.picks())

    def delete_picks(self, c, picks, ask: bool = True) -> bool:
        """고른 사진만 지움(검사도 이 길) — 이 창을 닫기 전에는 [되돌리기] 로 되살린다."""
        if ask and QMessageBox.question(self, tr("명단 관리"), tr("고른 사진 {n}개를 지웁니다 — 이 창을 닫기 전에는 [되돌리기] 로 "
                                                                "되살릴 수 있습니다.").format(n=len(picks))) != QMessageBox.StandardButton.Yes:
            return False
        ok = self._record([c["id"]], lambda: self.fd.delete_card_pictures(c, picks))
        self._after()
        return ok

    def delete(self, ask: bool = True) -> int:
        c = self.current_card()
        if not c:
            return 0
        n = self._record([c["id"]], lambda: self.fd.delete_cards([c], ask=ask))
        if n:
            self._after()
        return n

    def add(self) -> int:
        """vcf 사람 줄 [추가] — 그림 없는 명함으로(주소록 가져오기와 같은 `apply_import`)."""
        person, g = self.current_person()
        d = self._sel()
        if person is None or not d or d[0] != "vcf":
            return 0
        # 같은 사람이 두 번 생기지 않게(261122-7) — 이 줄에서 이미 [추가] 했거나, 그 이름이고 그 010 번호를 모두 가진 명단이 이미 있으면
        st = self.fd._store()
        self._prune_added()
        if str(g["gi"]) in self.added or RS.person_resolved(g, RS.all_cards(st)):
            QMessageBox.information(self, tr("명단 관리"), tr("이미 추가한 사람입니다 — 다시 추가하지 않습니다."))
            return 0
        before = {c["id"] for c in RS.all_cards(st)}
        n = self._record([], lambda: P.apply_import(st, [dict(person)]))
        if n:
            new = sorted({c["id"] for c in RS.all_cards(st)} - before)
            self.added[str(g["gi"])] = new[0] if new else 0
            self._save_state()
            if not getattr(self.fd, "_dirty", False):
                self.fd.refresh()
            self._after()
        return n

    def _prune_added(self):
        """되돌리기로 없어진 추가는 잊는다(다시 [추가] 할 수 있게)."""
        st = self.fd._store()
        gone = [k for k, cid in self.added.items() if cid and P.card_by_id(st, cid) is None]
        for k in gone:
            self.added.pop(k, None)
        if gone:
            self._save_state()

    def vcf_numbers(self) -> bool:
        """'같은 이름·번호 다름' 줄 [vcf 번호로] — 010 번호(종류 무관)를 vcf 의 것으로, 010 아닌 번호는 그대로(`store_card_edit` 한 길)."""
        from viewer.bizcard import phone as PH
        c = self.current_card()
        person, g = self.current_person()
        if not c or person is None:
            return False
        keep = [tuple(x) for x in c.get("phones") or []
                if not ((PH.kr_digits(tuple(x)[-1]) or "").startswith("010"))]
        new = {k: c.get(k) for k in ("name", "company", "dept", "title", "address", "memo", "emails", "urls")}
        new = {k: (v if v is not None else ([] if k in ("emails", "urls") else "")) for k, v in new.items()}
        new["phones"] = [("cell", PH.format_kr(k) or k) for k in g["keys"]] + keep
        if not self._record([c["id"]], lambda: self.fd.store_card_edit(c, new) is not None):
            return False
        if not getattr(self.fd, "_dirty", False):
            self.fd.refresh()
        self._after()
        return True

    def vcf_name(self) -> bool:
        """'이름 바뀜?' 줄 [vcf 이름으로] — 그 명단 이름을 vcf 이름으로(`store_card_edit` 한 길)."""
        c = self.current_card()
        person, _g = self.current_person()
        if not c or person is None or not (person.get("name") or "").strip():
            return False
        new = {k: c.get(k) for k in ("company", "dept", "title", "address", "memo", "phones", "emails", "urls")}
        new = {k: (v if v is not None else ([] if k in ("phones", "emails", "urls") else "")) for k, v in new.items()}
        new["name"] = person["name"].strip()
        if not self._record([c["id"]], lambda: self.fd.store_card_edit(c, new) is not None):
            return False
        if not getattr(self.fd, "_dirty", False):
            self.fd.refresh()
        self._after()
        return True
