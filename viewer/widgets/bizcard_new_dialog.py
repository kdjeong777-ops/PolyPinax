# -*- coding: utf-8 -*-
"""새 명함 입력 창 (명함 SOT §5.24.1 '새 명함 입력', 261120-15).

명함찾기 아래 줄 [새 명함 입력]·명함 읽기 위 줄 [새 명함 입력] 이 같이 쓴다.
칸(세부 칸과 같은 것) + 명함 그림 앞·뒷면 + 인물 사진 여러 장 → [저장] 이면 배경에서 `people.add_new_card`.
앞면 그림이 없으면 그림 없는 명함(`contact:`), 있으면 명함 읽기 [적용]과 같은 길(정리본 `성명_회사명`).
"""
from __future__ import annotations

import os

from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QPlainTextEdit, QLabel,
                             QPushButton, QListWidget, QFileDialog, QMessageBox, QGroupBox)

from viewer.i18n import tr
from viewer.bizcard import people as P
from viewer.bizcard import phone as PH
from viewer.bizcard import recognize as R

_KEEP = []


class NewCardWorker(QObject):
    """저장(배경) — 그림 쓰기·인물 사진 JPG 가 메인을 세우지 않게(응답성 SOT). done(새 id, 사진 실패 수, 오류 글)."""
    done = pyqtSignal(int, int, str)
    finished = pyqtSignal()

    def __init__(self, db, fields, folder, front, back, photos):
        super().__init__()
        self._a = (db, fields, folder, front, back, list(photos))

    def run(self):
        db, fields, folder, front, back, photos = self._a
        from viewer.bizcard.store import BizcardStore
        st = None
        try:
            st = BizcardStore(db)
            nid, bad = P.add_new_card(st, fields, folder, front, back, photos)
            self.done.emit(int(nid), int(bad), "")
        except Exception as e:                       # 오류 글에 명함 값을 싣지 않는다(§2.1 의 3)
            self.done.emit(0, 0, type(e).__name__)
        finally:
            if st is not None:
                st.close()
            self.finished.emit()


class CopyWorker(QObject):
    """[사진에서 읽기](261120-31) — 고른 사진을 명함 폴더 맨 위에 복사(배경, 원본 그대로, 같은 이름이면 ' (2)').
    done(복사한 경로들, 실패 수)."""
    done = pyqtSignal(list, int)
    finished = pyqtSignal()

    def __init__(self, files, folder):
        super().__init__()
        self._files, self._folder = list(files), folder

    def run(self):
        import shutil
        from pathlib import Path
        from viewer.bizcard.apply import unique_path
        out, bad = [], 0
        try:
            for f in self._files:
                try:
                    dst = unique_path(Path(self._folder), os.path.basename(f), set())
                    shutil.copy2(f, str(dst))
                    out.append(str(dst))
                except Exception:                    # 경로·명함 값은 싣지 않는다(§2.1 의 3)
                    bad += 1
            self.done.emit(out, bad)
        finally:
            self.finished.emit()


def fields_from(texts: dict, memo: str) -> dict:
    """칸 글 → 명함 값(세부 칸 [저장]과 같은 꼴 — 번호 꼴 §5.11, 한글 이름 다듬기, 회사 법인 꼴 뗌)."""
    g = {k: (texts.get(k) or "").strip() for k in ("name", "company", "dept", "title", "cell", "work", "fax",
                                                   "email", "address", "url")}
    for k in ("cell", "work", "fax"):
        g[k] = PH.normalize(g[k])
    name = g["name"]
    if R._HANGUL.search(name) and not R._LATIN.search(name):
        name = R.clean_name_ko(name)
    return {"name": name, "company": R.strip_corp(g["company"]), "dept": g["dept"], "title": g["title"],
            "address": g["address"], "phones": [(k, g[k]) for k in ("cell", "work", "fax") if g[k]],
            "emails": [g["email"]] if g["email"] else [], "urls": [g["url"]] if g["url"] else [],
            "memo": memo or ""}


