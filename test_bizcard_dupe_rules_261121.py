# -*- coding: utf-8 -*-
"""중복 검토 묶기 규칙 (명함 SOT §5.24.8 '묶기', 261120-48) — 가짜 명함(010-0000-…·example.com)과 임시 DB 만.

휴대폰만 같은 사람을 가르는 번호 — 일반 전화·팩스는 평가에서 뺌, 휴대폰이 다르면 다른 사람(이름·회사·메일이 같아도),
같은 휴대폰은 이름이 달라도, 같은 이름 + 휴대폰 오타(한 자리 다름·이웃 자리바뀜), 메일+이름·이름+회사는 휴대폰이 서로 다르지 않을 때만,
휴대폰 없는 명함이 서로 다른 휴대폰 둘을 잇지 않음, 합친 값에서도 자리바뀜 오타 번호는 뺌, 구글 싱크 짝 맞추기와 같은 휴대폰 꼴.
"""
import os, sys, tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_dupe_rules_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_dupe_rules_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
from viewer.bizcard import people as P, store as S, gsync as G

fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def c(name, company="", cells=(), works=(), faxes=(), emails=()):
    return {"name": name, "company": company, "emails": list(emails), "urls": [],
            "phones": [("cell", x) for x in cells] + [("work", x) for x in works] + [("fax", x) for x in faxes]}


def groups(name, people):
    st = S.BizcardStore(TMP / (name + ".db"))
    P.apply_import(st, people, "주소록", "google")
    gs = P.dupe_groups(st)
    out = sorted(sorted(x["name"] + "|" + x["company"] for x in g["cards"]) for g in gs)
    why = {x["name"] + "|" + x["company"]: g["why"][x["id"]] for g in gs for x in g["cards"]}
    st.close()
    return out, why


# 1 휴대폰이 다르면 다른 사람 — 이름·회사가 같아도. 단 성명+메일이 같으면 확정 동일인(261120-74 — 휴대폰이 달라도)
g, _w = groups("diff", [c("가짜일", "가짜사", ["010-0000-1001"], emails=["one@example.com"]),
                        c("가짜일", "가짜사", ["010-0000-2002"], emails=["one@example.com"])])
chk(g == [["가짜일|가짜사", "가짜일|가짜사"]] and set(_w.values()) == {"namemail"}, "1 휴대폰이 달라도 성명+메일이 같으면 확정 묶음(261120-74)", str((g, _w)))
g, _w = groups("diff2", [c("가짜일", "가짜사", ["010-0000-1001"]), c("가짜일", "가짜사", ["010-0000-2002"])])
chk(g == [], "1 휴대폰이 다르면 이름·회사가 같아도(메일 없음) 묶지 않음", str(g))

# 2 일반 전화·팩스는 평가에서 뺌 — 같은 이름이어도
g, _w = groups("land", [c("가짜이", "가짜사A", works=["02-0000-3000"], faxes=["02-0000-3001"]),
                        c("가짜이", "가짜사B", works=["02-0000-3000"], faxes=["02-0000-3001"])])
chk(g == [], "2 일반 전화·팩스만 같으면 같은 이름이어도 묶지 않음", str(g))

# 2b 일반 번호(지역·070·050x·15xx)는 종류 칸이 '휴대폰'으로 잘못 들어와도 휴대폰으로 보지 않음 — 이름이 다르면 묶지 않음(사용자 지시 261121)
g, _w = groups("land2", [c("가짜갑", "같은사", ["02-0000-0000", "031-000-0000"]), c("가짜을", "같은사", ["02-0000-0000", "031-000-0000"]),
                         c("가짜병", "", ["044-000-0000", "070-0000-0000"]), c("가짜정", "", ["044-000-0000", "070-0000-0000"]),
                         c("가짜무", "", ["0505-000-0000", "1588-0000"]), c("가짜기", "", ["0505-000-0000", "1588-0000"])])
chk(g == [], "2b 일반 번호만 같고 이름이 다르면(같은 회사여도·종류가 '휴대폰'이어도) 묶지 않음", str(g))
chk(P._mobile_keys({"phones": [("cell", "02-0000-0000"), ("cell", "070-0000-0000"), ("cell", "0505-000-0000"), ("cell", "+1 650 000 0000")]})
    == ["16500000000"], "2b 휴대폰 꼴 — 국내 번호는 01x 만, 외국 번호는 종류 '휴대폰'을 믿음",
    str(P._mobile_keys({"phones": [("cell", "02-0000-0000"), ("cell", "+1 650 000 0000")]})))

# 3 같은 휴대폰은 이름이 달라도(지금처럼)
g, w = groups("same", [c("가짜삼", "가짜사", ["010-0000-3333"]), c("Fake Sam", "", ["+82 10-0000-3333"])])
chk(len(g) == 1 and set(w.values()) == {"phone_name"}, "3 같은 휴대폰(+82 꼴도)은 이름이 달라도 묶음 — 010 하나씩이면 '같은 번호·이름 다름 — 확인'(261122-1)", str((g, w)))

