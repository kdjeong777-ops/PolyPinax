# -*- coding: utf-8 -*-
"""번호 종류 바로잡기·일반 번호로 묶이지 않기 (명함 SOT §5.11 '번호 종류 바로잡기'·§5.24.8 '묶기', 261120-55) — 가짜 번호·임시 DB 만.

A 같은 일반 번호(033 — 종류 '휴대폰'·앞 0 빠짐·15xx 내선)·같은 옛 011 번호는 이름이 다르면 묶지 않음, 같은 010 은 묶고 맞은 번호를 알려 줌
B phone.fix_kinds — 010 은 휴대폰, 휴대폰인데 010 아니면 일반 전화, 011·016~019 는 빼서 메모로, 팩스·외국 번호는 그대로
C 쓰는 길 — 주소록 가져오기·update_card·store.upsert 가 같은 규칙(메모 줄은 한 번만)
D 이미 있는 DB 한 번 옮기기 — 백업·바꾼 수·두 번째는 0, 구글과 짝지은 명함은 다음 싱크에 '구글 고침 — 전화'
E 명함찾기를 처음 열면 배경에서 옮기고 알림(메인 정지 없음)
"""
import os, sys, tempfile, time, json
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_kinds_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_kinds_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
from viewer.bizcard import people as P, store as S, phone as PH, gsync as G
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def pump(cond, timeout=10.0):
    t = time.monotonic()
    while time.monotonic() - t < timeout:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


def c(name, phones, emails=(), company=""):
    return {"name": name, "company": company, "phones": list(phones), "emails": list(emails), "urls": []}


def raw_insert(st, people):
    """종전 판이 넣어 둔 것처럼 — 바로잡기 길을 거치지 않고 DB 에 바로."""
    ids = []
    for p in people:
        cur = st.con.execute("INSERT INTO cards(front, name, company, phones, emails, urls, tags, en, scanned, created, updated) "
                             "VALUES(?,?,?,?,?,'[]','[]','{}','',?,?)",
                             ("contact:%s%d" % (p["name"], len(ids)), p["name"], p.get("company", ""),
                              json.dumps([list(x) for x in p["phones"]], ensure_ascii=False),
                              json.dumps(list(p.get("emails") or []), ensure_ascii=False), 1.0, 1.0))
        ids.append(cur.lastrowid)
    st.con.commit()
    return ids


# ── A ──
print("=== A. 일반 번호로 묶이지 않기 ===")
st = S.BizcardStore(TMP / "a.db")
raw_insert(st, [c("가짜갑", [("cell", "033-000-0000")]), c("가짜을", [("cell", "033-000-0000")]),
                c("가짜병", [("cell", "33-000-0001")]), c("가짜정", [("cell", "33-000-0001")]),
                c("가짜무", [("cell", "1588-0000 내선 12")]), c("가짜기", [("cell", "1588-0000 내선 12")]),
                c("가짜경", [("cell", "011-000-0000")]), c("가짜신", [("cell", "011-000-0000")]),
                c("가짜임", [("cell", "010-0000-9999")]), c("가짜계", [("cell", "010-0000-9999")])])
gs = P.dupe_groups(st)
names = sorted(sorted(x["name"] for x in g["cards"]) for g in gs)
chk(names == [["가짜계", "가짜임"]], "A 033(종류 휴대폰)·앞 0 빠진 지역번호·15xx 내선·옛 011 이 같아도 이름이 다르면 묶지 않음, 같은 010 은 묶음", str(names))
m = (gs[0].get("match") or {}) if gs else {}
chk(m and all(PH.digits(v) == "01000009999" for v in m.values()), "A 묶음에 맞은 휴대폰 번호(풍선 도움말용)", str(m))
st.close()

# ── B ──
print("\n=== B. fix_kinds ===")
fk = getattr(PH, "fix_kinds", None)
if fk:
    ph, old = fk([("work", "010-0000-1111"), ("cell", "033-000-0000"), ("cell", "+82 10-0000-2222"), ("cell", "016-000-0000"),
                  ("fax", "010-0000-3333"), ("cell", "+1 650 000 0000"), ("cell", "1000002222")])
    chk(ph == [("cell", "010-0000-1111"), ("work", "033-000-0000"), ("cell", "+82 10-0000-2222"), ("fax", "010-0000-3333"),
               ("cell", "+1 650 000 0000"), ("cell", "1000002222")] and old == ["016-000-0000"],
        "B 010 은 휴대폰·휴대폰인데 010 아니면 일반 전화·옛 016 은 빼서 메모로·팩스·외국 그대로·앞 0 빠진 010", str((ph, old)))
else:
    chk(False, "B phone.fix_kinds 가 있다")

