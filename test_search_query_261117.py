# -*- coding: utf-8 -*-
"""261117-30(검색창 SOT §4.2): 앱 안 모든 검색에 연산자 — 띄어쓰기 AND · `|` OR · `-` NOT · 괄호 · "따옴표" 구절.

A. 해석기 단위 — 우선순위(구글: - > | > 띄어쓰기)·구절·낱말 안 하이픈·관대한 해석·NOT 뿐·SQL 은 매개변수만·FTS5 식
B. 색인 결과(`PdfIndex.search`) — 같은 쪽 안 AND·NOT·OR·괄호·구절, 개수·조각 글은 긍정 낱말만, NOT 뿐은 빈 결과, Aa·정규식
C. 본문 강조(`page_hits`·`search_pages`) — 식이 참인 쪽만, 긍정 낱말만 칠한다, 낱말 하나는 종전 그대로
D. 책갈피창 거르기 — 파일 단위(이름·책갈피·키워드), `#태그` 는 따로
E. 명함찾기(`people.find`) — 가짜 명함만(명함 SOT §2.1)
F. 사진 검색(`photo_index.search`) — FTS5 식
G. 오른쪽 창 본문 찾기(`content_find`) · 사용자 뜻 · 태그 붙이기 창 찾기 · 설정 찾기
수정 전 코드로는 실패한다(`a b` 가 '빈칸 무시 구절' 이었고 `|`·`-`·괄호는 글자였다).
"""
import os, sys, tempfile, shutil
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pathlib import Path
import fitz
from PyQt6.QtCore import QStandardPaths
from PyQt6.QtWidgets import QApplication

QStandardPaths.setTestModeEnabled(True)           # 검사 작성 SOT §14.7.2 — 실제 설정 폴더를 쓰지 않는다
app = QApplication.instance() or QApplication(sys.argv)
app.setApplicationName("polypdf_test_query_261117")

fails = []


def chk(c, m, extra=""):
    print(("PASS" if c else "FAIL"), "-", m, ("" if c else extra))
    if not c:
        fails.append(m)


