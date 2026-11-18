# -*- coding: utf-8 -*-
"""명함 인식 모듈 (명함 SOT §5.2·§5.4, P1 261117-2) — 가짜 명함만 쓴다(실제 명함 값 금지, 명함 SOT §2.1).

A. 다듬기 — 법인 꼴 떼기·띄운 회사명 붙이기, `성명_회사명.jpg`, ScanSnap 파일 이름 힌트
B. 전화·메일 — 앞말(M·F·T)로 종류, 숫자 사이 O→0, ©→@, 지역번호·휴대폰 꼴만
C. 이름 후보 — 큰 글자·성씨·직함 이웃이 이기고, 회사·주소 줄은 지며, '홍길동부장' 같은 붙은 줄에서도 나온다
D. 앞뒤 합치기 — 한글판은 한글 주·영문 따로(R7), 한글 없는 명함은 영문 주, 영문판은 영문 주, 홍보 뒷면 판정(R8)
E. 원천 — 그림 폴더의 하위 `pdf\\<앞부분>.pdf` 가 있으면 PDF 가 원천, 앞·뒤 짝 찾기
F. 그린 가짜 명함(그림·PDF)을 로컬 Tesseract 로 끝까지(없으면 SKIP)
G. 정답 대조로 고친 규칙(§5.22) · H. 두 엔진 합침·해외 번호·기관 이름 직함(§5.23) · I. 보조 OCR 엔진 붙이기(단어학습 SOT §14.25)
J. 이름 정확도(§5.25) — 드문 음절·낱말 조각·두 글자 조각 보정, 파일 이름 두 글자 힌트, 영문 I/l·기관 문구
"""
import os, sys, tempfile, shutil
os.environ["QT_QPA_PLATFORM"] = "offscreen"          # 검사 작성 SOT §14.7 — Qt 를 쓰는 검사는 오프스크린
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
chk(r.dept_ko == "기술연구소", "C 부서(직함 앞 부서 낱말)", r.dept_ko)                      # 261117-11
rd = R.parse_lines([L("(주)가나다건설", 0.10, 90, 0.05), L("기술본부 품질관리팀", 0.06, 90, 0.3), L("홍길동 과장", 0.14, 90, 0.4),
                    L("서울특별시 가나구 다라로 12", 0.05, 90, 0.8)])
chk(rd.dept_ko == "기술본부품질관리팀" and rd.titles_ko == ["과장"], "C 부서 둘을 붙여 씀(띄어쓰기 없음, 261117-15)·회사·주소 줄은 부서가 아님", rd.dept_ko)
for line, want in (("대표 이사 홍 길 동", "대표이사"), ("전무 이사  김철수", "전무이사"), ("상무이사 이영희", "상무이사"),
                   ("대 표 이 사", "대표이사")):
    rt = R.parse_lines([L("(주)가나다건설", 0.10, 90, 0.05), L(line, 0.12, 90, 0.4)])
    chk(rt.titles_ko[:1] == [want], "C 직함은 줄이지 않는다 — '%s' → %s" % (line, want), str(rt.titles_ko))
rt2 = R.parse_lines([L("한국가나다기술연구원", 0.10, 90, 0.05), L("홍길동 과장", 0.12, 90, 0.4)])
chk(rt2.titles_ko == ["과장"], "C 기관 이름 속 '연구원' 은 직함이 아니다", str(rt2.titles_ko))
rq = R.parse_lines([L("(주)가나다건설", 0.10, 90, 0.05), L("공학박사 홍길동", 0.14, 90, 0.4), L("토목구조기술사", 0.06, 90, 0.5),
                    L("상무이사", 0.06, 90, 0.6)])
chk(rq.titles_ko[:1] == ["상무이사"] and not any(q in t for t in rq.titles_ko for q in ("박사", "기술사")),
    "C 공학박사·기술사는 직함이 아니다(261117-17)", str(rq.titles_ko))
