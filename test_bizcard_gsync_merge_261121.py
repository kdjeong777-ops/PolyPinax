# -*- coding: utf-8 -*-
"""구글 싱크 — 같은 사람이 둘로·합치기와 짝 (명함 SOT §5.29 '짝 맞추기'·'명함 합치기와 짝'·'새 사람'·'미리보기', 261120-46).
가짜 구글(메모리 안 사전)과 가짜 값(010-0000-…·example.com)만 — 실제 구글·실제 명함 DB 에는 붙지 않는다(§2.1).

A. 종류 없는 번호(구글 연락처·구글 vCard 의 '전화')끼리도 휴대폰 꼴이면 짝 — 새 명함·새 연락처로 둘이 되지 않음
B. 출처가 구글인 명함이 짝을 못 찾으면 '구글로 보냄' 은 처음 꺼짐·'구글에 이미 있을 수 있음'(보통 명함은 그대로 켬)
C. 이미 둘로 들어온 뒤 합치기 — vCard 명함을 남겨도 짝이 옮겨 와 다음 싱크는 '구글 고침' 하나(새 연락처·지워짐 없음), 반영 뒤 바꿀 것 없음
D. 구글 짝 명함을 남기는 쪽도 같음
E. 둘 다 짝이면 대표 짝을 두고 남은 구글 연락처는 '합쳐져 남음 — 지울까요' 기본 체크, 반영하면 지움 · 카톡 표시도 옮김
F. 명함 파일 이름(front)이 바뀌어도 짝 유지(트리거)
G. 미리보기 창 — 고침 줄 아래 옛 값 → 새 값, 백업 권함 한 줄, 처음 체크(합쳐져 남음 켬·구글 vCard 새 연락처 끔)
"""
import os, sys, time, tempfile, itertools, copy
os.environ["QT_QPA_PLATFORM"] = "offscreen"          # 검사 작성 SOT §14.7
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_gsync_merge_%d" % os.getpid())
fails = []
TMP = Path(tempfile.mkdtemp(prefix="bizcard_gsync_merge_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()

from viewer.bizcard import gsync as G, people as P, store as S
from viewer.bizcard.vcard import people_from_vcf


rd = getattr(G, "row_default", lambda r: G.DEFAULT_ON.get(r["kind"], True))   # 이 판 전 코드엔 없다


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


OLD = "2020-01-01T00:00:00.000Z"


def person(rn, name, phones=(), company="", emails=()):
    """phones = [(번호, 종류 또는 None)] — 종류 None 은 구글이 type 을 주지 않은 번호."""
    return {"resourceName": rn, "etag": "e1", "names": [{"unstructuredName": name}],
            "organizations": [{"name": company}] if company else [],
            "phoneNumbers": [dict({"value": v}, **({"type": t} if t else {})) for v, t in phones],
            "emailAddresses": [{"value": e} for e in emails], "photos": [],
            "metadata": {"sources": [{"type": "CONTACT", "updateTime": OLD}]}}


class FakeApi:
    """gsync_api.Api 와 같은 이름의 메서드만 — 메모리 안 가짜 구글."""
    def __init__(self):
        self.people, self.n, self.deleted = {}, itertools.count(100), []

    def list_people(self):
        return [copy.deepcopy(p) for p in self.people.values()]

    def create(self, p):
        rn = "people/n%d" % next(self.n)
        q = dict(copy.deepcopy(p), resourceName=rn, etag="e1",
                 metadata={"sources": [{"type": "CONTACT", "updateTime": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())}]})
        self.people[rn] = q
        return copy.deepcopy(q)

    def update(self, rn, p):
        q = self.people[rn]
        for k, v in p.items():
            if k != "etag":
                q[k] = copy.deepcopy(v)
        q["etag"] = q["etag"] + "x"
        q["metadata"] = {"sources": [{"type": "CONTACT", "updateTime": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())}]}
        return copy.deepcopy(q)

    def delete(self, rn):
        self.deleted.append(rn)
        self.people.pop(rn, None)


