# -*- coding: utf-8 -*-
"""261128-8(검색창 SOT §5.2): 검색 범위 — 지금 파일 / 폴더 단추, 결과 없는 지금 파일 줄, 책갈피창 정렬을 따르는 파일 차례.

사용자 지시 '아이콘 버튼(파일(현재 파일), 폴더(폴더의 전체 파일))을 추가하여 기본은 현재 보고있는 파일 전체(파일)에서 검색 …
폴더로 되어 있어도 현재 보고있는 파일에 검색결과가 없으면, 해당하는 파일명 하부에 '검색결과 없음'을 표시하고, 항목을 이동시키지는 마 …
폴더로 되어 있을 경우 검색결과의 파일 순서는 책갈피창의 파일 정렬 기준을 적용', 결정 '아이콘 하나·누르면 바뀜'·'켤 때마다 파일'·'새 파일에서 다시 찾기'.
실제 색인·실제 마우스·키로:
  A  기본 범위는 '파일'(단추 그림·풍선), 새 검색 막대도 '파일'(기억하지 않음)
  B  '파일' 범위 — Enter 로 찾으면 지금 파일 결과만, 본문은 그 결과로
  C  '파일' 범위에서 결과 없는 다른 파일을 열면 그 파일에서 다시 찾고 — 그 파일 줄 + '검색결과 없음', 본문은 연 쪽 그대로
  D  단추를 누르면 '폴더' — 다시 찾아 다른 파일 결과도, 지금 파일엔 '검색결과 없음' 줄, 다른 파일로 옮기지 않는다
  E  '검색결과 없음' 줄은 눌러도 가지 않고 엑셀 저장 목록에도 없다
  F  폴더 결과의 파일 차례 = 책갈피창의 지금 정렬 — 정렬을 바꾸면 결과도 따라간다
수정 전 코드는 단추가 없어 A 부터 실패한다.
"""
import os, sys, time, faulthandler, tempfile, shutil
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
faulthandler.dump_traceback_later(240, exit=True)

from PyQt6.QtCore import QStandardPaths, Qt, QPoint
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
import modal_guard
modal_guard.install(echo=False)
from PyQt6.QtCore import QCoreApplication as _QCA
_QCA.setApplicationName("polypdf_search_scope_%d" % os.getpid())
fails = []


def chk(c, m, extra=""):
    print(("PASS" if c else "FAIL"), "-", m, ("" if c else extra))
    if not c:
        fails.append(m)


def make_pdf(path, words_by_page):
    import fitz
    d = fitz.open()
    for words in words_by_page:
        pg = d.new_page(width=420, height=595)
        pg.insert_text((50, 80), "page text " + words, fontsize=12)
    d.save(str(path)); d.close()


def wait(cond, sec=8.0):
    t0 = time.time()
    while time.time() - t0 < sec and not cond():
        app.processEvents(); time.sleep(0.02)
    app.processEvents()
    return cond()


