# -*- coding: utf-8 -*-
"""명함 환경설정 창 (명함 SOT §5.24.9, 261120-17·-18).

명함찾기 찾기 줄 오른쪽 끝 톱니 단추가 연다. 명함 폴더·전화번호 기본 국가(본 뷰어 환경설정과 같은 값 — 설정 파일)와
'최근' 항목 제한·메일 보내기·메모·구글 주소록(§5.29)(명함 DB meta)을 고친다.
"""
from __future__ import annotations

import os

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, QSpinBox,
                             QGroupBox, QFileDialog, QDialogButtonBox, QRadioButton, QMessageBox)

from viewer.i18n import tr, tr_noop
from viewer.bizcard import people as P

# '최근' 제한 고르기 — (모드, n) · n=0 이면 직접(옆 칸)
LIMIT_CHOICES = (("count", 20), ("count", 0), ("days", 7), ("days", 14), ("days", 0))


class BizcardSettingsDialog(QDialog):
    """host = 명함 창의 호스트(본 뷰어 MainWindow 또는 명함 프로그램 Host). store = 명함 DB(BizcardStore)."""

    def __init__(self, parent=None, host=None, store=None):
        super().__init__(parent)
        from viewer import settings_store
        self._host, self._st = host, store
        prefs = getattr(host, "_prefs", None)
        pic = (prefs or {}).get("picture") if isinstance(prefs, dict) else None
        if not isinstance(pic, dict):
            pic = settings_store.peek_pref("picture") or {}
        self.setWindowTitle(tr("명함 환경설정"))
        self.resize(520, 460)
        v = QVBoxLayout(self)

        g1 = QGroupBox(tr("명함 폴더"))
        r1 = QHBoxLayout(g1)
        self.ed_folder = QLineEdit(str(pic.get("bizcard_folder") or ""))
        self.ed_folder.setReadOnly(True)
        self.ed_folder.setPlaceholderText(tr("지정하지 않음 — '명함 관리' 는 열린 폴더"))
        r1.addWidget(self.ed_folder, 1)
        b_pick = QPushButton(tr("바꾸기"))
        b_pick.clicked.connect(lambda _c=False: self._pick())
        r1.addWidget(b_pick)
        self.btn_move = QPushButton(tr("다른 폴더로 이전"))
        self.btn_move.setToolTip(tr("명함 폴더 안의 모든 것(원본·PDF·정리·인물 사진)을 새 폴더로 옮기고, 명함 기록·해시태그의 경로도 바꿉니다"))
        self.btn_move.clicked.connect(lambda _c=False: self._move())
        self.btn_move.setVisible(callable(getattr(host, "_bizcard_relocate", None)))   # 본 뷰어 안에서 연 창만(§5.12)
        r1.addWidget(self.btn_move)
        b_clr = QPushButton(tr("지우기"))
        b_clr.clicked.connect(lambda _c=False: self.ed_folder.setText(""))
        r1.addWidget(b_clr)
        v.addWidget(g1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel(tr("전화번호 기본 국가:")))
        self.cmb_country = QComboBox()
        self.cmb_country.addItem(tr("한국 — +82 번호를 010-… 국내 꼴로"), "KR")
        self.cmb_country.addItem(tr("지정 안 함 — +82 번호도 국제 꼴 그대로"), "")
        pc = pic.get("phone_country", "KR")
        self.cmb_country.setCurrentIndex(max(0, self.cmb_country.findData(pc if pc in ("KR", "") else "KR")))
        r2.addWidget(self.cmb_country)
        r2.addStretch(1)
        v.addLayout(r2)

        gm = QGroupBox(tr("메일 보내기"))                 # 받는 칸·Gmail 보낼 계정(§5.24.1 'Gmail 보내기', 261120-33)
        fm = QVBoxLayout(gm)
        rm = QHBoxLayout()
        rm.addWidget(QLabel(tr("받는 칸:")))
        self.rb_to, self.rb_bcc = QRadioButton(tr("받는 사람")), QRadioButton(tr("숨은 참조"))
        cur_f = store.meta_get(P.MAIL_FIELD_KEY, None) if store is not None else None
        (self.rb_bcc if cur_f == "bcc" else self.rb_to).setChecked(True)
        rm.addWidget(self.rb_to)
        rm.addWidget(self.rb_bcc)
        rm.addStretch(1)
        fm.addLayout(rm)
        ra = QHBoxLayout()
        ra.addWidget(QLabel(tr("Gmail 보낼 계정:")))
        self.ed_gmail = QLineEdit(str((store.meta_get("gmail_account", None) if store is not None else "") or ""))
        self.ed_gmail.setPlaceholderText(tr("비우면 브라우저의 기본 구글 계정"))
        ra.addWidget(self.ed_gmail, 1)
        fm.addLayout(ra)
        v.addWidget(gm)

        g3 = QGroupBox(tr("'최근' 항목 제한"))
        r3 = QHBoxLayout(g3)
        self.cmb_limit = QComboBox()
        labels = {("count", 20): tr("20개"), ("count", 0): tr("개수 직접"), ("days", 7): tr("1주"),
                  ("days", 14): tr("2주"), ("days", 0): tr("기간 직접")}
        for key in LIMIT_CHOICES:
            self.cmb_limit.addItem(labels[key], key)
        self.spin_limit = QSpinBox()
        self.spin_limit.setRange(1, 9999)
        self.lbl_unit = QLabel("")
        r3.addWidget(self.cmb_limit)
        r3.addWidget(self.spin_limit)
        r3.addWidget(self.lbl_unit)
        r3.addStretch(1)
        note = QLabel(tr("넘는 기록은 지웁니다(명함은 그대로)."))
        v.addWidget(g3)
        v.addWidget(note)
        lim = P.recent_limit(store) if store is not None else dict(P.RECENT_LIMIT_DEFAULT)
        i = self.cmb_limit.findData((lim["mode"], lim["n"]))
        if i < 0:
            i = self.cmb_limit.findData((lim["mode"], 0))
        self.cmb_limit.setCurrentIndex(max(0, i))
        self.spin_limit.setValue(lim["n"])
        self.cmb_limit.currentIndexChanged.connect(lambda _i: self._limit_ui())
        self._limit_ui()

        # 메모(§5.9 '메모 기록'·'메모 날짜', 261120-26·-27) — 명함 DB meta(이 PC), 처음은 둘 다 켬
        from PyQt6.QtWidgets import QCheckBox
        g4 = QGroupBox(tr("메모"))
        r4 = QVBoxLayout(g4)
        self.chk_memo_log = QCheckBox(tr("칸을 고치면 메모 맨 위에 날짜와 고친 칸 이름을 적기"))
        self.chk_memo_log.setToolTip(tr("예: [2026-11-21 수정] 휴대폰·메일 — 옛 값은 적지 않습니다"))
        self.chk_memo_date = QCheckBox(tr("메모를 쓰기 시작하면 맨 앞에 오늘 날짜"))
        self.chk_memo_date.setToolTip(tr("메모가 비었거나 맨 앞에서 쓸 때 — 넣은 날짜는 지워도 됩니다"))
        self.chk_memo_log.setChecked(P.memo_opt(store, P.MEMO_LOG_KEY))
        self.chk_memo_date.setChecked(P.memo_opt(store, P.MEMO_DATE_KEY))
        r4.addWidget(self.chk_memo_log)
        r4.addWidget(self.chk_memo_date)
        v.addWidget(g4)

        self._gsync_ui(v, store)                         # 구글 주소록(§5.29, 261120-36)

        v.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(tr("확인"))
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("취소"))
        bb.accepted.connect(self.apply)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    # ── 폴더 ──
    def _pick(self):
        d = QFileDialog.getExistingDirectory(self, tr("명함 폴더"), self.ed_folder.text() or "")
        if d:
            self.ed_folder.setText(d)

    def _move(self):
        src = self.ed_folder.text().strip()
        if not src or not os.path.isdir(src):
            return
        dst = QFileDialog.getExistingDirectory(self, tr("새 명함 폴더"), os.path.dirname(src))
        if dst:
            new = self._host._bizcard_relocate(src, dst, parent=self)
            if new:
                self.ed_folder.setText(new)

    # ── 최근 제한 ──
    def _limit_ui(self):
        mode, n = self.cmb_limit.currentData()
        self.spin_limit.setVisible(n == 0)
        self.lbl_unit.setText(tr("개") if mode == "count" else tr("일"))
        self.lbl_unit.setVisible(n == 0)

    def limit(self) -> tuple:
        mode, n = self.cmb_limit.currentData()
        return mode, (n or int(self.spin_limit.value()))

    # ── 적용 ──
    def apply(self):
        """두 값은 설정 파일(본 뷰어 안이면 본 뷰어 기억도 함께), '최근' 제한은 명함 DB."""
        from viewer import settings_store
        vals = {"bizcard_folder": self.ed_folder.text().strip(), "phone_country": self.cmb_country.currentData() or ""}
        prefs = getattr(self._host, "_prefs", None)
        if isinstance(prefs, dict) and callable(getattr(self._host, "_save_settings_now", None)):
            pic = prefs.get("picture")
            if not isinstance(pic, dict):
                pic = prefs["picture"] = {}
            pic.update(vals)
            self._host._save_settings_now()
            gate = getattr(self._host, "_gate_api_dependent_ui", None)
            if callable(gate):
                gate(prefs)                            # 명함 아이콘 숨김 판정(§5.24.6)
        else:
            settings_store.set_picture_prefs(vals)
        from viewer.bizcard import phone as PH
        PH.reload()
        if self._st is not None:
            P.set_memo_opt(self._st, P.MEMO_LOG_KEY, self.chk_memo_log.isChecked())     # 261120-26
            P.set_memo_opt(self._st, P.MEMO_DATE_KEY, self.chk_memo_date.isChecked())   # 261120-27
            self._st.meta_set(P.MAIL_FIELD_KEY, "bcc" if self.rb_bcc.isChecked() else "to")   # 261120-33
            self._st.meta_set("gmail_account", self.ed_gmail.text().strip())
            mode, n = self.limit()
            P.set_recent_limit(self._st, mode, n)
            self._gsync_save()                           # 261120-36
        self.accept()

    # ── 구글 주소록(§5.29, 261120-36) — 기본 꺼짐, 클라이언트 ID 는 쓰는 사람이 자기 '개인 모드' 프로젝트에서 ──
    def _gsync_ui(self, v, store):
        from PyQt6.QtWidgets import QCheckBox, QFormLayout
        from viewer.bizcard import gsync as G
        from viewer.bizcard import gsync_auth as A
        g = QGroupBox(tr("구글 주소록"))
        f = QVBoxLayout(g)
        self.lbl_gsync = QLabel("")
        f.addWidget(self.lbl_gsync)
        form = QFormLayout()
        cid, sec = A.client(store) if store is not None else ("", "")
        self.ed_gcid = QLineEdit(cid if cid != A.BUILT_CLIENT_ID else "")
        self.ed_gcid.setPlaceholderText(tr("구글 클라우드 '개인 모드' 프로젝트의 데스크톱 앱 클라이언트 ID"))
        self.ed_gsec = QLineEdit(sec if cid != A.BUILT_CLIENT_ID else "")
        self.ed_gsec.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(tr("클라이언트 ID:"), self.ed_gcid)
        form.addRow(tr("클라이언트 보안 비밀:"), self.ed_gsec)
        f.addLayout(form)
        row = QHBoxLayout()
        self.btn_gconnect = QPushButton(tr("구글 계정 연결"))
        self.btn_gconnect.clicked.connect(lambda _c=False: self.gsync_connect())
        self.btn_gdisconnect = QPushButton(tr("연결 끊기"))
        self.btn_gdisconnect.setToolTip(tr("구글에 연결 권한 철회를 요청하고, 이 PC 에 보관한 토큰과 짝 기록을 지웁니다"))
        self.btn_gdisconnect.clicked.connect(lambda _c=False: self.gsync_disconnect())
        b_help = QPushButton(tr("도움말"))
        b_help.clicked.connect(lambda _c=False: QMessageBox.information(self, tr("구글 주소록"), tr(GSYNC_HELP)))
        for b in (self.btn_gconnect, self.btn_gdisconnect, b_help):
            row.addWidget(b)
        row.addStretch(1)
        f.addLayout(row)
        meta = (lambda k, d: store.meta_get(k, d)) if store is not None else (lambda k, d: d)
        self.chk_gphotos = QCheckBox(tr("인물 사진도 연락처 사진으로 주고받기"))
        self.chk_gphotos.setChecked(bool(meta(G.OPT_PHOTOS, False)))
        self.chk_gdrive = QCheckBox(tr("명함 그림을 구글 드라이브에 원본으로 올리고 연락처에 링크"))
        self.chk_gdrive.setChecked(bool(meta(G.OPT_DRIVE, False)))
        self.ed_gfolder = QLineEdit(str(meta(G.OPT_FOLDER, "") or G.DRIVE_FOLDER_DEFAULT))
        rd = QHBoxLayout()
        rd.addWidget(QLabel(tr("드라이브 폴더:")))
        rd.addWidget(self.ed_gfolder, 1)
        self.chk_gkakao = QCheckBox(tr("구글에 새로 보낼 때 카톡 친구추가 방지(이름 앞 #)"))
        self.chk_gkakao.setToolTip(tr("휴대폰이 구글 주소록을 받아도 카카오톡이 자동 친구로 넣지 않게 — 이미 구글에 있는 연락처는 그대로"))
        self.chk_gkakao.setChecked(G.kakao_new_default(store) if store is not None else True)
        f.addWidget(self.chk_gkakao)
        f.addWidget(self.chk_gphotos)
        f.addWidget(self.chk_gdrive)
        f.addLayout(rd)
        note = QLabel(tr("켜면 명함의 글 칸(과 고른 사진)을 구글 People·Drive API 로만 주고받습니다. 반영 전에는 늘 미리보기를 거칩니다."))
        note.setWordWrap(True)
        f.addWidget(note)
        v.addWidget(g)
        self._gworker = None
        self._gsync_status()

    def _gsync_status(self):
        from viewer.bizcard import gsync_auth as A
        on = A.connected()
        em = A.account_email()
        self.lbl_gsync.setText(tr("연결됨 — {email}").format(email=em) if on and em else
                               (tr("연결됨") if on else tr("연결 안 됨")))
        self.btn_gdisconnect.setEnabled(on)

    def gsync_connect(self, open_url=None) -> bool:
        """[구글 계정 연결] — 칸 값을 저장하고 배경에서 브라우저 로그인을 기다린다."""
        from viewer.bizcard import gsync_auth as A
        from viewer.workers import run_in_thread
        if self._gworker is not None or self._st is None:
            return False
        cid, sec = self.ed_gcid.text().strip(), self.ed_gsec.text().strip()
        if not cid:
            QMessageBox.information(self, tr("구글 주소록"), tr("클라이언트 ID 를 넣으세요 — [도움말] 에 만드는 차례가 있습니다."))
            return False
        if not A.set_client(self._st, cid, sec):
            QMessageBox.information(self, tr("구글 주소록"), tr("이 PC 에서 비밀값을 잠글 수 없어 보안 비밀은 저장하지 않습니다(이번 연결에만 씁니다)."))
        w = LoginWorkerRef(cid, sec, self.chk_gdrive.isChecked(), open_url)
        self._gworker = w
        self.btn_gconnect.setEnabled(False)
        self.lbl_gsync.setText(tr("브라우저에서 구글 로그인을 마치세요…"))
        w.done.connect(self._gsync_logged)
        run_in_thread(w, _GKEEP)
        return True

    def _gsync_logged(self, email, err):
        self._gworker = None
        self.btn_gconnect.setEnabled(True)
        self._gsync_status()
        if err:
            QMessageBox.warning(self, tr("구글 주소록"), tr("구글 계정을 연결하지 못했습니다({err}).").format(err=err))

    def gsync_disconnect(self) -> bool:
        from viewer.bizcard import gsync_auth as A
        from viewer.bizcard import gsync as G
        A.disconnect()
        if self._st is not None:
            G.unlink(self._st)
        self._gsync_status()
        return True

    def _gsync_save(self):
        from viewer.bizcard import gsync as G
        from viewer.bizcard import gsync_auth as A
        A.set_client(self._st, self.ed_gcid.text().strip(), self.ed_gsec.text().strip())
        self._st.meta_set(G.OPT_PHOTOS, bool(self.chk_gphotos.isChecked()))
        self._st.meta_set(G.OPT_KAKAO_NEW, bool(self.chk_gkakao.isChecked()))
        self._st.meta_set(G.OPT_DRIVE, bool(self.chk_gdrive.isChecked()))
        self._st.meta_set(G.OPT_FOLDER, self.ed_gfolder.text().strip() or G.DRIVE_FOLDER_DEFAULT)

    def closeEvent(self, ev):
        if self._gworker is not None:
            self._gworker.stop = True                    # 로그인 기다리기를 그만둔다(창을 닫으면)
        super().closeEvent(ev)

    def reject(self):
        if getattr(self, "_gworker", None) is not None:
            self._gworker.stop = True
        super().reject()


