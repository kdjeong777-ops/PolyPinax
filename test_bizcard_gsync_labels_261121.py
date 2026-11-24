# -*- coding: utf-8 -*-
"""구글 싱크 — 고른 해시태그 ↔ 구글 라벨 (구글 싱크 SOT §5.29 '라벨', 261120-61). 가짜 구글(메모리 안)·가짜 값만.

A 명함에 붙인 고른 해시태그 → 구글 라벨(없으면 만듦), 다시 계획하면 바꿀 것 없음
B 구글에서 라벨을 떼면 해시태그도 뗌
C 고르지 않은 구글 라벨·시스템 라벨은 들여오지 않음, 구글에서 가져오는 새 명함은 고른 라벨만 해시태그로
D 새로 보내는 연락처는 그 라벨을 닮
E 해시태그를 고른 목록에서 빼면 '구글 라벨 — 지울까요'(기본 남김), 고르면 라벨만 지움(연락처 그대로)
F 미리보기 줄 글에 +라벨·−라벨
"""
import os, sys, tempfile, time, copy, itertools
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_labels_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_labels_"))
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


NOW = lambda: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())


class FakeApi:
    def __init__(self):
        self.people, self.n = {}, itertools.count(100)
        self.groups = {"contactGroups/myContacts": {"resourceName": "contactGroups/myContacts", "name": "myContacts",
                                                     "groupType": "SYSTEM_CONTACT_GROUP"}}
        self.deleted_groups = []

    def list_people(self):
        return [copy.deepcopy(p) for p in self.people.values()]

    def create(self, p):
        rn = "people/n%d" % next(self.n)
        q = dict(copy.deepcopy(p), resourceName=rn, etag="e1", metadata={"sources": [{"type": "CONTACT", "updateTime": NOW()}]})
        self.people[rn] = q
        return copy.deepcopy(q)

    def update(self, rn, p):
        self.people[rn].update({k: copy.deepcopy(v) for k, v in p.items() if k != "etag"})
        return copy.deepcopy(self.people[rn])

    def delete(self, rn):
        self.people.pop(rn, None)

    def list_groups(self):
        return [copy.deepcopy(g) for g in self.groups.values()]

    def create_group(self, name):
        rn = "contactGroups/g%d" % next(self.n)
        self.groups[rn] = {"resourceName": rn, "name": name, "groupType": "USER_CONTACT_GROUP"}
        return copy.deepcopy(self.groups[rn])

    def modify_members(self, group, add=(), remove=()):
        for rn in add:
            ms = self.people[rn].setdefault("memberships", [])
            ms.append({"contactGroupMembership": {"contactGroupResourceName": group}})
        for rn in remove:
            self.people[rn]["memberships"] = [m for m in self.people[rn].get("memberships") or []
                                              if m["contactGroupMembership"]["contactGroupResourceName"] != group]
        return {}

    def delete_group(self, group):
        self.deleted_groups.append(group)
        self.groups.pop(group, None)
        for p in self.people.values():
            p["memberships"] = [m for m in p.get("memberships") or [] if m["contactGroupMembership"]["contactGroupResourceName"] != group]


def labels_of(api, rn):
    names = {g["resourceName"]: g["name"] for g in api.groups.values()}
    return sorted(names.get(m["contactGroupMembership"]["contactGroupResourceName"], "?") for m in api.people[rn].get("memberships") or [])


def plan(st, api, **k):
    return G.plan(st, api.list_people(), groups=api.list_groups(), **k)


def run(st, api, rows):
    return G.apply(st, api, rows, people=api.list_people())


