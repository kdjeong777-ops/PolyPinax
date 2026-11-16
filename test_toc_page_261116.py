# -*- coding: utf-8 -*-
"""261116-5: 목차 쪽 — 책갈피창 '목차 페이지 만들기' + 다단 목차 같은 방법 (마스터 §11.10.6, 책갈피창·저장 SOT §4.7.29).

A. 실제 우클릭 메뉴: 편집 모드에서 '페이지순 책갈피 정렬(선택 파일)' 바로 아래 '목차 페이지 만들기' (편집 모드가 아니면 없음)
B. 그 메뉴 → 앱 길(창 값 1~2단계 → 배경 만들기 → `_finalize_save`): 쪽 수 +1, 제목 '목  차'(한글 문서), 점선, 번호는 끼운 뒤 실제 쪽(오른쪽 끝),
   링크 대상 쪽, 단계 2 들여쓰기·단계 3 빠짐, 책갈피 1쪽씩 밀림·맨 앞 '목차', 원본 정보 그대로, 메인 최장 정지 < 1초
C. 다시 만들기: '바꿀까요?' → 바꾸기 → 옛 목차 빼고 새로(쪽 수 그대로·'목차' 책갈피 하나·1~3단계·입력 제목)
D. 저장 안 한 편집이 있으면 막음(파일 그대로)
E. 다단: 기본(1단계) 목차 줄·번호는 종전과 같다, 2단계면 하위 줄 들여쓰기·링크는 실제 시트, 제목 입력·판정, 여러 파일 2단계 = 파일 + 책갈피
F. 샘플 하나: 목차_샘플.docx 에 {{TITLE}}·{{TOC}}·'TOC 1' 스타일 점선 오른쪽 탭, 옛 양식(스타일 없음)도 단계 스타일로 채움, 제목 판정
(수정 전 코드: 실패 — 메뉴·모듈이 없다)
"""
import os, sys, tempfile, shutil, time, faulthandler
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(300, exit=True)
from pathlib import Path

import fitz
from PyQt6.QtCore import QStandardPaths, QTimer, QCoreApplication
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtWidgets import QApplication, QMessageBox, QDialog, QMenu
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_tocpage_%d" % os.getpid())   # 검사 작성 SOT §14.7.2 의 3
import modal_guard
modal_guard.install(label=lambda: "목차 페이지", echo=False)               # §14.7.2 의 6
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def spin(n=10, ms=20):
    for _ in range(n):
        app.processEvents(); QTest.qWait(ms)


TOC = [[1, "1장 서론", 2], [2, "1.1 배경", 3], [2, "1.2 목적", 4], [1, "2장 방법", 6], [2, "2.1 재료", 7],
       [3, "2.1.1 시료", 8], [1, "3장 결과", 10]]
