# -*- coding: utf-8 -*-
"""261116-12: 본문 PDF 링크 누르기 — 목차 줄을 누르면 그 쪽으로 (입력 장치 SOT §4.2, 마스터 §11.10.6).

사용자 보고: "목차 만든 항목을 클릭시 해당 페이지로 이동하지 않아".
A. 책갈피창 '목차 페이지 만들기' 길의 PDF(`toc_page.insert_toc`): 저장된 링크 대상 = 목차 번호 − 1
B. 그 PDF 를 앱으로 열어 2쪽(목차)의 줄 자리에 **실제 마우스 누름·놓음** → 지금 쪽이 링크 대상, 링크 위 포인터 손가락
C. 끌기(누른 채 옮김)는 쪽을 안 바꾼다, 손바닥 도구면 안 간다
D. 다단 목차(`twoup.build_twoup`)도 같은 누르기로 그 시트
(수정 전 코드: 본문이 PDF 링크를 읽지 않아 쪽이 그대로 — 실패)
"""
import os, sys, tempfile, shutil, faulthandler
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(240, exit=True)
from pathlib import Path

import fitz
from PyQt6.QtCore import QStandardPaths, QCoreApplication, QEvent, QPointF, Qt
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_linkclick_%d" % os.getpid())   # 검사 작성 SOT §14.7.2 의 3
import modal_guard
modal_guard.install(label=lambda: "PDF 링크 누르기", echo=False)            # §14.7.2 의 6
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def spin(n=10, ms=20):
    for _ in range(n):
        app.processEvents(); QTest.qWait(ms)


L = Qt.MouseButton.LeftButton
NO = Qt.MouseButton.NoButton
NM = Qt.KeyboardModifier.NoModifier


def mouse(mv, kind, pt, button, buttons):
    vp = mv.view.viewport()
    QApplication.sendEvent(vp, QMouseEvent(kind, QPointF(pt), QPointF(vp.mapToGlobal(pt.toPoint())),
                                           button, buttons, NM))
    app.processEvents()


def link_rects(path, pno):
    """그 쪽의 내부 링크 [(화면 좌표 상자, 대상 쪽)] — 저장된 PDF 에서."""
    with fitz.open(path) as o:
        return [(fitz.Rect(l["from"]), l["page"]) for l in o[pno].get_links() if l.get("kind") == fitz.LINK_GOTO]


def vp_point(mv, x, y):
    """PDF 쪽 좌표(점) → 본문 뷰포트 좌표."""
    z = mv._zoom or 1.0
    return QPointF(mv.view.mapFromScene(QPointF(x * z, y * z)))


def click(mv, pt):
    mouse(mv, QEvent.Type.MouseButtonPress, pt, L, L)
    mouse(mv, QEvent.Type.MouseButtonRelease, pt, L, NO)
    spin(3)


