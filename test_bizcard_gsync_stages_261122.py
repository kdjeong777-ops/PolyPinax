# -*- coding: utf-8 -*-
"""구글 싱크 단계 — 글 먼저(일괄 요청) → 사진·드라이브는 배경 대기열 (명함 SOT §5.29 '단계', 261120-71).
가짜 구글(메모리 안)·가짜 명함·임시 폴더만 — 실제 구글에 붙지 않는다(§2.1 의 7).

A 1단계 [적용] — 새 연락처는 일괄 만들기(한 명씩 만들지 않음)·라벨은 라벨마다 한 번, 사진·드라이브는 올리지 않고 대기열에
B 2단계 run_media — 대기열을 사람마다: 연락처 사진(줄여서 PHOTO_MAX_PX)·드라이브 파일, 링크는 사람마다 한 번, 대기열 비움
C 멈춤 — 한 사람 몫이 끝나면 멈추고 남은 것은 대기열, 다시 돌리면 이어서(겹쳐 올리지 않음)
D 대기열에 있는 줄은 다음 미리보기에 다시 내지 않음
E 다른 까닭으로 세 번 실패한 줄은 대기열에서 빼 '지난번 못 올림'
F 요청 한도(429) — 실패로 끝내지 않고 Retry-After 만큼 쉬었다 이어 감
G 명함찾기를 열면 남은 대기열을 배경에서 저절로 이어 올림(아래 줄 진행 글), 메인 최장 정지 < 1초
"""
import os, sys, tempfile, time, copy, itertools, io, threading
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, QTimer
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox
from pathlib import Path
from PIL import Image

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_gstages_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_gstages_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
from viewer.bizcard import people as P, store as S, gsync as G
from viewer.bizcard.gsync_api import ApiError
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


class FakeApi:
    def __init__(self):
        self.people, self.n, self.fid = {}, itertools.count(100), itertools.count(1)
        self.calls, self.photos, self.files, self.bad = {}, {}, {}, set()
        self.lock = threading.Lock()

    def _c(self, k):
        with self.lock:
            self.calls[k] = self.calls.get(k, 0) + 1

    def list_people(self):
        self._c("list")
        return [copy.deepcopy(p) for p in self.people.values()]

    def _make(self, p):
        rn = "people/n%d" % next(self.n)
        self.people[rn] = dict(copy.deepcopy(p), resourceName=rn, etag="e1",
                               metadata={"sources": [{"type": "CONTACT", "updateTime": "2020-01-01T00:00:00.000Z"}]})
        return copy.deepcopy(self.people[rn])

    def create(self, p):
        self._c("create")
        return self._make(p)

    def batch_create(self, persons):
        self._c("batch_create")
        assert len(persons) <= G.BATCH
        return [self._make(p) for p in persons]

    def update(self, rn, p):
        self._c("update")
        self.people[rn].update({k: copy.deepcopy(v) for k, v in p.items() if k != "etag"})
        return copy.deepcopy(self.people[rn])

    def batch_update(self, persons):
        self._c("batch_update")
        return {rn: self.update(rn, p) for rn, p in persons.items()}

    def update_photo(self, rn, data):
        self._c("photo")
        if rn in self.bad:
            raise ApiError("http 500", 500)
        self.photos[rn] = data
        self.people[rn]["photos"] = [{"url": "https://example.com/p", "default": False}]
        return {}

    def list_groups(self):
        return [{"resourceName": "contactGroups/g1", "name": "가짜모임", "groupType": "USER_CONTACT_GROUP"}]

    def create_group(self, name):
        return {"resourceName": "contactGroups/g2"}

    def modify_members(self, g, add=(), remove=()):
        self._c("members")
        for rn in add:
            self.people[rn].setdefault("memberships", []).append({"contactGroupMembership": {"contactGroupResourceName": g}})
        return {}

    def ensure_folder(self, name):
        return "folder1"

    def upload(self, path, name, folder_id, file_id=""):
        self._c("upload")
        with open(path, "rb") as f:
            self.files[file_id or "f%d" % next(self.fid)] = f.read()
        return file_id or "f%d" % next(self.fid)