errs = []
sys.excepthook = lambda t, v, tb: errs.append(f"{t.__name__}: {v}")
root = Path(tempfile.mkdtemp(prefix="polypdf_tocpage_"))
try:
    from viewer import twoup
    try:
        from viewer import toc_page
    except ImportError:
        toc_page = None
    chk(toc_page is not None, "공용 목차 모듈(viewer/toc_page.py)")

    # ── E·F (앱 없이 — 엔진) ──
    src = root / "src.pdf"
    d = fitz.open()
    for i in range(12):
        d.new_page(width=595, height=842).insert_text((72, 100), "page %d" % (i + 1))
    d.set_toc(TOC)
    d.save(str(src)); d.close()
    item = [{"type": "pdf", "path": str(src), "name": "src"}]

    def norm(t):
        return "".join(ch for ch in t if not ch.isspace() and ch not in ".·…")

    def toc_page_info(path, page=0):
        """목차 쪽 — (띄어쓰기·점선 뺀 글, 오른쪽 끝 번호들, 낱말 [(x0, 글)], 링크 대상, 쪽 수).
        다단은 만들 때 Word 가 있으면 Word 로 그린다(낱말 나눔이 fitz 와 다르다) — 어느 쪽이어도 같은 판정이 되게."""
        with fitz.open(path) as o:
            p = o[page]
            words = p.get_text("words")
            right = [w[4] for w in words if w[4].isdigit() and w[2] > p.rect.width * 0.8]
            return (norm(p.get_text()), right, [(w[0], w[4]) for w in words],
                    [l["page"] for l in p.get_links() if l.get("kind") == fitz.LINK_GOTO], o.page_count)

    n1 = root / "n1.pdf"
    twoup.build_twoup(item, twoup.single_file_settings({"nup": 2, "make_toc": True, "footer_pos": "none"}), str(n1))
    t1, r1, _w1, lk1, pc1 = toc_page_info(str(n1))
    chk(all(norm(k) in t1 for k in ("1장 서론", "2장 방법", "3장 결과")) and norm("1.1 배경") not in t1,
        "E 다단 기본은 1단계 줄만(종전 '책갈피 1단계')", t1[:80])
    # 종전 번호: 2쪽 → 시트 1, 6쪽 → 시트 3, 10쪽 → 시트 5 (2-up, 목차 1쪽 뒤 본문 번호)
    chk(r1 == ["1", "3", "5"], "E 기본 번호는 종전 본문 번호(1·3·5)", str(r1))
    chk(pc1 == 1 + 6, "E 쪽 수 = 목차 1 + 본문 시트 6", str(pc1))
    chk(lk1 == [1, 3, 5], "E 목차 줄 링크 → 그 시트(실제 쪽)", str(lk1))
    chk(t1.startswith("목차"), "E 제목 판정 — 한글 문서 '목  차'", t1[:20])
    n2 = root / "n2.pdf"
    twoup.build_twoup(item, twoup.single_file_settings({"nup": 2, "make_toc": True, "toc_levels": 2,
                                                        "toc_title": "차례", "footer_pos": "none"}), str(n2))
    t2, r2, w2, lk2, _pc2 = toc_page_info(str(n2))
    x_sub = min((x0 for x0, w in w2 if w.startswith("1.1")), default=-1)
    x_top = min((x0 for x0, w in w2 if w.startswith("2") and not w.startswith("2.")), default=-1)
    chk(norm("1.1 배경") in t2 and 0 < x_top < x_sub, "E 2단계 — 하위 줄 들여쓰기", "%s %s" % (x_top, x_sub))
    chk(norm("2.1.1 시료") not in t2, "E 2단계 — 3단계 줄은 빠짐")
    chk(r2 == ["1", "2", "2", "3", "4", "5"] and lk2 == [1, 2, 2, 3, 4, 5], "E 2단계 번호·링크 → 실제 시트", str((r2, lk2)))
    chk(t2.startswith("차례"), "E 입력 제목", t2[:10])
    # 여러 파일(병합 길) 2단계 = 파일 이름 + 그 파일 책갈피
    n3 = root / "n3.pdf"
    twoup.build_twoup(item + [{"type": "pdf", "path": str(src), "name": "second"}],
                      {"nup": 2, "make_toc": True, "toc_levels": 2, "footer_pos": "none"}, str(n3))
    t3, _r3, _w3, _lk3, _pc3 = toc_page_info(str(n3))
    chk("src" in t3 and "second" in t3 and norm("1장 서론") in t3 and norm("1.1 배경") not in t3,
        "E 여러 파일 2단계 = 파일 이름 + 책갈피 1단계", t3[:80])
    # 다단 설정 창 — 제목·단계 칸이 스타일 저장값에 들어가고, 두 값이 없는 옛 스타일은 기본값(빈 제목·1단계)
    from viewer.widgets.twoup_dialog import TwoUpSettingsDialog
    presets = [{"name": "옛 스타일", "nup": 2}]
    dlg = TwoUpSettingsDialog({"toc_title": "차례", "toc_levels": 3}, None, preset_api={"get_presets": lambda: presets})
    gs = dlg.get_settings()
    chk(gs.get("toc_title") == "차례" and gs.get("toc_levels") == 3, "E 설정 창 값 → 저장값(toc_title·toc_levels)", str(gs.get("toc_levels")))
    i_old = dlg.cmb_preset.findText("옛 스타일")
    dlg.cmb_preset.setCurrentIndex(i_old); dlg.cmb_preset.activated.emit(i_old)
    chk(dlg.ed_toc_title.text() == "" and dlg.cmb_toc_lv.currentData() == 1, "E 옛 스타일은 기본값(빈 제목·1단계)")
    dlg.done(0)
    # 점선·오른쪽 끝 번호(fitz 그리기)
    if toc_page is not None:
        dd, rects = toc_page.render_fitz([(1, "가나다", "12"), (2, "라마", "7")], 595, 842, "목  차")
        words = dd[0].get_text("words")
        nums = [w for w in words if w[4] in ("12", "7")]
        chk(len(nums) == 2 and all(abs(w[2] - (595 - toc_page.MARGIN_X)) < 1.5 for w in nums),
            "F 번호 끝이 오른쪽 여백에 맞음", str([(w[4], round(w[2], 1)) for w in nums]))
        chk(sum(1 for w in words if w[4] == toc_page.LEADER) > 10, "F 점선 채움")
        dd.close()
        # 창 미리보기(Qt)의 쪽 수 셈이 실제 그리기(fitz)와 같다
        many = [(1, "항목 %d" % i, "9") for i in range(75)]
        dm, _r = toc_page.render_fitz(many, 595, 842, "목  차")
        chk(toc_page.fitz_pages(75, 842) == dm.page_count == 3, "F 쪽 수 셈(미리보기·한 번 그리기) = 실제 그리기",
            "%d vs %d" % (toc_page.fitz_pages(75, 842), dm.page_count))
        dm.close()
        chk(toc_page.auto_title(["Introduction", "Methods"]) == "CONTENTS" and toc_page.auto_title(["서론", "방법"]) == "목  차",
            "F 제목 판정 — 영문 CONTENTS·한글 '목  차'")
        # 샘플 하나(다단 샘플 저장과 같은 함수)
        made = twoup.write_sample_templates(str(root), divider=False)
        smp = next((m for m in made if Path(m).name.startswith("목차")), None)
        chk(smp is not None, "F 다단 샘플 저장이 목차_샘플.docx 를 만든다", str(made))
        if smp:
            from docx import Document
            from docx.enum.text import WD_TAB_LEADER, WD_TAB_ALIGNMENT
            sd = Document(smp)
            body = "\n".join(p.text for p in sd.paragraphs)
            st = next((s for s in sd.styles if s.name == "TOC 1"), None)
            tabs = list(st.paragraph_format.tab_stops) if st is not None else []
            chk("{{TITLE}}" in body and "{{TOC}}" in body, "F 샘플에 {{TITLE}}·{{TOC}}")
            chk(any(t.leader == WD_TAB_LEADER.DOTS and t.alignment == WD_TAB_ALIGNMENT.RIGHT for t in tabs),
                "F 'TOC 1' 스타일 — 점선 오른쪽 탭", str([(t.alignment, t.leader) for t in tabs]))
            # 옛 양식(스타일·{{TITLE}} 없음)
            old = Document(); old.add_paragraph("목차"); old.add_paragraph("{{TOC}}"); old.save(str(root / "old.docx"))
            ok = toc_page.fill_docx(str(root / "old.docx"), [(1, "가", "3"), (2, "나", "4")], "목  차", str(root / "old_out.docx"))
            od = Document(str(root / "old_out.docx"))
            sty = [(p.text, p.style.name) for p in od.paragraphs if "\t" in p.text]
            chk(ok and sty == [("가\t3", "TOC 1"), ("나\t4", "TOC 2")], "F 옛 양식도 단계 스타일·탭으로 채움", str(sty))
        # 덧붙임 2: 1쪽짜리 PDF 면 그 뒤에
        one = root / "one.pdf"
        d1 = fitz.open(); d1.new_page().insert_text((72, 100), "only"); d1.set_toc([[1, "Only", 1]]); d1.save(str(one)); d1.close()
        r1 = toc_page.insert_toc(str(one), str(root / "one_out.pdf"), "", 1)
        with fitz.open(str(root / "one_out.pdf")) as o1:
            chk(o1.page_count == 2 and "only" in o1[0].get_text() and "CONTENTS" in o1[1].get_text()
                and o1.get_toc() == [[1, "Only", 1], [1, "CONTENTS", 2]],
                "F 1쪽짜리 PDF 는 그 뒤에 목차(영문 문서 CONTENTS)", str((o1.page_count, o1.get_toc())))

    # ── A~D (앱 길) ──
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    import test_fixtures as _TFX; _TFX.autotag_off()
    from viewer.app import MainWindow
    from viewer.history import HistoryItem
    pdf = root / "doc" / "doc.pdf"
    pdf.parent.mkdir()
    d = fitz.open()
    for i in range(12):
        d.new_page(width=595, height=842).insert_text((72, 100), "page %d" % (i + 1))
    d.set_toc([[1, "표지", 1]] + TOC)                     # 덧붙임 2: 1쪽(표지) 책갈피는 그대로 남아야 한다
    d.set_metadata({"title": "원본 제목", "author": "작성자"})
    d[0].insert_link({"kind": fitz.LINK_GOTO, "from": fitz.Rect(72, 120, 200, 140), "page": 9, "to": fitz.Point(0, 0)})
    d.save(str(pdf)); d.close()
    mw = MainWindow(); mw.resize(1200, 800); mw.show(); app.processEvents()
    bt = mw.bookmark_tree
    mw.open_folder(pdf.parent); spin(20)
    mw._load_main(HistoryItem(str(pdf), 0, "", "bookmark"), sync=True); spin(10)
    fn = next(iter(bt._iter_file_nodes()))
    fn.setExpanded(True)
    for _ in range(100):
        if fn.data(0, bt.DATA_TOC_LOADED):
            break
        spin(1)

    def menu_actions(it):
        got = []
        orig = QMenu.exec

        def fake_exec(menu, *a, **k):
            got.extend(menu.actions())
            return None
        QMenu.exec = fake_exec
        try:
            bt.tree.scrollToItem(it)
            bt._on_tree_context_menu(bt.tree.visualItemRect(it).center())
        finally:
            QMenu.exec = orig
        return [a for a in got if a.text()]

    def names(it):
        return [a.text().split("\t")[0] for a in menu_actions(it)]

    bt.btn_edit.setChecked(False); spin(10)
    chk(not bt.is_edit_mode() and "목차 페이지 만들기" not in names(fn.child(0)), "A 편집 모드가 아니면 메뉴 없음")
    bt.btn_edit.setChecked(True); spin(10)
    acts = names(fn.child(0))
    i_sort = acts.index("페이지순 책갈피 정렬(선택 파일)") if "페이지순 책갈피 정렬(선택 파일)" in acts else -9
    chk("목차 페이지 만들기" in acts and acts.index("목차 페이지 만들기") == i_sort + 1,
        "A '페이지순 책갈피 정렬(선택 파일)' 바로 아래 '목차 페이지 만들기'", str(acts[max(0, i_sort - 1):i_sort + 3]))
    chk("목차 페이지 만들기" in names(fn), "A 파일 줄에서도")

    calls = {"fin": 0}
    _orig_fin = mw._finalize_save

    def _fin(*a, **k):
        calls["fin"] += 1
        return _orig_fin(*a, **k)
    mw._finalize_save = _fin

    def run_menu(levels, title=""):
        """실제 메뉴 항목 → 창(값만 고르고 [만들기]) → 끝날 때까지. 메인 최장 정지(초)를 돌려준다."""
        orig = QDialog.exec

        def fake(dlg, *a, **k):
            if type(dlg).__name__ == "TocPageDialog":
                dlg.cmb_level.setCurrentIndex(dlg.cmb_level.findData(levels))
                dlg.ed_title.setText(title)
                dlg._render_preview()                     # 미리보기 한 번(실제 창이 값 바꿀 때 그리는 것)
                dlg.accept()                              # [만들기] — 실제처럼 done() 을 지난다
                return QDialog.DialogCode.Accepted
            return orig(dlg, *a, **k)
        QDialog.exec = fake
        beats = [time.perf_counter()]
        hb = QTimer(); hb.setInterval(20); hb.timeout.connect(lambda: beats.append(time.perf_counter())); hb.start()
        try:
            a = next((x for x in menu_actions(fn.child(0)) if x.text().split("\t")[0] == "목차 페이지 만들기"), None)
            if a is not None:
                a.trigger()
            t0 = time.perf_counter()
            while time.perf_counter() - t0 < 30 and calls["fin"] < want_fin[0]:
                spin(1)
            spin(30)
        finally:
            QDialog.exec = orig
            hb.stop()
        return max((b - a for a, b in zip(beats, beats[1:])), default=0.0)

    want_fin = [1]
    size0 = pdf.stat().st_size
    stall = run_menu(2)
    size1 = pdf.stat().st_size
    chk(size1 - size0 < 300_000, "B 글꼴은 쓴 글자만(맑은 고딕 전체가 들어가지 않는다, §4.5.10)", "%d → %d" % (size0, size1))
    chk(calls["fin"] == 1, "B 저장은 _finalize_save 한 길", str(calls))
    with fitz.open(str(pdf)) as o:
        pc = o.page_count
        toc = o.get_toc()
        t0 = o[1].get_text()
        links = [l["page"] for l in o[1].get_links() if l.get("kind") == fitz.LINK_GOTO]
        words = o[1].get_text("words")
        cover = o[0].get_text()
        cover_links = [l["page"] for l in o[0].get_links() if l.get("kind") == fitz.LINK_GOTO]
        meta = o.metadata
        rng = toc_page.marked_range(o) if toc_page and hasattr(toc_page, "marked_range") else None
    chk(pc == 13, "B 목차 1쪽을 끼움(12 → 13쪽)", str(pc))
    chk("page 1" in cover and "목  차" in t0, "B 덧붙임 2 — 1쪽(표지) 그대로, 목차는 2쪽", (cover[:10], t0[:20]))
    chk("1.1 배경" in t0 and "2.1.1 시료" not in t0, "B 1~2단계 — 단계 2 포함, 단계 3 빠짐")
    nums = [w[4] for w in words if w[4].isdigit()]
    chk(nums == ["1", "3", "4", "5", "7", "8", "11"], "B 번호 = 끼운 뒤 실제 쪽(1쪽은 그대로)", str(nums))
    chk(links == [0, 2, 3, 4, 6, 7, 10], "B 목차 줄 링크 → 그 쪽(0-based)", str(links))
    chk(cover_links == [10], "B 원본 쪽의 내부 링크도 밀린 쪽으로(10쪽 → 11쪽)", str(cover_links))
    chk(sum(1 for w in words if w[4] == "·") > 10, "B 점선 채움")
    chk(toc[:4] == [[1, "표지", 1], [1, "목차", 2], [1, "1장 서론", 3], [2, "1.1 배경", 4]] and toc[-1] == [1, "3장 결과", 11],
        "B 1쪽 책갈피 그대로·'목차'(2쪽)·2쪽 이후 1쪽씩 밀림", str(toc[:4]))
    chk(meta.get("title") == "원본 제목" and meta.get("author") == "작성자", "B 원본 정보 그대로", str(meta))
    chk(rng == (1, 1), "B 목차 쪽 표식(2쪽부터 1쪽)", str(rng))
    chk(stall < 1.0, "B 메인 최장 정지 < 1초", "%.3f" % stall)
    chk(mw.main_view.current_file() and Path(mw.main_view.current_file()).name == "doc.pdf", "B 저장 뒤 그 파일을 다시 연다")

    # ── C 다시 만들기 ──
    asked = []
    _orig_mb_exec = QMessageBox.exec

    def mb_exec(box, *a, **k):
        asked.append(box.text())
        for b in box.buttons():
            if b.text() == "바꾸기":
                b.click()
                break
        return 0
    QMessageBox.exec = mb_exec
    fn = next(iter(bt._iter_file_nodes()))
    fn.setExpanded(True)
    for _ in range(100):
        if fn.data(0, bt.DATA_TOC_LOADED):
            break
        spin(1)
    if not bt.is_edit_mode():
        bt.btn_edit.setChecked(True); spin(10)
    want_fin = [2]
    run_menu(3, "My Contents")
    QMessageBox.exec = _orig_mb_exec
    chk(any("바꿀까요" in t for t in asked), "C 옛 목차가 있으면 바꿀지 묻는다", str(asked))
    with fitz.open(str(pdf)) as o:
        pc = o.page_count
        toc = o.get_toc()
        t0 = o[1].get_text()
        marked = toc_page.count_marked(o) if toc_page else 0
        cover_links = [l["page"] for l in o[0].get_links() if l.get("kind") == fitz.LINK_GOTO]
    chk(pc == 13 and marked == 1, "C 옛 목차를 빼고 같은 자리에 새로(쪽 수 그대로)", str((pc, marked)))
    titles = [e[1] for e in toc]
    chk(titles.count("목차") + titles.count("My Contents") == 1 and toc[1][:3] == [1, "My Contents", 2],
        "C 목차 책갈피 하나(입력 제목, 2쪽)", str(toc[:3]))
    chk("2.1.1 시료" in t0 and "My Contents" in t0, "C 1~3단계·입력 제목")
    chk(toc[0] == [1, "표지", 1] and toc[2] == [1, "1장 서론", 3], "C 책갈피는 두 번 밀리지 않는다", str(toc[:3]))
    chk(cover_links == [10], "C 원본 쪽 링크도 두 번 밀리지 않는다", str(cover_links))

    # ── D 저장 안 한 편집 ──
    bt._dirty = True
    infos = []
    _orig_info = QMessageBox.information
    QMessageBox.information = staticmethod(lambda *a, **k: infos.append(a[2] if len(a) > 2 else ""))
    from viewer import toc_page_flow
    r = toc_page_flow.run(mw, str(pdf))
    QMessageBox.information = _orig_info
    chk(r is None and any("저장하지 않은 편집" in t for t in infos), "D 저장 안 한 편집이 있으면 막음", str(infos))
    with fitz.open(str(pdf)) as o:
        chk(o.page_count == 13, "D 파일 그대로")
    bt._dirty = False

    chk(not errs, "예외 없음", str(errs))
    mw.close(); spin(5)
except Exception:
    import traceback
    traceback.print_exc()
    fails.append("예외")
finally:
    shutil.rmtree(root, ignore_errors=True)

print("FAILS:", len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
