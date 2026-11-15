# -*- coding: utf-8 -*-
"""261115-16: 무거운 PDF 를 보통으로 열 때(책갈피창 누름·첫 열기) 메인이 쪽 썸네일을 그리지 않는다 (응답성 SOT §4.4).

사용자 지시(261115-11) '책갈피창에서 아래 파일로 빠르게 내리면서 속도 등에 문제없는지' 의 부하 시험(3,061개 폴더 색인 중)이 잡았다 —
첫 파일을 보통으로 열면 메인이 썸네일 한 장에 0.1~0.25초씩 그리고, 같은 때 문서 정보 읽기가 쪽마다 글자층을 판정해 최장 0.52~1.32초 섰다.

A. 책갈피창에서 쪽마다 도형이 많은 PDF 를 고르면(`setCurrentItem` — 마우스와 같은 보통 열기) 보이는 썸네일이 다 차고,
   **메인 스레드의 `render_thumbnail` 호출은 0** — 쪽 그림은 배경(`ThumbRenderer`)이 그린다
B. 문서 정보 배경 읽기(`DocInfoWorker`)는 연 직후 시작하지 않고(`DOC_INFO_DELAY_MS`) 조금 뒤 시작해 정보 줄을 채운다
C. 낡은 세대·다른 해상도의 배경 그림은 버린다
D. 곧바로 다른 파일을 고르면 썸네일은 그 파일 것만 차고, 앞 파일의 늦은 그림이 끼지 않는다
E. 회전(저장 전)을 바꾸면 그 쪽만 다시 — 배경으로 다시 그린다
F. 최장 정지 < 1초(실측 기준 — 판정의 큰 몫은 A·B)
수정 전 코드는 A(메인 그리기)·B(곧바로 시작)로 실패한다.
"""
import os, sys, time, tempfile, shutil, faulthandler, threading
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.pop("POLYPDF_FAKE_POWER_SAVING", None)
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(300, exit=True)
from pathlib import Path

import fitz
from PyQt6.QtCore import QStandardPaths, QCoreApplication, QTimer
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
QStandardPaths.setTestModeEnabled(True)               # 검사 작성 SOT §14.7.2 의 3
QCoreApplication.setApplicationName("polypdf_thumbs_bg_%d" % os.getpid())
import modal_guard
modal_guard.install(label=lambda: "썸네일 배경 그리기", echo=False)   # §14.7.2 의 6
fails = []
MAIN = threading.get_ident()


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def spin(ms=300):
    t = time.perf_counter()
    while (time.perf_counter() - t) * 1000 < ms:
        app.processEvents(); QTest.qWait(5)


def wait(cond, ms=8000):
    t = time.perf_counter()
    while (time.perf_counter() - t) * 1000 < ms:
        if cond():
            return True
        app.processEvents(); QTest.qWait(10)
    return cond()


def heavy_pdf(dst, pages=12, lines=5000, tag="h"):
    """쪽마다 짧은 선 수천 개 — 쪽 한 장 그리기가 비싼 논문 그림 꼴."""
    d = fitz.open()
    for k in range(pages):
        p = d.new_page()
        sh = p.new_shape()
        for j in range(lines):
            x = 40 + (j * 7) % 520
            y = 60 + (j * 13) % 720
            sh.draw_line((x, y), (x + 3 + j % 5, y + 2))
        sh.finish(color=(0.2, 0.2, 0.6), width=0.3)
        sh.commit()
        p.insert_text((60, 40), f"{tag} page {k + 1} figure heavy", fontsize=14)
    d.save(str(dst)); d.close()


