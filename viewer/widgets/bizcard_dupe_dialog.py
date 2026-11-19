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

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QListView,
    QAbstractItemView, QPushButton, QSplitter, QTreeWidget, QTreeWidgetItem, QMessageBox, QMenu, QWidget)

from viewer.i18n import tr, tr_noop
from viewer.bizcard import people as P
from viewer.bizcard import vcard as V

ROLE = Qt.ItemDataRole.UserRole
SRC_LABEL = {"card": tr_noop("명함"), "remember": tr_noop("리멤버"), "google": tr_noop("구글"), "contact": tr_noop("주소록")}
WHY_LABEL = {"phone": tr_noop("같은 번호"), "mail": tr_noop("같은 메일"), "typo": tr_noop("번호 오타?"),
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
        st = self.fd._store()
        self.bak = st.path.with_name(st.path.name + ".dupe_bak")
        self.log_path = st.path.with_suffix(".dupe_undo.json")
        self.groups, self.rep, self.chk, self.gchk = [], {}, {}, {}
        self._busy = False
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
        rv.addWidget(self.after)
        split.addWidget(lw)
        split.addWidget(rw)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        v.addWidget(split, 1)
        self.before.currentItemChanged.connect(lambda cur, _p: self._sync(cur, self.after))
        self.after.currentItemChanged.connect(lambda cur, _p: self._sync(cur, self.before))

        bot = QHBoxLayout()
        self.lbl = QLabel()
        bot.addWidget(self.lbl, 1)
        self.btn_apply = QPushButton(tr("합치기 적용"))
        self.btn_apply.clicked.connect(lambda _c=False: self.apply())
        self.btn_undo = QPushButton(tr("마지막 합치기 되돌리기"))
        self.btn_undo.clicked.connect(lambda _c=False: self.undo())
        b_close = QPushButton(tr("닫기"))
        b_close.clicked.connect(lambda _c=False: self.accept())
        for b in (self.btn_apply, self.btn_undo, b_close):
            bot.addWidget(b)
        v.addLayout(bot)
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
        self.rep, self.chk, self.gchk = {}, {}, {}
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
        return P.merge_plan(cards, self.groups[gi].get("manual")) if self.gchk.get(gi) and len(cards) >= 2 else None

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
            for k, label in SHOW:
                val = _val(p["fields"], k)
                if not val:
                    continue
                frm = p["frm"].get(k)
                src = tr(SRC_LABEL[g["src"][frm]]) if frm else (tr("모두") if k in ("phones", "emails", "urls", "memo") else "")
                it = QTreeWidgetItem([tr(label), val.replace("\n", " ⏎ "), src])
                it.setData(0, ROLE, (gi, k))
                if val != _val(rep, k):
                    f = it.font(1)
                    f.setBold(True)
                    it.setFont(1, f)
                top.addChild(it)
            top.setExpanded(True)
        for i in range(self.after.columnCount()):
            self.after.resizeColumnToContents(i)
        self.lbl.setText(tr("묶음 {g}개 · 합칠 묶음 {n}개 · 지울 명함 {d}장").format(g=len(self.groups), n=n_g, d=n_d))
        self.btn_apply.setEnabled(n_g > 0)

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
        if it is None or it.parent() is None:
            return
        gi, cid = it.data(0, ROLE)
        m = QMenu(self)
        m.addAction(tr("대표로"), lambda: self.set_rep(gi, cid))
        m.exec(self.before.viewport().mapToGlobal(pos))

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
        st = self.fd._store()
        self._drop_old_hold()
        self.setEnabled(False)
        try:
            return self._apply(st, plans, ask)
        finally:
            self.setEnabled(True)

    def _apply(self, st, plans, ask) -> int:
        dbp, bak = st.path, self.bak
        self._bg(lambda: _copy_db(dbp, bak))                  # 적용 전 DB 백업(되돌리기) — 배경(응답성 SOT)
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
                self.fd._retag(paths, set(), p["fields"]["tags"])
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
        self._bg(write)
        self.last_failed = failed
        if failed and ask:
            QMessageBox.warning(self, tr("중복 검토"), tr("파일 {n}개를 옮기지 못했습니다 — 다른 프로그램이 열고 있는지 확인하세요.").format(n=failed))
        self.reload()
        return len(plans)

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
        if not (self.log_path.exists() and self.bak.exists()):
            return False
        if ask and QMessageBox.question(self, tr("중복 검토"), tr("마지막 합치기를 되돌립니다 — 옮긴 파일을 제자리로, 명함 DB 를 합치기 전으로.")) \
                != QMessageBox.StandardButton.Yes:
            return False
        try:
            moves = json.load(open(self.log_path, encoding="utf-8")).get("moves") or []
        except (OSError, ValueError):
            moves = []
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
        self.setEnabled(False)
        try:
            self._bg(restore)
        finally:
            self.setEnabled(True)
        self.reload()
        return True

    def _bg(self, fn):
        """배경 스레드에서 fn — 끝날 때까지 `QEventLoop` 로 기다려 창이 멈추지 않게(응답성 SOT §6, 병합 `_merge_pdfs` 와 같은 꼴).
        그동안 창은 꺼 둔다(부르는 쪽). 예외는 그대로 올린다."""
        import threading
        from PyQt6.QtCore import QEventLoop, QTimer
        box = {}

        def run():
            try:
                box["r"] = fn()
            except Exception as e:              # noqa: BLE001 — 메인에서 다시 올린다
                box["e"] = e
        t = threading.Thread(target=run, daemon=True, name="bizcard-dupe")
        loop = QEventLoop()
        tick = QTimer()
        tick.setInterval(20)
        tick.timeout.connect(lambda: t.is_alive() or loop.quit())
        t.start()
        tick.start()
        loop.exec()
        tick.stop()
        t.join()
        if "e" in box:
            raise box["e"]
        return box.get("r")