chk(rq.names_ko and rq.names_ko[0].text == "홍길동", "C 이름 앞 '공학박사' 는 떼고 이름만", str([c.text for c in rq.names_ko[:2]]))
chk(R.rescore({"title": "공학박사", "name_cands": [], "company_cands": []})["title"] == ""
    and R.rescore({"title": "상무이사", "name_cands": [], "company_cands": []})["title"] == "상무이사",
    "C 옛 캐시에 직함으로 남은 자격은 다시 매기기에서 비운다(직함은 그대로)")
for line, want in (("(주) 가나다 기술 품질팀", "가나다기술"), ("가나다 기술(주)", "가나다기술"), ("기술연구소 가나다기술(주)", "가나다기술"),
                   ("(유) 라마바 대표이사", "라마바"), ("㈜사아자건설", "사아자건설")):
    rc_ = R.parse_lines([L(line, 0.08, 90, 0.1), L("홍길동", 0.14, 90, 0.4), L("가나다기술연구원장 김철수", 0.05, 90, 0.7)])
    chk(rc_.companies_ko and rc_.companies_ko[0].text == want, "C (주)·(유) 가 앞뒤에 붙은 낱말이 회사 — '%s' → %s" % (line, want),
        str([c.text for c in rc_.companies_ko[:2]]))
# 261117-18: 교정은 오인식만 — 다른 값을 고른 것(이사 ↔ 대표이사, 선임 → 선임컨설턴트)은 배우지도 쓰지도 않는다
chk(not R.correction_ok("title", "이사", "대표이사") and not R.correction_ok("title", "대표이사", "이사")
    and not R.correction_ok("title", "선임", "선임컨설턴트") and not R.correction_ok("company", "가나다", "가나다기술")
    and R.correction_ok("title", "다표이사", "대표이사") and R.correction_ok("company", "가나다기슬", "가나다기술"),
    "C 교정 판정 — 오인식만 배운다(늘이기·줄이기·다른 직함은 아님)")
bad = {"title": {"이사": "대표이사", "대표이사": "이사", "선임": "선임컨설턴트", "다표이사": "대표이사"}}
chk([R.rescore({"title": t, "name_cands": [], "company_cands": []}, None, None, None, bad)["title"] for t in ("이사", "대표이사", "선임", "다표이사")]
    == ["이사", "대표이사", "선임", "대표이사"], "C 이미 잘못 배운 교정은 쓰지 않는다 — 이사는 이사, 대표이사는 대표이사, 선임은 선임")
chk(R.nospace_ko("품질 관리 팀") == "품질관리팀" and R.nospace_ko("ABC 기술") == "ABC 기술", "C 한글 사이 띄어쓰기만 없앤다")
rg = R.parse_lines([L("국토교통부", 0.12, 90, 0.05), L("도로정책과", 0.06, 90, 0.3), L("홍길동 주무관", 0.14, 90, 0.4)])
chk(rg.dept_ko == "도로정책과", "C 기관 이름(…부)은 부서가 아니고 그 아래 과가 부서", rg.dept_ko)
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
chk(c.dept == "기술연구소", "D 합친 결과에 부서", c.dept)
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

# ── G ── 정답 대조로 고친 규칙(§5.22, 261118) — 가짜 값만
print("\n=== G. 정답 대조로 고친 규칙(§5.22) ===")
_has = lambda n: hasattr(R, n)
chk(all(_has(n) for n in ("fix_email", "pick_emails", "pick_phones", "join_letter_lines", "org_token", "project_line",
                          "dept_runs", "unglue_name")), "G 새 규칙 함수들이 있다")
