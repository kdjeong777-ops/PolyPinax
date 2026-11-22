# -*- coding: utf-8 -*-
"""구글 싱크 — 사진·드라이브 (명함 SOT §5.29 '드라이브(선택)'·'새 연락처의 사진·드라이브'·'못 올렸을 때', 261120-70).
가짜 구글(메모리 안)·가짜 명함·임시 폴더만 — 실제 구글 계정에 붙지 않는다(§2.1 의 7).

A 새 연락처도 같은 [적용] 으로 사진·드라이브(1단계 만들기 → 2단계 run_media, 261120-71) — 연락처 사진 = 첫 인물 사진, 앞면 링크 = 누리집, 뒷면·인물 사진 링크 = 메모 끝 줄
B 드라이브에 올리는 그림은 줄여서(긴 변 DRIVE_MAX_PX)
C 새 연락처 줄을 고르지 않으면 그 사람 사진·드라이브 줄은 건너뜀(못 한 수 아님)
D 드라이브 저장 공간 부족 — 까닭별 알림, 2단계 멈춤(대기열 그대로·미리보기에 다시 안 냄), 공간 뒤 이어 올리면 그것만, '지난번 못 올림' 줄 글
E 다시 계획하면 바꿀 것 없음(링크가 명함 DB 에도 적혀 되돌지 않음)
"""
import os, sys, tempfile, time, copy, itertools, io
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication
from pathlib import Path
from PIL import Image

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_gphotos_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_gphotos_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
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
        self.photos, self.files, self.quota_left = {}, {}, 99

    def list_people(self):
        return [copy.deepcopy(p) for p in self.people.values()]

    def create(self, p):
        rn = "people/n%d" % next(self.n)
        q = dict(copy.deepcopy(p), resourceName=rn, etag="e1", metadata={"sources": [{"type": "CONTACT", "updateTime": "2020-01-01T00:00:00.000Z"}]})
        self.people[rn] = q
        return copy.deepcopy(q)

    def update(self, rn, p):
        self.people[rn].update({k: copy.deepcopy(v) for k, v in p.items() if k != "etag"})
        return copy.deepcopy(self.people[rn])

    def update_photo(self, rn, data):
        self.photos[rn] = data
        self.people[rn]["photos"] = [{"url": "https://example.com/p/%s" % rn.split("/")[-1], "default": False}]
        return {}

    def modify_members(self, *a, **k):
        return {}

    def ensure_folder(self, name):
        return "folder1"

    def upload(self, path, name, folder_id, file_id=""):
        if self.quota_left <= 0:
            raise ApiError("http 403", 403, "storageQuotaExceeded")
        self.quota_left -= 1
        with open(path, "rb") as f:
            data = f.read()
        fid = file_id or "f%d" % next(self.fid)
        self.files[fid] = (name, data)
        return fid


def card_with_pictures(st, name, cell, big=False):
    fold = TMP / "cards" / "정리"
    fold.mkdir(parents=True, exist_ok=True)
    size = (3000, 1800) if big else (340, 200)
    front, back = fold / ("%s_가짜사.jpg" % name), fold / ("%s_가짜사_뒷면.jpg" % name)
    Image.new("RGB", size, "white").save(front)
    Image.new("RGB", size, "gray").save(back)
    cid = st.upsert({"front": str(front), "back": str(back), "name": name, "company": "가짜사", "phones": [("cell", cell)]})
    pf = P.photo_front(P.card_by_id(st, cid), str(TMP / "cards"))
    src = TMP / ("%s_face.jpg" % name)
    Image.new("RGB", (120, 160), "red").save(src)
    P.save_person_photo(str(src), P.next_photo_path(pf))
    return cid


