"""명함 들이기 — 폴더 훑기 + 배경 인식 (명함 SOT §5.10, P2).

`scan_folder(folder)` 는 파일 시스템만 본다(빠름). `ImportWorker` 는 차례로 인식하고 결과를 `bizcard.db` 의
`recog` 캐시에 남긴다 — 다시 열면 캐시에서 곧바로. ★ 명함 글은 로그·예외 메시지에 싣지 않는다(§2.1).
"""
from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import threading

from PyQt6.QtCore import QObject, pyqtSignal

from viewer.bizcard import recognize as R

PDF_DIR = "pdf"
OUT_DIR = "정리"          # 정리본 기본 폴더 이름(D10) — 훑기에서 뺀다


@dataclass
class CardItem:
    key: str                     # 원천 열쇠 = 원본 PDF, 없으면 앞면 그림
    base: str                    # 묶음 이름(파일 이름 앞부분)
    front: str = ""              # 앞면 그림(없을 수 있다 — PDF 만)
    back: str = ""
    pdf: str = ""
    scanned: str = ""            # YYYY-MM-DD (D7 — 원천 파일 날짜)
    sig: str = ""
    result: dict = field(default_factory=dict)
    edit: dict = field(default_factory=dict)


def _date_of(paths) -> str:
    ts = []
    for p in paths:
        if p:
            try:
                ts.append(os.path.getmtime(p))
            except OSError:
                pass
    return time.strftime("%Y-%m-%d", time.localtime(min(ts))) if ts else ""


def _split(stem: str):
    for suf in R.FRONT_SUFFIXES:
        if stem.endswith(suf):
            return stem[: -len(suf)], "front"
    for suf in R.BACK_SUFFIXES:
        if stem.endswith(suf):
            return stem[: -len(suf)], "back"
    return stem, "front"


def scan_folder(folder) -> list:
    """폴더(하위는 `pdf\\` 만) → [CardItem], 이름 차례. PDF 가 있는 명함의 PNG 짝은 원천으로 쓰지 않는다."""
    folder = Path(folder)
    groups = {}
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    for n in names:
        p = folder / n
        if p.is_file() and p.suffix.lower() == ".pdf":
            groups.setdefault(p.stem, {}).setdefault("pdf", str(p))    # 261117-9: 원본 PDF 가 그림 옆에 있어도(사용자가 옮김)
            continue
        if not p.is_file() or p.suffix.lower() not in R.IMG_EXTS:
            continue
        base, side = _split(p.stem)
        g = groups.setdefault(base, {})
        g.setdefault(side, str(p))           # 같은 면이 여럿이면 이름 차례 첫째
    pdir = folder / PDF_DIR
    if pdir.is_dir():
        for n in sorted(os.listdir(pdir)):
            p = pdir / n
            if p.is_file() and p.suffix.lower() == ".pdf":
                groups.setdefault(p.stem, {}).setdefault("pdf", str(p))
    out = []
    for base in sorted(groups):
        g = groups[base]
        if not (g.get("front") or g.get("pdf")):
            continue                          # 뒷면만 있는 묶음은 건너뛴다
        key = g.get("pdf") or g.get("front")
        out.append(CardItem(key=key, base=base, front=g.get("front", ""), back=g.get("back", ""),
                            pdf=g.get("pdf", ""), scanned=_date_of([g.get("pdf"), g.get("front")])))
    return out


def result_dict(res: "R.CardResult") -> dict:
    d = asdict(res)
    d["phones"] = [list(x) for x in res.phones]
    return d


class ImportWorker(QObject):
    """차례로 인식 — 한 장마다 `itemDone(index, result, edit)`. 캐시에 있으면 읽지 않는다.
    `workers.run_in_thread` 로 돌린다(응답성 SOT §4.3 — QThread 를 직접 상속하지 않는다)."""
    itemDone = pyqtSignal(int, dict, dict)
    progressed = pyqtSignal(int, int)
    finishedAll = pyqtSignal(bool)        # True = 끝까지, False = 멈춤
    finished = pyqtSignal()               # run_in_thread 가 스레드를 닫는 신호

    def __init__(self, items: list, db=None, ui_lang: str = "ko", force: bool = False, rows=None):
        """force = 캐시를 건너뛰고 다시 읽기(261117-15 [다시 읽기]), rows = 신호에 실을 표 줄 번호(없으면 차례)."""
        super().__init__()
        self._items = list(items)
        self._force = bool(force)
        self._rows = list(rows) if rows is not None else list(range(len(self._items)))
        self._db = db
        self._lang = ui_lang
        self._stop = False
        self.done_event = threading.Event()   # 창을 닫을 때 기다린다

    def request_cancel(self):
        self._stop = True

    def run(self):
        try:
            self._run()
        finally:
            self.done_event.set()
            self.finished.emit()

    def _run(self):
        import time as _t
        from viewer.bizcard.store import BizcardStore, source_sig
        st = BizcardStore(self._db)
        try:
            n = len(self._items)
            for i, it in enumerate(self._items):
                if self._stop:
                    self.finishedAll.emit(False)
                    return
                sig = source_sig([it.pdf, it.front, it.back])
                hit = None if self._force else st.recog_get(it.key, sig)
                if hit is None:
                    try:
                        res = result_dict(R.recognize(it.front or it.pdf, ui_lang=self._lang))
                    except Exception as e:        # 명함 글은 싣지 않는다 — 몇 번째·종류만
                        res = {"error": type(e).__name__}
                    old = st.recog_get(it.key, sig) if self._force else None
                    st.recog_put(it.key, sig, res)
                    keep = (old or {}).get("edit") or {}          # 다시 읽어도 손으로 고친 칸은 지킨다(창이 거른 것)
                    if keep:
                        st.edit_put(it.key, keep)
                    hit = {"result": res, "edit": keep}
                self.itemDone.emit(self._rows[i], hit["result"], hit["edit"] or {})
                self.progressed.emit(i + 1, n)
                _t.sleep(0.001)                   # 응답성 SOT §4 ④ — 메인에 숨 쉴 틈
            self.finishedAll.emit(True)
        finally:
            st.close()