if all(_has(n) for n in ("fix_email", "pick_emails", "pick_phones", "join_letter_lines")):
    chk(R.fix_email("hong@hanmal.net") == "hong@hanmail.net" and R.fix_email("hong@nale.com") == "hong@nate.com",
        "G 흔한 메일 도메인 한두 글자 오인식", R.fix_email("hong@hanmal.net"))
    chk(R.fix_email("e-mail.hong@example.co") == "hong@example.co.kr" and R.fix_email("hong@example.co.ke") == "hong@example.co.kr",
        "G 앞에 붙은 이름표 떼기·끝이 빠지거나 틀린 .kr", R.fix_email("e-mail.hong@example.co"))
    chk(R.find_emails("E-mail: hong0000@hanmailnet") == ["hong0000@hanmail.net"], "G 점이 빠진 'hanmailnet'",
        str(R.find_emails("E-mail: hong0000@hanmailnet")))
    pe = R.pick_emails("hongl000@example.com\nhong1000@example.com\nhong1000@example.com\n000@example.com")
    chk(pe == ["hong1000@example.com"], "G 여러 번 읽은 메일 — 한 글자 다른·앞이 잘린 것을 묶어 많이 나온 것", str(pe))
    pp = R.pick_phones(["T. 02-000-0001  F. 02-000-0002", "T. 02-000-0001", "T. 02-000-0007", "M. 010-0000-0003"])
    chk(pp[:1] == [("work", "02-000-0001")] and ("fax", "02-000-0002") in pp and ("cell", "010-0000-0003") in pp
        and not any(n == "02-000-0007" for _k, n in pp),
        "G 번호 고르기 — 한 자리 다른 같은 번호는 많이 나온 쪽, 전화·팩스는 따로", str(pp))
    pc = R.pick_phones(["Phone 010-0000-0004"])
    chk(pc == [("cell", "010-0000-0004")], "G 01x 는 'Phone' 표시여도 휴대폰", str(pc))
    jl = R.join_letter_lines([L("홍", 0.12, 90, 0.40, 0.30, 0.46), L("길", 0.12, 90, 0.40, 0.45, 0.46),
                              L("동", 0.12, 90, 0.40, 0.60, 0.46), L("홍", 0.12, 90, 0.40, 0.30, 0.46)])
    chk([x.text for x in jl] == ["홍길동"], "G 한 글자씩 따로 읽힌 이름을 잇는다(같은 자리 겹친 글자는 한 번)", str([x.text for x in jl]))
    rn = R.parse_lines([L("가나다기술", 0.10, 90, 0.05), L("홍", 0.16, 90, 0.4, 0.3, 0.48), L("길", 0.16, 90, 0.4, 0.45, 0.48),
                        L("동", 0.16, 90, 0.4, 0.6, 0.48), L("부장", 0.06, 90, 0.6)])
    chk(rn.names_ko and rn.names_ko[0].text == "홍길동", "G 이은 이름이 1위", str([c.text for c in rn.names_ko[:3]]))
