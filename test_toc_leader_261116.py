# -*- coding: utf-8 -*-
"""261116-14: 목차 점선이 쪽 번호를 넘거나 겹치지 않는다 — 그림(픽셀)으로 본다 (마스터 §11.10.6).

사용자 보고: "목차만들기 후, 항목 2개의 페이지 오른 쪽으로 점이 몇개 있어" — 한 자리 번호 줄은 점선이 번호
오른쪽으로 넘고, 두·세 자리 번호 줄은 마지막 점이 번호 첫 글자와 겹쳤다. 원인: `twoup._kr_text` 가 굵은·보통
맑은 고딕을 같은 자원 이름(`krf`)으로 넣어, 쪽에 먼저 들어간 굵은 제목 글꼴이 번호·점선에도 쓰였다(폭은 보통으로 쟀다).

줄마다 (그 줄 높이의 띠에서) ① 오른쪽 여백(번호 끝) 뒤에 잉크가 없다 ② 번호 바로 왼쪽에 흰 틈(≥ 1pt)이 있다
③ 번호·점선은 보통 글꼴(굵게 그리지 않는다). 책갈피창 목차(영문·한글, fitz)·다단 목차, Word 가 있으면 샘플 양식 길도.
(수정 전 코드: ①② 실패)
"""
import os, sys, tempfile, shutil, faulthandler
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(300, exit=True)
from pathlib import Path

import fitz

fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


ZOOM = 4.0          # 1pt = 4px
INK = 200           # 이보다 어두우면 잉크


def rows_ok(doc, pno, label):
    """그 쪽의 목차 줄(오른쪽 끝 숫자가 있는 줄)마다 ①② 를 그림으로 본다. [(번호, 끝 뒤 잉크 px, 틈 pt)]"""
    page = doc[pno]
    W = page.rect.width
    pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), colorspace=fitz.csGRAY, alpha=False)
    sam, stride = pix.samples, pix.stride

    def dark(x, y):
        return sam[y * stride + x] < INK

    words = page.get_text("words")
    nums = [w for w in words if w[4].isdigit() and w[2] > W * 0.8]
    res = []
    for w in nums:
        y0, y1 = int((w[1] + 1) * ZOOM), int((w[3] - 1) * ZOOM)
        x_end = int((w[2] + 1.0) * ZOOM)               # 번호 글자 상자 끝 + 1pt
        after = sum(1 for x in range(x_end, pix.width) for y in range(y0, y1) if dark(x, y))
        # 번호 잉크의 왼쪽 끝 — 번호 상자 안에서 가장 왼쪽 잉크 열
        cols = [x for x in range(int(w[0] * ZOOM) - 2, int(w[2] * ZOOM) + 1)
                if any(dark(x, y) for y in range(y0, y1))]
        left = min(cols) if cols else int(w[0] * ZOOM)
        gap = 0
        x = left - 1
        while x > 0 and not any(dark(x, y) for y in range(y0, y1)):
            gap += 1; x -= 1
        res.append((w[4], after, round(gap / ZOOM, 1)))
    bad = [r for r in res if r[1] > 0 or r[2] < 1.0]     # Word 의 탭 점선은 번호 앞 1.5pt 안팎(겹치지 않음)
    chk(bool(res) and not bad, "%s — 점선이 번호를 넘거나 겹치지 않는다(끝 뒤 잉크 0·번호 앞 틈 ≥ 1pt)" % label,
        str(bad or res))
    return res


def plain_nums(doc, pno, label):
    """번호 글자의 글꼴이 굵지 않다(③)."""
    fonts = set()
    W = doc[pno].rect.width
    for b in doc[pno].get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                t = "".join(c["c"] for c in s["chars"]).strip()
                if t.isdigit() and s["bbox"][2] > W * 0.8:
                    fonts.add(s["font"])
    chk(fonts and not any("Bold" in f for f in fonts), "%s — 번호는 보통 글꼴" % label, str(fonts))


root = Path(tempfile.mkdtemp(prefix="polypdf_tocleader_"))
try:
    from viewer import toc_page, twoup
    EN = [[1, "CONTENTS", 2], [1, "1. GENERAL CONCEPTS", 3], [1, "2. LABORATORY TESTS - FRENCH STANDARDS AFNOR", 25],
          [1, "3. EMULSION MANFACTURE", 81], [1, "4. MAINTENANCE AND REPAIR", 93], [1, "5. SURFACE DRESSINGS", 101],
          [1, "6. TACK COATS - SEAL COATS", 132]]
    KO = [[1, "1장 서론", 2], [2, "1.1 배경", 3], [1, "2장 방법", 9], [1, "3장 결과", 98], [1, "4장 고찰", 120]]

    def make(name, toc, n):
        p = root / name
        d = fitz.open()
        for i in range(n):
            d.new_page(width=595, height=842).insert_text((72, 100), "page %d" % (i + 1))
        d.set_toc(toc)
        d.save(str(p)); d.close()
        return p

    en = make("en.pdf", EN, 140)
    ko = make("ko.pdf", KO, 125)

    # 책갈피창 목차 길(fitz) — 영문·한글
    for src, lv, label in ((en, 1, "책갈피창 영문"), (ko, 2, "책갈피창 한글")):
        out = root / (src.stem + "_toc.pdf")
        toc_page.insert_toc(str(src), str(out), "", lv)
        with fitz.open(str(out)) as o:
            rows_ok(o, 1, label)
            plain_nums(o, 1, label)

    # 다단 목차
    nup = root / "nup.pdf"
    twoup.build_twoup([{"type": "pdf", "path": str(en), "name": "en"}],
                      twoup.single_file_settings({"nup": 2, "make_toc": True, "footer_pos": "none"}), str(nup))
    with fitz.open(str(nup)) as o:
        rows_ok(o, 0, "다단 영문")

    # 직접 그리기 — 한 자리·세 자리 번호가 섞인 줄, 점이 아주 많은 짧은 제목
    d, _r = toc_page.render_fitz([(1, "A", "6"), (1, "B", "7"), (1, "Short", "105"), (2, "가", "136")], 595, 842, "CONTENTS")
    rows_ok(d, 0, "render_fitz 짧은 제목")
    plain_nums(d, 0, "render_fitz")
    d.close()

    # Word 가 있으면 샘플 양식 길(Word 의 오른쪽 탭 점선)
    tpl = root / "목차_샘플.docx"
    if toc_page.write_sample(str(tpl)):
        out = root / "en_word.pdf"
        try:
            toc_page.insert_toc(str(en), str(out), "", 1, template=str(tpl), tmpdir=str(root))
            with fitz.open(str(out)) as o:
                rows_ok(o, 1, "샘플 양식(Word 있으면 Word, 없으면 fitz)")
        except Exception as e:
            chk(False, "샘플 양식 길 예외 없음", repr(e))
finally:
    shutil.rmtree(root, ignore_errors=True)

print("\n%s — 실패 %d" % ("ALL PASS" if not fails else "FAIL", len(fails)))
sys.exit(1 if fails else 0)
