# -*- coding: utf-8 -*-
"""261116-21(입력 장치 SOT §4.2 '비용'): 본문 링크 캐시는 문서를 다시 열면 비고, 문서 판이 바뀌면 다시 읽는다.

SOT 내용 점검(261116) C-1: 캐시 키가 `(id(fitz 문서), 쪽)` 뿐이라 회전·크롭으로 다시 연 문서가 옛 문서와 같은 `id` 를
받으면 옛(돌리기 전) 링크 상자를 쓸 수 있었다. 이 PC 에서 다섯 번 다시 열어서는 `id` 가 다시 쓰이지 않아 낡은 상자를
직접 보지는 못했다 — 그래서 그것을 막는 성질을 본다.
A. 문서를 다시 열면(`load_document`) 링크 캐시가 빈다(옛 문서의 것을 들고 가지 않는다)
B. 같은 문서 객체라도 문서 판(`_cache_tag` — 저장 전 회전·크롭 판)이 바뀌면 캐시를 다시 쓰지 않는다
C. 저장 전 회전(`/Rotate` 덧입히기) 뒤 다시 열면 돌린 화면 좌표에서 링크를 찾고, 돌리기 전 자리는 링크가 아니다
(수정 전 코드: A·B 실패)
"""
import os, sys, tempfile, shutil, faulthandler
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(120, exit=True)

import fitz
from PyQt6.QtCore import QStandardPaths, QCoreApplication
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_linkcache_%d" % os.getpid())   # 검사 작성 SOT §14.7.2 의 3
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


root = tempfile.mkdtemp(prefix="polypdf_linkcache_")
try:
    from viewer.widgets.main_view import MainView
    from viewer import page_rotate
    p = os.path.join(root, "a.pdf")
    d = fitz.open()
    for i in range(3):
        d.new_page(width=595, height=842)
    d[0].insert_link({"kind": fitz.LINK_GOTO, "from": fitz.Rect(50, 100, 300, 120), "page": 2})
    d.save(p); d.close()
    mv = MainView(); mv.resize(900, 700); mv.show()
    mv.load_document(p, 0); app.processEvents()
    chk(mv.link_at(100, 110) == 2, "전제 — 링크 자리에서 대상 쪽")

    # A. 다시 열면 캐시가 빈다
    rot = {0: 90}
    page_rotate.set_provider(lambda path: dict(rot))
    page_rotate.bump(p)
    mv.load_document(p, 0); app.processEvents()
    chk(getattr(mv, "_link_cache", None) is None, "A 다시 열면 링크 캐시가 빈다(옛 문서의 상자를 들고 가지 않는다)",
        str(getattr(mv, "_link_cache", None)))

    # C. 돌린 화면 좌표에서 찾는다
    real = [fitz.Rect(l["from"]) for l in mv._doc.doc[0].get_links()]
    r = real[0] if real else fitz.Rect()
    chk(mv._doc.doc[0].rotation == 90 and mv.link_at((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2) == 2,
        "C 저장 전 회전 뒤 돌린 자리에서 링크", str(real))
    chk(mv.link_at(100, 110) is None, "C 돌리기 전 자리는 링크가 아니다")

    # B. 같은 문서 객체라도 판이 바뀌면 다시 읽는다 — 캐시에 '옛 판' 상자를 넣어 두고 판만 바꾼다
    mv._goto_links()
    stale = fitz.Rect(0, 0, 595, 842)                      # 쪽 전체 — 남아 있으면 어디를 눌러도 링크
    mv._link_cache = (mv._link_cache[0], [(stale, 1)])
    mv._doc._cache_tag = str(getattr(mv._doc, "_cache_tag", "")) + "|rot999"
    chk(mv.link_at(10, 10) is None, "B 문서 판이 바뀌면 캐시의 옛 상자를 쓰지 않는다")
    page_rotate.set_provider(None)
    mv.close()
finally:
    shutil.rmtree(root, ignore_errors=True)

print("\n%s — 실패 %d" % ("ALL PASS" if not fails else "FAIL", len(fails)))
sys.exit(1 if fails else 0)
