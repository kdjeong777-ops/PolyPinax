# -*- coding: utf-8 -*-
"""명함 인식 모듈 (명함 SOT §5.2·§5.4, P1 261117-2) — 가짜 명함만 쓴다(실제 명함 값 금지, 명함 SOT §2.1).

A. 다듬기 — 법인 꼴 떼기·띄운 회사명 붙이기, `성명_회사명.jpg`, ScanSnap 파일 이름 힌트
B. 전화·메일 — 앞말(M·F·T)로 종류, 숫자 사이 O→0, ©→@, 지역번호·휴대폰 꼴만
C. 이름 후보 — 큰 글자·성씨·직함 이웃이 이기고, 회사·주소 줄은 지며, '홍길동부장' 같은 붙은 줄에서도 나온다
D. 앞뒤 합치기 — 한글판은 한글 주·영문 따로(R7), 한글 없는 명함은 영문 주, 영문판은 영문 주, 홍보 뒷면 판정(R8)
E. 원천 — 그림 폴더의 하위 `pdf\\<앞부분>.pdf` 가 있으면 PDF 가 원천, 앞·뒤 짝 찾기
F. 그린 가짜 명함(그림·PDF)을 로컬 Tesseract 로 끝까지(없으면 SKIP)
"""
import os, sys, tempfile, shutil
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pathlib import Path
from PyQt6.QtCore import QStandardPaths
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2 — 실제 설정·데이터 폴더를 쓰지 않는다

fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


try:
    from viewer.bizcard import recognize as R
except Exception as e:                      # 이 판 전 코드엔 모듈이 없다
    chk(False, "모듈 viewer.bizcard.recognize 를 불러온다", repr(e))
    print("FAILURES: %d" % len(fails))
    sys.exit(1)

L = R.Line

# ── A ──
print("=== A. 다듬기 ===")
chk(R.strip_corp("(주) 가나다기술") == "가나다기술", "A (주) 떼기", R.strip_corp("(주) 가나다기술"))
chk(R.strip_corp("㈜가나다 건설") == "가나다건설", "A ㈜ 떼기·한글 회사명은 붙여 쓴다", R.strip_corp("㈜가나다 건설"))
chk(R.strip_corp("주식회사 라마바") == "라마바", "A 주식회사 떼기")
chk(R.strip_corp("( 주)사아자") == "사아자", "A 빈칸 낀 ( 주) 떼기")
chk(R.strip_corp("(주) 가 나 다 엔 씨") == "가나다엔씨", "A 한 글자씩 띄운 회사명 붙이기", R.strip_corp("(주) 가 나 다 엔 씨"))
chk(R.strip_corp("Example Co., Ltd.") == "Example", "A 영문 법인 꼴 떼기", R.strip_corp("Example Co., Ltd."))
chk(R.card_filename("홍 길동", "(주)가나다기술") == "홍길동_가나다기술.jpg", "A 성명_회사명 — 한글 이름 붙임·법인 꼴 없음")
chk(R.card_filename("John Doe", "Example Inc.") == "John Doe_Example.jpg", "A 영문 이름은 그대로", R.card_filename("John Doe", "Example Inc."))
chk(R.card_filename("홍길동", 'A/B:C*"') == "홍길동_ABC.jpg", "A 파일 이름에 못 쓰는 글자 빼기", R.card_filename("홍길동", 'A/B:C*"'))
chk(R.card_filename("홍길동", "") == "홍길동.jpg", "A 회사가 없으면 성명만")
chk(R.parse_hint(r"C:\x\(주) 가나다기술_홍 길동_p0001.png") == ("홍길동", "가나다기술"), "A 파일 이름 힌트(_p0001)",
    str(R.parse_hint(r"C:\x\(주) 가나다기술_홍 길동_p0001.png")))
chk(R.parse_hint(r"C:\x\가나다_공학박사 홍길동_1.jpg")[0] == "홍길동", "A 힌트에서 '공학박사' 빼기")
chk(R.parse_hint(r"C:\x\Example University_John Doe_1.jpg")[0] == "John Doe", "A 영문 이름 힌트")

