# -*- coding: utf-8 -*-
"""구글 싱크 — 전화는 구글에 국제 꼴로·프로필 사진은 '구글 사진 있음' 이 아님 (구글 싱크 SOT §5.29 '오가는 칸'·'사진', 261128-18).
가짜 구글(메모리 안)·가짜 명함(010-0000-…)만 — 실제 구글에 붙지 않는다(명함 SOT §2.1 의 7).

A 명함 → 구글 사람: 한국 번호는 `+82 10-…`·`+82 2-…`, 대표번호·외국 번호·글 섞인 번호는 그대로
B 올린 뒤 다시 싱크하면 바꿀 것 없음 — 기본 국가 한국·지정 안 함 둘 다
C 이미 구글에 국내 꼴로 있는 짝 → '구글을 명함 값으로 고침 — 전화'(처음 체크) 한 번, 적용 뒤엔 없음
D 구글 사진이 프로필 사진(PROFILE)뿐이면 명함 인물 사진을 올림·받지 않음, 연락처 사진(CONTACT·출처 없음)은 종전대로
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
QCoreApplication.setApplicationName("polypdf_bizcard_gphone_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_gphone_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
from viewer.bizcard import people as P, store as S, gsync as G, phone as PH
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat().replace("+00:00", "Z")


class FakeApi:
    def __init__(self):
        self.people, self.n = {}, itertools.count(100)

    def _touch(self, rn):
        self.people[rn]["metadata"] = {"sources": [{"type": "CONTACT", "updateTime": iso(time.time())}]}
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


def apply_default(st, api, rows):
    out = [r for r in rows if G.row_default(r)]
    out += [dict(r, kind="unlink", was=r["kind"]) for r in rows if not G.row_default(r) and r["kind"] in G.UNLINK_IF_KEPT]
    order = {k: n for n, k in enumerate(G.KINDS + ("link", "unlink"))}
    return G.apply(st, api, sorted(out, key=lambda r: order.get(r["kind"], 99)), "", people=api.list_people())


def changes(rows):
    return [r for r in rows if r["kind"] in (G.TO_CARD, G.TO_GOOGLE, G.NEW_CARD, G.NEW_GOOGLE, G.GONE_VALUE)]


def gvals(api, rn):
    return [x["value"] for x in api.people[rn].get("phoneNumbers") or []]


try:
    PH.set_country(PH.KR)
    print("=== A 명함 → 구글 사람의 전화 꼴 ===")
    body = G.card_person({"name": "가짜", "phones": [("cell", "010-0000-1111"), ("work", "02-000-0000"), ("work", "031-000-0000"),
                                                    ("work", "1588-0000"), ("work", "+1-555-0100"), ("work", "02-000-0000 내선 7")]})
    got = [x["value"] for x in body["phoneNumbers"]]
    chk(got == ["+82 10-0000-1111", "+82 2-000-0000", "+82 31-000-0000", "1588-0000", "+1-555-0100", "02-000-0000 내선 7"],
        "A 한국 번호만 +82 국제 꼴", str(got))

    for ctry in (PH.KR, ""):
        PH.set_country(ctry)
        print("\n=== B 올린 뒤 다시 싱크 (기본 국가 %r) ===" % ctry)
        st = S.BizcardStore(TMP / "local" / ("b%s.db" % (ctry or "none")))
        st.meta_set(P.KINDS_FIXED_KEY, 1.0)
        P.src_init(st)
        a = P._insert_contact(st, {"name": "가짜갑", "phones": [("cell", "010-0000-1111"), ("work", "02-000-0000")]}, ["명함"])
        st.con.commit()
        api = FakeApi()
        apply_default(st, api, G.plan(st, api.list_people(), "", card_first=True))
        rn = G.links(st)[a]["rn"]
        chk(gvals(api, rn) == ["+82 10-0000-1111", "+82 2-000-0000"], "B 구글에 국제 꼴로 올라감", str(gvals(api, rn)))
        again = G.plan(st, api.list_people(), "")
        chk(not changes(again), "B 다시 싱크하면 바꿀 것 없음", str([(r["kind"], r.get("changes")) for r in again]))
        st.con.close()

    PH.set_country(PH.KR)
    print("\n=== C 이미 구글에 국내 꼴로 있는 짝 ===")
    st = S.BizcardStore(TMP / "local" / "c.db")
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    P.src_init(st)
    b = P._insert_contact(st, {"name": "가짜을", "phones": [("cell", "010-0000-2222")], "emails": ["eul@example.com"]}, ["명함"])
    st.con.commit()
    api = FakeApi()
    old = api.create({"names": [{"unstructuredName": "가짜을"}], "phoneNumbers": [{"value": "010-0000-2222", "type": "mobile"}],
                      "emailAddresses": [{"value": "eul@example.com"}]})
    apply_default(st, api, G.plan(st, api.list_people(), ""))          # 처음 짝 — 값이 같으면 짝만
    chk(G.links(st).get(b, {}).get("rn") == old["resourceName"], "C 짝지음")
    rows = G.plan(st, api.list_people(), "")
    ph = [r for r in rows if r["kind"] == G.TO_GOOGLE and r["card_id"] == b]
    chk(len(ph) == 1 and ph[0]["fields"] == ["phones"] and G.row_default(ph[0]),
        "C '구글을 명함 값으로 고침 — 전화' 한 줄(처음 체크)", str([(r["kind"], r.get("fields")) for r in rows]))
    chk(ph and ph[0]["changes"] == [("phones", "010-0000-2222", "+82 10-0000-2222")], "C 옛 값 → 새 값 글",
        str(ph and ph[0]["changes"]))
    apply_default(st, api, rows)
    chk(gvals(api, old["resourceName"]) == ["+82 10-0000-2222"], "C 적용 뒤 구글 번호 국제 꼴", str(gvals(api, old["resourceName"])))
    chk(not changes(G.plan(st, api.list_people(), "")), "C 그 뒤 다시 싱크하면 없음")
    chk(P.card_by_id(st, b)["phones"][0][1] == "010-0000-2222", "C 명함 쪽은 국내 꼴 그대로")

    print("\n=== D 프로필 사진 ===")
    prof = {"photos": [{"url": "https://example.com/p.jpg", "metadata": {"primary": True, "source": {"type": "PROFILE", "id": "1"}}}]}
    cont = {"photos": [{"url": "https://example.com/c.jpg", "metadata": {"source": {"type": "CONTACT", "id": "2"}}}]}
    bare = {"photos": [{"url": "https://example.com/b.jpg"}]}
    both = {"photos": prof["photos"] + cont["photos"]}
    chk(G.g_photo(prof) == "", "D 프로필 사진뿐이면 구글 사진 없음", G.g_photo(prof))
    chk(G.g_photo(cont) == "https://example.com/c.jpg" and G.g_photo(bare) == "https://example.com/b.jpg"
        and G.g_photo(both) == "https://example.com/c.jpg", "D 연락처 사진·출처 없는 사진은 종전대로")
    rn = old["resourceName"]
    real_first = G.first_photo
    try:
        G.first_photo = lambda c, folder: str(TMP / "fake_person.jpg")    # 명함 인물 사진이 있다고
        api.people[rn].update(copy.deepcopy(prof))
        up = [r for r in G.plan(st, api.list_people(), "", photos=True) if r["kind"] == G.PHOTO_UP]
        chk(len(up) == 1, "D 프로필 사진뿐 — 명함 인물 사진을 올림")
        api.people[rn].update(copy.deepcopy(cont))
        up = [r for r in G.plan(st, api.list_people(), "", photos=True) if r["kind"] == G.PHOTO_UP]
        chk(not up, "D 연락처 사진이 있으면 덮어쓰지 않음(종전대로)")
        G.first_photo = lambda c, folder: ""                              # 명함 인물 사진 없음
        api.people[rn].update(copy.deepcopy(prof))
        down = [r for r in G.plan(st, api.list_people(), "", photos=True) if r["kind"] == G.PHOTO_DOWN]
        chk(not down, "D 프로필 사진은 명함으로 받지 않음")
    finally:
        G.first_photo = real_first
    st.con.close()
except Exception:
    import traceback
    traceback.print_exc()
    fails.append("예외")

print("\n결과:", "ALL PASS" if not fails else "FAIL %d: %s" % (len(fails), fails))
sys.exit(1 if fails else 0)