try:
    st = S.BizcardStore(TMP / "local" / "bizcard.db")
    api = FakeApi()
    api.people["people/a"] = {"resourceName": "people/a", "etag": "e", "names": [{"unstructuredName": "가짜일"}],
                              "phoneNumbers": [{"value": "010-0000-0001", "type": "mobile"}],
                              "memberships": [{"contactGroupMembership": {"contactGroupResourceName": "contactGroups/myContacts"}}],
                              "metadata": {"sources": [{"type": "CONTACT", "updateTime": "2020-01-01T00:00:00.000Z"}]}}
    a = P._insert_contact(st, {"name": "가짜일", "phones": [("cell", "010-0000-0001")]}, ["명함", "가짜모임", "가짜안고름"])
    st.con.commit()
    run(st, api, [r for r in G.plan(st, api.list_people()) if r["kind"] == "link"])
    st.meta_set(getattr(G, "OPT_LABELS", "gsync_label_tags"), ["가짜모임", "가짜새라벨"])

    # ── A ──
    print("=== A. 명함 → 구글 라벨 ===")
    try:
        rows = plan(st, api)
    except TypeError:
        rows = []
    lab = [r for r in rows if r["kind"] == getattr(G, "LABELS", "?")]
    chk(len(lab) == 1 and lab[0].get("add_g") == ["가짜모임"] and not lab[0].get("rm_t"), "A 고른 해시태그를 구글 라벨로(안 고른 태그는 아님)", str(rows))
    chk(lab and "+가짜모임" in (lab[0].get("txt") or ""), "F 줄 글에 +라벨", str(lab))
    run(st, api, rows)
    chk(labels_of(api, "people/a") == ["myContacts", "가짜모임"], "A 라벨을 만들고 달았음", str(labels_of(api, "people/a")))
    chk(not plan(st, api), "A 다시 계획하면 바꿀 것 없음", str(plan(st, api)))

    # ── B ──
    print("\n=== B. 구글에서 떼면 해시태그도 ===")
    g = next(rn for rn, x in api.groups.items() if x["name"] == "가짜모임")
    api.modify_members(g, remove=["people/a"])
    api.people["people/a"]["metadata"] = {"sources": [{"type": "CONTACT", "updateTime": NOW()}]}
    rows = plan(st, api)
    lab = [r for r in rows if r["kind"] == getattr(G, "LABELS", "?")]
    chk(len(lab) == 1 and lab[0].get("rm_t") == ["가짜모임"] and not lab[0].get("add_g"), "B 해시태그 떼기 줄", str(rows))
    run(st, api, rows)
    tags = P.card_by_id(st, a)["tags"]
    chk("가짜모임" not in tags and "가짜안고름" in tags, "B 고른 태그만 뗌(안 고른 태그는 그대로)", str(tags))
    chk(not plan(st, api), "B 다시 계획하면 바꿀 것 없음", str(plan(st, api)))

    # ── C ──
    print("\n=== C. 들여오기 ===")
    api.create_group("가짜외부")
    gx = next(rn for rn, x in api.groups.items() if x["name"] == "가짜외부")
    gnew = api.create_group("가짜새라벨")["resourceName"]
    api.people["people/c"] = {"resourceName": "people/c", "etag": "e", "names": [{"unstructuredName": "가짜셋"}],
                              "phoneNumbers": [{"value": "010-0000-0003", "type": "mobile"}],
                              "memberships": [{"contactGroupMembership": {"contactGroupResourceName": gx}},
                                              {"contactGroupMembership": {"contactGroupResourceName": gnew}},
                                              {"contactGroupMembership": {"contactGroupResourceName": "contactGroups/myContacts"}}],
                              "metadata": {"sources": [{"type": "CONTACT", "updateTime": NOW()}]}}
    api.modify_members(gx, add=["people/a"])
    rows = plan(st, api)
    la = [r for r in rows if r["kind"] == getattr(G, "LABELS", "?")]
    chk(len(la) == 1 and la[0]["add_t"] == ["가짜외부"] and not la[0]["add_g"],
        "C 구글 라벨은 해시태그로 가져옴(사용자 지시 261121 — 시스템 라벨은 빼고)", str(rows))
    run(st, api, rows)
    cc = [c for c in G.all_cards(st) if c["name"] == "가짜셋"]
    chk(cc and "가짜새라벨" in cc[0]["tags"] and "가짜외부" in cc[0]["tags"] and "myContacts" not in cc[0]["tags"]
        and "가짜외부" in P.card_by_id(st, a)["tags"], "C 구글에서 가져온 새 명함도 라벨을 해시태그로(myContacts 빼고)", str(cc and cc[0]["tags"]))
    chk(not plan(st, api), "C 다시 계획하면 바꿀 것 없음", str(plan(st, api)))
    st.meta_set("gsync_label_off", ["가짜외부"])
    chk(not plan(st, api), "C 환경설정에서 끈 라벨은 다시 맞추지 않음", str(plan(st, api)))

    # ── D ──
    print("\n=== D. 새로 보내는 연락처 ===")
    d = P._insert_contact(st, {"name": "가짜넷", "phones": [("cell", "010-0000-0004")]}, ["명함", "가짜새라벨"])
    st.con.commit()
    rows = plan(st, api)
    run(st, api, rows)
    rnd = G.links(st)[d]["rn"]
    chk(labels_of(api, rnd) == ["가짜새라벨"], "D 새 연락처가 그 라벨을 닮", str(labels_of(api, rnd)))
    chk(not plan(st, api), "D 다시 계획하면 바꿀 것 없음", str(plan(st, api)))

    # ── E ──
    print("\n=== E. 고른 목록에서 뺀 라벨 ===")
    st.meta_set(getattr(G, "OPT_LABELS", "gsync_label_tags"), ["가짜새라벨"])
    st.meta_set("gsync_label_off", ["가짜외부", "가짜모임"])
    rows = plan(st, api)
    gone = [r for r in rows if r["kind"] == getattr(G, "LABEL_GONE", "?")]
    chk(len(gone) == 1 and gone[0]["name"] == "가짜모임" and not G.row_default(gone[0]), "E 앱이 쓰던 라벨을 뺐으면 '지울까요'(기본 남김)", str(rows))
    run(st, api, gone)
    chk(not any(x["name"] == "가짜모임" for x in api.groups.values()) and "people/a" in api.people and "가짜외부" in [x["name"] for x in api.groups.values()],
        "E 고르면 그 라벨만 지움(연락처·다른 라벨 그대로)", str(api.deleted_groups))

    # ── G ── 명함 환경설정 '구글 라벨로 올릴 해시태그'
    print("\n=== G. 명함 환경설정 ===")
    from viewer.widgets.bizcard_settings_dialog import BizcardSettingsDialog
    sd = BizcardSettingsDialog(None, host=None, store=st)
    lw = getattr(sd, "lst_glabels", None)
    from PyQt6.QtWidgets import QApplication as _QA
    import time as _t
    _end = _t.monotonic() + 5                             # 명함 해시태그 전체는 배경에서 채운다(261120-68)
    while lw is not None and _t.monotonic() < _end and not any(lw.item(i).text() == "가짜안고름" for i in range(lw.count())):
        _QA.processEvents()
        _t.sleep(0.01)
    items = {lw.item(i).text(): lw.item(i).checkState() for i in range(lw.count())} if lw is not None else {}
    from PyQt6.QtCore import Qt
    chk(items.get("가짜새라벨") == Qt.CheckState.Checked and items.get("가짜안고름") == Qt.CheckState.Unchecked and "명함" not in items,
        "G 해시태그 목록에 체크(고른 것만 켜짐, '명함' 은 없음)", str(items))
    if lw is not None:
        next(lw.item(i) for i in range(lw.count()) if lw.item(i).text() == "가짜안고름").setCheckState(Qt.CheckState.Checked)
        sd._gsync_save()
    chk(sorted(st.meta_get(G.OPT_LABELS, [])) == ["가짜새라벨", "가짜안고름"] and "가짜외부" in (st.meta_get("gsync_label_off", []) or []),
        "G 저장하면 고른 해시태그 기억·끈 것은 끈 목록에", str((st.meta_get(G.OPT_LABELS, []), st.meta_get("gsync_label_off", []))))
    sd.close()
    st.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외")
print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
