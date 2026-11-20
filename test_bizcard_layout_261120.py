# -*- coding: utf-8 -*-
"""명함 구획 다시 읽기·회사 다듬기·법인 꼴 (명함 SOT §5.28) — 가짜 명함만 쓴다(실제 명함 값 금지, 명함 SOT §2.1).

A. 구획 나누기 — 그린 가짜 명함(굵고 큰 이름 줄·작은 연락처 줄·QR 비슷한 덩이·세로 괘선·테두리)에서 줄이 따로 잎이 되고,
   이름 줄이 가장 굵고 크며, 다시 읽을 구획 1위가 이름 줄
B. 회사 글 다듬기 `tidy_company` — 앞 영문 찌꺼기·기관 끝말 뒤 부서/직함·끝에 붙은 이름은 떼고, '대학교'·'테크노파크'·대문자 약칭은 둔다
C. 회사 후보 다시 매기기 `tidy_companies`·`rescore` — 구호·학회 목록·끝말만인 낱말은 내리고, 같은 글은 묶고, 기관 끝말까지 있는 긴 후보가 앞,
   영문 1위는 그대로
D. 법인 꼴 — [주]·(합)·농업회사법인·의료법인 은 떼고 옆 낱말이 회사, 협동조합은 남긴다
E. 다시 읽기 연결 — 앞면 첫 읽기(extra)에서만 굵은 구획을 한 줄(psm 7)로 읽어 그 줄이 이름 후보가 된다, `BLOCK_READ` 를 끄면 읽지 않는다
"""
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"          # 검사 작성 SOT §14.7
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2 — 실제 설정·데이터 폴더를 쓰지 않는다

fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


try:
    from viewer.bizcard import recognize as R
    from viewer.bizcard import layout as LY
except Exception as e:                      # 이 판 전 코드엔 구획 모듈이 없다
    chk(False, "모듈 viewer.bizcard.layout 을 불러온다", repr(e))
    print("FAILURES: %d" % len(fails))
    sys.exit(1)

from PIL import Image, ImageDraw