tmp = tempfile.mkdtemp(prefix="polypdf_scope_")
try:
    from pathlib import Path
    folder = Path(tmp) / "pdfs"; folder.mkdir()
    Z, M, A = folder / "z_doc.pdf", folder / "m_doc.pdf", folder / "a_doc.pdf"
    make_pdf(Z, ["beta", "alpha one", "beta", "alpha two"])        # alpha 2·4쪽
    make_pdf(M, ["alpha three", "beta"])                           # alpha 1쪽
    make_pdf(A, ["beta", "beta", "gamma"])                         # alpha 없음
    now = time.time()
    for p, age in ((Z, 0), (M, 100), (A, 200)):                    # 수정일: z 가 가장 새것 → 수정일 순 z,m,a / 이름 순 a,m,z
        os.utime(p, (now - age, now - age))
    from viewer.indexer import PdfIndex
    db = Path(tmp) / "index.db"
    ix = PdfIndex(db)
    for p in (Z, M, A):
        ix.index_file(p)
    ix.close()

    from test_fixtures import wait_main_open
    from viewer.app import MainWindow, HistoryItem
    from viewer.widgets.search_panel import SearchBar
    mw = MainWindow(); mw._skip_save_on_close = True
    mw.resize(1500, 900); mw.show(); mw.activateWindow(); QTest.qWait(200)
    mw._db_path = db
    mw._folder = folder
    bt = mw.bookmark_tree
    bt._sort_combo.setCurrentIndex(bt._sort_combo.findData(bt.SORT_MTIME))
    bt.load_folder(folder)
    wait(lambda: len(bt.all_file_paths()) == 3)
    mw._refresh_search_scope()
    mw._load_main(HistoryItem(str(Z), 0, "", "bookmark")); wait_main_open(mw); QTest.qWait(150)
    mw._vm_search(); QTest.qWait(100)
    sb, sr, mv = mw.search_bar, mw.search_results, mw.main_view
    chk(sb.isVisible() and mv.current_file() and Path(mv.current_file()).name == "z_doc.pdf", "준비 — z_doc 을 열고 검색 막대가 보인다")

    # A
    chk(sb.scope() == "file" and "지금 보는 파일" in sb.btn_scope.toolTip(), "A 기본 범위는 '파일'", sb.btn_scope.toolTip())
    chk(SearchBar().scope() == "file", "A 새 검색 막대도 '파일'(기억하지 않음)")
    lay = sb.layout()                                  # 덧붙인 지시 '폴더/파일 버튼을 검색 바로 오른쪽에'
    chk(lay.indexOf(sb.btn_scope) == lay.indexOf(sb.edit) + 1
        and sb.edit.geometry().right() < sb.btn_scope.x() < sb.btn_regex.x(),
        "A 범위 단추는 검색칸 바로 오른쪽(Aa·.* 앞)", "%d %d" % (lay.indexOf(sb.btn_scope), lay.indexOf(sb.edit)))

    def tops():
        return [sr.tree.topLevelItem(i) for i in range(sr.tree.topLevelItemCount())]

    def names():
        return [t.text(0) for t in tops()]

    def search_enter(q):
        QTest.mouseClick(sb.edit, Qt.MouseButton.LeftButton); sb.edit.selectAll()
        QTest.keyClicks(sb.edit, q); n0 = len(done)
        QTest.keyClick(sb.edit, Qt.Key.Key_Return)
        return wait(lambda: len(done) > n0)

    done = []
    _orig = mw._on_search_finished

    def spy(q, r):
        _orig(q, r); done.append(q)
    mw._on_search_finished = spy

    # B
    mv.go_to_page(0); QTest.qWait(50)
    chk(search_enter("alpha"), "준비 — 검색이 끝났다")
    QTest.qWait(300)
    chk(names() == ["z_doc"], "B '파일' 범위 — 지금 파일 결과만", str(names()))
    chk(Path(mv.current_file()).name == "z_doc.pdf" and mv.current_page() in (1, 3), "B 본문은 지금 파일의 결과 쪽으로", str(mv.current_page()))

    # C — 결과 없는 파일을 연다
    n0 = len(done)
    mw._load_main(HistoryItem(str(A), 1, "", "bookmark")); wait_main_open(mw)
    chk(wait(lambda: len(done) > n0), "C 다른 파일을 열면 그 파일에서 다시 찾는다")
    QTest.qWait(300)
    t = tops()
    chk(names() == ["a_doc"] and t[0].childCount() == 1 and t[0].child(0).text(0) == "검색결과 없음",
        "C 그 파일 줄 + '검색결과 없음'", str(names()))
    chk(Path(mv.current_file()).name == "a_doc.pdf" and mv.current_page() == 1, "C 본문은 연 쪽 그대로", "%s %d" % (mv.current_file(), mv.current_page()))
    chk(mw._recent_searches[0].get("query") == "alpha" and sum(1 for r in mw._recent_searches if r.get("query") == "alpha") == 1,
        "C 다시 찾기는 최근 검색어를 늘리지 않는다")

    # D — 단추를 눌러 폴더로
    n0 = len(done)
    QTest.mouseClick(sb.btn_scope, Qt.MouseButton.LeftButton)
    chk(sb.scope() == "folder" and "폴더" in sb.btn_scope.toolTip().split("—")[0], "D 단추를 누르면 '폴더'", sb.btn_scope.toolTip())
    chk(wait(lambda: len(done) > n0), "D 범위를 바꾸면 다시 찾는다")
    QTest.qWait(300)
    chk(set(names()) == {"z_doc", "m_doc", "a_doc"}, "D 폴더 — 다른 파일 결과와 지금 파일 줄", str(names()))
    a_row = [x for x in tops() if x.text(0) == "a_doc"]
    chk(a_row and a_row[0].child(0).text(0) == "검색결과 없음", "D 지금 파일엔 '검색결과 없음' 줄")
    chk(Path(mv.current_file()).name == "a_doc.pdf" and mv.current_page() == 1, "D 다른 파일로 옮기지 않는다", "%s %d" % (mv.current_file(), mv.current_page()))

    # E
    sent = []
    sr.resultActivated.connect(lambda f, p, q: sent.append((f, p)))
    none = a_row[0].child(0)
    QTest.mouseClick(sr.tree.viewport(), Qt.MouseButton.LeftButton, pos=sr.tree.visualItemRect(none).center()); QTest.qWait(300)
    QTest.mouseClick(sr.tree.viewport(), Qt.MouseButton.LeftButton, pos=sr.tree.visualItemRect(a_row[0]).center()); QTest.qWait(300)
    chk(sent == [] and Path(mv.current_file()).name == "a_doc.pdf", "E '검색결과 없음' 줄·그 파일 줄은 눌러도 가지 않는다", str(sent))
    chk(all(Path(r.file_path).name != "a_doc.pdf" for r in sr.get_displayed_results()), "E 엑셀 저장 목록엔 없다")

    # F — 책갈피창 정렬
    want = [Path(p).stem for p in bt.ordered_pdf_files()]
    chk(names() == want, "F 결과 파일 차례 = 책갈피창 차례(수정일 순)", "%s / %s" % (names(), want))
    bt._sort_combo.setCurrentIndex(bt._sort_combo.findData(bt.SORT_NAME)); QTest.qWait(300)
    want2 = [Path(p).stem for p in bt.ordered_pdf_files()]
    chk(want2 != want and names() == want2, "F 책갈피창 정렬을 바꾸면 결과도 따라간다(이름 순)", "%s / %s" % (names(), want2))
    mw.close()
except Exception:
    import traceback; traceback.print_exc()
    fails.append("예외")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
print("FAILED:", len(fails)) if fails else print("ALL PASS")
sys.stdout.flush()
os._exit(1 if fails else 0)          # Qt 소멸 단계 충돌을 피한다(MainWindow 검사 관례)