# ── C ──
print("\n=== C. 쓰는 길 ===")
st = S.BizcardStore(TMP / "c.db")
P.apply_import(st, [c("가짜하나", [("work", "010-0000-4444"), ("cell", "019-000-0000"), ("cell", "02-0000-0000")])], "주소록", "google")
a = P.card_by_id(st, st.con.execute("SELECT MAX(id) FROM cards").fetchone()[0])
chk(a["phones"] == [("cell", "010-0000-4444"), ("work", "02-0000-0000")] and "예전 휴대폰 019-000-0000" in (a.get("memo") or ""),
    "C 주소록 가져오기 — 종류 바로잡고 옛 019 는 메모로", str((a["phones"], a.get("memo"))))
P.update_card(st, a["id"], {"phones": [("work", "010-0000-5555"), ("cell", "019-000-0000")]})
b = P.card_by_id(st, a["id"])
chk(b["phones"] == [("cell", "010-0000-5555")] and (b.get("memo") or "").count("예전 휴대폰 019-000-0000") == 1,
    "C update_card — 같은 메모 줄은 한 번만", str((b["phones"], b.get("memo"))))
fr = TMP / "x.jpg"
fr.write_bytes(b"x")
cid = st.upsert({"front": str(fr), "name": "가짜둘", "phones": [("cell", "031-000-0000")]})
chk(P.card_by_id(st, cid)["phones"] == [("work", "031-000-0000")], "C store.upsert(인식·[적용]) — 휴대폰인데 031 이면 일반 전화",
    str(P.card_by_id(st, cid)["phones"]))
st.close()

# ── D ──
print("\n=== D. 이미 있는 DB 옮기기 ===")
db = TMP / "local" / "bizcard.db"
st = S.BizcardStore(db)
ids = raw_insert(st, [c("가짜셋", [("work", "010-0000-6666")]), c("가짜넷", [("cell", "033-000-0000"), ("cell", "017-000-0000")]),
                      c("가짜다섯", [("cell", "010-0000-7777")])])
G.init(st)
st.con.execute("INSERT INTO google_link(card_id, resource_name, etag, synced, front) VALUES(?,?,?,?,?)",
               (ids[0], "people/k1", "e", 5.0, P.card_by_id(st, ids[0])["front"]))
st.con.commit()
fa = getattr(P, "fix_kinds_all", None)
if fa:
    n = fa(st, str(TMP / "local" / "bizcard.db.kinds_bak"))
    chk(n == 2 and (TMP / "local" / "bizcard.db.kinds_bak").exists(), "D 바꾼 명함 수·바꾸기 전 백업", str(n))
    chk(P.card_by_id(st, ids[1])["phones"] == [("work", "033-000-0000")] and "예전 휴대폰 017-000-0000" in P.card_by_id(st, ids[1])["memo"],
        "D 옮긴 값", str(P.card_by_id(st, ids[1])))
    chk(fa(st, str(TMP / "local" / "bizcard.db.kinds_bak")) == 0, "D 두 번째는 바꿀 것 없음")
    person = {"resourceName": "people/k1", "etag": "e", "names": [{"unstructuredName": "가짜셋"}],
              "phoneNumbers": [{"value": "010-0000-6666", "type": "work"}],
              "metadata": {"sources": [{"type": "CONTACT", "updateTime": "2020-01-01T00:00:00.000Z"}]}}
    rows = G.plan(st, [person])
    mine = [(r["kind"], r.get("fields")) for r in rows if r["card_id"] == ids[0]]
    chk(mine == [(G.TO_GOOGLE, ["phones"])], "D 구글과 짝지은 명함은 다음 싱크에 '구글 고침 — 전화'", str(mine))
else:
    chk(False, "D people.fix_kinds_all 이 있다")
st.con.execute("DELETE FROM meta WHERE k='phone_kinds_fixed'")
st.con.execute("UPDATE cards SET phones=? WHERE id=?", (json.dumps([["work", "010-0000-8888"]]), ids[2]))
st.con.commit()
st.close()

# ── E ──
print("\n=== E. 명함찾기를 처음 열면 ===")
notes = []
QMessageBox.information = staticmethod(lambda *a, **k: notes.append(a[2] if len(a) > 2 else "") or QMessageBox.StandardButton.Ok)
from viewer.widgets import bizcard_find_dialog as FD
dlg = FD.BizcardFindDialog(None, db=db)
dlg.show()
ok = pump(lambda: bool(notes), timeout=15)
stv = S.BizcardStore(db)
chk(ok and stv.meta_get("phone_kinds_fixed", None) and P.card_by_id(stv, ids[2])["phones"] == [("cell", "010-0000-8888")],
    "E 처음 열면 배경에서 바로잡고 바꾼 수를 알림", str((ok, notes)))
stv.close()
dlg.close()

print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
