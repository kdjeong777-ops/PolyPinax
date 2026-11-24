# -*- coding: utf-8 -*-
"""명함 변경 기록·되살리기 창 (명함찾기 SOT §5.30, 261120-64).

기간·종류·출처로 거른 '바뀐 명함' 목록 — 줄을 펼치면 칸마다 `지금 → 되살릴 값`. 체크한 줄만 [되살리기](배경 — 자기 연결).
그 기간 뒤에 또 바뀐 명함은 '그 뒤 또 바뀜' 을 붙이고 처음에 체크를 끈다.
"""
from __future__ import annotations

import json
import time

from PyQt6.QtCore import Qt, QDate, QObject, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTreeWidget, QTreeWidgetItem,
                             QDateEdit, QComboBox, QCheckBox, QMessageBox)

from viewer.i18n import tr, tr_noop
from viewer.bizcard import history as H

_KEEP = []
SRC_LABELS = {"edit": tr_noop("직접"), "sync": tr_noop("싱크"), "merge": tr_noop("합치기"), "kinds": tr_noop("번호 종류"), "split": tr_noop("나누기"),
              "restore": tr_noop("되살리기"), "unhash": tr_noop("# 빼기")}
FIELD_LABELS = (("name", tr_noop("이름")), ("company", tr_noop("회사")), ("dept", tr_noop("부서")), ("title", tr_noop("직함")),
                ("phones", tr_noop("전화")), ("emails", tr_noop("메일")), ("address", tr_noop("주소")), ("urls", tr_noop("누리집")),
                ("memo", tr_noop("메모")), ("tags", tr_noop("해시태그")))


def _txt(v) -> str:
    if isinstance(v, str) and v[:1] == "[":
        try:
            v = json.loads(v)
        except ValueError:
            pass
    if isinstance(v, list):
        v = ", ".join(str(x[-1] if isinstance(x, (list, tuple)) else x) for x in v)
    v = " / ".join(t.strip() for t in str(v or "").splitlines() if t.strip())
    return v if len(v) <= 70 else v[:69] + "…"


class _RestoreWorker(QObject):
    done = pyqtSignal(int)
    finished = pyqtSignal()

    def __init__(self, db, items):
        super().__init__()
        self._db, self._items = db, items

    def run(self):
        n = -1
        st = None
        try:
            from viewer.bizcard.store import BizcardStore
            st = BizcardStore(self._db)
            n = H.restore(st, self._items)
        except Exception:
            n = -1
        finally:
            if st is not None:
                st.close()
            self.done.emit(n)
            self.finished.emit()


class _EntriesWorker(QObject):
    """목록 읽기(`history.entries` — 명함마다 지금 행·그 뒤 기록) — 배경, 자기 연결(261120-68). done(세대, 줄들)."""
    done = pyqtSignal(int, list)
    finished = pyqtSignal()

    def __init__(self, db, gen, args):
        super().__init__()
        self._db, self._gen, self._args = db, gen, args

    def run(self):
        items, st = [], None
        try:
            from viewer.bizcard.store import BizcardStore
            st = BizcardStore(self._db)
            items = H.entries(st, *self._args[:2], kinds=self._args[2], srcs=self._args[3])
        except Exception:
            items = []
        finally:
            if st is not None:
                st.close()
            self.done.emit(self._gen, items)
            self.finished.emit()