_GKEEP = []
GSYNC_HELP = tr_noop("구글 주소록 연결 — 처음 한 번, 구글 클라우드 콘솔(console.cloud.google.com)에서:\n"
                     "\n"
                     "1. 프로젝트 만들기: 위쪽 프로젝트 고르기 → [새 프로젝트].\n"
                     "2. People API 켜기: 왼쪽 'API 및 서비스 → 라이브러리' 에서 'People API' 를 검색해 [사용](처음 보이는 '사용 설정된 API' 목록에는 켜기 전이라 없습니다). 명함 그림을 드라이브에 올리려면 'Google Drive API' 도 같은 방법으로.\n"
                     "3. 'Google 인증 플랫폼' 시작하기: 앱 이름(예: PolyCardex)·사용자 지원 이메일·연락처 이메일에 본인 Gmail. 대상은 '외부'(개인 Gmail 은 '내부' 를 고를 수 없습니다). 로고·홈페이지·개인정보처리방침·도메인은 비워 둡니다(로고를 올리면 구글 검증 제출이 필요해집니다).\n"
                     "4. 테스트 사용자: 'Google 인증 플랫폼 → 대상 → 테스트 사용자 → [+ Add users]' 에 로그인할 본인 Gmail 을 넣습니다(빠뜨리면 로그인 때 '403 오류: access_denied — 앱은 현재 테스트 중' 이 뜹니다). 테스트 상태에서는 7일마다 다시 연결해야 합니다.\n"
                     "5. 클라이언트 만들기: 'Google 인증 플랫폼 → 클라이언트 → [클라이언트 만들기]' → 애플리케이션 유형 '데스크톱 앱', 이름(예: PolyCardex), 'AI 기반 에이전트에 이 클라이언트 사용' 은 체크하지 않음 → [만들기] → 나온 클라이언트 ID·보안 비밀을 복사합니다.\n"
                     "\n"
                     "그다음 이 창에서:\n"
                     "6. 클라이언트 ID·보안 비밀을 붙여 넣고 [구글 계정 연결] → 브라우저에서 4번에 넣은 계정을 고르고, 'Google 에서 확인하지 않은 앱' 이 뜨면 [계속] → 주소록(드라이브) 권한에 체크 → [계속]. 위쪽에 '연결됨 — (메일)' 이 보이면 [확인] 으로 닫습니다.\n"
                     "7. 싱크: 명함찾기 [주소록] → [구글 주소록과 싱크] → 미리보기에서 바꿀 줄을 고르고 [반영]. 처음에는 몇 줄만 골라 시험해 보세요.\n"
                     "\n"
                     "콘솔에서 바꾼 설정은 반영되는 데 몇 분 걸릴 수 있습니다. 로그인은 구글 화면에서 하고, 이 앱은 구글 비밀번호를 보지 않습니다. 7일이 지나 '연결 안 됨' 이 되면 [구글 계정 연결] 만 다시 누르면 됩니다.")


def LoginWorkerRef(*a):
    from viewer.widgets.bizcard_gsync_dialog import LoginWorker
    return LoginWorker(*a)