root = Path(tempfile.mkdtemp(prefix="polypdf_thumbs_bg_"))
try:
    heavy_pdf(root / "a_heavy.pdf", tag="A")
    heavy_pdf(root / "b_heavy.pdf", tag="B")
    heavy_pdf(root / "c_heavy.pdf", tag="C")

    from viewer.app import MainWindow
    from viewer import pdf_doc, doc_info
    calls = []                                             # (스레드가 메인인가, 쪽)
    _rt = pdf_doc.PdfDocument.render_thumbnail

    def _spy_rt(self, page_index, dpi=48):
        calls.append((threading.get_ident() == MAIN, int(page_index)))
        return _rt(self, page_index, dpi=dpi)
    pdf_doc.PdfDocument.render_thumbnail = _spy_rt
    info_starts = []
    _di = doc_info.DocInfoWorker.__init__

    def _spy_di(self, gen, pane, path, password=None):
        info_starts.append((time.perf_counter(), str(path)))
        _di(self, gen, pane, path, password)
    doc_info.DocInfoWorker.__init__ = _spy_di

    mw = MainWindow(); mw.resize(1300, 850); mw.show(); app.processEvents()
    bt = mw.bookmark_tree; mv = mw.main_view; pt = mw.page_thumbs
    mw.open_folder(root)
    wait(lambda: len(list(bt._iter_file_nodes())) >= 3, 8000)
    spin(1500)
    nodes = {Path(str(n.data(0, bt.DATA_FILE))).name: n for n in bt._iter_file_nodes()}

    def visible_items():
        vr = pt.list.viewport().rect()
        return [pt.list.item(i) for i in range(pt.list.count())
                if pt.list.visualItemRect(pt.list.item(i)).intersects(vr)]

    def thumbs_full():
        its = visible_items()
        return bool(its) and all(not it.icon().isNull() for it in its)

    beat = {"last": time.perf_counter(), "max": 0.0, "on": False}

    def tick():
        now = time.perf_counter()
        if beat["on"]:
            beat["max"] = max(beat["max"], now - beat["last"])
        beat["last"] = now
    hb = QTimer(); hb.setInterval(20); hb.timeout.connect(tick); hb.start()

    # ── A·B·F. 보통 열기 ─────────────────────────────────────────
    calls.clear(); info_starts.clear()
    bt.tree.setFocus()
    beat["last"] = time.perf_counter(); beat["max"] = 0.0; beat["on"] = True
    t_open = time.perf_counter()
    bt.tree.setCurrentItem(nodes["a_heavy.pdf"])
    ok_open = wait(lambda: mv.current_file() and Path(str(mv.current_file())).name == "a_heavy.pdf", 8000)
    early = [t for t, p in info_starts if t - t_open < 0.6]
    full = wait(thumbs_full, 10000)
    beat["on"] = False
    n_vis = len(visible_items())
    main_calls = [p for m, p in calls if m]
    chk(ok_open, "A 책갈피창 누름으로 본문이 연다")
    chk(full and n_vis >= 3, "A 보이는 썸네일이 다 찬다", "보이는 %d" % n_vis)
    chk(not main_calls, "A 메인 스레드는 쪽 썸네일을 그리지 않는다(배경이)", "메인 그리기 %s" % main_calls[:8])
    chk(any(not m for m, _ in calls), "A 배경 스레드가 그렸다", str(calls[:4]))
    chk(not early, "B 문서 정보 배경 읽기는 연 직후 시작하지 않는다", "%.3fs 뒤 시작" % (early[0] - t_open) if early else "")
    chk(wait(lambda: any(Path(p).name == "a_heavy.pdf" for _, p in info_starts), 4000), "B 조금 뒤 문서 정보 읽기를 시작한다")
    st = mw._doc_info_state[0]
    chk(wait(lambda: (st.get("info") or {}).get("pages_checked") == 12, 8000), "B 정보 줄 값이 찬다(쪽 12)", str(st.get("info")))
    chk(beat["max"] < 1.0, "F 최장 정지 < 1초", "%.3fs" % beat["max"])
    print("   (참고) 최장 정지 %.3fs, 배경 그리기 %d장" % (beat["max"], sum(1 for m, _ in calls if not m)))

    # ── C. 낡은 세대·다른 해상도는 버린다 ──────────────────────────
    row = pt.row_of_page(0)
    it0 = pt.list.item(row)
    img = QImage(60, 80, QImage.Format.Format_RGB888); img.fill(0)
    from PyQt6.QtGui import QIcon
    it0.setIcon(QIcon()); pt._iconed.pop(id(it0), None)
    pt._on_bg_thumb(pt._bg.gen() - 1, 0, pt._thumb_dpi(), img)
    chk(it0.icon().isNull(), "C 앞 세대 그림은 버린다")
    pt._on_bg_thumb(pt._bg.gen(), 0, pt._thumb_dpi() + 7, img)
    chk(it0.icon().isNull(), "C 다른 해상도 그림은 버린다")
    pt._on_bg_thumb(pt._bg.gen(), 0, pt._thumb_dpi(), img)
    chk(not it0.icon().isNull(), "C 지금 세대·해상도면 붙인다")

    # ── D. 곧바로 다른 파일 ─────────────────────────────────────
    calls.clear()
    bt.tree.setCurrentItem(nodes["b_heavy.pdf"])
    app.processEvents()
    bt.tree.setCurrentItem(nodes["c_heavy.pdf"])
    wait(lambda: mv.current_file() and Path(str(mv.current_file())).name == "c_heavy.pdf", 8000)
    full = wait(thumbs_full, 10000)
    spin(400)
    chk(full and Path(str(pt._doc_path)).name == "c_heavy.pdf", "D 썸네일은 나중 고른 파일 것으로 찬다", str(pt._doc_path))
    chk(not [p for m, p in calls if m], "D 메인은 그리지 않는다", str([p for m, p in calls if m][:6]))

    # ── E. 회전 바꾸면 그 쪽만 배경으로 다시 ────────────────────────
    calls.clear()
    pt.set_rotations({1: 90})
    it1 = pt.list.item(pt.row_of_page(1))
    chk(wait(lambda: not it1.icon().isNull() and any(p == 1 for _, p in calls), 6000),
        "E 회전한 쪽을 다시 그린다", str(calls[:6]))
    chk(all(p == 1 for _, p in calls) and not [p for m, p in calls if m], "E 그 쪽만·배경에서", str(calls[:6]))
    pt.set_rotations({})
finally:
    shutil.rmtree(root, ignore_errors=True)

print("\n=== " + ("ALL PASS" if not fails else f"FAILURE ({len(fails)})") + " ===")
for m in fails:
    print(" -", m)
sys.stdout.flush()
os._exit(1 if fails else 0)