if _has("org_token"):
    chk(R.parse_hint(r"C:\x\가나다기술_홍 길동_001_1.jpg")[0] == "홍길동" and R.parse_hint(r"C:\x\가나다_이름_1.jpg")[0] == "",
        "G 파일 이름 덧번호 '_001' 떼기·자리 글자 '이름' 은 이름이 아님", str(R.parse_hint(r"C:\x\가나다기술_홍 길동_001_1.jpg")))
    rh = R.parse_lines([L("가나다기술", 0.12, 90, 0.1), L("010-0000-0005", 0.05, 90, 0.9)], hint_name="홍길동")
    chk(rh.names_ko and rh.names_ko[0].text == "홍길동", "G 파일 이름의 이름은 OCR 에 없어도 후보 1위", str([c.text for c in rh.names_ko[:2]]))
    rh2 = R.parse_lines([L("가나다기술", 0.10, 90, 0.1), L("홍길순", 0.16, 90, 0.4), L("부장", 0.06, 90, 0.5)], hint_name="홍길동")
    chk(rh2.names_ko and rh2.names_ko[0].text == "홍길순", "G 파일 이름과 한 글자만 다른 큰 글자 이름이면 OCR 쪽", str([c.text for c in rh2.names_ko[:2]]))
    rcmp = R.parse_lines([L("AB 가나다주택공사", 0.10, 90, 0.05), L("홍길동", 0.16, 90, 0.4)])
    chk(rcmp.companies_ko and rcmp.companies_ko[0].text == "가나다주택공사", "G 줄 속 기관 낱말만 회사로", str([c.text for c in rcmp.companies_ko[:2]]))
    rcmp2 = R.parse_lines([L("가나 교통부", 0.10, 90, 0.05), L("홍길동", 0.16, 90, 0.4)])
    chk(rcmp2.companies_ko and rcmp2.companies_ko[0].text == "가나교통부", "G 띄어 읽힌 기관 이름을 잇는다", str([c.text for c in rcmp2.companies_ko[:2]]))
    rp = R.parse_lines([L("(주)가나다건설", 0.10, 90, 0.05), L("가나-다라 도로건설공사", 0.06, 90, 0.3), L("홍길동 현장소장", 0.14, 90, 0.4)])
    chk(rp.companies_ko and rp.companies_ko[0].text == "가나다건설" and rp.dept_ko == "가나-다라도로건설공사"
        and rp.titles_ko[:1] == ["현장소장"], "G 공사 이름(현장)은 회사가 아니라 부서 칸", rp.dept_ko + " / " + str([c.text for c in rp.companies_ko[:2]]))
    rd2 = R.parse_lines([L("가나다기술", 0.10, 90, 0.05), L("도로교통연구 본부", 0.06, 90, 0.3), L("감리2부 / 부장", 0.06, 90, 0.35),
                         L("홍길동", 0.14, 90, 0.4)])
    chk(rd2.dept_ko == "도로교통연구본부감리2부" and rd2.titles_ko[:1] == ["부장"], "G 이어진 부서 낱말 묶음·숫자 낀 부서·다음 줄 부서 잇기",
        rd2.dept_ko)
    rt3 = R.parse_lines([L("가나다기술", 0.10, 90, 0.05), L("책임 연구원 / 시설 사무관", 0.06, 90, 0.3), L("홍길동", 0.14, 90, 0.4)])
    chk(rt3.titles_ko[:2] == ["책임연구원", "시설사무관"] or set(rt3.titles_ko[:2]) == {"책임연구원", "시설사무관"},
        "G 겹 직함을 줄이지 않는다", str(rt3.titles_ko))
    chk(R.unglue_name("가나다기업홍길동", "홍길동") == "가나다기업", "G 회사명에 붙어 읽힌 이름 떼기")
    rdm = R.parse_lines([L("Cx 안국도로공사", 0.10, 90, 0.05), L("홍길동", 0.16, 90, 0.4), L("hong@ex.co.kr", 0.05, 90, 0.9)])
    chk(rdm.companies_ko and rdm.companies_ko[0].text == "한국도로공사", "G 메일 도메인이 아는 기관이면 닮은 회사 후보를 그 이름으로",
        str([c.text for c in rdm.companies_ko[:2]]))

# ── H ── 두 엔진 합침·해외 번호·기관 이름 직함(§5.23, 261118) — 가짜 값만
print("\n=== H. 두 엔진 합침·해외 번호(§5.23) ===")
chk(all(_has(n) for n in ("loose_phone", "_rare_ko", "_pick_twin_variant")) and "src" in R.Line.__dataclass_fields__,
    "H 새 규칙 함수·줄 엔진 표시(src)가 있다")
