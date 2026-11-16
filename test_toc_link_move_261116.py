# -*- coding: utf-8 -*-
"""261116-16: 쪽을 옮겨 저장해도 문서 안 링크가 남는다 (책갈피창·저장 SOT §4.7.9).

사용자 보고: "목차를 다른 페이지로 옮기면, 하이퍼링크가 사라져." — 쪽 편집 저장(`page_edit_build.build`)은 이어진 쪽 구간마다
`insert_pdf` 를 따로 부르는데, `insert_pdf` 는 같은 호출로 복사한 구간 안을 가리키는 링크만 남긴다 — 구간을 넘는 링크가 사라졌다.

A. 실제 메뉴 길로 목차 만들기(2쪽) — 원본 쪽에도 문서 안 링크 둘(3쪽→11쪽, 9쪽→4쪽)
B. 썸네일에서 목차 쪽을 뒤로 세 칸(실제 `_move_selected`) → 편집 모드 💾 저장(`_op_save`) → 저장된 PDF:
   목차 줄 링크가 모두 남고 대상이 옮긴 뒤 쪽(줄의 번호 = 그 책갈피의 새 쪽), 원본 쪽 링크도 새 쪽 번호로
C. 다시 연 본문에서 목차 줄을 **실제 마우스로 누르면** 그 쪽으로(입력 장치 SOT §4.2)
D. 다른 쪽을 지우면 그 쪽을 가리키던 링크는 버리고 나머지는 남는다
(수정 전 코드: B·C·D 실패 — 링크 0개)
"""
import os, sys, tempfile, shutil, time, faulthandler
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(300, exit=True)
from pathlib import Path

import fitz
from PyQt6.QtCore import QStandardPaths, QCoreApplication, QEvent, QPointF, Qt
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QMessageBox, QDialog
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_toclinkmove_%d" % os.getpid())   # 검사 작성 SOT §14.7.2 의 3
import modal_guard
modal_guard.install(label=lambda: "목차 링크 옮김", echo=False)               # §14.7.2 의 6
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def spin(n=10, ms=20):
    for _ in range(n):
        app.processEvents(); QTest.qWait(ms)


def goto_links(path):
    """{쪽: [(대상, 상자)]} — 문서 안 링크."""
    with fitz.open(str(path)) as o:
        out = {}
        for i in range(o.page_count):
            ls = [(l["page"], fitz.Rect(l["from"])) for l in o[i].get_links() if l.get("kind") == fitz.LINK_GOTO]
            if ls:
                out[i] = ls
        return out


L, NO, NM = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier


def mouse(mv, kind, pt, button, buttons):
    vp = mv.view.viewport()
    QApplication.sendEvent(vp, QMouseEvent(kind, QPointF(pt), QPointF(vp.mapToGlobal(pt.toPoint())), button, buttons, NM))
    app.processEvents()


