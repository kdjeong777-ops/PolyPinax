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
    QDialogButtonBox)

from viewer.i18n import tr, tr_noop
from viewer.bizcard import people as P
from viewer.bizcard import roster as RS
from viewer.bizcard import vcard as V

ROLE = Qt.ItemDataRole.UserRole
THUMB = 96
VIEWS = (("all", tr_noop("전체")), ("multi", tr_noop("010 둘 이상")), ("vcf", tr_noop("vcf 비교")))
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

    def __init__(self, gen, db, mode, text, vcf_path, persons, show_new):
        super().__init__()
        self._a = (gen, db, mode, text, vcf_path, persons, show_new)

    def run(self):
        gen, db, mode, text, vcf_path, persons, show_new = self._a
        out = {"mode": mode, "cards": [], "groups": [], "persons": persons, "error": ""}
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
                stage = "vcf"
                if persons is None and vcf_path:
                    persons = RS.read_vcf(vcf_path)
                    out["persons"] = persons
                stage = "compare"
                groups = RS.vcf_compare(cards, persons or [], show_new=show_new)
                out["groups"] = [g for g in groups if RS.text_match(g["person"], text)
                                 or any(RS.text_match(s["card"], text) for s in g["subs"])]
            else:
                if mode == "multi":
                    cards = RS.multi_mobile(cards)
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
        split.addWidget(self.tree)
        self.thumbs = QListWidget()
        self.thumbs.setViewMode(QListView.ViewMode.IconMode)
        self.thumbs.setMovement(QListView.Movement.Static)
        self.thumbs.setIconSize(QSize(THUMB * 2, THUMB * 2))
        self.thumbs.setGridSize(QSize(THUMB * 2 + 16, THUMB * 2 + 28))
        split.addWidget(self.thumbs)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        v.addWidget(split, 1)
        self.lbl_help = QLabel(tr("바로잡는 차례: ① 잘못 합쳐지기 전에 구글 주소록에서 내보내 둔 vcf 를 [vcf 비교] 로 열어 그것을 바른 기준으로 "
                                  "나누기·vcf 번호로·vcf 이름으로 ② 변경 기록이 남은 합치기는 주소록 ▸ 변경 기록·되살리기에서 출처 '합치기' 로 되살릴 수도 "
                                  "③ 그 뒤 구글 주소록과 싱크 미리보기 [적용] 으로 구글·휴대폰에 올립니다."))
        self.lbl_help.setWordWrap(True)
        v.addWidget(self.lbl_help)
        bot = QHBoxLayout()
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
        self.reload()

    def open_vcf(self, path=None) -> bool:
        if path is None:
            path, _f = QFileDialog.getOpenFileName(self, tr("vcf 열기"), "", tr("vCard (*.vcf)"))
        if not path:
            return False
        self.vcf_path, self.persons = path, None
        if self.view() != "vcf":
            self.set_view("vcf")
        else:
            self.reload()
        return True

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
                          self.chk_new.isChecked())
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
        self.cards, self.groups = out["cards"], out["groups"]
        self.fill()

    def _card_item(self, c, why="", data=None):
        it = QTreeWidgetItem([c.get("name") or "", c.get("company") or "", _m010(c), _other_phones(c),
                              ", ".join(c.get("emails") or []), "" if V.is_contact(c) else tr("명함"), why])
        it.setData(0, ROLE, data or ("card", c["id"]))
        return it

    def fill(self):
        from viewer.bizcard import phone as PH
        self.tree.clear()
        if self.view() == "vcf":
            for gi, g in enumerate(self.groups):
                p = g["person"]
                top = QTreeWidgetItem([p.get("name") or "", p.get("company") or "", ", ".join(PH.format_kr(k) or k for k in g["keys"]),
                                       "", ", ".join(p.get("emails") or []), "", tr("vcf") if g["kind"] != RS.NEW else tr(KIND_LABEL[RS.NEW])])
                top.setData(0, ROLE, ("vcf", gi))
                f = top.font(0)
                f.setBold(True)
                top.setFont(0, f)
                self.tree.addTopLevelItem(top)
                for s in g["subs"]:
                    top.addChild(self._card_item(s["card"], tr(KIND_LABEL[s["kind"]]), ("card", s["card"]["id"], gi, s["kind"])))
                top.setExpanded(True)
            self.lbl.setText(tr("vcf 사람 {n}명").format(n=len(self.groups)))
        else:
            why = tr("010 {n}개") if self.view() == "multi" else ""
            for c in self.cards:
                self.tree.addTopLevelItem(self._card_item(c, why.format(n=len(P.mobiles_010(c))) if why else ""))
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
        if gi is None or gi >= len(self.groups):
            return None, None
        return self.groups[gi]["person"], self.groups[gi]

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

    def _preview(self):
        """고른 명단의 명함 앞·뒷면·인물 사진 썸네일(배경 읽기 — 중복 검토와 같은 `_ImgWorker`)."""
        from viewer.widgets.bizcard_dupe_dialog import _ImgWorker
        from viewer.workers import run_in_thread
        self.thumbs.clear()
        self._img_gen += 1
        c = self.current_card()
        if not c:
            return
        paths = []
        if not V.is_contact(c):
            paths += [P._real(x) for x in (c.get("front"), c.get("back")) if x and os.path.exists(P._real(x))]
        pf = self.fd._photo_front(c)
        paths += P.person_photos(pf) if pf else []
        jobs = []
        for p in paths:
            it = QListWidgetItem(os.path.basename(p))
            it.setData(ROLE, p)
            jobs.append((self.thumbs.count(), p, THUMB * 2, THUMB * 2))
            self.thumbs.addItem(it)
        if jobs:
            w = _ImgWorker(self._img_gen, None, jobs)
            w.one.connect(self._img_ready)
            self.imgs_pending += len(jobs)
            keep = getattr(self.fd._mw, "_thread_keep", None) if self.fd._mw is not None else None
            run_in_thread(w, keep if isinstance(keep, list) else _KEEP)

    def _img_ready(self, gen, _big, i, path, img):
        self.imgs_pending = max(0, self.imgs_pending - 1)
        it = self.thumbs.item(i) if gen == self._img_gen else None
        if it is not None and it.data(ROLE) == path and not img.isNull():
            it.setIcon(QIcon(QPixmap.fromImage(img)))

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

    def edit(self, dlg=None) -> bool:
        from viewer.widgets.bizcard_dupe_dialog import CardEditDialog
        c = self.current_card()
        if not c:
            return False
        if dlg is None:
            dlg = CardEditDialog(c, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return False
        if self.fd.store_card_edit(c, dlg.values()) is None:
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
        nid = run_split(self, self.fd, c["id"], preset=preset, dlg=dlg)
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
        if QMessageBox.question(self, tr("명단 관리"), tr("고른 사진 {n}개를 휴지통으로 보냅니다.").format(n=len(dlg.picks()))) \
                != QMessageBox.StandardButton.Yes:
            return False
        ok = self.fd.delete_card_pictures(c, dlg.picks())
        self._after()
        return ok

    def delete(self, ask: bool = True) -> int:
        c = self.current_card()
        if not c:
            return 0
        n = self.fd.delete_cards([c], ask=ask)
        if n:
            self._after()
        return n

    def add(self) -> int:
        """vcf 사람 줄 [추가] — 그림 없는 명함으로(주소록 가져오기와 같은 `apply_import`)."""
        person, _g = self.current_person()
        d = self._sel()
        if person is None or not d or d[0] != "vcf":
            return 0
        n = P.apply_import(self.fd._store(), [dict(person)])
        if n:
            if not getattr(self.fd, "_dirty", False):
                self.fd.refresh()
            self._after()
        return n

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
        if self.fd.store_card_edit(c, new) is None:
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
        if self.fd.store_card_edit(c, new) is None:
            return False
        if not getattr(self.fd, "_dirty", False):
            self.fd.refresh()
        self._after()
        return True