VCF = ("BEGIN:VCARD\r\nVERSION:3.0\r\nFN:가짜홍 가짜상사\r\nN:;가짜홍 가짜상사;;;\r\nTEL:+82 10-0000-1111\r\n"
       "EMAIL:hong@example.com\r\nEND:VCARD\r\n")


def fresh(name):
    db = TMP / "local" / (name + ".db")
    st = S.BizcardStore(db)
    api = FakeApi()
    # 구글 연락처 — 번호 종류 없음(사용자 PC 와 같은 꼴), 메일 없음
    api.people["people/g1"] = person("people/g1", "가짜홍 가짜상사", [("+82 10-0000-1111", None)])
    return st, api


def vcard_card(st):
    """구글 주소록 vCard 가져오기(실제 길 apply_import) 뒤 사용자가 이름·회사를 고친 명함(명함찾기 [저장]과 같이 출처를 지움)."""
    persons = people_from_vcf(VCF)
    for p in persons:
        p["emails"] = []                                    # 메일로 짝지어지지 않게 — 휴대폰 단계만 본다
    P.apply_import(st, persons, "주소록", "google")
    cid = st.con.execute("SELECT MAX(id) FROM cards").fetchone()[0]
    P.update_card(st, cid, {"name": "가짜홍", "company": "가짜상사", "phones": [("work", "010-0000-1111")]})
    P.forget_srcs(st, cid, ["name", "company"])
    return cid


def merge(st, ids):
    cards = [P.card_by_id(st, i) for i in ids]
    plan = P.merge_plan(cards)
    P.merge_db(st, plan)
    return plan["keeper"]


def kinds(rows):
    return sorted((r["kind"], r.get("card_id") or r.get("rn")) for r in rows)


# ── A ──
print("=== A. 종류 없는 번호끼리 휴대폰 짝 ===")
st, api = fresh("a")
v = vcard_card(st)
chk(P.card_by_id(st, v)["phones"][0][0] == "work", "A (전제) vCard 의 종류 없는 TEL 은 '전화' 로 들어옴")
rows = G.plan(st, api.list_people())
chk(not any(r["kind"] in (G.NEW_CARD, G.NEW_GOOGLE) for r in rows), "A 같은 번호면 새 명함·새 연락처로 둘이 되지 않음", str(kinds(rows)))
chk(any(r["kind"] in (G.TO_GOOGLE, G.TO_CARD, "link") and r["card_id"] == v and r["rn"] == "people/g1" for r in rows),
    "A vCard 명함과 구글 연락처가 짝지어짐", str(kinds(rows)))
c_other = P._insert_contact(st, {"name": "가짜다른", "company": "가짜회사", "phones": [("work", "02-0000-1111")]}, ["명함"])
st.con.commit()
api.people["people/g9"] = person("people/g9", "가짜다른2", [("02-9000-1111", None)])
rows = G.plan(st, api.list_people())
chk((G.NEW_GOOGLE, c_other) in kinds(rows) and (G.NEW_CARD, "people/g9") in kinds(rows),
    "A 회사 전화(02)는 휴대폰 단계로 짝짓지 않음")
st.close()

# ── B ──
print("=== B. 출처가 구글인 명함의 '구글로 보냄' ===")
st, api = fresh("b")
api.people.clear()
v = vcard_card(st)
plain = P._insert_contact(st, {"name": "가짜새", "phones": [("cell", "010-0000-2222")]}, ["명함"])
st.con.commit()
rows = G.plan(st, api.list_people())
rv = [r for r in rows if r["card_id"] == v]
rp = [r for r in rows if r["card_id"] == plain]
chk(rv and rv[0]["kind"] == G.NEW_GOOGLE and rv[0].get("maybe_dup") is True, "B 구글 vCard 명함은 '구글에 이미 있을 수 있음'", str(rv))
chk(rp and rp[0]["kind"] == G.NEW_GOOGLE and not rp[0].get("maybe_dup"), "B 보통 명함은 표시 없음", str(rp))
chk(rd(rv[0]) is False and rd(rp[0]) is True, "B 처음 체크 — 구글 vCard 명함 끔·보통 명함 켬")
st.close()


