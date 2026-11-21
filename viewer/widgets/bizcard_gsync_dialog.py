# -*- coding: utf-8 -*-
"""구글 주소록 싱크 — 로그인 일꾼·미리보기 창 (명함 SOT §5.29 '연결'·'미리보기', 261120-36).

[구글 주소록과 싱크](명함찾기 [주소록] 메뉴) → 배경에서 구글 목록을 받아 계획만 세움 → 갈래별 줄·체크 → [반영] 을 눌러야 바뀐다.
네트워크·DB 쓰기는 모두 배경 일꾼(응답성 SOT §4). 오류 글에 명함 값·토큰을 싣지 않는다(§2.1 의 3).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTreeWidget, QTreeWidgetItem,
                             QMessageBox, QProgressBar)

from viewer.i18n import tr, tr_noop
from viewer.bizcard import gsync as G

_KEEP = []
KIND_LABELS = {G.NEW_CARD: tr_noop("구글에서 가져옴(새 명함)"), G.NEW_GOOGLE: tr_noop("구글로 보냄(새 연락처)"),
               G.TO_CARD: tr_noop("명함을 구글 값으로 고침"), G.TO_GOOGLE: tr_noop("구글을 명함 값으로 고침"),
               G.GONE_GOOGLE: tr_noop("구글에서 지워짐 — 명함도 지울까요"), G.GONE_CARD: tr_noop("명함에서 지워짐 — 구글도 지울까요"),
               G.PHOTO_UP: tr_noop("인물 사진을 연락처 사진으로"), G.PHOTO_DOWN: tr_noop("연락처 사진을 인물 사진으로"),
               G.DRIVE_UP: tr_noop("명함 그림을 드라이브에"), "link": tr_noop("같은 사람으로 짝지음(값 같음)"),
               G.KAKAO_UP: tr_noop("카톡 친구추가 방지 바꿈(구글 이름 앞 #)"),
               G.KAKAO_DOWN: tr_noop("카톡 친구추가 방지 표시를 구글 이름대로")}


def _api(store):
    from viewer.bizcard import gsync_auth as A
    from viewer.bizcard.gsync_api import Api
    cid, sec = A.client(store)
    return Api(lambda: A.access_token(cid, sec))


class LoginWorker(QObject):
    """구글 계정 연결(배경) — 브라우저 로그인을 기다린다. done(계정 메일, 오류 갈래)."""
    done = pyqtSignal(str, str)
    finished = pyqtSignal()

    def __init__(self, cid, secret, drive, open_url=None):
        super().__init__()
        self._a = (cid, secret, drive, open_url)
        self.stop = False

    def run(self):
        from viewer.bizcard import gsync_auth as A
        cid, sec, drive, op = self._a
        try:
            email = A.login(cid, sec, drive, open_url=op, cancel=lambda: self.stop)
            self.done.emit(email or "", "")
        except Exception as e:
            self.done.emit("", str(e) if isinstance(e, A.AuthError) else type(e).__name__)
        finally:
            self.finished.emit()


class PlanWorker(QObject):
    """구글 목록 받기 + 계획(배경). done(줄들, 사람들, 오류 갈래)."""
    done = pyqtSignal(list, list, str)
    finished = pyqtSignal()

    def __init__(self, db, folder, photos, drive):
        super().__init__()
        self._a = (db, folder, photos, drive)

    def run(self):
        from viewer.bizcard.store import BizcardStore
        db, folder, photos, drive = self._a
        st = None
        try:
            st = BizcardStore(db)
            people = _api(st).list_people()
            rows = G.plan(st, people, folder, photos=photos, drive=drive)
            self.done.emit(rows, people, "")
        except Exception as e:
            self.done.emit([], [], str(e) if str(e).startswith("http") else type(e).__name__)
        finally:
            if st is not None:
                st.close()
            self.finished.emit()


class ApplyWorker(QObject):
    """고른 줄 반영(배경). progressed(i, n) · done(결과 사전)."""
    progressed = pyqtSignal(int, int)
    done = pyqtSignal(dict)
    finished = pyqtSignal()

    def __init__(self, db, rows, people, folder, drive_folder):
        super().__init__()
        self._a = (db, rows, people, folder, drive_folder)

    def run(self):
        from viewer.bizcard.store import BizcardStore
        db, rows, people, folder, dfolder = self._a
        st = None
        try:
            st = BizcardStore(db)
            res = G.apply(st, _api(st), rows, folder, dfolder, progress=lambda i, n: self.progressed.emit(i, n),
                          people=people)
            self.done.emit(res)
        except Exception as e:
            self.done.emit({"done": 0, "failed": len(rows), "delete_cards": [], "error": type(e).__name__})
        finally:
            if st is not None:
                st.close()
            self.finished.emit()


class GSyncDialog(QDialog):
    """미리보기 창. 반영 뒤 result = gsync.apply 결과(지울 명함 id 는 부르는 쪽이 휴지통 길로)."""

    def __init__(self, parent=None, db=None, folder: str = "", photos: bool = False, drive: bool = False,
                 drive_folder: str = G.DRIVE_FOLDER_DEFAULT, start: bool = True):
        super().__init__(parent)
        self._db, self._folder, self._dfolder = db, folder or "", drive_folder or G.DRIVE_FOLDER_DEFAULT
        self._opts = (photos, drive)
        self.rows, self.people, self.result, self.busy = [], [], None, False
        self.setWindowTitle(tr("구글 주소록과 싱크"))
        self.resize(640, 560)
        v = QVBoxLayout(self)
        self.lbl = QLabel(tr("구글 주소록을 받는 중…"))
        self.lbl.setWordWrap(True)
        v.addWidget(self.lbl)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        v.addWidget(self.tree, 1)
        self.bar = QProgressBar()
        self.bar.setVisible(False)
        v.addWidget(self.bar)
        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_apply = QPushButton(tr("반영"))
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(lambda _c=False: self.apply())
        b_close = QPushButton(tr("닫기"))
        b_close.clicked.connect(self.reject)
        for b in (self.btn_apply, b_close):
            b.setAutoDefault(False)
            b.setDefault(False)
            row.addWidget(b)
        v.addLayout(row)
        if start:
            self.load()

    def _keep(self):
        k = getattr(self.parent(), "_thread_keep", None) if self.parent() is not None else None
        return k if isinstance(k, list) else _KEEP

    def load(self):
        from viewer.workers import run_in_thread
        self.busy = True
        w = PlanWorker(self._db, self._folder, *self._opts)
        w.done.connect(self._planned)
        run_in_thread(w, self._keep())

    def _planned(self, rows, people, err):
        self.busy = False
        if err:
            self.lbl.setText(tr("구글에 연결하지 못했습니다({err}). 명함 환경설정에서 연결을 확인하세요.").format(err=err))
            return
        self.rows, self.people = rows, people
        self.tree.clear()
        cnt = G.counts(rows)
        for kind in G.KINDS + ("link",):
            items = [r for r in rows if r["kind"] == kind]
            if not items:
                continue
            top = QTreeWidgetItem([tr(KIND_LABELS[kind]) + "  (%d)" % len(items)])
            top.setFlags(top.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
            on = Qt.CheckState.Checked if (G.DEFAULT_ON.get(kind, True)) else Qt.CheckState.Unchecked
            for r in items:
                txt = r.get("name") or tr("(이름 없음)")
                if r.get("fields"):
                    txt += "  — " + ", ".join(r["fields"])
                it = QTreeWidgetItem([txt])
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(0, on)
                it.setData(0, Qt.ItemDataRole.UserRole, rows.index(r))
                top.addChild(it)
            self.tree.addTopLevelItem(top)
        total = sum(cnt.values())
        self.lbl.setText(tr("바뀔 것 {n}건 — 줄을 골라 [반영] 을 누르면 바뀝니다(지워진 것은 처음에 '남김').").format(n=total)
                         if total else tr("구글 주소록과 명함이 같습니다 — 바꿀 것이 없습니다."))
        self.btn_apply.setEnabled(bool(total))

    def chosen(self) -> list:
        out = []
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                it = top.child(j)
                if it.checkState(0) == Qt.CheckState.Checked:
                    out.append(self.rows[it.data(0, Qt.ItemDataRole.UserRole)])
        return out

    def apply(self) -> bool:
        rows = self.chosen()
        if self.busy or not rows:
            return False
        from viewer.workers import run_in_thread
        self.busy = True
        self.btn_apply.setEnabled(False)
        self.bar.setVisible(True)
        self.bar.setRange(0, len(rows))
        w = ApplyWorker(self._db, rows, self.people, self._folder, self._dfolder)
        w.progressed.connect(lambda i, n: self.bar.setValue(i))
        w.done.connect(self._applied)
        run_in_thread(w, self._keep())
        return True

    def _applied(self, res):
        self.busy = False
        self.result = res
        if res.get("failed"):
            QMessageBox.warning(self, tr("구글 주소록과 싱크"),
                                tr("{ok}건 반영, {bad}건은 하지 못했습니다(다음 싱크에서 다시 보입니다).").format(
                                    ok=res.get("done", 0), bad=res.get("failed", 0)))
        self.accept()