errs = []
sys.excepthook = lambda t, v, tb: errs.append(f"{t.__name__}: {v}")
root = Path(tempfile.mkdtemp(prefix="polypdf_toclinkmove_"))
try:
    pdf = root / "doc" / "doc.pdf"
    pdf.parent.mkdir()
    d = fitz.open()
    for i in range(12):
        d.new_page(width=595, height=842).insert_text((72, 100), "page %d" % (i + 1))
    d.set_toc([[1, "Cover", 1], [1, "A", 2], [1, "B", 6], [1, "C", 10]])
    d[2].insert_link({"kind": fitz.LINK_GOTO, "from": fitz.Rect(72, 120, 200, 140), "page": 10})   # 3쪽 → 11쪽
    d[8].insert_link({"kind": fitz.LINK_GOTO, "from": fitz.Rect(72, 120, 200, 140), "page": 3})    # 9쪽 → 4쪽
    d.save(str(pdf)); d.close()

    import test_fixtures as _TFX; _TFX.autotag_off()
    from viewer.app import MainWindow
    from viewer.history import HistoryItem
    mw = MainWindow(); mw.resize(1200, 900); mw.show(); app.processEvents()
    bt = mw.bookmark_tree
    mw.open_folder(pdf.parent); spin(20)
    mw._load_main(HistoryItem(str(pdf), 0, "", "bookmark"), sync=True); spin(10)
    next(iter(bt._iter_file_nodes())).setExpanded(True); spin(20)
    bt.btn_edit.setChecked(True); spin(10)

    fin = {"n": 0}
    _of = mw._finalize_save

    def _f(*a, **k):
        fin["n"] += 1
        return _of(*a, **k)
    mw._finalize_save = _f

    def wait_fin(want):
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < 30 and fin["n"] < want:
            spin(1)
        spin(40)

    # ── A. 목차 만들기 ──
    orig = QDialog.exec

    def fake(dlg, *a, **k):
        if type(dlg).__name__ == "TocPageDialog":
            dlg.accept(); return QDialog.DialogCode.Accepted
        return orig(dlg, *a, **k)
    QDialog.exec = fake
    try:
        bt._file_action("toc_page", [str(pdf)])           # 우클릭 '목차 페이지 만들기' 가 부르는 것
        wait_fin(1)
    finally:
        QDialog.exec = orig
    lk0 = goto_links(pdf)
    chk(sorted(t for t, _r in lk0.get(1, [])) == [0, 2, 6, 10] and lk0.get(3) and lk0.get(9),
        "A 전제 — 목차(2쪽) 줄 링크 넷·원본 쪽 링크 둘(4쪽·10쪽)", str({k: [t for t, _r in v] for k, v in lk0.items()}))

    # ── B. 썸네일로 목차 쪽을 뒤로 세 칸 → 💾 저장 ──
    pt = mw.page_thumbs
    spin(20)
    pt.set_edit_mode(True); spin(5)
    pt.list.clearSelection(); pt.list.item(1).setSelected(True)
    for _ in range(3):
        pt._move_selected(1)
    spin(5)
    bt._op_save()
    wait_fin(2)
    lk = goto_links(pdf)
    with fitz.open(str(pdf)) as o:
        toc = {t: p for _l, t, p in o.get_toc()}
        pc = o.page_count
        page5 = o[4].get_text()
    chk(pc == 13 and "Cover" in page5, "B 전제 — 목차가 5쪽으로 옮겨 저장됨", str(pc))
    toc_targets = sorted(t for t, _r in lk.get(4, []))
    want = sorted(toc[k] - 1 for k in ("Cover", "A", "B", "C"))
    chk(toc_targets == want, "B 옮긴 목차 쪽 줄 링크가 모두 남고 대상 = 그 책갈피의 새 쪽", str((toc_targets, want, lk)))
    # 원본 3쪽(색인 2) → 저장 뒤 색인 3(목차 끼운 뒤)… 목차를 옮긴 뒤엔 색인 2. 9쪽(색인 9) 그대로
    others = {k: sorted(t for t, _r in v) for k, v in lk.items() if k != 4}
    chk(others == {2: [11], 9: [3]}, "B 원본 쪽 링크도 새 쪽 번호로(본문 'page 3'→'page 11', 'page 9'→'page 4')", str(others))
    with fitz.open(str(pdf)) as o:
        tg = [o[t].get_text().strip() for t in (11, 3)]
    chk(tg == ["page 11", "page 4"], "B 원본 쪽 링크 대상 쪽의 글이 원래 대상과 같다", str(tg))

    # ── C. 다시 연 본문에서 목차 줄을 실제 마우스로 ──
    mw._load_main(HistoryItem(str(pdf), 4, "", "bookmark"), sync=True); spin(10)
    mv = mw._mv[mw._active_pane]
    mv.go_to_page(4); spin(5)
    # (대상, 상자) — 가장 뒤 쪽을 가리키는 줄. 링크가 없으면(수정 전) 목차 줄 글자 자리를 눌러 본다
    if lk.get(4):
        t, r = max(lk[4], key=lambda x: x[0])
    else:
        with fitz.open(str(pdf)) as o:
            wl = [w for w in o[4].get_text("words") if w[4] == "C"]
        r, t = (fitz.Rect(wl[0][:4]) if wl else fitz.Rect(60, 180, 200, 200)), toc["C"] - 1
    z = mv._zoom or 1.0
    ptv = QPointF(mv.view.mapFromScene(QPointF((r.x0 + r.x1) / 2 * z, (r.y0 + r.y1) / 2 * z)))
    if mv._draw_tool is not None:
        mv.set_draw_mode(False); spin(2)
    mouse(mv, QEvent.Type.MouseButtonPress, ptv, L, L)
    mouse(mv, QEvent.Type.MouseButtonRelease, ptv, L, NO)
    spin(5)
    chk(mv.current_page() == t, "C 옮겨 저장한 목차 줄을 누르면 그 쪽으로", "now %d want %d" % (mv.current_page(), t))

    # ── D. 지운 쪽을 가리키던 링크는 버리고 나머지는 남는다(엔진) ──
    from viewer import page_edit_build as peb
    plan = [("own", i) for i in range(13) if i != 11]          # 'page 11'(색인 11) 지우기
    res = peb.build(str(pdf), plan, [], str(root / "re.pdf"), str(root / "bk.pdf"))
    lkd = goto_links(res["path"])
    chk(lkd.get(2) is None and sorted(t for t, _r in lkd.get(4, [])) == [x if x < 11 else x - 1 for x in want if x != 11]
        and [t for t, _r in lkd.get(9, [])] == [3],
        "D 지운 쪽을 가리키던 링크는 버리고 나머지는 새 번호로", str({k: [t for t, _r in v] for k, v in lkd.items()}))

    chk(not errs, "예외 없음", str(errs[:3]))
    mw.close(); spin(5)
except Exception as e:
    import traceback; traceback.print_exc()
    chk(False, "검사 도중 예외", repr(e))
finally:
    shutil.rmtree(root, ignore_errors=True)

print("\n%s — 실패 %d" % ("ALL PASS" if not fails else "FAIL", len(fails)))
sys.exit(1 if fails else 0)