def doubled(name):
    """고치기 전 판이 만든 상태 — 구글 연락처는 '새 명함'(N)으로, vCard 명함(V)은 짝 없이."""
    st, api = fresh(name)
    v = vcard_card(st)
    G.apply(st, api, [{"kind": G.NEW_CARD, "card_id": 0, "rn": "people/g1", "name": ""}], people=api.list_people())
    n = G.links(st)
    n = [cid for cid, l in n.items() if l["rn"] == "people/g1"][0]
    return st, api, v, n


for label, first in (("C", "v"), ("D", "n")):
    print("=== %s. 둘로 들어온 뒤 합치기 — %s 명함을 남김 ===" % (label, "vCard" if first == "v" else "구글 짝"))
    st, api, v, n = doubled(label.lower())
    keep = merge(st, [v, n] if first == "v" else [n, v])
    chk(keep == (v if first == "v" else n), "%s (전제) 대표가 남음" % label)
    rows = G.plan(st, api.list_people())
    chk(kinds(rows) == [(G.TO_GOOGLE, keep)], "%s 다음 싱크는 남은 명함 → 구글 고침 하나(새 연락처·지워짐 없음)" % label, str(kinds(rows)))
    res = G.apply(st, api, [r for r in rows if rd(r)], people=api.list_people())
    g = api.people.get("people/g1") or {}
    chk(res["failed"] == 0 and len(api.people) == 1 and (g.get("organizations") or [{}])[0].get("name") == "가짜상사"
        and g["names"][0]["unstructuredName"].lstrip("#") == P.card_by_id(st, keep)["name"],
        "%s 반영하면 그 구글 연락처가 합친 값(이름·회사)으로" % label, str(g.get("names")))
    chk(not G.plan(st, api.list_people()), "%s 반영 뒤 다시 계획하면 바꿀 것 없음" % label,
        str(kinds(G.plan(st, api.list_people()))))
    st.close()

# ── E ──
print("=== E. 둘 다 짝 — 남은 구글 연락처 ===")
st, api = fresh("e")
api.people["people/g2"] = person("people/g2", "가짜홍", [("010-0000-1111", "mobile")], company="가짜상사")
G.apply(st, api, [{"kind": G.NEW_CARD, "card_id": 0, "rn": rn, "name": ""} for rn in ("people/g1", "people/g2")],
        people=api.list_people())
lk = {l["rn"]: cid for cid, l in G.links(st).items()}
n1, n2 = lk["people/g1"], lk["people/g2"]
G.kakao_set(st, [n2], True)
G.kakao_set(st, [n1], False)
st.con.execute("DELETE FROM kakao_block WHERE card_id=?", (n1,))
st.con.commit()
keep = merge(st, [n1, n2])
rows = G.plan(st, api.list_people())
mg = [r for r in rows if r["kind"] == getattr(G, "MERGED_GOOGLE", "?")]
chk(G.links(st).get(keep, {}).get("rn") == "people/g1", "E 대표 짝(g1)을 남김")
chk(len(mg) == 1 and mg[0]["rn"] == "people/g2" and rd(mg[0]) is True,
    "E 남은 구글 연락처는 '합쳐져 남음 — 지울까요' 기본 체크", str(kinds(rows)))
chk(not any(r["kind"] in (G.GONE_CARD, G.NEW_GOOGLE) for r in rows), "E '명함에서 지워짐'·새 연락처로 보이지 않음", str(kinds(rows)))
chk(keep in G.blocked_ids(st), "E 카톡 표시도 남는 명함으로")
G.apply(st, api, [r for r in rows if rd(r)], people=api.list_people())
chk(api.deleted == ["people/g2"] and "people/g1" in api.people, "E 반영하면 남은 구글 연락처를 지움", str(api.deleted))
chk(not G.plan(st, api.list_people()), "E 반영 뒤 바꿀 것 없음", str(kinds(G.plan(st, api.list_people()))))
st.close()

