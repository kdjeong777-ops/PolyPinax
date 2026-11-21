# -*- coding: utf-8 -*-
"""명함 환경설정 창 (명함 SOT §5.24.9, 261120-17·-18).

명함찾기 찾기 줄 오른쪽 끝 톱니 단추가 연다. 명함 폴더·전화번호 기본 국가(본 뷰어 환경설정과 같은 값 — 설정 파일)와
'최근' 항목 제한(명함 DB meta)을 고친다.
"""
from __future__ import annotations

import os

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, QSpinBox,
                             QGroupBox, QFileDialog, QDialogButtonBox, QRadioButton)

from viewer.i18n import tr
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
        self.accept()