class NewCardDialog(QDialog):
    """새 명함 입력. folder = 명함 폴더(없으면 그림·인물 사진 고르기 꺼짐). 저장되면 new_id·dupes(같은 사람일 수 있는 id)."""

    def __init__(self, parent=None, db=None, folder: str = ""):
        super().__init__(parent)
        from viewer.widgets.bizcard_find_dialog import FIELDS, MEMO_LABEL, PHONE_KEYS, IMG_FILTER
        PH.reload()
        self._db, self._folder = db, folder or ""
        self._img_filter = tr("그림") + " (%s)" % IMG_FILTER
        self.new_id, self.dupes, self.photo_bad, self.busy = 0, [], 0, False
        self.read_files = []                           # [사진에서 읽기] 로 명함 폴더에 복사한 사진(부르는 쪽이 명함 읽기로 넘긴다)
        self.front_img, self.back_img = "", ""
        self.setWindowTitle(tr("새 명함 입력"))
        self.resize(520, 720)
        v = QVBoxLayout(self)
        form = QFormLayout()
        self.eds = {}
        for k, label in FIELDS:
            ed = QLineEdit()
            if k in PHONE_KEYS:
                PH.attach(ed)
            if k in ("name", "cell"):                   # 세부 칸과 같게 굵게(§5.24.1 '이름 굵게')
                f = ed.font()
                f.setBold(True)
                ed.setFont(f)
            form.addRow(tr(label), ed)
            self.eds[k] = ed
        self.ed_memo = QPlainTextEdit()
        self.ed_memo.setFixedHeight(80)
        form.addRow(tr(MEMO_LABEL), self.ed_memo)
        v.addLayout(form)

        has_folder = bool(self._folder)
        gb = QGroupBox(tr("명함 그림"))
        gl = QFormLayout(gb)
        self.lbl_front, self.lbl_back = QLabel(tr("없음")), QLabel(tr("없음"))
        for side, lbl in (("front", self.lbl_front), ("back", self.lbl_back)):
            row = QHBoxLayout()
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(lbl, 1)
            b_pick = QPushButton(tr("고르기"))
            b_pick.clicked.connect(lambda _c=False, s=side: self.pick_side(s))
            b_pick.setEnabled(has_folder)
            b_clear = QPushButton(tr("빼기"))
            b_clear.clicked.connect(lambda _c=False, s=side: self.set_side(s, ""))
            row.addWidget(b_pick)
            row.addWidget(b_clear)
            setattr(self, "btn_%s" % side, b_pick)
            gl.addRow(tr("앞면") if side == "front" else tr("뒷면"), row)
        v.addWidget(gb)

        gp = QGroupBox(tr("인물 사진"))
        pl = QVBoxLayout(gp)
        self.lst_photos = QListWidget()
        self.lst_photos.setFixedHeight(80)
        pl.addWidget(self.lst_photos)
        prow = QHBoxLayout()
        self.btn_photo_add = QPushButton(tr("사진 추가"))
        self.btn_photo_add.clicked.connect(lambda _c=False: self.pick_photos())
        self.btn_photo_add.setEnabled(has_folder)
        b_del = QPushButton(tr("빼기"))
        b_del.clicked.connect(lambda _c=False: self.remove_photo())
        prow.addWidget(self.btn_photo_add)
        prow.addWidget(b_del)
        prow.addStretch(1)
        pl.addLayout(prow)
        v.addWidget(gp)
        if not has_folder:
            note = QLabel(tr("명함 폴더가 정해지지 않아 명함 그림·인물 사진은 넣을 수 없습니다(환경설정에서 정함)."))
            note.setWordWrap(True)
            v.addWidget(note)

        brow = QHBoxLayout()
        # 261120-31(§5.24.1 '사진에서 읽기'): 명함 사진 여러 장·다중 명함 사진 → 명함 폴더에 복사 → 명함 읽기 확인 표에서 확인
        self.btn_read = QPushButton(tr("사진에서 읽기"))
        self.btn_read.setToolTip(tr("명함 사진 여러 장(한 사진에 여러 장도)을 명함 폴더에 복사하고, 명함 읽기에서 읽어 확인합니다(원본은 그대로)"))
        self.btn_read.clicked.connect(lambda _c=False: self.pick_read())
        self.btn_read.setEnabled(has_folder)
        brow.addWidget(self.btn_read)
        brow.addStretch(1)
        self.btn_save = QPushButton(tr("저장"))
        self.btn_save.clicked.connect(lambda _c=False: self.save())
        b_cancel = QPushButton(tr("취소"))
        b_cancel.clicked.connect(self.reject)
        for b in (self.btn_read, self.btn_save, b_cancel):
            b.setAutoDefault(False)
            b.setDefault(False)
            brow.addWidget(b)
        v.addLayout(brow)

    # ── 그림 ──
    def pick_side(self, side):
        f, _ = QFileDialog.getOpenFileName(self, tr("명함 그림"), "", self._img_filter)
        if f:
            self.set_side(side, f)

    def set_side(self, side, path):
        setattr(self, "%s_img" % side, path or "")
        (self.lbl_front if side == "front" else self.lbl_back).setText(os.path.basename(path) if path else tr("없음"))

    def pick_photos(self):
        files, _ = QFileDialog.getOpenFileNames(self, tr("인물 사진"), "", self._img_filter)
        self.add_photos(files)

    def add_photos(self, files):
        from PyQt6.QtWidgets import QListWidgetItem
        have = set(self.photos())
        for f in files or []:
            if f and f not in have:
                it = QListWidgetItem(os.path.basename(f))   # 이름만 보이고 전체 경로는 마우스를 올리면
                it.setData(Qt.ItemDataRole.UserRole, f)
                it.setToolTip(f)
                self.lst_photos.addItem(it)
                have.add(f)

    def remove_photo(self):
        for it in self.lst_photos.selectedItems() or ([self.lst_photos.item(self.lst_photos.count() - 1)]
                                                      if self.lst_photos.count() else []):
            self.lst_photos.takeItem(self.lst_photos.row(it))

    def photos(self) -> list:
        return [self.lst_photos.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.lst_photos.count())]

    # ── 사진에서 읽기(261120-31) ──
    def pick_read(self):
        files, _ = QFileDialog.getOpenFileNames(self, tr("사진에서 읽기"), "", self._img_filter)
        return self.read_photos(files)

    def read_photos(self, files) -> bool:
        """사진들을 명함 폴더에 복사(배경)한 뒤 창을 닫는다 — 부르는 쪽이 `read_files` 를 명함 읽기로 넘긴다."""
        files = [f for f in files or [] if f and os.path.isfile(f)]
        if not files or self.busy or not self._folder:
            return False
        typed = any(ed.text().strip() for ed in self.eds.values()) or self.ed_memo.toPlainText().strip()
        if typed and QMessageBox.question(self, tr("사진에서 읽기"),
                                          tr("입력한 칸은 저장하지 않습니다 — 사진을 명함 읽기에서 읽을까요?")) \
                != QMessageBox.StandardButton.Yes:
            return False
        from viewer.workers import run_in_thread
        self.busy = True
        for b in (self.btn_read, self.btn_save):
            b.setEnabled(False)
        w = CopyWorker(files, self._folder)
        w.done.connect(self._copied)
        keep = getattr(self.parent(), "_thread_keep", None) if self.parent() is not None else None
        run_in_thread(w, keep if isinstance(keep, list) else _KEEP)
        return True

    def _copied(self, out, bad):
        self.busy = False
        for b in (self.btn_read, self.btn_save):
            b.setEnabled(True)
        if bad:
            QMessageBox.warning(self, tr("사진에서 읽기"), tr("사진 {n}장을 명함 폴더에 복사하지 못했습니다.").format(n=bad))
        if out:
            self.read_files = list(out)
            self.accept()

    # ── 저장 ──
    def fields(self) -> dict:
        return fields_from({k: ed.text() for k, ed in self.eds.items()}, self.ed_memo.toPlainText())

    def save(self) -> bool:
        if self.busy:
            return False
        f = self.fields()
        if not f["name"]:
            QMessageBox.information(self, tr("새 명함 입력"), tr("이름을 넣으세요."))
            return False
        if self.back_img and not self.front_img:
            QMessageBox.information(self, tr("새 명함 입력"), tr("뒷면만 넣을 수는 없습니다 — 앞면 그림을 고르세요."))
            return False
        from viewer.workers import run_in_thread
        self.busy = True
        self.btn_save.setEnabled(False)
        w = NewCardWorker(self._db, f, self._folder, self.front_img, self.back_img, self.photos())
        w.done.connect(self._saved)
        keep = getattr(self.parent(), "_thread_keep", None) if self.parent() is not None else None
        run_in_thread(w, keep if isinstance(keep, list) else _KEEP)
        return True

    def _saved(self, nid, bad, err):
        self.busy = False
        self.btn_save.setEnabled(True)
        if not nid:
            QMessageBox.warning(self, tr("새 명함 입력"), tr("명함을 넣지 못했습니다({err}).").format(err=err))
            return
        from viewer.bizcard.store import BizcardStore
        st = BizcardStore(self._db, ui=True)
        try:
            self.dupes = P.same_person_ids(st, nid)
        finally:
            st.close()
        self.new_id, self.photo_bad = nid, bad
        if bad:
            QMessageBox.warning(self, tr("새 명함 입력"), tr("인물 사진 {n}개를 넣지 못했습니다.").format(n=bad))
        self.accept()