# ── F ──
print("=== F. 파일 이름이 바뀌어도 짝 유지 ===")
st, api = fresh("f")
c = P._insert_contact(st, {"name": "가짜홍 가짜상사", "phones": [("cell", "010-0000-1111")]}, ["명함"])
st.con.commit()
G.apply(st, api, [r for r in G.plan(st, api.list_people()) if rd(r)], people=api.list_people())
chk(G.links(st).get(c, {}).get("rn") == "people/g1", "F (전제) 짝지음")
st.con.execute("UPDATE cards SET front=? WHERE id=?", (str(TMP / "정리" / "가짜홍_가짜상사.jpg"), c))   # relocate 와 같은 쓰기
st.con.commit()
rows = G.plan(st, api.list_people())
chk(not rows, "F 이름이 바뀐 명함도 같은 짝(지워짐·새 연락처 없음)", str(kinds(rows)))
st.close()

# ── G ──
print("=== G. 미리보기 창 ===")
from viewer.widgets.bizcard_gsync_dialog import GSyncDialog
st, api, v, n = doubled("g")
P.update_card(st, n, {"title": "가짜부장"})
st.con.execute("UPDATE cards SET updated=? WHERE id=?", (time.time() + 5, n))
api.people["people/g3"] = person("people/g3", "가짜삼", [("010-0000-3333", "mobile")])
G.apply(st, api, [{"kind": G.NEW_CARD, "card_id": 0, "rn": "people/g3", "name": ""}], people=api.list_people())
n3 = [cid for cid, l in G.links(st).items() if l["rn"] == "people/g3"][0]
keep = merge(st, [n, n3])                                   # 다른 사람이지만 짝 둘 합치기를 보이려고
v2 = vcard_card(st)
st.con.execute("UPDATE cards SET phones=? WHERE id=?", ('[["work", "010-0000-4444"]]', v2))
st.con.commit()
people = api.list_people()
rows = G.plan(st, people)
db = str(TMP / "local" / "g.db")
st.close()
dlg = GSyncDialog(None, db=db, start=False)
dlg._planned(rows, people, "")
items = {}
for i in range(dlg.tree.topLevelItemCount()):
    top = dlg.tree.topLevelItem(i)
    for j in range(top.childCount()):
        it = top.child(j)
        r = rows[it.data(0, Qt.ItemDataRole.UserRole)]
        items.setdefault(r["kind"], []).append((r, it))
tg = items.get(G.TO_GOOGLE) or []
sub = [tg[0][1].child(k).text(0) for k in range(tg[0][1].childCount())] if tg else []
chk(any("→" in s and "가짜부장" in s for s in sub), "G '구글 고침' 줄 아래 칸마다 옛 값 → 새 값", str(sub))
mg = items.get(getattr(G, "MERGED_GOOGLE", "?")) or []
chk(mg and all(it.checkState(0) == Qt.CheckState.Checked for _r, it in mg), "G 합쳐져 남은 구글 연락처는 처음 체크", str(list(items)))
ng = [(r, it) for r, it in items.get(G.NEW_GOOGLE) or [] if r["card_id"] == v2]
chk(ng and ng[0][1].checkState(0) == Qt.CheckState.Unchecked and "구글에 이미 있을 수 있음" in ng[0][1].text(0),
    "G 구글 vCard 명함의 새 연락처 줄은 처음 꺼짐·표시", str([it.text(0) for _r, it in ng]))
chk("contacts.google.com" in dlg.lbl.text(), "G 구글을 바꾸는 줄이 있으면 백업 권함", dlg.lbl.text())
dlg.deleteLater()

print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