if _has("loose_phone"):
    pf = R.pick_phones(["T. +1-555-000-0002  Cell: (555) 000-0001", "M. 0100000 0003", "2018 08 01 str. 42"])
    chk(("work", "+1-555-000-0002") in pf and ("cell", "555-000-0001") in pf and ("cell", "010-0000-0003") in pf and len(pf) == 3,
        "H 해외 번호·묶음이 다른 국내 번호도 뽑고, 표시 없는 숫자(날짜·주소)는 뽑지 않는다", str(pf))
    chk(R.pick_phones(["M. +82 10 0000 0004"]) == [("cell", "010-0000-0004")], "H +82 국제 꼴은 국내 꼴로",
        str(R.pick_phones(["M. +82 10 0000 0004"])))
    chk(R.title_token("가나환경연구원") == "" and R.title_token("선임연구원") == "선임연구원" and R.title_token("연구위원") == "연구위원",
        "H '…환경연구원' 은 기관 이름, '선임연구원' 은 직함", R.title_token("가나환경연구원"))
    chk(R._rare_ko("가나뮘") == 1 and R._rare_ko("가나다") == 0, "H 완성형 밖 음절 세기")
    rc = R.parse_lines([L("가나엔지니어팅", 0.12, 90, 0.05), L("가나엔지니어링", 0.08, 90, 0.10, src="w"), L("홍길동", 0.16, 90, 0.4)])
    chk(rc.companies_ko and rc.companies_ko[0].text == "가나엔지니어링", "H 한 글자 다른 회사 판 중 아는 회사 낱말이 든 것",
        str([c.text for c in rc.companies_ko[:3]]))
    rn2 = R.parse_lines([L("가나다기술", 0.10, 90, 0.05), L("홍길동", 0.14, 90, 0.4), L("홍길둥", 0.16, 90, 0.4, src="w"),
                         L("부장", 0.06, 90, 0.5)])
    chk(rn2.names_ko and rn2.names_ko[0].text == "홍길동", "H 보조 엔진에만 있고 한 글자 다른 이름은 뒤로",
        str([c.text for c in rn2.names_ko[:3]]))
    pm = R.pick_emails("hong5s5@example.com\nhong55@example.com")
    chk(pm == ["hong55@example.com"], "H 같은 수로 나온 메일 판은 숫자 옆 헷갈리는 글자(s·o·l) 없는 쪽", str(pm))

# ── I ── 보조 엔진(Windows 내장 OCR)을 붙이는 길(단어학습 SOT §14.25) — 대역으로, 있으면 실제 엔진도
print("\n=== I. 보조 OCR 엔진 붙이기(§14.25) ===")
try:
    from viewer.study import win_ocr as WO
    from viewer.study import tess_run as TR
    from viewer.study import ocr as O2
except Exception as e:
    WO = None
    chk(False, "I viewer.study.win_ocr 를 불러온다", repr(e))
if WO is not None and _has("win_lines"):
    from PIL import Image as _Im
    keep = (O2.ensure_tesseract, TR.data, WO.available, WO.read)
    try:
        O2.ensure_tesseract = lambda *a, **k: {"ok": True}
        TR.data = lambda imgs, lang, cfg: [{"text": []} for _ in imgs]
        WO.available = lambda: True
        WO.read = lambda g: [("홍길동", [(10.0, 10.0, 60.0, 20.0)])]
        im0 = _Im.new("L", (200, 100), 255)
        a = R.ocr_lines(im0)
        b = R.ocr_lines(im0, lang=R.O_FALLBACK())
        c = R.ocr_lines(im0, 7, win=False)
        chk([(x.text, x.src) for x in a] == [("홍길동", "w")] and abs(a[0].height - 0.2) < 1e-6,
            "I 기본 언어 읽기에 보조 엔진 줄이 붙는다(src='w', 높이 비율)", str([(x.text, x.src, x.height) for x in a]))
        chk(b == [] and c == [], "I 영어 덧읽기·고른 자리 읽기(win=False)에는 붙지 않는다", str((b, c)))
        WO.available = lambda: False
        chk(R.ocr_lines(im0) == [], "I 보조 엔진이 없으면 Tesseract 줄만")
    finally:
        O2.ensure_tesseract, TR.data, WO.available, WO.read = keep
    if WO.available():
        from PIL import ImageDraw, ImageFont
        im1 = _Im.new("L", (900, 160), 255)
        try:
            fnt = ImageFont.truetype(r"C:\Windows\Fonts\malgun.ttf", 56)
        except Exception:
            fnt = None
        if fnt is not None:
            ImageDraw.Draw(im1).text((20, 40), "010-0000-0001", font=fnt, fill=0)
            got = WO.read(im1)
            chk(any("0000" in t for t, _b in got), "I 실제 Windows OCR 이 그린 가짜 번호를 읽는다", str(got))
    else:
        print("SKIP - I 실제 Windows OCR(이 PC 에 한국어 OCR 이 없거나 Windows 가 아님)")