TOC = [[1, "1장 서론", 2], [2, "1.1 배경", 3], [1, "2장 방법", 6], [1, "3장 결과", 10]]
errs = []
sys.excepthook = lambda t, v, tb: errs.append(f"{t.__name__}: {v}")
root = Path(tempfile.mkdtemp(prefix="polypdf_linkclick_"))
try:
    from viewer import toc_page, twoup
    src = root / "src.pdf"
    d = fitz.open()
    for i in range(12):
        d.new_page(width=595, height=842).insert_text((72, 100), "page %d" % (i + 1))
    d.set_toc([[1, "표지", 1]] + TOC)
    d.save(str(src)); d.close()

    # ── A. 책갈피창 목차 길의 PDF — 링크 대상 = 번호 − 1 ──
    bm = root / "doc" / "bm.pdf"
    bm.parent.mkdir()
    toc_page.insert_toc(str(src), str(bm), "", 2)
    lk = link_rects(str(bm), 1)
    with fitz.open(str(bm)) as o:
        words = o[1].get_text("words")
        nums = [int(w[4]) for w in words if w[4].isdigit() and w[2] > o[1].rect.width * 0.8]
    chk(len(lk) == 5 and [t for _r, t in lk] == [n - 1 for n in nums],             # 표지·1장·1.1·2장·3장
        "A 저장된 목차 링크 대상 = 목차 번호 − 1(끼운 뒤 실제 쪽)", str(([t for _r, t in lk], nums)))

    # ── 다단 목차 PDF ──
    nup = root / "doc" / "nup.pdf"
    twoup.build_twoup([{"type": "pdf", "path": str(src), "name": "src"}],
                      twoup.single_file_settings({"nup": 2, "make_toc": True, "toc_levels": 2, "footer_pos": "none"}),
                      str(nup))
    lk_n = link_rects(str(nup), 0)
    chk(len(lk_n) >= 3, "D 다단 목차 쪽에 링크가 있다(전제)", str(len(lk_n)))

    # ── B. 앱으로 열어 실제 마우스로 누르기 ──
    import test_fixtures as _TFX; _TFX.autotag_off()
    from viewer.app import MainWindow
    from viewer.history import HistoryItem
    mw = MainWindow(); mw.resize(1200, 900); mw.show(); app.processEvents()
    mw.open_folder(bm.parent); spin(20)

    def open_at(path, page):
        mw._load_main(HistoryItem(str(path), page, "", "bookmark"), sync=True); spin(10)
        mv = mw._mv[mw._active_pane]
        mv.go_to_page(page); spin(5)
        return mv

    mv = open_at(bm, 1)
    chk(mv.current_page() == 1 and mv._draw_tool is None, "B 목차 쪽(2쪽)을 열었다·도구 없음(전제)",
        str((mv.current_page(), mv._draw_tool)))
    r3, t3 = lk[3]                                    # '2장 방법' 줄
    pt3 = vp_point(mv, (r3.x0 + r3.x1) / 2, (r3.y0 + r3.y1) / 2)
    mouse(mv, QEvent.Type.MouseMove, pt3, NO, NO)
    chk(mv.view.viewport().cursor().shape() == Qt.CursorShape.PointingHandCursor,
        "B 목차 줄 위 포인터 = 손가락", str(mv.view.viewport().cursor().shape()))
    seen = []
    mv.pageChanged.connect(seen.append)
    click(mv, pt3)
    chk(mv.current_page() == t3, "B 목차 줄을 누르면 그 쪽으로", "now %d want %d" % (mv.current_page(), t3))
    chk(t3 in seen, "B pageChanged 가 나간다(썸네일·책갈피·텍스트 창이 따라온다)", str(seen))
    # 링크 밖(제목 자리)을 누르면 그대로
    mv.go_to_page(1); spin(3)
    mouse(mv, QEvent.Type.MouseMove, vp_point(mv, 30, 30), NO, NO)
    chk(mv.view.viewport().cursor().shape() != Qt.CursorShape.PointingHandCursor, "B 링크 밖으로 나가면 손가락이 아니다")
    click(mv, vp_point(mv, 30, 30))
    chk(mv.current_page() == 1, "B 링크 밖을 누르면 쪽 그대로", str(mv.current_page()))
    # 단계 2 줄(들여쓴 줄)도
    r2, t2 = lk[2]                                    # '1.1 배경' 줄
    click(mv, vp_point(mv, (r2.x0 + r2.x1) / 2, (r2.y0 + r2.y1) / 2))
    chk(mv.current_page() == t2, "B 들여쓴(단계 2) 줄도 그 쪽으로", "now %d want %d" % (mv.current_page(), t2))

    # ── C. 끌기·손바닥이면 안 간다 ──
    mv.go_to_page(1); spin(3)
    a = vp_point(mv, r3.x0 + 5, (r3.y0 + r3.y1) / 2)
    mouse(mv, QEvent.Type.MouseButtonPress, a, L, L)
    for i in range(1, 5):
        mouse(mv, QEvent.Type.MouseMove, QPointF(a.x() + 20 * i, a.y()), NO, L)
    mouse(mv, QEvent.Type.MouseButtonRelease, QPointF(a.x() + 80, a.y()), L, NO)
    spin(3)
    chk(mv.current_page() == 1, "C 끌기(글 선택)는 쪽을 안 바꾼다", str(mv.current_page()))
    mv.clear_text_selection()
    pb = mv._draw_pan_btn
    pb.click(); spin(2)
    click(mv, pt3)
    chk(mv._draw_kind == "pan" and mv.current_page() == 1, "C 손바닥 도구면 링크를 눌러도 안 간다",
        str((mv._draw_kind, mv.current_page())))
    pb.click(); spin(2)
    # 편집 모드라도 도구가 없으면 간다(꾸미기 줄의 사진 잡기 길을 지나도)
    mv.set_draw_mode(True); spin(2)
    click(mv, pt3)
    chk(mv._draw_tool is None and mv.current_page() == t3, "C 편집 모드(도구 없음)에서도 그 쪽으로",
        str((mv._draw_tool, mv.current_page())))
    mv.set_draw_mode(False); spin(2)

    # ── D. 다단 목차 ──
    mv = open_at(nup, 0)
    rn, tn = lk_n[-1]
    click(mv, vp_point(mv, (rn.x0 + rn.x1) / 2, (rn.y0 + rn.y1) / 2))
    chk(mv.current_page() == tn and tn > 0, "D 다단 목차 줄을 누르면 그 시트로", "now %d want %d" % (mv.current_page(), tn))

    chk(not errs, "예외 없음", str(errs[:3]))
    mw.close(); spin(5)
finally:
    shutil.rmtree(root, ignore_errors=True)

print("\n%s — 실패 %d" % ("ALL PASS" if not fails else "FAIL", len(fails)))
sys.exit(1 if fails else 0)