# 4 같은 이름 + 오타 — 한 자리 다름·이웃 자리바뀜, 두 자리 다르면 아님
g, w = groups("typo", [c("가짜사", "가", ["010-0000-1234"]), c("가짜사", "나", ["010-0000-1243"]),
                       c("가짜오", "가", ["010-0000-5555"]), c("가짜오", "나", ["010-0000-5556"]),
                       c("가짜육", "가", ["010-0000-6600"]), c("가짜육", "나", ["010-0000-6611"])])
chk(["가짜사|가", "가짜사|나"] in g and ["가짜오|가", "가짜오|나"] in g and w.get("가짜사|나") == "typo",
    "4 같은 이름 + 이웃 자리바뀜·한 자리 다름은 '번호 오타?'", str((g, w)))
chk(not any("가짜육|가" in x for x in g), "4 두 자리 다르면 다른 사람", str(g))

# 5 메일+이름 — 한쪽 휴대폰 없으면 묶음, 이름이 다르면 아님
g, w = groups("mail", [c("가짜칠", "", ["010-0000-7777"], emails=["seven@example.com"]),
                       c("가짜칠", "다른사", emails=["Seven@example.com"]),
                       c("가짜팔", "", emails=["office@example.com"]), c("가짜구", "", emails=["office@example.com"])])
chk(["가짜칠|", "가짜칠|다른사"] in g and w.get("가짜칠|다른사") == "namemail", "5 메일+이름 같고 한쪽 휴대폰 없으면 묶음(확정, 261120-74)", str((g, w)))
chk(not any("가짜팔|" in x for x in g), "5 메일만 같고 이름이 다르면 묶지 않음", str(g))

# 5b 회사 공용 메일 — 메일만으로는 묶지 않고 휴대폰·성명으로 판단(사용자 덧붙임 261121)
g, _w = groups("shared", [c("가짜갑", "공용사", ["010-0000-4101"], emails=["info@example.com"]),
                          c("가짜을", "공용사", ["010-0000-4202"], emails=["info@example.com"]),
                          c("가짜병", "공용사", ["010-0000-4303"], emails=["info@example.com"]),
                          c("가짜병", "공용사", ["010-0000-4999"], emails=["info@example.com"])])
chk(g == [["가짜병|공용사", "가짜병|공용사"]], "5b 공용 메일 — 다른 이름은 묶지 않고, 같은 이름은 휴대폰이 달라도 확정 묶음(261120-74 사용자 결정)", str(g))

# 6 이름+회사 — 휴대폰이 둘 다 없거나 한쪽만이면 묶음
g, w = groups("nc", [c("가짜십", "가짜회사", works=["02-0000-1010"]), c("가짜십", "가짜회사", works=["031-000-1010"]),
                     c("가짜열", "열회사", ["010-0000-1111"]), c("가짜열", "열회사")])
chk(["가짜십|가짜회사", "가짜십|가짜회사"] in g and ["가짜열|열회사", "가짜열|열회사"] in g and w.get("가짜십|가짜회사") == "namecomp",
    "6 휴대폰이 없거나 한쪽만이면 이름+회사로 묶음", str((g, w)))

# 7 사슬 — 휴대폰 없는 명함이 서로 다른 휴대폰 둘을 잇지 않음
g, _w = groups("chain", [c("가짜백", "백회사", ["010-0000-0100"]), c("가짜백", "백회사"), c("가짜백", "백회사", ["010-0000-5678"])])
chk(len(g) == 1 and len(g[0]) == 2, "7 휴대폰 다른 둘은 휴대폰 없는 명함을 거쳐서도 한 묶음이 되지 않음", str(g))

# 8 합친 값 — 자리바뀜 오타 번호도 뺌
mp = P.merge_plan([dict(c("가짜", "", ["010-0000-1234"]), id=1), dict(c("가짜", "", ["010-0000-1243"]), id=2)])
chk([n for _k, n in mp["fields"]["phones"]] == ["010-0000-1234"], "8 합친 전화에서 자리바뀜 오타 번호는 뺌", str(mp["fields"]["phones"]))

# 9 구글 싱크 짝 맞추기와 같은 휴대폰 꼴(한 곳)
chk(G._cell_keys([("work", "+82 10-0000-9999"), ("work", "02-0000-9999"), ("fax", "010-0000-8888")])
    == {k[-8:] for k in P._mobile_keys({"phones": [("work", "+82 10-0000-9999"), ("work", "02-0000-9999"), ("fax", "010-0000-8888")]})}
    == {"00009999"}, "9 구글 싱크 짝 맞추기의 휴대폰 꼴 = 중복 검토의 휴대폰 꼴")

print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