root = Path(tempfile.mkdtemp(prefix="polypdf_query_"))
try:
    # ── A. 해석기 ──
    from viewer.query import parse
    r = lambda q: repr(parse(q).root)
    chk(r("a b|c") == "AND(a, OR(b, c))", "A1 '|' 가 띄어쓰기보다 먼저 묶인다(구글)", r("a b|c"))
    chk(r("(a b)|c") == "OR(AND(a, b), c)", "A2 괄호로 묶는다", r("(a b)|c"))
    chk(r("a -b") == "AND(a, -(b))", "A3 낱말 앞 '-' 는 NOT", r("a -b"))
    chk(parse("coarse-graded").single == "coarse-graded", "A4 낱말 안 하이픈은 NOT 이 아니다")
    chk(parse('"a b"').single == "a b" and parse('"a | -b"').single == "a | -b", "A5 따옴표 안은 구절(연산자도 글자)")
    chk(parse("-a").neg_only and parse("-a -b").neg_only and not parse("-a").ok, "A6 NOT 뿐이면 찾을 낱말 없음")
    chk(parse("a | -b").single == "a", "A7 OR 의 NOT 갈래는 버린다", r("a | -b"))
    chk(r("a (b") == "AND(a, b)" and r("a ) b") == "AND(a, b)" and parse("| a |").single == "a" and parse('"a').single == "a",
        "A8 관대한 해석 — 닫히지 않은 괄호·따옴표, 짝 없는 ')', 앞뒤 '|'")
    chk(parse("").empty and parse("()").empty and parse("-").empty and not parse("-").neg_only, "A9 빈 질의")
    sql, args = parse("x'); DROP TABLE files; -- -y").sql("flat")
    chk("DROP" not in sql and "x'" not in sql and any("DROP" in a for a in args), "A10 SQL 은 낱말을 매개변수로만", sql)
    chk(parse("a -(b|c)").fts() == '("a"*) NOT ("b"* OR "c"*)', "A11 FTS5 식", parse("a -(b|c)").fts())
    chk(parse("asphalt crack").matches("Asphalt\nconcrete with CRACK") and not parse("asphalt -crack").matches("asphalt crack"),
        "A12 matches — 대소문자·빈칸 무시, NOT")
    chk(parse('"pavement crack"').matches("pave-\nment crack") and not parse('"pavement crack"').matches("crack pavement"),
        "A13 구절은 이어진 글(빈칸·하이픈 무시)")

    # ── B. 색인 결과 ──
    pdf = root / "doc.pdf"
    d = fitz.open()
    for line in ("asphalt pavement crack survey", "asphalt concrete repair", "concrete crack repair method",
                 "Asphalt pavement design"):
        pg = d.new_page()
        pg.insert_text((72, 100), line, fontname="helv", fontsize=11)
    d.save(str(pdf)); d.close()
    from viewer.indexer import PdfIndex
    PdfIndex.MAKE_TAGFEAT = False
    ix = PdfIndex(root / "index.db")
    ix.index_file(pdf)
    pages = lambda q, mode=None: sorted(x.page_index for x in ix.search(q, mode=mode))
    chk(pages("asphalt crack") == [0], "B1 띄어쓰기 = 같은 쪽 AND", str(pages("asphalt crack")))
    chk(pages("asphalt -crack") == [1, 3], "B2 '-' = NOT", str(pages("asphalt -crack")))
    chk(pages("asphalt|repair") == [0, 1, 2, 3], "B3 '|' = OR", str(pages("asphalt|repair")))
    chk(pages("(asphalt|concrete) -repair") == [0, 3], "B4 괄호", str(pages("(asphalt|concrete) -repair")))
    chk(pages('"pavement crack"') == [0] and pages('"crack pavement"') == [], "B5 따옴표 구절")
    chk(pages("asphalt") == [0, 1, 3], "B6 낱말 하나는 종전 그대로", str(pages("asphalt")))
    res = ix.search("crack asphalt -concrete")
    chk(len(res) == 1 and res[0].match_count == 2 and "<" in res[0].snippet, "B7 개수·조각 글은 긍정 낱말만",
        str([(x.match_count, x.snippet) for x in res]))
    chk(ix.search("-asphalt") == [], "B8 NOT 뿐이면 빈 결과")
    chk(pages("Asphalt -crack", mode=(True, False)) == [3], "B9 Aa — 낱말마다 대소문자 구분", str(pages("Asphalt -crack", mode=(True, False))))
    chk(pages("asphalt -crack", mode=(False, True)) == [], "B10 정규식이면 연산자를 해석하지 않는다")
    chk(pages("asphalt|repair", mode=(False, True)) == [0, 1, 2, 3], "B11 정규식의 | 는 정규식 갈래")
    ix.close()

    # ── C. 본문 강조 ──
    from viewer.pdf_doc import PdfDocument, page_hits
    doc = PdfDocument(str(pdf))
    hit_pages = sorted(h.page_index for h in doc.search_pages("asphalt crack", None, range(4)))
    chk(hit_pages == [0], "C1 문서 전체 찾기 — 식이 참인 쪽만", str(hit_pages))
    p0 = doc.doc.load_page(0)
    chk(len(page_hits(p0, "asphalt crack")) == 2, "C2 긍정 낱말을 모두 칠한다")
    chk(page_hits(p0, "asphalt -crack") == [], "C3 NOT 이 든 쪽은 칠하지 않는다")
    chk(len(page_hits(doc.doc.load_page(1), "asphalt -crack")) == 1, "C4 NOT 낱말은 칠하지 않는다")
    chk(len(page_hits(p0, "asphalt")) == 1, "C5 낱말 하나는 종전 그대로")
    chk(sorted(h.page_index for h in doc.search_pages("-asphalt", None, range(4))) == [], "C6 NOT 뿐이면 없다")

    # ── D. 책갈피창 거르기 ──
    from viewer.widgets.bookmark_tree import BookmarkTree
    from viewer.tag_store import TagStore
    from PyQt6.QtWidgets import QTreeWidgetItem
    ts = TagStore(str(root / "tags.json"))
    bt = BookmarkTree(); bt._tags = ts
    fa, fb = str(root / "fa.pdf"), str(root / "fb.pdf")
    ts.set(fa, ["보고서"]); ts.set_keywords(fb, ["porous"])
    ia = QTreeWidgetItem(["alpha report"]); ia.setData(0, bt.DATA_FILE, fa)
    ia.addChild(QTreeWidgetItem(["chapter crack"])); ia.addChild(QTreeWidgetItem(["chapter repair"]))
    ib = QTreeWidgetItem(["beta report"]); ib.setData(0, bt.DATA_FILE, fb)
    bt.tree.addTopLevelItem(ia); bt.tree.addTopLevelItem(ib)
    vis = lambda: [it.text(0) for it in (ia, ib) if not it.isHidden()]
    bt._on_filter("alpha crack")
    chk(vis() == ["alpha report"] and not ia.child(0).isHidden() and ia.child(1).isHidden(),
        "D1 파일 단위 AND(이름+책갈피), 책갈피 줄은 긍정 낱말이 든 줄만", str(vis()))
    bt._on_filter("report -crack")
    chk(vis() == ["beta report"], "D2 NOT", str(vis()))
    bt._on_filter("alpha|porous")
    chk(vis() == ["alpha report", "beta report"], "D3 OR(키워드 포함)", str(vis()))
    bt._on_filter("#보고서 report")
    chk(vis() == ["alpha report"], "D4 #태그 는 따로 AND", str(vis()))
    bt._on_filter("")
    chk(vis() == ["alpha report", "beta report"], "D5 비우면 모두")

    # ── E. 명함찾기 (가짜 값만) ──
    from viewer.bizcard.store import BizcardStore
    from viewer.bizcard import people
    bs = BizcardStore(root / "biz.db")
    bs.upsert({"front": str(root / "c1.jpg"), "name": "가나다", "company": "가상도로", "memo": "시험용", "tags": ["협력"],
               "phones": [("cell", "010-0000-1111")], "scanned": "2026-01-01"})
    bs.upsert({"front": str(root / "c2.jpg"), "name": "라마바", "company": "가상건설", "memo": "", "tags": [],
               "scanned": "2026-01-02"})
    names = lambda q: sorted(x["name"] for x in people.find(bs, q))
    chk(names("가상 -도로") == ["라마바"], "E1 NOT", str(names("가상 -도로")))
    chk(names("가나다|라마바") == ["가나다", "라마바"], "E2 OR", str(names("가나다|라마바")))
    chk(names("#협력 가상") == ["가나다"], "E3 #태그 와 AND", str(names("#협력 가상")))
    chk(names("00001111") == ["가나다"], "E4 번호 하이픈 무시", str(names("00001111")))
    chk(names("-가상") == [], "E5 NOT 뿐이면 없다")
    chk(len(people.find(bs, "")) == 2, "E6 빈 질의는 모두")

    # ── F. 사진 검색 ──
    from viewer import photo_index
    pdb = root / "photo.db"
    con = photo_index.connect(pdb)
    for n, tk in (("road_crack.jpg", "2020:01:02 10:00:00"), ("road_clean.jpg", "2021:05:06 10:00:00"), ("cat.jpg", "2021:07:08 10:00:00")):
        p = str(root / n)
        photo_index.upsert(con, os.path.normcase(p), p, photo_index.norm_folder(root), n, ".jpg", 1, 1, {"taken": tk}, [])
    con.commit(); con.close()
    pn = lambda q: sorted(x["name"] for x in photo_index.search(q, path=pdb))
    chk(pn("road -crack") == ["road_clean.jpg"], "F1 NOT", str(pn("road -crack")))
    chk(pn("crack|cat") == ["cat.jpg", "road_crack.jpg"], "F2 OR", str(pn("crack|cat")))
    chk(pn("-road") == [], "F3 NOT 뿐이면 없다")

    # ── G. 오른쪽 창 본문 찾기 · 사용자 뜻 · 태그 창 · 설정 ──
    from PyQt6.QtWidgets import QTextBrowser
    from viewer.widgets import content_find as cf
    tb = QTextBrowser(); tb.setPlainText("asphalt binder\nconcrete crack\nasphalt crack")
    cf.set_mode(None)
    st = {}
    chk(cf.search(tb, "asphalt crack", False, st)[1] == 4, "G1 본문 찾기 — 긍정 낱말 자리 모두", str(st.get("positions")))
    st = {}
    chk(cf.search(tb, "asphalt -crack", False, st)[1] == 0, "G2 본문 찾기 — 식이 거짓이면 없다")
    st = {}
    chk(cf.search(tb, "asphalt", False, st)[1] == 2, "G3 낱말 하나는 종전 그대로")

    from viewer.study.dict_store import DictStore
    ds = DictStore(root / "dict.db")
    ds.add_entry(term_ko="배수성 포장", term_en="porous pavement")
    ds.add_entry(term_ko="균열", term_en="crack")
    ue = lambda q: sorted(x["term_en"] for x in ds.user_entries(q))
    chk(ue("pavement|crack") == ["crack", "porous pavement"] and ue("포장 -균열") == ["porous pavement"],
        "G4 사용자 뜻 찾기", str(ue("pavement|crack")))

    from viewer.widgets.tag_apply_dialog import TagApplyDialog
    ts.set(fb, ["여행", "가족"])
    dlg = TagApplyDialog(ts, [fa, fb], [fa, fb])
    dlg.ed_find.setText("여행|보고서"); app.processEvents()
    got = sorted(dlg.lst_tags.item(i).data(0x0100) for i in range(dlg.lst_tags.count()) if dlg.lst_tags.item(i).data(0x0100))
    chk(got == ["보고서", "여행"], "G5 태그 붙이기 창 찾기 — OR", str(got))
    dlg.ed_find.setText("-여행"); app.processEvents()
    chk(dlg.lst_tags.count() == 0 or not any(dlg.lst_tags.item(i).data(0x0100) for i in range(dlg.lst_tags.count())),
        "G6 태그 찾기 — NOT 뿐이면 없다")
    dlg.close()

    from viewer.widgets.settings_dialog import SettingsDialog, page_name, PAGES
    sd = SettingsDialog({}, None)
    pid0 = PAGES[0][0]
    w0 = page_name(pid0)
    sd._on_search(w0 + " -" + w0)                    # 같은 쪽 이름을 넣고 빼면 어느 쪽도 맞지 않는다
    chk(sd._page_items[pid0].isHidden(), "G7 설정 찾기 — NOT", w0)
    sd._on_search(w0 + "|없는낱말일리없다")
    chk(not sd._page_items[pid0].isHidden(), "G8 설정 찾기 — OR")
    sd.close()
finally:
    shutil.rmtree(root, ignore_errors=True)

print()
print("FAILED:", len(fails)) if fails else print("ALL PASS")
sys.exit(1 if fails else 0)
