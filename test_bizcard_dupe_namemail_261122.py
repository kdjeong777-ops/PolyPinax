# -*- coding: utf-8 -*-
"""중복 검토 — 성명+메일 같으면 확정 동일인 (명함 SOT §5.24.8 '묶기' ⑤, 261120-74). 가짜 명함·임시 DB 만.

A 휴대폰이 서로 달라도 성명·메일이 같으면 한 묶음, 이유 'namemail'(확정)·처음 체크
B 성명 비교는 빈칸·대소문자·앞 #·괄호 속 직함 무시, 메일은 여럿 중 하나라도(대소문자 무시)
C 성명이 다르면(메일만 같음 — 공용 메일) 휴대폰이 다르면 묶지 않음(종전 규칙 그대로)
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
QCoreApplication.setApplicationName("polypdf_bizcard_namemail_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_namemail_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
from viewer.bizcard import people as P, store as S
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


try:
    st = S.BizcardStore(TMP / "local" / "bizcard.db")
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    a1 = P._insert_contact(st, {"name": "가짜일", "phones": [("cell", "010-0000-0001")], "emails": ["One@Example.com"]}, ["명함"])
    a2 = P._insert_contact(st, {"name": "가짜 일 (부장)", "phones": [("cell", "010-0000-0091")],
                                "emails": ["other@example.com", "one@example.com"]}, ["명함"])
    a3 = P._insert_contact(st, {"name": "#가짜일", "phones": [("cell", "010-0000-0071")], "emails": ["ONE@example.com"]}, ["명함"])
    b1 = P._insert_contact(st, {"name": "가짜이", "phones": [("cell", "010-0000-0002")], "emails": ["team@example.com"]}, ["명함"])
    b2 = P._insert_contact(st, {"name": "가짜삼", "phones": [("cell", "010-0000-0003")], "emails": ["team@example.com"]}, ["명함"])
    st.con.commit()
    gs = P.dupe_groups(st)
    grp = next((g for g in gs if a1 in [c["id"] for c in g["cards"]]), None)
    ids = sorted(c["id"] for c in grp["cards"]) if grp else []
    chk(ids == sorted([a1, a2, a3]), "A·B 휴대폰이 달라도 성명(빈칸·괄호 직함·앞 #·대소문자 무시)+메일(하나라도)이면 한 묶음", str(ids))
    chk(grp is not None and all(grp["why"][i] == "namemail" for i in ids) and "namemail" in P.WHY_SURE,
        "A 이유 '이름·메일 같음(확정)' — 확실 갈래(처음 체크)", str(grp and grp["why"]))
    chk(not any(b1 in [c["id"] for c in g["cards"]] for g in gs), "C 이름이 다르면(공용 메일) 휴대폰이 다를 때 묶지 않음", str(gs))
    from viewer.widgets import bizcard_dupe_dialog as DD
    chk("namemail" in DD.WHY_LABEL, "A 중복 검토 창 이유 글")
    st.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외")
print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