# ── B ──
print("\n=== B. 전화·메일 ===")
ph = R.find_phones("T. 02-000-0001  F. 02-000-0002  M. 010-0000-0003")
chk(ph == [("work", "02-000-0001"), ("fax", "02-000-0002"), ("cell", "010-0000-0003")], "B 앞말로 종류(T·F·M)", str(ph))
chk(R.find_phones("H.P 010.0000.0004") == [("cell", "010-0000-0004")], "B 점으로 나눈 휴대폰")
chk(R.find_phones("Tel 031) 000-0005") == [("work", "031-000-0005")], "B 지역번호 괄호")
chk(R.find_phones("010-OOOO-0006") == [("cell", "010-0000-0006")], "B 숫자 사이 O 를 0 으로", str(R.find_phones("010-OOOO-0006")))
chk(R.find_phones("+82-10-0000-0007") == [("cell", "010-0000-0007")], "B 국제 꼴 +82", str(R.find_phones("+82-10-0000-0007")))
chk(R.find_phones("팩스 : 051-000-0008") == [("fax", "051-000-0008")], "B 한글 앞말 팩스")
chk(R.find_phones("사업자 123-45-67890") == [], "B 사업자번호 꼴은 전화가 아니다", str(R.find_phones("사업자 123-45-67890")))
chk(R.find_emails("E-mail: user©example.com") == ["user@example.com"], "B © 를 @ 로")
chk(R.find_emails("hong @ example , co.kr") == ["hong@example.co.kr"], "B 빈칸·쉼표 낀 메일", str(R.find_emails("hong @ example , co.kr")))
chk(R.find_urls("www.example.co.kr") == ["www.example.co.kr"], "B 누리집")

# ── C ──
print("\n=== C. 이름 후보 ===")
lines = [L("(주) 가나다기술", 0.10, 90, 0.05), L("기술연구소 부장", 0.06, 90, 0.30), L("홍 길 동", 0.16, 85, 0.40),
         L("서울특별시 가나구 다라로 12", 0.05, 90, 0.80), L("M. 010-0000-0001 E. hong@example.com", 0.05, 90, 0.90)]
r = R.parse_lines(lines)
chk(r.names_ko and r.names_ko[0].text == "홍길동", "C 띄운 이름이 큰 글자·직함 이웃으로 1위", str([c.text for c in r.names_ko[:3]]))
chk(r.companies_ko and r.companies_ko[0].text == "가나다기술", "C 회사 1위", str([c.text for c in r.companies_ko[:3]]))
chk(r.address_ko.startswith("서울특별시"), "C 주소")
chk(r.titles_ko == ["부장"], "C 직함", str(r.titles_ko))
chk(r.phones == [("cell", "010-0000-0001")] and r.emails == ["hong@example.com"], "C 연락처")
lines2 = [L("가나다건설", 0.12, 90, 0.1), L("대표이사홍길동", 0.10, 70, 0.4), L("010-0000-0002", 0.05, 90, 0.9)]
r2 = R.parse_lines(lines2)
chk(any(c.text == "홍길동" for c in r2.names_ko[:3]), "C 직함에 붙은 이름도 후보 3위 안", str([c.text for c in r2.names_ko[:3]]))
lines3 = [L("나무기술", 0.15, 90, 0.1), L("홍길동", 0.08, 90, 0.5), L("김철수", 0.08, 90, 0.6)]
r3 = R.parse_lines(lines3, hint_name="김철수")
chk(r3.names_ko[0].text == "김철수", "C 파일 이름 힌트가 같은 크기 후보를 가른다", str([c.text for c in r3.names_ko[:3]]))
chk(all(c.text != "나무기술" for c in r3.names_ko[:2]), "C 회사꼴 낱말은 이름 위로 가지 않는다")