def make_cards(st, n, start=0):
    fold = TMP / "cards" / "정리"
    fold.mkdir(parents=True, exist_ok=True)
    ids = []
    for i in range(start, start + n):
        f, b = fold / ("가짜%03d_사.jpg" % i), fold / ("가짜%03d_사_뒷면.jpg" % i)
        Image.new("RGB", (340, 200), "white").save(f)
        Image.new("RGB", (340, 200), "gray").save(b)
        cid = st.upsert({"front": str(f), "back": str(b), "name": "가짜%03d" % i, "phones": [("cell", "010-0000-%04d" % i)]})
        P.update_card(st, cid, {"tags": ["명함", "가짜모임"]})
        pf = P.photo_front(P.card_by_id(st, cid), str(TMP / "cards"))
        src = TMP / "face.jpg"
        Image.new("RGB", (1500, 2000), "red").save(src)
        P.save_person_photo(str(src), P.next_photo_path(pf))
        ids.append(cid)
    st.con.commit()
    return ids


try:
    FOLDER = str(TMP / "cards")
    st = S.BizcardStore(TMP / "local" / "bizcard.db")
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    st.meta_set(G.OPT_LABELS, ["가짜모임"])
    ids = make_cards(st, 5)
    api = FakeApi()

    # ── A ──
    print("=== A. 1단계 글 ===")
    rows = G.plan(st, api.list_people(), FOLDER, photos=True, drive=True, groups=api.list_groups())
    api.calls.clear()
    res = G.apply(st, api, rows, FOLDER, people=api.list_people())
    q = st.meta_get(getattr(G, "QUEUE_KEY", "gsync_media_queue"), []) or []
    chk(api.calls.get("batch_create") == 1 and not api.calls.get("create"), "A 새 연락처 5명은 일괄 만들기 한 번", str(api.calls))
    chk(api.calls.get("members") == 1, "A 라벨은 라벨마다 한 번", str(api.calls))
    chk(not api.calls.get("photo") and not api.calls.get("upload") and len(q) == 5 * 4 and res.get("queued") == 20,
        "A 사진·드라이브는 올리지 않고 대기열(사람마다 사진 1·파일 3)", str((api.calls, len(q), res.get("queued"))))

    # ── D ──
    again = G.plan(st, api.list_people(), FOLDER, photos=True, drive=True, groups=api.list_groups())
    chk(not [r for r in again if r["kind"] in (G.PHOTO_UP, G.DRIVE_UP)], "D 대기열에 있는 줄은 다시 내지 않음",
        str([(r["kind"], r.get("side")) for r in again]))

    # ── C ──
    print("\n=== C. 멈춤·이어서 ===")
    api.calls.clear()
    seen = []
    r1 = G.run_media(st, api, FOLDER, should_stop=lambda: len(seen) >= 1, progress=lambda i, n: seen.append((i, n)))
    left = len(st.meta_get(G.QUEUE_KEY, []) or [])
    chk(left == 16 and api.calls.get("update") == 1, "C 한 사람 몫이 끝나면 멈춤 — 남은 16줄 대기열, 링크 넣기는 그 사람 한 번", str((left, api.calls, r1)))

    # ── B ──
    print("\n=== B. 2단계 나머지 ===")
    r2 = G.run_media(st, api, FOLDER)
    left = len(st.meta_get(G.QUEUE_KEY, []) or [])
    chk(left == 0 and api.calls.get("update") == 5 and api.calls.get("upload") == 15 and api.calls.get("photo") == 5,
        "B 이어서 끝까지 — 링크 넣기는 사람마다 한 번(5), 파일 15·사진 5(겹침 없음)", str((left, api.calls, r2)))
    sizes = [Image.open(io.BytesIO(d)).size for d in api.photos.values()]
    chk(sizes and max(max(s) for s in sizes) <= G.PHOTO_MAX_PX, "B 연락처 사진도 줄여서", str(sizes))
    memo = (api.people[G.links(st)[ids[0]]["rn"]].get("biographies") or [{}])[0].get("value", "")
    chk("명함 뒷면: " in memo and "인물 사진 1: " in memo, "B 메모 링크 줄", repr(memo))
    _rr = G.plan(st, api.list_people(), FOLDER, photos=True, drive=True, groups=api.list_groups())
    chk(not _rr, "B 다시 계획하면 바꿀 것 없음", str([(r["kind"], r.get("fields"), r.get("side")) for r in _rr][:6]))

    # ── E ──
    print("\n=== E. 세 번 실패 ===")
    more = make_cards(st, 1, start=50)
    rows = G.plan(st, api.list_people(), FOLDER, photos=True, drive=False, groups=api.list_groups())
    G.apply(st, api, rows, FOLDER, people=api.list_people())
    api.bad.add(G.links(st)[more[0]]["rn"])
    for _ in range(3):
        G.run_media(st, api, FOLDER)
    nxt = G.plan(st, api.list_people(), FOLDER, photos=True, drive=False, groups=api.list_groups())
    chk(not (st.meta_get(G.QUEUE_KEY, []) or []) and any(r.get("retry") and r["kind"] == G.PHOTO_UP for r in nxt),
        "E 세 번 실패하면 대기열에서 빼 '지난번 못 올림'", str([(r["kind"], r.get("retry")) for r in nxt]))
    api.bad.clear()

    # ── F ──
    print("\n=== F. 429 ===")
    import urllib.error, urllib.request
    from viewer.bizcard import gsync_api as GA
    waits, n429 = [], [0]

    class _R:
        def __init__(self, b):
            self.b = b

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self.b

    def fake_open(req, timeout=0):
        if n429[0] < 6:
            n429[0] += 1
            raise urllib.error.HTTPError(req.full_url, 429, "x", {"Retry-After": "7"}, io.BytesIO(b"{}"))
        return _R(b'{"ok": 1}')
    _uo = urllib.request.urlopen
    urllib.request.urlopen = fake_open
    try:
        a = GA.Api(lambda: "tok")
        a._sleep = waits.append
        out = a._req("GET", "https://example.com/x")
    except Exception as e:
        out = repr(e)
    finally:
        urllib.request.urlopen = _uo
    chk(out == b'{"ok": 1}' and waits[:6] == [7] * 6, "F 429 여섯 번에도 실패로 끝내지 않고 Retry-After(7초)만큼 쉬었다 이어 감", str((out, waits)))

    # ── G ──
    print("\n=== G. 명함찾기를 열면 이어서 ===")
    more2 = make_cards(st, 2, start=70)
    rows = G.plan(st, api.list_people(), FOLDER, photos=True, drive=True, groups=api.list_groups())
    G.apply(st, api, rows, FOLDER, people=api.list_people())
    chk(len(st.meta_get(G.QUEUE_KEY, []) or []) >= 8, "(전제) 대기열 — 새 두 사람 8줄 이상")
    st.close()
    from viewer.widgets import bizcard_gsync_dialog as GD
    from viewer.bizcard import gsync_auth as GAU
    GD._api = lambda _st: api
    GAU.connected = lambda: True
    from viewer.widgets import bizcard_find_dialog as FD
    fd = FD.BizcardFindDialog(None, db=TMP / "local" / "bizcard.db")
    fd._bz_folder = FOLDER
    gap = [0.0]
    last = [time.monotonic()]

    def tick():
        now = time.monotonic()
        gap[0] = max(gap[0], now - last[0])
        last[0] = now
    tm = QTimer()
    tm.timeout.connect(tick)
    tm.start(20)
    fd.show()
    texts = []
    t0 = time.monotonic()
    while time.monotonic() - t0 < 15:
        app.processEvents()
        lb = getattr(fd, "lbl_media", None)
        if lb is not None and lb.isVisible() and lb.text():
            texts.append(lb.text())
        st2 = fd._store()
        if not (st2.meta_get(G.QUEUE_KEY, []) or []) and not getattr(fd, "media_busy", False):
            break
        time.sleep(0.01)
    tm.stop()
    chk(not (fd._store().meta_get(G.QUEUE_KEY, []) or []), "G 열면 남은 대기열을 배경에서 이어 올림")
    chk(any("사진" in t for t in texts), "G 아래 줄에 진행 글", str(texts[:3]))
    chk(gap[0] < 1.0, "G 메인 최장 정지 < 1초", "%.3f" % gap[0])
    fd.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외")
print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
