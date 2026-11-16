# -*- coding: utf-8 -*-
"""261116-5(책갈피창·저장 SOT §4.7.29): 책갈피창 '목차 페이지 만들기' 의 앱 길 — 목차는 1쪽(표지) 뒤, 2쪽부터(덧붙임 2).

저장 안 한 편집 막기 → 배경으로 읽기(`toc_page.probe` — 옛 목차·책갈피·암호) → 옛 목차면 바꿀지 묻기 → 창 →
배경으로 새 임시 PDF(`toc_page.insert_toc`) → `MainWindow._finalize_save` 한 길 → 옆 파일을 새 쪽 번호로 → 다시 열기.
쪽 편집 저장(`_page_edit_save`, §4.7.9)과 같은 나눔이다 — 원본에 놓기만 메인.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from PyQt6.QtWidgets import QDialog, QMessageBox

from viewer.i18n import tr


def run(mw, path) -> str | None:
    """만든(저장한) 파일 경로, 그만두면 None."""
    from viewer import toc_page
    from viewer.twoup import MergeCancelled
    src = Path(str(path))
    title = tr("목차 페이지 만들기")
    if src.suffix.lower() != ".pdf":
        return None
    try:
        dirty = bool((mw._on_instance_request("query", str(src)) or {}).get("dirty"))
    except Exception:
        dirty = False
    if dirty:
        QMessageBox.information(mw, title, tr("이 파일에 저장하지 않은 편집이 있습니다 — 먼저 💾 저장하거나 되돌린 뒤 다시 해 주세요."))
        return None
    got = {}

    def _probe(progress):
        progress(0, 1, tr("목차 읽는 중…"))
        got.update(toc_page.probe(str(src)))
        progress(1, 1, tr("완료"))
    res = mw._run_merge_job(_probe, title, cancellable=False)
    if not res.get("ok"):
        QMessageBox.warning(mw, title, res.get("err") or tr("알 수 없는 오류"))
        return None
    if got.get("encrypted"):
        QMessageBox.information(mw, title, tr("암호 PDF 에는 목차 쪽을 끼우지 않습니다."))
        return None
    if not got.get("toc"):
        QMessageBox.information(mw, title, tr("이 파일에는 목차로 쓸 책갈피가 없습니다."))
        return None
    old = int(got.get("old") or 0)
    if old:
        box = QMessageBox(QMessageBox.Icon.Question, title,
                          tr("이미 만든 목차 {n}쪽이 있습니다 — 새 목차로 바꿀까요?").format(n=old), parent=mw)
        b_ok = box.addButton(tr("바꾸기"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(b_ok)
        box.exec()
        if box.clickedButton() is not b_ok:
            return None
    from viewer.widgets.toc_page_dialog import TocPageDialog
    dlg = TocPageDialog(str(src), got, mw)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    vals = dlg.values()
    out = src.with_name(src.stem + "_toc_tmp.pdf")
    wdir = Path(tempfile.mkdtemp(prefix="polypdf_toc_"))
    built = {}

    def _job(progress):
        try:
            built.update(toc_page.insert_toc(str(src), str(out), vals["title"], vals["levels"],
                                             vals["template"], wdir, progress))
        except toc_page.Cancelled:
            raise MergeCancelled()
    try:
        res = mw._run_merge_job(_job, title)
    finally:
        shutil.rmtree(str(wdir), ignore_errors=True)
    if res.get("cancelled"):
        mw.status.showMessage(tr("목차 페이지 만들기를 취소했습니다 — 원본은 그대로입니다."), 5000)
        return None
    if not res.get("ok"):
        QMessageBox.warning(mw, title, res.get("err") or tr("알 수 없는 오류"))
        return None
    try:
        final = mw._finalize_save(str(src), str(out), None, carry=False)    # 원본 덮어쓰기는 이 한 길(서명 가드·다른 창·첫 백업)
    except Exception as e:
        try:
            if out.exists():
                os.remove(str(out))
        except Exception:
            pass
        from viewer.file_overwrite import SaveCancelled
        if isinstance(e, SaveCancelled):
            mw.status.showMessage(str(e), 5000)
            return None
        QMessageBox.warning(mw, title, str(e))
        return None
    k, keep = int(built["toc_pages"]), list(built["keep"])
    # 새 쪽 i 의 옛 쪽 — 1쪽, 목차 k 쪽(빈 자리), 나머지(옛 목차 쪽 것은 버림)
    meta_keys = keep[:1] + [None] * k + keep[1:]
    plan = [("own", i) if i is not None else None for i in meta_keys]
    mw._remap_page_keys(str(src), str(final), meta_keys)          # 꾸밈·숨김·링크
    mw._remap_page_text(str(src), str(final), plan)              # OCR·단어장·텍스트 창 고침
    mw._remap_closed_pane_pages(str(src), str(final), meta_keys)
    mw._mirror_to_pdf(final, reopen=False)
    mw.status.showMessage(tr("목차 {k}쪽을 2쪽부터 넣어 저장했습니다 → {name}").format(k=k, name=Path(final).name), 6000)
    try:
        mw.bookmark_tree.add_or_refresh_file(final, after=str(src))
        mw._open_saved_file(final, 0)
    except Exception:
        pass
    return str(final)