# ── D ──
print("\n=== D. 앞뒤 합치기 ===")
front = R.parse_lines(lines)
back = R.parse_lines([L("Gildong Hong", 0.12, 90, 0.3), L("Senior Manager", 0.06, 90, 0.4),
                      L("Ganada Tech Co., Ltd.", 0.08, 90, 0.1), L("M. +82-10-0000-0001", 0.05, 90, 0.9)])
c = R.merge_sides(front, back)
chk(c.name == "홍길동" and c.company == "가나다기술", "D 한글판 — 한글이 주", c.name + "/" + c.company)
chk(c.en.get("name") == "Gildong Hong" and "Ganada" in c.en.get("company", ""), "D 영문은 en 칸에 따로", str(c.en))
chk(c.phones == [("cell", "010-0000-0001")], "D 같은 번호는 한 번", str(c.phones))
chk(set(c.langs) == {"한글", "영어"}, "D 해시태그 언어 둘 다", str(c.langs))
chk(c.back_promo is False, "D 연락처 있는 뒷면은 홍보 면이 아니다")
ce = R.merge_sides(front, back, ui_lang="en")
chk(ce.name == "Gildong Hong" and ce.en == {}, "D 영문판 — 영문만 주", ce.name)
fo = R.merge_sides(R.parse_lines([L("Jane Roe", 0.14, 90, 0.3), L("Professor", 0.06, 90, 0.4),
                                  L("Example University", 0.08, 90, 0.1), L("jane@example.edu", 0.05, 90, 0.9)]), None)
chk(fo.name == "Jane Roe" and fo.langs == ("영어",) and fo.back_promo is None, "D 한글 없는 명함(외국인) — 영문이 주, 뒷면 없음", fo.name + str(fo.langs))
promo = R.parse_lines([L("친환경 포장 기술의 선두 기업", 0.08, 80, 0.3), L("품질 · 신뢰 · 혁신", 0.06, 80, 0.6)])
chk(R.merge_sides(front, promo).back_promo is True, "D 연락처 없는 홍보 뒷면 → 홍보 면(R8)")

# ── E ──
print("\n=== E. 원천 ===")
tmp = Path(tempfile.mkdtemp(prefix="bizcard_src_"))
try:
    (tmp / "pdf").mkdir()
    for n in ("가나다_홍길동_p0001.png", "가나다_홍길동_p0002.png", "라마_김철수_1.jpg", "가나다_홍길동_1.jpg"):
        (tmp / n).write_bytes(b"x")
    (tmp / "pdf" / "가나다_홍길동.pdf").write_bytes(b"%PDF")
    s1 = R.card_sources(tmp / "가나다_홍길동_p0001.png")
    chk(s1["pdf"] and s1["pdf"].name == "가나다_홍길동.pdf", "E 하위 pdf 폴더의 같은 앞부분 PDF 가 원천")
    chk(s1["back"] and s1["back"].name == "가나다_홍길동_p0002.png", "E 뒷면 짝")
    s2 = R.card_sources(tmp / "pdf" / "가나다_홍길동.pdf")
    chk(s2["front"] is not None and s2["pdf"] is not None, "E PDF 경로로 불러도 그림 짝을 찾는다")
    s3 = R.card_sources(tmp / "라마_김철수_1.jpg")
    chk(s3["pdf"] is None and s3["front"].name == "라마_김철수_1.jpg" and s3["back"] is None, "E PDF 없는 JPG 는 그림이 원천")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ── F ──
print("\n=== F. 가짜 명함 끝까지(로컬 Tesseract) ===")
from viewer.study import ocr as O
from test_fixtures import KRFONT
if not O.ensure_tesseract().get("ok") or not KRFONT or "kor" not in O.available_langs():
    print("SKIP - Tesseract·한국어 자료·한글 글꼴이 없다")