class HistoryDialog(QDialog):
    def __init__(self, parent=None, db=None):
        super().__init__(parent)
        self._db = db
        self.setWindowTitle(tr("변경 기록·되살리기"))
        self.resize(760, 560)
        self.items, self.busy, self.last_restored = [], False, None
        self._gen = 0                                    # 목록 읽기 세대 — 늦게 끝난 옛 읽기는 버린다
        v = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel(tr("기간")))
        self.d_from = QDateEdit(QDate.currentDate().addDays(-7))
        self.d_to = QDateEdit(QDate.currentDate())
        for d in (self.d_from, self.d_to):
            d.setCalendarPopup(True)
            d.setDisplayFormat("yyyy-MM-dd")
            d.dateChanged.connect(lambda _d: self.reload())
        top.addWidget(self.d_from)
        top.addWidget(QLabel("~"))
        top.addWidget(self.d_to)
        self.cb_kind = QComboBox()
        for key, label in (("both", tr("지운 것·고친 것")), ("delete", tr("지운 것만")), ("edit", tr("고친 것만"))):
            self.cb_kind.addItem(label, key)
        self.cb_kind.currentIndexChanged.connect(lambda _i: self.reload())
        top.addWidget(self.cb_kind)
        top.addStretch(1)
        v.addLayout(top)
        srow = QHBoxLayout()
        srow.addWidget(QLabel(tr("출처")))
        self.chk_src = {}
        for k in H.SOURCES:
            cb = QCheckBox(tr(SRC_LABELS[k]))
            cb.setChecked(True)
            cb.toggled.connect(lambda _on: self.reload())
            self.chk_src[k] = cb
            srow.addWidget(cb)
        srow.addStretch(1)
        v.addLayout(srow)
        self.lbl = QLabel("")
        self.lbl.setWordWrap(True)
        v.addWidget(self.lbl)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr("명함"), tr("종류"), tr("때"), tr("출처"), ""])
        self.tree.itemChanged.connect(lambda *_a: self._apply_enabled())   # 체크 0개면 [적용] 꺼짐(디자인 SOT §2.7, 261120-78)
        v.addWidget(self.tree, 1)
        brow = QHBoxLayout()
        brow.addStretch(1)
        self.btn_restore = QPushButton(tr("적용"))   # 미리보기 → [적용] 공통(디자인 SOT §2.7, 261120-69)
        self.btn_restore.setToolTip(tr("체크한 명함을 기간이 시작되기 전 모습으로 되살립니다 — 되살리기도 기록에 남아 되돌릴 수 있습니다"))
        self.btn_restore.clicked.connect(lambda _c=False: self.restore())
        b_close = QPushButton(tr("닫기"))
        b_close.clicked.connect(self.reject)
        for b in (self.btn_restore, b_close):
            b.setAutoDefault(False)
            b.setDefault(False)
            brow.addWidget(b)
        v.addLayout(brow)
        self.reload()

    def _range(self):
        a = self.d_from.date()
        b = self.d_to.date().addDays(1)
        t0 = time.mktime((a.year(), a.month(), a.day(), 0, 0, 0, 0, 0, -1))
        t1 = time.mktime((b.year(), b.month(), b.day(), 0, 0, 0, 0, 0, -1)) - 0.001
        return t0, t1

    def _keep(self) -> list:
        par = self.parent()
        keep = getattr(getattr(par, "_mw", None), "_thread_keep", None) if par is not None else None
        return keep if isinstance(keep, list) else _KEEP

    def reload(self):
        """조건으로 목록을 배경에서 다시 읽는다(`_EntriesWorker`, 261120-68) — 끝나면 `_fill`."""
        if self.busy:
            return
        from viewer.workers import run_in_thread
        t0, t1 = self._range()
        kind = self.cb_kind.currentData()
        srcs = {k for k, cb in self.chk_src.items() if cb.isChecked()}
        self._gen += 1
        w = _EntriesWorker(self._db, self._gen, (t0, t1, None if kind == "both" else {kind}, srcs or {"-"}))
        w.done.connect(self._fill)
        run_in_thread(w, self._keep())
        self._entries_worker = w

    def _fill(self, gen, items):
        if gen != self._gen:
            return
        self.items = items
        self.tree.clear()
        for i, e in enumerate(self.items):
            row = e["row"]
            if e.get("note"):                             # 지운 할 일 기록(§5.30 '할 일 기록')
                it = QTreeWidgetItem([" · ".join(x for x in (tr("할 일 기록"), e.get("name") or "", str(row.get("made") or "")) if x),
                                      tr("지움"), time.strftime("%Y-%m-%d %H:%M", time.localtime(e["at"])),
                                      ", ".join(tr(SRC_LABELS.get(s, s)) for s in sorted(e["srcs"])), ""])
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(0, Qt.CheckState.Checked)
                it.setData(0, Qt.ItemDataRole.UserRole, i)
                for ln in [x for x in str(row.get("body") or "").splitlines() if x.strip()][:3]:
                    it.addChild(QTreeWidgetItem([_txt(ln)]))
                self.tree.addTopLevelItem(it)
                continue
            nm = " · ".join(x for x in (row.get("name") or "", row.get("company") or "") if x) or tr("(이름 없음)")
            it = QTreeWidgetItem([nm, tr("지움") if e["kind"] == "delete" else tr("고침"),
                                  time.strftime("%Y-%m-%d %H:%M", time.localtime(e["at"])),
                                  ", ".join(tr(SRC_LABELS.get(s, s)) for s in sorted(e["srcs"])),
                                  tr("그 뒤 또 바뀜") if e["later"] else ""])
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(0, Qt.CheckState.Unchecked if e["later"] else Qt.CheckState.Checked)
            it.setData(0, Qt.ItemDataRole.UserRole, i)
            now = e.get("now") or {}
            for k, lab in FIELD_LABELS:
                old = _txt(row.get(k))
                cur = _txt(now.get(k)) if now else ""
                if old != cur:
                    it.addChild(QTreeWidgetItem(["%s: %s → %s" % (tr(lab), cur or tr("(없음)"), old or tr("(없음)"))]))
            self.tree.addTopLevelItem(it)
        self.tree.resizeColumnToContents(0)
        self.lbl.setText(tr("바뀐 명함 {n}장 — 되살릴 값은 그 기간이 시작되기 전 모습입니다. 지운 그림 명함의 그림 파일은 휴지통에서 되살리세요.").format(
            n=len(self.items)) + "\n" + tr("되살리기도 기록에 남아 이 창에서 되돌릴 수 있습니다."))
        self._apply_enabled()

    def _apply_enabled(self):
        self.btn_restore.setEnabled(not self.busy and bool(self.chosen()))

    def chosen(self) -> list:
        out = []
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if it.checkState(0) == Qt.CheckState.Checked:
                out.append(self.items[it.data(0, Qt.ItemDataRole.UserRole)])
        return out

    def restore(self) -> bool:
        items = self.chosen()
        if self.busy or not items:
            return False
        from viewer.workers import run_in_thread
        self.busy = True
        self.setEnabled(False)
        self._asked = len(items)
        w = _RestoreWorker(self._db, items)
        w.done.connect(self._restored)
        run_in_thread(w, self._keep())
        return True

    def _restored(self, n):
        self.busy = False
        self.setEnabled(True)
        self.last_restored = n
        asked, self._asked = getattr(self, "_asked", n), None
        if n < 0:
            QMessageBox.warning(self, tr("변경 기록·되살리기"), tr("되살리지 못했습니다 — 명함 DB 를 다른 곳에서 쓰고 있는지 확인하세요."))
        else:
            msg = tr("{n}건을 되살렸습니다.").format(n=n)
            if asked is not None and asked > n:            # 탭이 지워진 할 일 기록 등(§5.30 '할 일 기록')
                msg += " " + tr("{m}건은 되살리지 못했습니다(할 일 탭이 지워졌음).").format(m=asked - n)
            QMessageBox.information(self, tr("변경 기록·되살리기"), msg)
        self.reload()

    def reject(self):
        if self.busy:                                    # 되살리는 중엔 닫지 않는다
            return
        super().reject()