else:
    chk(False, "I 보조 엔진 함수(win_lines)가 있다")

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

# ── J ── 이름 정확도(§5.25) — 고정 보정·힌트 옮기기·영문 기관 문구 (모두 가짜 값)
print("\n=== J. 이름 정확도(§5.25) ===")
chk(_has("name_adjust") and _has("fix_latin_name"), "J 새 규칙 함수가 있다")
if _has("name_adjust"):
    adj = R.name_adjust({"홍길동": 0, "홍길층": 0})
    chk(adj["홍길층"] < 0 and adj["홍길동"] == 0, "J 한 글자 다른 짝 — 이름에 드문 음절('층') 쪽을 내림", str(adj))
    adj = R.name_adjust({"부문장": 0, "홍길동": 0, "가나사무소": 0})
    chk(adj["부문장"] < 0 and adj["가나사무소"] < 0 and adj["홍길동"] == 0, "J 이름이 아닌 낱말 조각(부문·사무소)을 내림", str(adj))
    adj = R.name_adjust({"길동": 0, "홍길동": 0, "홍길": 0})
    chk(adj["길동"] < 0 and adj["홍길"] < 0 and adj["홍길동"] == 0, "J 세 글자 이름의 두 글자 조각(성 빠짐·끝 빠짐)을 내림", str(adj))
    lines = [L("가나다기술", 0.10, 90, 0.05), L("홍길층", 0.16, 90, 0.4), L("홍길동", 0.14, 90, 0.45), L("부장", 0.06, 90, 0.5)]
    nk = R.name_candidates_ko(lines, [])
    chk(nk and nk[0].text == "홍길동", "J 후보 고르기 — 큰 글자라도 드문 음절이 낀 판보다 흔한 이름", str([c.text for c in nk[:3]]))
    nk = R.name_candidates_ko([L("가나다기술", 0.10, 90, 0.05), L("홍길동", 0.14, 90, 0.4), L("부장", 0.06, 90, 0.5)], [], hint="길동")
    chk(nk and nk[0].text == "홍길동", "J 파일 이름이 성을 빠뜨린 두 글자면 힌트 덤을 '성+두 글자' 쪽으로", str([c.text for c in nk[:3]]))
    w = dict(R.NAME_W)
    sc0 = R.name_score({"bias": 1.0, "adj": -3.0}, w)
    chk(abs(sc0 - (w["bias"] - 3.0)) < 1e-6, "J 고정 보정(adj)은 배운 가중치와 따로 늘 더함", str(sc0))
    chk(R.fix_latin_name("John BeII") == "John Bell" and R.fix_latin_name("JOHN DOE") == "JOHN DOE",
        "J 영문 이름 — 소문자 뒤 대문자 I 는 l, 대문자 이름은 그대로", R.fix_latin_name("John BeII"))
    ne = R.name_candidates_en([L("FOR ROADS", 0.16, 90, 0.05), L("UNIVE RSITY", 0.15, 90, 0.1), L("John Doe", 0.12, 90, 0.4)], [])
    chk(ne and ne[0].text == "John Doe" and all(c.text not in ("FOR ROADS", "UNIVE RSITY") for c in ne),
        "J 영문 기관 문구(이음말·띄어 읽힌 기관 낱말)는 이름이 아님", str([c.text for c in ne]))

print()
print("ALL PASS" if not fails else "FAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