else:
    from PIL import Image, ImageDraw, ImageFont
    import fitz

    def draw_card(w, h, k):
        im = Image.new("RGB", (w, h), "white")
        d = ImageDraw.Draw(im)
        f = lambda s: ImageFont.truetype(KRFONT, int(s * k))
        d.text((int(30 * k), int(25 * k)), "(주) 가나다기술", font=f(22), fill="navy")
        d.text((int(30 * k), int(80 * k)), "홍길동", font=f(46), fill="black")
        d.text((int(200 * k), int(98 * k)), "부장", font=f(22), fill="black")
        d.text((int(30 * k), int(170 * k)), "서울특별시 가나구 다라로 12", font=f(18), fill="black")
        d.text((int(30 * k), int(200 * k)), "M. 010-0000-0001   T. 02-000-0002", font=f(18), fill="black")
        d.text((int(30 * k), int(228 * k)), "E. hong@example.com", font=f(18), fill="black")
        return im

    def draw_back(w, h, k):
        im = Image.new("RGB", (w, h), "white")
        d = ImageDraw.Draw(im)
        f = lambda s: ImageFont.truetype(KRFONT, int(s * k))
        d.text((int(30 * k), int(40 * k)), "Gildong Hong", font=f(36), fill="black")
        d.text((int(30 * k), int(95 * k)), "Senior Manager", font=f(20), fill="black")
        d.text((int(30 * k), int(140 * k)), "Ganada Tech Co., Ltd.", font=f(20), fill="black")
        d.text((int(30 * k), int(200 * k)), "M. +82-10-0000-0001", font=f(18), fill="black")
        return im

    tmp = Path(tempfile.mkdtemp(prefix="bizcard_ocr_"))
    try:
        # 그림 원천 — 낮은 해상도(실제 JPG 와 같은 339픽셀 폭)
        small = draw_card(1060, 580, 2).resize((339, 186), Image.LANCZOS)
        small.save(tmp / "잘못된회사_잘못된이름_1.jpg", quality=90)
        res = R.recognize(tmp / "잘못된회사_잘못된이름_1.jpg")
        chk(("cell", "010-0000-0001") in res.phones, "F 낮은 해상도 그림 — 휴대폰", str(res.phones))
        chk("hong@example.com" in res.emails, "F 낮은 해상도 그림 — 메일", str(res.emails))
        chk(any(cd.text == "홍길동" for cd in res.name_cands), "F 낮은 해상도 그림 — 이름 후보 3위 안(틀린 파일 이름 힌트에도)",
            str([cd.text for cd in res.name_cands]))
        # PDF 원천 — 300 dpi 그림 2쪽(앞·뒤)
        (tmp / "pdf").mkdir()
        doc = fitz.open()
        for im in (draw_card(1075, 591, 1.0), draw_back(1075, 591, 1.0)):
            buf = tmp / "pg.png"
            im.save(buf)
            pg = doc.new_page(width=91 / 25.4 * 72, height=50 / 25.4 * 72)
            pg.insert_image(pg.rect, filename=str(buf))
        doc.save(str(tmp / "pdf" / "가나다_홍길동.pdf"))
        doc.close()
        small.save(tmp / "가나다_홍길동_p0001.png")
        res2 = R.recognize(tmp / "가나다_홍길동_p0001.png")
        chk(res2.sources.get("pdf", "").endswith("가나다_홍길동.pdf"), "F PDF 가 원천")
        chk(res2.name == "홍길동", "F PDF — 이름 1위", res2.name)
        chk("가나다기술" in res2.company, "F PDF — 회사(법인 꼴 없음)", res2.company)
        chk(("cell", "010-0000-0001") in res2.phones and ("work", "02-000-0002") in res2.phones, "F PDF — 휴대폰·전화", str(res2.phones))
        chk(res2.en.get("name") == "Gildong Hong", "F PDF — 영문 뒷면은 en 칸에(R7)", str(res2.en))
        chk(res2.back_promo is False, "F PDF — 연락처 있는 뒷면은 지우지 않는다")
        chk(R.card_filename(res2.name, res2.company) == "홍길동_가나다기술.jpg", "F 새 파일 이름")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

print()
print("ALL PASS" if not fails else "FAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