try:
    st = S.BizcardStore(TMP / "local" / "bizcard.db")
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    api = FakeApi()
    FOLDER = str(TMP / "cards")
    a = card_with_pictures(st, "가짜일", "010-0000-0001", big=True)
    st.con.commit()

    # ── A·B ──
    print("=== A·B. 새 연락처도 같은 적용에서 ===")
    rows = G.plan(st, api.list_people(), FOLDER, photos=True, drive=True)
    kinds = sorted((r["kind"], r.get("side", "")) for r in rows if r.get("card_id") == a)
    chk((G.NEW_GOOGLE, "") in kinds and (G.PHOTO_UP, "") in kinds and (G.DRIVE_UP, "front") in kinds and (G.DRIVE_UP, "back") in kinds
        and any(k == G.DRIVE_UP and s.startswith("photo") for k, s in kinds), "A 새 연락처 줄과 함께 사진·드라이브(앞·뒷면·인물 사진) 줄", str(kinds))
    res = G.apply(st, api, rows, FOLDER, people=api.list_people())
    mres = G.run_media(st, api, FOLDER)
    res = dict(res, failed=res.get("failed", 0) + mres.get("failed", 0))
    rn = G.links(st).get(a, {}).get("rn")
    p = api.people.get(rn, {})
    memo = (p.get("biographies") or [{}])[0].get("value", "")
    urls = [u["value"] for u in p.get("urls") or []]
    chk(res.get("failed") == 0 and rn in api.photos, "A 연락처 사진(첫 인물 사진)도 같은 적용에서", str(res))
    chk(any("drive.google.com/file/d/" in u for u in urls) and "명함 뒷면: https://drive.google.com/file/d/" in memo
        and "인물 사진 1: https://drive.google.com/file/d/" in memo, "A 앞면 링크 = 누리집, 뒷면·인물 사진 = 메모 끝 링크 줄", repr((urls, memo)))
    c = P.card_by_id(st, a)
    chk("명함 뒷면: " in (c.get("memo") or "") and any("drive.google.com" in u for u in c.get("urls") or []), "A 링크는 명함 DB 에도(되돌지 않게)")
    sizes = [Image.open(io.BytesIO(d)).size for _n, d in api.files.values()]
    chk(sizes and max(max(s) for s in sizes) <= G.DRIVE_MAX_PX, "B 드라이브에는 줄여서", str(sizes))

    # ── E ──
    again = G.plan(st, api.list_people(), FOLDER, photos=True, drive=True)
    chk(not again, "E 다시 계획하면 바꿀 것 없음", str([(r["kind"], r.get("side")) for r in again]))

    # ── C ──
    print("\n=== C. 새 연락처 줄을 고르지 않으면 ===")
    b = card_with_pictures(st, "가짜이", "010-0000-0002")
    st.con.commit()
    rows = G.plan(st, api.list_people(), FOLDER, photos=True, drive=True)
    only = [r for r in rows if r.get("card_id") == b and r["kind"] != G.NEW_GOOGLE]
    res = G.apply(st, api, only, FOLDER, people=api.list_people())
    mres = G.run_media(st, api, FOLDER)
    chk(res.get("failed") == 0 and mres.get("failed") == 0 and b not in G.links(st) and not G.media_left(st),
        "C 사진·드라이브 줄만 넘기면 건너뜀(못 한 수 아님, 대기열에서 빠짐)", str((res, mres)))

    # ── D ──
    print("\n=== D. 드라이브 저장 공간 부족 ===")
    api.quota_left = 1
    rows = G.plan(st, api.list_people(), FOLDER, photos=True, drive=True)
    G.apply(st, api, rows, FOLDER, people=api.list_people())
    res = G.run_media(st, api, FOLDER)
    why = res.get("reasons") or {}
    chk(res.get("failed", 0) >= 1 and why.get("quota", 0) >= 1 and res.get("stopped") == "quota" and G.media_left(st) >= 1,
        "D 까닭별(저장 공간 부족)·2단계 멈춤·대기열 그대로", str(res))
    nxt = G.plan(st, api.list_people(), FOLDER, photos=True, drive=True)
    chk(not [r for r in nxt if r["kind"] in (G.PHOTO_UP, G.DRIVE_UP)], "D 대기열에 남은 것은 미리보기에 다시 내지 않음",
        str([(r["kind"], r.get("side")) for r in nxt]))
    from viewer.widgets.bizcard_gsync_dialog import GSyncDialog, fail_text
    from PyQt6.QtCore import Qt
    ft = fail_text(res)
    chk("드라이브 저장 공간 부족" in ft and "이어서" in ft, "D 결과 알림에 까닭(저장 공간 부족)과 이어 올리는 길", ft)
    fake = [{"kind": G.DRIVE_UP, "card_id": b, "rn": "people/x", "name": "가짜이", "side": "back", "path": "x", "retry": True}]
    dlg = GSyncDialog(None, db=str(st.path), start=False)
    dlg._planned(fake, api.list_people(), "")
    texts = [dlg.tree.topLevelItem(i).child(j).text(0) for i in range(dlg.tree.topLevelItemCount())
             for j in range(dlg.tree.topLevelItem(i).childCount())]
    dlg.close()
    chk(any("지난번 못 올림" in t and "명함 뒷면" in t for t in texts), "D 미리보기 줄 글 '— 면 — 지난번 못 올림'", str(texts))
    api.quota_left = 99
    res2 = G.run_media(st, api, FOLDER)
    chk(res2.get("failed") == 0 and not G.media_left(st) and not G.plan(st, api.list_people(), FOLDER, photos=True, drive=True),
        "D 공간 뒤 이어 올리면 그것만 — 대기열 비고 바꿀 것 없음", str(res2))
    st.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외")
print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
