# -*- coding: utf-8 -*-
"""구글 싱크 — 명함 기준으로 올린 뒤 다시 싱크하면 바꿀 것 0 (명함 SOT §5.29, 261122-8).
가짜 구글(메모리 안)·가짜 명함(010-0000-…)만 — 실제 구글에 붙지 않는다(§2.1 의 7).

A 명함 기준으로 올림 → 보통 싱크 미리보기에 '명함을 구글 값으로 고침'·'구글로 보냄' 없음
  (명함의 `+82 10…` 번호·종류 없는 번호·새 연락처 라벨 뒤 바뀐 구글 시각에도)
B 명함 기준이면 '명함에서 지워짐' 은 처음부터 체크, 보통 싱크는 그대로 '남김'
C '지워짐' 을 남기면 구글에만 둠 — 다음 보통 싱크에 '구글에서 가져옴' 으로 다시 내지 않음
"""
import os, sys, tempfile, copy, itertools, time
from datetime import datetime, timezone
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_gresync_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_gresync_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
from viewer.bizcard import people as P, store as S, gsync as G
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat().replace("+00:00", "Z")


class FakeApi:
    """구글처럼 — 고칠 때마다 updateTime 을 지금으로, 라벨 넣기도 연락처 시각을 바꾼다(실제 구글과 같게)."""
    def __init__(self):
        self.people, self.n = {}, itertools.count(100)

    def _touch(self, rn, later=0.0):
        self.people[rn]["metadata"] = {"sources": [{"type": "CONTACT", "updateTime": iso(time.time() + later)}]}
        self.people[rn]["etag"] = "e%d" % next(self.n)

    def list_people(self):
        return [copy.deepcopy(p) for p in self.people.values()]

    def _make(self, p):
        rn = "people/n%d" % next(self.n)
        self.people[rn] = dict(copy.deepcopy({k: v for k, v in p.items() if k != "etag"}), resourceName=rn)
        self._touch(rn)
        return copy.deepcopy(self.people[rn])

    def create(self, p):
        return self._make(p)

    def batch_create(self, persons):
        return [self._make(p) for p in persons]

    def update(self, rn, p):
        self.people[rn].update({k: copy.deepcopy(v) for k, v in p.items() if k != "etag"})
        self._touch(rn)
        return copy.deepcopy(self.people[rn])

    def batch_update(self, persons):
        return {rn: self.update(rn, p) for rn, p in persons.items()}

    def delete(self, rn):
        self.people.pop(rn, None)

    def list_groups(self):
        return [{"resourceName": "contactGroups/g1", "name": "가짜모임", "groupType": "USER_CONTACT_GROUP"}]

    def create_group(self, name):
        return {"resourceName": "contactGroups/g2"}

    def modify_members(self, g, add=(), remove=()):
        for rn in add:
            self.people[rn].setdefault("memberships", []).append({"contactGroupMembership": {"contactGroupResourceName": g}})
            self._touch(rn, later=2.0)                  # 서버 시각이 조금 늦어도(라벨 넣기가 연락처 고친 시각을 바꿈)


def apply_default(st, api, rows):
    """미리보기 창과 같게 — 처음 체크(`row_default`)된 줄은 그대로, 안 된 '지워짐' 은 짝만 풀기(남김)."""
    out = [r for r in rows if G.row_default(r)]
    out += [dict(r, kind="unlink", was=r["kind"]) for r in rows if not G.row_default(r) and r["kind"] in G.UNLINK_IF_KEPT]
    order = {k: n for n, k in enumerate(G.KINDS + ("link", "unlink"))}
    return G.apply(st, api, sorted(out, key=lambda r: order.get(r["kind"], 99)), "", people=api.list_people())


def kinds(rows):
    return sorted({r["kind"] for r in rows})


try:
    st = S.BizcardStore(TMP / "local" / "bizcard.db")
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    st.meta_set(G.OPT_LABELS, ["가짜모임"])
    P.src_init(st)
    a = P._insert_contact(st, {"name": "가짜갑", "phones": [("cell", "+82 10-0000-1111"), ("", "02-000-0000")]}, ["명함", "가짜모임"])
    b = P._insert_contact(st, {"name": "가짜을", "phones": [("cell", "010-0000-2222")], "emails": ["eul@example.com"]}, ["명함", "가짜모임"])
    c = P._insert_contact(st, {"name": "가짜병", "phones": [("cell", "010-0000-3333")]}, ["명함"])
    st.con.commit()
    api = FakeApi()

    print("=== A 명함 기준으로 올린 뒤 다시 싱크 ===")
    rows = G.plan(st, api.list_people(), "", card_first=True, groups=api.list_groups())
    apply_default(st, api, rows)
    again = G.plan(st, api.list_people(), "", groups=api.list_groups())
    chk(not [r for r in again if r["kind"] in (G.TO_CARD, G.TO_GOOGLE, G.NEW_CARD, G.NEW_GOOGLE, G.GONE_VALUE)],
        "A 보통 싱크에 바꿀 것 없음", str([(r["kind"], r.get("fields")) for r in again]))
    lk = G.links(st)
    chk(all(lk[x]["synced"] >= G.person_time(api.people[lk[x]["rn"]]) for x in (a, b, c)),
        "A 짝 기록 시각이 라벨 넣은 뒤 구글 시각보다 늦음")

    print("\n=== B 명함에서 지운 사람 ===")
    rn_c = lk[c]["rn"]
    st.delete_card(c)
    st.con.commit()
    r_first = [r for r in G.plan(st, api.list_people(), "", card_first=True, groups=api.list_groups()) if r["kind"] == G.GONE_CARD]
    r_norm = [r for r in G.plan(st, api.list_people(), "", groups=api.list_groups()) if r["kind"] == G.GONE_CARD]
    chk(len(r_first) == 1 and G.row_default(r_first[0]), "B 명함 기준이면 '명함에서 지워짐' 처음부터 체크")
    chk(len(r_norm) == 1 and not G.row_default(r_norm[0]), "B 보통 싱크는 그대로 '남김'")

    print("\n=== C 남기면 구글에만 둠 ===")
    apply_default(st, api, r_norm)                     # 체크 안 함 = 남김(짝만 풀림)
    nxt = G.plan(st, api.list_people(), "", groups=api.list_groups())
    chk(rn_c in api.people and not [r for r in nxt if r["kind"] == G.NEW_CARD and r["rn"] == rn_c],
        "C 남긴 연락처는 다음 싱크에 '구글에서 가져옴' 으로 다시 나오지 않음", str(kinds(nxt)))
except Exception as e:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외", repr(e))
print("FAILURES: %d" % len(fails))
for f in fails:
    print("  -", f)
sys.stdout.flush()
os._exit(1 if fails else 0)