def glyph_row(d, x, y, n, h, w, thick):
    """글자 비슷한 막대 무리 — n 글자, 글자 높이 h, 글자 너비 w, 획 thick."""
    for i in range(n):
        gx = x + i * int(w * 1.3)
        d.rectangle([gx, y, gx + thick, y + h], fill=0)                       # 세로 획
        d.rectangle([gx, y + h // 2, gx + w, y + h // 2 + thick], fill=0)     # 가로 획
        d.rectangle([gx + w - thick, y, gx + w, y + h], fill=0)


def fake_card():
    im = Image.new("L", (1800, 1000), 255)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 1799, 999], outline=0, width=4)                       # 테두리(지워져야 함)
    glyph_row(d, 200, 150, 3, 110, 90, 16)                                    # 이름 — 굵고 크다
    glyph_row(d, 200, 330, 8, 40, 32, 4)                                      # 회사 줄(보통)
    for i in range(4):                                                        # 연락처 줄 넷
        glyph_row(d, 200, 520 + i * 90, 12, 34, 26, 3)
    d.line([1180, 500, 1180, 880], fill=0, width=3)                           # 세로 괘선(줄 절반 안 됨)
    for yy in range(520, 860, 20):                                            # QR 비슷한 덩이
        for xx in range(1250, 1600, 20):
            if (xx // 20 + yy // 20) % 2:
                d.rectangle([xx, yy, xx + 14, yy + 14], fill=0)
    return im.convert("RGB")


# ── A ──
print("=== A. 구획 나누기 ===")
card = fake_card()
lv = LY.leaves(card)
name_lv = [x for x in lv if x["y0"] < 0.3 and x["x0"] < 0.2]
chk(len(lv) >= 6, "A 이름·회사·연락처 넷이 따로 잎(QR·괘선 옆 줄도 나뉨)", str(len(lv)))
chk(len(name_lv) == 1 and name_lv[0]["sw"] == max(x["sw"] for x in lv) and name_lv[0]["h"] >= max(x["h"] for x in lv if x["x0"] < 0.6),
    "A 이름 잎이 가장 굵고(획) 가장 크다", str([(round(x["sw"], 1), round(x["h"], 3)) for x in lv]))
pk = LY.pick_blocks(lv)
chk(pk and pk[0] is name_lv[0] and len(pk) <= LY.BLOCK_TOPK, "A 다시 읽을 구획 1위가 이름 잎, 개수는 BLOCK_TOPK 이하",
    str([(round(x["y0"], 2), round(x["sw"], 1)) for x in pk]))
chk(not any(x["y0"] < 0.01 or x["y1"] > 0.99 for x in lv), "A 테두리는 잎이 되지 않는다")

# ── B ──
print("=== B. 회사 글 다듬기 ===")
T = R.tidy_company
cases = [("e_ 가나다엔지니어링", "", "가나다엔지니어링"), ("가나다대학교교수", "", "가나다대학교"),
         ("가나다국토관리사무소보수과과장", "", "가나다국토관리사무소"), ("가나다협회부방", "", "가나다협회"),
         ("가나다건설 홍길동", "", "가나다건설"), ("가나다산업홍길동", "홍길동", "가나다산업"),
         ("가나다대학교", "", "가나다대학교"), ("가나다테크노파크", "", "가나다테크노파크"), ("가나다이앤씨", "", "가나다이앤씨"),
         ("QX 건설산업", "", "QX 건설산업"), ("가나다 a&t", "", "가나다 a&t"), ("가나다컨설턴트圖", "", "가나다컨설턴트")]
for src, nm, want in cases:
    chk(T(src, nm) == want, "B %r → %r" % (src, want), repr(T(src, nm)))

# ── C ──
print("=== C. 다시 매기기 ===")
C = lambda t, s: {"text": t, "score": s, "why": [], "feat": {"cx": 0.5, "cy": 0.2}}
r = R.tidy_companies([C("최선을다하는기업", 4.5), C("가나다산업", 4.0)])
chk(r[0]["text"] == "가나다산업", "C 구호('…하는 기업')는 내린다", str([(c["text"], c["score"]) for c in r]))
r = R.tidy_companies([C("가나다학회", 4.0), C("라마바학회", 3.9), C("가나다대학교", 3.0)])
chk(r[0]["text"] == "가나다대학교", "C 여러 학회가 늘어선 회원 목록은 내린다", str([(c["text"], c["score"]) for c in r]))
r = R.tidy_companies([C("건설산업", 5.0), C("QX 건설산업", 4.0)])
chk(r[0]["text"] == "QX 건설산업", "C 끝말만인 네 글자 이하('건설산업')는 내린다", str([(c["text"], c["score"]) for c in r]))
r = R.tidy_companies([C("한국가나다", 3.0), C("한국가나다연구원", 2.5)])
chk(r[0]["text"] == "한국가나다연구원", "C 앞부분만 읽힌 것보다 기관 끝말까지 있는 긴 후보가 앞", str([(c["text"], c["score"]) for c in r]))
r = R.tidy_companies([C("e_ 가나다건설", 4.0), C("가나다건설", 3.9), C("라마바산업", 4.1)])
chk(r[0]["text"] == "가나다건설" and abs(r[0]["score"] - 4.3) < 1e-6, "C 다듬은 글이 같으면 하나로 묶고 덤", str([(c["text"], c["score"]) for c in r]))
res = {"name": "홍길동", "company": "", "name_cands": [{"text": "홍길동", "score": 6.0, "feat": {}}],
       "company_cands": [C("가나다산업홍길동", 4.0)], "need_check": []}
chk(R.rescore(res)["company"] == "가나다산업", "C rescore — 회사 끝에 붙은 그 명함의 이름을 뗀다", R.rescore(res)["company"])
res_en = {"name": "John Doe", "company": "", "name_cands": [], "company_cands": [C("Acme Fake Co", 4.0), C("가나다", 1.0)],
          "need_check": []}
chk(R.rescore(res_en)["company_cands"][0]["text"] == "Acme Fake Co", "C 영문 1위면 다듬지 않는다")

# ── D ──
print("=== D. 법인 꼴 ===")
chk(R.strip_corp("[주]가나다") == "가나다" and R.strip_corp("(합)가나다") == "가나다", "D [주]·(합) 는 뗀다",
    "%r %r" % (R.strip_corp("[주]가나다"), R.strip_corp("(합)가나다")))
chk(R.strip_corp("농업회사법인 가나다팜") == "가나다팜" and R.strip_corp("의료법인 가나다의료재단") == "가나다의료재단",
    "D 농업회사법인·의료법인 은 뗀다")
chk("가나다팜" in R.corp_adjacent("농업회사법인 가나다팜 영업팀"), "D 새 법인 꼴 옆 낱말이 회사", str(R.corp_adjacent("농업회사법인 가나다팜 영업팀")))
chk(R.strip_corp("가나다협동조합") == "가나다협동조합", "D 협동조합은 이름의 일부 — 남긴다", R.strip_corp("가나다협동조합"))

# ── E ──
print("=== E. 다시 읽기 연결 ===")
calls = []
orig = R.ocr_lines


def fake_ocr(im, psm=0, invert=False, lang="", win=True):
    calls.append(psm)
    if psm == 7:
        return [R.Line("홍길동", 0.6, 90, 0.2, 0.5, 0.5)]
    return [R.Line("가나다산업 영업팀", 0.04, 90, 0.33, 0.3, 0.35), R.Line("010-0000-0001", 0.03, 90, 0.5, 0.3, 0.52)]


R.ocr_lines = fake_ocr
try:
    s = R.read_side([card])
    n7 = calls.count(7)
    chk(1 <= n7 <= LY.BLOCK_TOPK, "E 앞면 첫 읽기에서 굵은 구획을 한 줄(psm 7)로 읽는다", str(calls))
    chk(s.names_ko and s.names_ko[0].text == "홍길동", "E 다시 읽은 줄이 이름 후보 1위", str([c.text for c in s.names_ko[:3]]))
    calls.clear()
    R.read_side([card], extra=False)
    chk(7 not in calls, "E 뒷면 등 extra 아닌 읽기에서는 다시 읽지 않는다", str(calls))
    calls.clear()
    R.BLOCK_READ = False
    R.read_side([card])
    chk(7 not in calls, "E BLOCK_READ 를 끄면 다시 읽지 않는다", str(calls))
finally:
    R.ocr_lines = orig
    R.BLOCK_READ = True

print()
print("ALL PASS" if not fails else "FAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
