# -*- coding: utf-8 -*-
"""구글 싱크 드라이브 — 올린 기록이 없는 파일도 폴더에 같은 파일(이름+md5)이 있으면 다시 올리지 않음
(구글 싱크 SOT §5.29 '드라이브', 261122-6). 가짜 구글(메모리 안)·가짜 명함·임시 폴더만 — 실제 구글에 붙지 않는다(§2.1 의 7).

A 처음 싱크 — 파일마다 새로 올림(사람마다 앞·뒷면·인물 사진 3)
B 짝의 드라이브 기록이 사라진 뒤(DB 손상 꼴) 다시 싱크 — 이름·내용이 같은 파일은 올리지 않고 그 파일을 씀, 드라이브 파일 수 그대로
C 이름은 같고 내용이 바뀐 파일 — 새 파일을 만들지 않고 그 파일 내용만 바꿈
D 폴더를 읽지 못하는 api(옛 꼴) — 종전처럼 올림(멈추지 않음)
"""
import os, sys, tempfile, copy, itertools, hashlib, json
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication
from pathlib import Path
from PIL import Image

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_greuse_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_greuse_"))
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


class FakeApi:
    def __init__(self, listable=True):
        self.people, self.n, self.fid = {}, itertools.count(100), itertools.count(1)
        self.calls, self.files = {}, {}                  # 파일 id → {name, data}
        if not listable:
            self.list_folder = None

    def _c(self, k):
        self.calls[k] = self.calls.get(k, 0) + 1

    def list_people(self):
        return [copy.deepcopy(p) for p in self.people.values()]

    def _make(self, p):
        rn = "people/n%d" % next(self.n)
        self.people[rn] = dict(copy.deepcopy(p), resourceName=rn, etag="e1",
                               metadata={"sources": [{"type": "CONTACT", "updateTime": "2020-01-01T00:00:00.000Z"}]})
        return copy.deepcopy(self.people[rn])

    def create(self, p):
        return self._make(p)

    def batch_create(self, persons):
        return [self._make(p) for p in persons]

    def update(self, rn, p):
        self.people[rn].update({k: copy.deepcopy(v) for k, v in p.items() if k != "etag"})
        return copy.deepcopy(self.people[rn])

    def batch_update(self, persons):
        return {rn: self.update(rn, p) for rn, p in persons.items()}

    def update_photo(self, rn, data):
        self.people[rn]["photos"] = [{"url": "https://example.com/p", "default": False}]
        return {}

    def list_groups(self):
        return []

    def ensure_folder(self, name):
        return "folder1"

    def list_folder(self, folder_id):
        self._c("list_folder")
        return [{"id": k, "name": v["name"], "md5Checksum": hashlib.md5(v["data"]).hexdigest()} for k, v in self.files.items()]

    def upload(self, path, name, folder_id, file_id=""):
        self._c("upload_patch" if file_id else "upload_new")
        with open(path, "rb") as f:
            data = f.read()
        fid = file_id or "f%d" % next(self.fid)
        self.files[fid] = {"name": name, "data": data}
        return fid


def make_cards(st, n):
    fold = TMP / "cards" / "정리"
    fold.mkdir(parents=True, exist_ok=True)
    ids = []
    for i in range(n):
        f, b = fold / ("가짜%03d_사.jpg" % i), fold / ("가짜%03d_사_뒷면.jpg" % i)
        Image.new("RGB", (340, 200), "white").save(f)
        Image.new("RGB", (340, 200), (i * 40, 90, 90)).save(b)
        cid = st.upsert({"front": str(f), "back": str(b), "name": "가짜%03d" % i, "phones": [("cell", "010-0000-%04d" % (i * 1111))]})
        pf = P.photo_front(P.card_by_id(st, cid), str(TMP / "cards"))
        src = TMP / "face.jpg"
        Image.new("RGB", (300, 400), "red").save(src)
        P.save_person_photo(str(src), P.next_photo_path(pf))
        ids.append(cid)
    st.con.commit()
    return ids


def sync(st, api):
    rows = G.plan(st, api.list_people(), FOLDER, photos=False, drive=True)
    G.apply(st, api, rows, FOLDER, people=api.list_people())
    return G.run_media(st, api, FOLDER)


def forget_drive(st):
    st.con.execute("UPDATE google_link SET drive='{}'")    # 짝의 드라이브 기록이 사라진 꼴(261123 DB 손상)
    st.con.commit()


try:
    FOLDER = str(TMP / "cards")
    st = S.BizcardStore(TMP / "local" / "bizcard.db")
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    ids = make_cards(st, 3)
    api = FakeApi()

    print("=== A 처음 싱크 ===")
    sync(st, api)
    chk(api.calls.get("upload_new") == 9 and len(api.files) == 9, "A 파일 9개(3명 × 앞·뒷면·인물 사진) 새로 올림", str(api.calls))
    ids0 = {cid: dict(G.links(st)[cid]["drive"]) for cid in ids}

    print("\n=== B 드라이브 기록이 사라진 뒤 ===")
    forget_drive(st)
    api.calls.clear()
    rows = G.plan(st, api.list_people(), FOLDER, photos=False, drive=True)
    chk(len([r for r in rows if r["kind"] == G.DRIVE_UP]) == 9, "B (전제) 기록이 없으니 9개를 올릴 줄로 냄")
    G.apply(st, api, rows, FOLDER, people=api.list_people())
    G.run_media(st, api, FOLDER)
    chk(not api.calls.get("upload_new") and not api.calls.get("upload_patch") and len(api.files) == 9,
        "B 같은 이름·내용 파일은 올리지 않음(드라이브 파일 수 그대로)", str((api.calls, len(api.files))))
    chk(api.calls.get("list_folder") == 1, "B 폴더는 한 번만 읽음", str(api.calls))
    ids1 = {cid: dict(G.links(st)[cid]["drive"]) for cid in ids}
    chk(all(ids1[c][s]["id"] == ids0[c][s]["id"] for c in ids for s in ids0[c]), "B 짝 기록은 있던 파일 id 로 다시 채움")
    chk(not [r for r in G.plan(st, api.list_people(), FOLDER, photos=False, drive=True) if r["kind"] == G.DRIVE_UP],
        "B 다음 싱크엔 올릴 것 없음")

    print("\n=== C 이름은 같고 내용이 바뀜 ===")
    back0 = P.card_by_id(st, ids[0])["back"]
    Image.new("RGB", (340, 200), "blue").save(P._real(back0))
    forget_drive(st)
    api.calls.clear()
    sync(st, api)
    chk(api.calls.get("upload_patch") == 1 and not api.calls.get("upload_new") and len(api.files) == 9,
        "C 바뀐 한 파일만 그 파일 내용 바꿈(새 파일 없음)", str((api.calls, len(api.files))))

    print("\n=== D 폴더를 읽지 못하는 api ===")
    api2 = FakeApi(listable=False)
    api2.people, api2.files = api.people, api.files
    forget_drive(st)
    try:
        sync(st, api2)
        ok = api2.calls.get("upload_new") == 9
    except Exception as e:
        ok = False
        print(repr(e))
    chk(ok, "D 폴더를 못 읽으면 종전처럼 올림(멈추지 않음)", str(api2.calls))
except Exception as e:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외", repr(e))
print("FAILURES: %d" % len(fails))
for f in fails:
    print("  -", f)
sys.stdout.flush()
os._exit(1 if fails else 0)
