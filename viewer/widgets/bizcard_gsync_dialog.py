# -*- coding: utf-8 -*-
"""구글 주소록 싱크 — 로그인 일꾼·미리보기 창 (명함 SOT §5.29 '연결'·'미리보기', 261120-36).

[구글 주소록과 싱크](명함찾기 ≡ 메뉴 '주소록 ▸') → 배경에서 구글 목록을 받아 계획만 세움 → 갈래별 줄·체크 → [반영] 을 눌러야 바뀐다.
네트워크·DB 쓰기는 모두 배경 일꾼(응답성 SOT §4). 오류 글에 명함 값·토큰을 싣지 않는다(§2.1 의 3).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTreeWidget, QTreeWidgetItem,
                             QMessageBox, QProgressBar, QCheckBox)

from viewer.i18n import tr, tr_noop
from viewer.bizcard import gsync as G

_KEEP = []
KIND_LABELS = {G.NEW_CARD: tr_noop("구글에서 가져옴(새 명함)"), G.NEW_GOOGLE: tr_noop("구글로 보냄(새 연락처)"),
               G.TO_CARD: tr_noop("명함을 구글 값으로 고침"), G.TO_GOOGLE: tr_noop("구글을 명함 값으로 고침"),
               G.GONE_GOOGLE: tr_noop("구글에서 지워짐 — 명함도 지울까요"), G.GONE_CARD: tr_noop("명함에서 지워짐 — 구글도 지울까요"),
               G.MERGED_GOOGLE: tr_noop("명함 합치기로 남은 구글 연락처 — 구글에서 지울까요"),
               G.GOOGLE_EXTRA: tr_noop("구글에만 있음(명함에 없음) — 구글에서 지울까요"),
               G.PHOTO_UP: tr_noop("인물 사진을 연락처 사진으로"), G.PHOTO_DOWN: tr_noop("연락처 사진을 인물 사진으로"),
               G.DRIVE_UP: tr_noop("명함 그림·인물 사진을 드라이브에"), "link": tr_noop("같은 사람으로 짝지음(값 같음)"),
               G.KAKAO_UP: tr_noop("카톡 친구추가 방지 바꿈(구글 이름 앞 #)"),
               G.KAKAO_FIX: tr_noop("# 바로잡기 — 예전 구글 연락처의 이름 앞 # 뗌"),
               G.KAKAO_DOWN: tr_noop("카톡 친구추가 방지 표시를 구글 이름대로"),
               G.GONE_VALUE: tr_noop("구글에서 지운 값 — 명함에서도 지울까요(안 고르면 구글로 다시)"),
               G.PHOTO_GONE: tr_noop("명함에서 지운 인물 사진 — 구글 연락처 사진도 지울까요"),
               G.LABELS: tr_noop("라벨·해시태그 맞춤"), G.LABEL_GONE: tr_noop("고른 목록에서 뺀 구글 라벨 — 지울까요(연락처는 그대로)")}
FIELD_LABELS = {"name": tr_noop("이름"), "company": tr_noop("회사"), "dept": tr_noop("부서"), "title": tr_noop("직함"),
                "phones": tr_noop("전화"), "emails": tr_noop("메일"), "address": tr_noop("주소"), "urls": tr_noop("누리집"),
                "memo": tr_noop("메모")}


def _field(f: str) -> str:
    return tr(FIELD_LABELS[f]) if f in FIELD_LABELS else f


def _api(store):
    from viewer.bizcard import gsync_auth as A
    from viewer.bizcard.gsync_api import Api
    cid, sec = A.client(store)
    return Api(lambda: A.access_token(cid, sec))


class MediaWorker(QObject):
    """2단계 사진·드라이브(배경, 명함 SOT §5.29 '단계', 261120-71) — 대기열을 한 사람씩. progressed(i, n) · done(결과).
    stop() 하면 그 사람 뒤에 멈춘다(남은 것은 대기열 — 다음에 열 때 이어서)."""
    progressed = pyqtSignal(int, int)
    done = pyqtSignal(dict)
    finished = pyqtSignal()

    def __init__(self, db, folder, drive_folder):
        super().__init__()
        self._a = (db, folder, drive_folder)
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        from viewer.bizcard.store import BizcardStore
        db, folder, dfolder = self._a
        st = None
        try:
            st = BizcardStore(db)
            res = G.run_media(st, _api(st), folder, dfolder, progress=lambda i, n: self.progressed.emit(i, n),
                              should_stop=lambda: self._stop)
        except Exception as e:
            res = {"done": 0, "failed": 0, "reasons": {}, "left": -1, "error": type(e).__name__}
        finally:
            if st is not None:
                st.close()
        self.done.emit(res)
        self.finished.emit()


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

    def __init__(self, db, folder, photos, drive, card_first=False):
        super().__init__()
        self._a = (db, folder, photos, drive)
        self._card_first = bool(card_first)

    def run(self):
        from viewer.bizcard.store import BizcardStore
        db, folder, photos, drive = self._a
        st = None
        try:
            st = BizcardStore(db)
            api = _api(st)
            people = api.list_people()
            groups = api.list_groups() if (G.label_tags(st) or st.meta_get(G.META_LABEL_GROUPS, {})) else None   # 라벨(261120-61)
            rows = G.plan(st, people, folder, photos=photos, drive=drive, card_first=self._card_first, groups=groups)
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


KAKAO_WHY = {"google_src": tr_noop("구글에서 가져온 명함"), "google_name": tr_noop("구글 이름을 따른 표시"),
             "linked": tr_noop("예전 구글 연락처와 짝"), "same_mobile": tr_noop("같은 휴대폰이 예전 구글 연락처에"),
             "user": tr_noop("직접 정한 표시"), "off": tr_noop("설정에서 끔"), "auto": tr_noop("지난 싱크의 표시")}
WHY_LABELS = {"quota": tr_noop("드라이브 저장 공간 부족 {n}건"), "auth": tr_noop("권한 없음 {n}건"),
              "limit": tr_noop("구글 한도 초과 {n}건"), "net": tr_noop("연결 안 됨 {n}건"), "other": tr_noop("그 밖 {n}건")}


def fail_text(res) -> str:
    """[적용] 뒤 못 한 것 — 까닭별(명함 SOT §5.29 '못 올렸을 때', 261120-70). 값은 싣지 않는다."""
    msg = tr("{ok}건 적용, {bad}건은 하지 못했습니다(다음 싱크에서 다시 보입니다).").format(ok=res.get("done", 0), bad=res.get("failed", 0))
    why = res.get("reasons") or {}
    parts = [tr(WHY_LABELS[k]).format(n=why[k]) for k in WHY_LABELS if why.get(k)]
    if parts:
        msg += "\n" + tr("까닭: {list}").format(list=" · ".join(parts))
    if why.get("quota"):                                      # 2단계가 멈춤 — 대기열 그대로, 다음에 열 때 이어서(261120-71)
        msg += "\n" + tr("구글 드라이브 공간을 비운 뒤 명함찾기를 다시 열면 남은 사진·명함 그림을 이어서 올립니다.")
    elif res.get("left", 0) > 0:
        msg += "\n" + tr("남은 {n}건은 다음에 명함찾기를 열 때 이어서 올립니다.").format(n=res["left"])
    return msg


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
        self._card_first = False
        self.chk_card_first = QCheckBox(tr("명함 기준으로 올리기"))   # §5.29 '명함 기준으로 올리기'(261120-59)
        self.chk_card_first.setToolTip(tr("명함 값이 이깁니다 — 구글에서 지워진 사람은 새 연락처로 다시 만들고, 구글 → 명함으로 고치거나 가져오는 줄은 만들지 않습니다"))
        self.chk_card_first.toggled.connect(self._toggle_card_first)
        v.addWidget(self.chk_card_first)
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
        self.btn_apply = QPushButton(tr("적용"))   # 미리보기 → [적용] 공통(디자인 SOT §2.7, 261120-69)
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

    def _toggle_card_first(self, on):
        if self.busy:
            self.chk_card_first.blockSignals(True)
            self.chk_card_first.setChecked(not on)
            self.chk_card_first.blockSignals(False)
            return
        self._card_first = bool(on)
        self.btn_apply.setEnabled(False)
        self.tree.clear()
        self.lbl.setText(tr("구글 주소록을 받는 중…"))
        self.load()

    def load(self):
        from viewer.workers import run_in_thread
        self.busy = True
        w = PlanWorker(self._db, self._folder, *self._opts, card_first=self._card_first)
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
            for r in items:
                txt = r.get("name") or tr("(이름 없음)")
                if r.get("fields"):
                    txt += "  — " + ", ".join(_field(f) for f in r["fields"])
                if r.get("txt"):                                  # 라벨 줄 — +라벨·−라벨(라벨 이름은 데이터)
                    txt += "  — " + r["txt"].replace("구글 ", tr("구글") + " ", 1).replace("해시태그 ", tr("해시태그") + " ", 1)
                if r.get("maybe_dup"):
                    txt += "  — " + tr("구글에 이미 있을 수 있음")
                if r["kind"] in (G.NEW_GOOGLE, G.KAKAO_FIX) and r.get("kakao_why"):   # '#' 까닭(§5.29 '카톡', 261120-72)
                    if r.get("kakao"):
                        txt += "  — " + tr("# 붙임")
                    else:
                        txt += "  — " + tr("# 없음 — {why}").format(why=tr(KAKAO_WHY.get(r["kakao_why"], KAKAO_WHY["off"])))
                sd = r.get("side") or ""
                if sd:                                            # 드라이브 줄 — 무엇을 올리는지(§5.29 '드라이브')
                    txt += "  — " + (tr("명함 앞면") if sd == "front" else tr("명함 뒷면") if sd == "back"
                                     else tr("인물 사진 {n}").format(n=sd[5:]))
                if r.get("new"):                                  # 새 연락처와 같은 [적용] 에서(261120-70)
                    txt += "  — " + tr("새 연락처와 함께")
                if r.get("retry"):                                # 지난번 못 올림(§5.29 '못 올렸을 때')
                    txt += "  — " + tr("지난번 못 올림")
                it = QTreeWidgetItem([txt])
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(0, Qt.CheckState.Checked if G.row_default(r) else Qt.CheckState.Unchecked)
                it.setData(0, Qt.ItemDataRole.UserRole, rows.index(r))
                for f, old, new in r.get("changes") or []:          # 칸마다 옛 값 → 새 값(§5.29 '미리보기', 261120-46)
                    it.addChild(QTreeWidgetItem(["%s: %s → %s" % (_field(f), old or tr("(없음)"), new or tr("(없음)"))]))
                top.addChild(it)
            self.tree.addTopLevelItem(top)
        total = sum(cnt.values())
        msg = (tr("바뀔 것 {n}건 — 줄을 골라 [적용] 을 누르면 바뀝니다(지워진 것은 처음에 '남김').").format(n=total)
               if total else tr("구글 주소록과 명함이 같습니다 — 바꿀 것이 없습니다."))
        if any(r["kind"] in G.GOOGLE_WRITES for r in rows):
            msg += "\n" + tr("구글 주소록이 바뀝니다 — [적용] 전에 contacts.google.com → 내보내기로 백업해 두기를 권합니다.")
        self.lbl.setText(msg)
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

    def to_apply(self) -> list:
        """[적용] 에 넘길 줄 — 체크한 것 + 체크하지 않은 지워짐은 짝만 풀기, 체크하지 않은 '구글에서 지운 값' 은 명함 값을 구글로 다시
        (§5.29 '지운 것'·'구글에서 지운 값', 261120-62). 갈래 차례대로(명함 고침이 구글로 다시보다 먼저)."""
        out = []
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                it = top.child(j)
                r = self.rows[it.data(0, Qt.ItemDataRole.UserRole)]
                if it.checkState(0) == Qt.CheckState.Checked:
                    out.append(r)
                elif r["kind"] in G.UNLINK_IF_KEPT:
                    out.append(dict(r, kind="unlink", was=r["kind"]))   # 무엇을 남겼나 — 구글에만 둘 것 기억(261122-8)
                elif r["kind"] == G.GONE_VALUE:
                    out.append(dict(r, kind=G.TO_GOOGLE))
        order = {k: n for n, k in enumerate(G.KINDS + ("link", "unlink"))}
        return sorted(out, key=lambda r: order.get(r["kind"], 99))

    def apply(self) -> bool:
        rows = self.to_apply()
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
            QMessageBox.warning(self, tr("구글 주소록과 싱크"), fail_text(res))
        elif res.get("queued"):                               # 1단계 끝 — 사진·드라이브는 배경에서(§5.29 '단계', 261120-71)
            QMessageBox.information(self, tr("구글 주소록과 싱크"), tr(
                "글 자료 {n}건을 적용했습니다. 사진·명함 그림 {m}건은 명함찾기 아래 줄에서 이어 올립니다 — 창을 닫아도 다음에 열 때 이어서 올립니다.").format(
                n=res.get("done", 0), m=res.get("queued", 0)))
        self.accept()
