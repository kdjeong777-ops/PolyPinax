# -*- coding: utf-8 -*-
"""구글 주소록 싱크 (명함 SOT §5.29, 261120-36) — 가짜 OAuth·People·Drive 서버(이 PC 안 http)와 가짜 연락처만(§2.1).
실제 구글에는 붙지 않는다.

A. 루프백 로그인 — PKCE(code_verifier 가 challenge 와 맞음)·state, 계정 메일, 갱신 토큰은 DPAPI 로 잠가 파일에(평문 없음)
B. 계획 — 메일·휴대폰으로 짝, 나중에 바뀐 쪽이 이김(명함이 나중이면 구글로, 구글이 나중이면 명함으로), 새 사람 양쪽
C. 미리보기 [반영] 전에는 구글·명함 모두 그대로
D. 반영 — 구글에 새 연락처·고침, 명함에 새 명함(#구글·출처 google)·고침, 짝 기록, 다시 계획하면 바꿀 것 없음
E. 지운 것 — 한쪽에서 지워져도 기본 '남김'(자동으로 안 지움), 고르면 구글 지움·명함은 부르는 쪽에 지울 id
F. 사진 — 인물 사진 ↔ 연락처 사진(켰을 때만), 드라이브 — 명함 그림 올리고 연락처 누리집에 링크
G. 429 는 기다렸다 다시 · [연결 끊기]는 철회 요청과 토큰 파일 지움
H. 화면 — 명함 환경설정 [구글 계정 연결]·미리보기 창(지워짐 기본 체크 꺼짐·[반영])·메인 정지 < 1초
"""
import os, sys, time, json, base64, hashlib, tempfile, shutil, threading, urllib.parse, urllib.request
os.environ["QT_QPA_PLATFORM"] = "offscreen"          # 검사 작성 SOT §14.7
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QTimer
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtTest import QTest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_gsync_%d" % os.getpid())
fails = []
TMP = Path(tempfile.mkdtemp(prefix="bizcard_gsync_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def pump(cond=None, timeout=15.0):
    t = time.monotonic()
    while time.monotonic() - t < timeout:
        app.processEvents()
        if cond is not None and cond():
            return True
        if cond is None and time.monotonic() - t > 0.3:
            return True
        time.sleep(0.01)
    return False


try:
    from viewer.bizcard import gsync as G, gsync_auth as A, gsync_api as API
except Exception as e:                       # 이 판 전 코드엔 모듈이 없다
    chk(False, "구글 싱크 모듈을 불러온다", repr(e))
    print("FAILURES: %d" % len(fails))
    sys.stdout.flush()
    os._exit(1)
from viewer.bizcard import people as P, store as S
from PIL import Image

# ── 가짜 서버 ──
SV = {"people": {}, "n": 0, "challenge": "", "pkce_ok": None, "revoked": [], "auth_hdr": True, "photos": {},
      "files": {}, "folders": {}, "fail429": 0, "deleted": []}
NOW = lambda: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())


def person(rn, name, emails=(), cells=(), title="", when="2020-01-01T00:00:00.000Z", company=""):
    return {"resourceName": rn, "etag": "e1", "names": [{"unstructuredName": name}],
            "organizations": [{"name": company, "title": title}] if (company or title) else [],
            "phoneNumbers": [{"value": c, "type": "mobile"} for c in cells],
            "emailAddresses": [{"value": e} for e in emails],
            "photos": [{"url": "https://x/default.jpg", "default": True}],
            "metadata": {"sources": [{"type": "CONTACT", "updateTime": when}]}}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj=None, raw=None, ctype="application/json", headers=None):
        b = raw if raw is not None else json.dumps(obj or {}).encode("utf-8")
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _auth(self):
        if not (self.headers.get("Authorization") or "").startswith("Bearer AT"):
            SV["auth_hdr"] = False

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/auth":
            SV["challenge"] = q["code_challenge"][0]
            SV["scope"] = q["scope"][0]
            loc = q["redirect_uri"][0] + "?" + urllib.parse.urlencode({"code": "CODE1", "state": q["state"][0]})
            return self._send(302, raw=b"", headers={"Location": loc})
        self._auth()
        if u.path == "/v1/people/me/connections":
            if SV["fail429"]:
                SV["fail429"] -= 1
                return self._send(429, {})
            return self._send(200, {"connections": list(SV["people"].values())})
        if u.path.startswith("/photo/"):
            return self._send(200, raw=SV["photos"][u.path[7:]], ctype="image/jpeg")
        if u.path == "/drive/v3/files":
            name = q["q"][0].split("'")[1]
            fid = SV["folders"].get(name)
            return self._send(200, {"files": [{"id": fid}] if fid else []})
        return self._send(404, {})

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        body = self._body()
        if u.path == "/token":
            f = urllib.parse.parse_qs(body.decode("ascii"))
            if f["grant_type"][0] == "authorization_code":
                v = f["code_verifier"][0]
                ch = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).decode().rstrip("=")
                SV["pkce_ok"] = (ch == SV["challenge"] and f["code"][0] == "CODE1")
                idt = "x." + base64.urlsafe_b64encode(json.dumps({"email": "fake.user@example.com"}).encode()).decode().rstrip("=") + ".y"
                return self._send(200, {"access_token": "AT1", "refresh_token": "RT_SECRET_1", "expires_in": 3600, "id_token": idt})
            return self._send(200, {"access_token": "AT2", "expires_in": 3600})
        if u.path == "/revoke":
            SV["revoked"].append(urllib.parse.parse_qs(body.decode())["token"][0])
            return self._send(200, {})
        self._auth()
        if u.path == "/v1/people:createContact":
            SV["n"] += 1
            p = json.loads(body)
            rn = "people/c%d" % SV["n"]
            p.update(resourceName=rn, etag="e1", metadata={"sources": [{"type": "CONTACT", "updateTime": NOW()}]})
            SV["people"][rn] = p
            return self._send(200, p)
        if u.path == "/drive/v3/files":
            m = json.loads(body)
            fid = "fold%d" % len(SV["folders"])
            SV["folders"][m["name"]] = fid
            return self._send(200, {"id": fid})
        if u.path == "/upload/drive/v3/files":
            fid = "file%d" % len(SV["files"])
            SV["files"][fid] = len(body)
            return self._send(200, {"id": fid})
        return self._send(404, {})

    def do_PATCH(self):
        u = urllib.parse.urlparse(self.path)
        body = self._body()
        self._auth()
        rn = u.path[len("/v1/"):].split(":")[0]
        if u.path.endswith(":updateContact"):
            p = SV["people"][rn]
            p.update(json.loads(body))
            p["etag"] = "e%d" % (int(p["etag"][1:]) + 1)
            p["metadata"] = {"sources": [{"type": "CONTACT", "updateTime": NOW()}]}
            return self._send(200, p)
        if u.path.endswith(":updateContactPhoto"):
            SV["photos"][rn.split("/")[1]] = base64.b64decode(json.loads(body)["photoBytes"])
            SV["people"][rn]["photos"] = [{"url": BASE + "/photo/" + rn.split("/")[1]}]
            return self._send(200, SV["people"][rn])
        if u.path.startswith("/upload/drive/v3/files/"):
            return self._send(200, {"id": u.path.rsplit("/", 1)[1]})
        return self._send(404, {})

    def do_DELETE(self):
        u = urllib.parse.urlparse(self.path)
        self._auth()
        rn = u.path[len("/v1/"):].split(":")[0]
        SV["people"].pop(rn, None)
        SV["deleted"].append(rn)
        return self._send(200, {})


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % srv.server_address[1]
A.AUTH_URL, A.TOKEN_URL, A.REVOKE_URL = BASE + "/auth", BASE + "/token", BASE + "/revoke"
API.PEOPLE_BASE = API.DRIVE_BASE = BASE
API.RETRY_WAITS = (0.01, 0.01, 0.01)


def fake_open(url):                                   # 브라우저 대신 — 가짜 구글이 루프백 주소로 돌려보낸다
    threading.Thread(target=lambda: urllib.request.urlopen(url, timeout=10).read(), daemon=True).start()
    return True


import webbrowser
webbrowser.open = fake_open                           # 혹시 실제 브라우저가 열리지 않게
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)

DB = TMP / "local" / "bizcard.db"
(TMP / "local").mkdir()
FOLDER = TMP / "cards"
FOLDER.mkdir()
st = S.BizcardStore(DB)
try:
    # ── A ──
    print("=== A. 로그인 ===")
    A.set_client(st, "fake-client-id", "fake-secret")
    email = A.login(*A.client(st), drive=True, open_url=fake_open, timeout=20)
    raw = A.token_path().read_text(encoding="utf-8") if A.token_path().exists() else ""
    chk(SV["pkce_ok"] is True and email == "fake.user@example.com", "A PKCE 가 맞고 계정 메일을 받음", str((SV["pkce_ok"], email)))
    chk(raw and "RT_SECRET_1" not in raw and "dpapi:v1:" in raw and A.connected(), "A 갱신 토큰은 DPAPI 로 잠가 파일에(평문 없음)")
    chk(st.meta_get(A.META_SECRET, "").startswith("dpapi:v1:"), "A 클라이언트 보안 비밀도 잠가 저장")
    chk(A.SCOPE_DRIVE in SV.get("scope", "") and A.SCOPE_CONTACTS in SV.get("scope", ""), "A 드라이브를 켜면 drive.file 범위를 더함")

    # ── B ──
    print("=== B. 계획 ===")
    SV["people"]["people/g1"] = person("people/g1", "가짜일", emails=["one@example.com"], title="부장")
    SV["people"]["people/g2"] = person("people/g2", "가짜이", cells=["010-0000-0102"], title="대리", when=NOW())
    SV["people"]["people/g3"] = person("people/g3", "구글만", emails=["only@example.com"])
    c1 = P._insert_contact(st, {"name": "가짜일", "emails": ["ONE@example.com"], "title": "과장"}, ["명함"])
    c2 = P._insert_contact(st, {"name": "가짜이", "phones": [("cell", "010-0000-0102")], "title": "사원"}, ["명함"])
    c4 = P._insert_contact(st, {"name": "명함만", "emails": ["card@example.com"]}, ["명함"])
    st.con.execute("UPDATE cards SET updated=? WHERE id=?", (1.0, c2))     # 명함 c2 는 오래전 — 구글 쪽이 나중
    st.con.commit()
    api = API.Api(lambda: A.access_token(*A.client(st)), sleep=lambda s: None)
    people = api.list_people()
    rows = G.plan(st, people, str(FOLDER))
    kinds = {(r["kind"], r["card_id"] or r["rn"]) for r in rows}
    chk((G.TO_GOOGLE, c1) in kinds, "B 메일로 짝·명함이 나중 → 구글로", str(sorted(kinds, key=str)))
    chk((G.TO_CARD, c2) in kinds, "B 휴대폰으로 짝·구글이 나중 → 명함으로")
    chk((G.NEW_CARD, "people/g3") in kinds and (G.NEW_GOOGLE, c4) in kinds, "B 구글에만·명함에만 있는 사람은 반대쪽에 새로")
    # ── C ──
    n_cards = st.con.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    chk(len(SV["people"]) == 3 and n_cards == 3 and SV["people"]["people/g1"]["organizations"][0]["title"] == "부장",
        "C 계획만으로는 아무것도 바뀌지 않음")
    # ── D ──
    print("=== D. 반영 ===")
    res = G.apply(st, api, [r for r in rows if G.DEFAULT_ON.get(r["kind"], True)], str(FOLDER), people=people)
    g1 = SV["people"]["people/g1"]
    newc = [P.card_by_id(st, r[0]) for r in st.con.execute("SELECT id FROM cards WHERE name='구글만'")]
    chk(res["failed"] == 0 and g1["organizations"][0]["title"] == "과장", "D 구글을 명함 값으로 고침", str(res))
    chk(P.card_by_id(st, c2)["title"] == "대리", "D 명함을 구글 값으로 고침")
    chk(newc and "구글" in newc[0]["tags"] and str(newc[0]["front"]).startswith("contact:")
        and P.field_srcs(st, newc[0]["id"]).get("name") == "google" if hasattr(P, "field_srcs") else bool(newc),
        "D 구글에만 있던 사람은 그림 없는 명함(#구글, 출처 google)")
    chk(any(p["names"][0].get("unstructuredName") == "#명함만" for p in SV["people"].values()),
        "D 명함에만 있던 사람은 구글에 새 연락처(기본 친구추가 방지 — 이름 앞 '#')")
    chk(SV["auth_hdr"], "D 모든 요청에 Bearer 접근 토큰")
    rows2 = G.plan(st, api.list_people(), str(FOLDER))
    chk(not rows2, "D 다시 계획하면 바꿀 것 없음", str([(r["kind"], r.get("fields")) for r in rows2]))

    # ── E ──
    print("=== E. 지운 것 ===")
    SV["people"].pop("people/g3")
    st.delete_card(c4)
    people = api.list_people()
    rows3 = G.plan(st, people, str(FOLDER))
    k3 = {r["kind"] for r in rows3}
    chk(k3 == {G.GONE_GOOGLE, G.GONE_CARD} and not any(G.DEFAULT_ON[k] for k in k3),
        "E 한쪽에서 지워진 것은 갈래로 보이고 기본 '남김'", str(k3))
    before = set(SV["people"])
    G.apply(st, api, [r for r in rows3 if G.DEFAULT_ON[r["kind"]]], str(FOLDER), people=people)
    chk(set(SV["people"]) == before, "E 기본으로는 자동으로 안 지움")
    res3 = G.apply(st, api, rows3, str(FOLDER), people=people)
    chk(len(SV["people"]) == len(before) - 1 and res3["delete_cards"] and newc and res3["delete_cards"][0] == newc[0]["id"],
        "E 고르면 구글 연락처 지움·명함은 지울 id 를 돌려줌(휴지통 길은 창이)", str(res3))
    for cid in res3["delete_cards"]:                  # 창이 휴지통 길로 지우는 것을 흉내(§5.20)
        st.delete_card(cid)

    # ── F ──
    print("=== F. 사진·드라이브 ===")
    c1c = P.card_by_id(st, c1)
    pf = P.photo_front(c1c, str(FOLDER))
    src = TMP / "face.jpg"
    Image.new("RGB", (120, 160), "orange").save(src)
    P.save_person_photo(str(src), P.next_photo_path(pf))
    rn2 = G.links(st)[c2]["rn"]
    jb = TMP / "g2.jpg"
    Image.new("RGB", (90, 90), "purple").save(jb)
    SV["photos"]["g2"] = jb.read_bytes()
    SV["people"][rn2]["photos"] = [{"url": BASE + "/photo/g2"}]
    people = api.list_people()
    rows4 = G.plan(st, people, str(FOLDER), photos=True)
    chk({r["kind"] for r in rows4} == {G.PHOTO_UP, G.PHOTO_DOWN}, "F 사진을 켜면 올림·받음 갈래", str([r["kind"] for r in rows4]))
    chk(not G.plan(st, people, str(FOLDER), photos=False), "F 사진을 끄면 사진 줄 없음")
    G.apply(st, api, rows4, str(FOLDER), people=people)
    G.run_media(st, api, str(FOLDER))                         # 연락처 사진 올림은 2단계(261120-71)
    pf2 = P.photo_front(P.card_by_id(st, c2), str(FOLDER))
    chk("g1" in SV["photos"] and len(P.person_photos(pf2)) == 1, "F 인물 사진 ↔ 연락처 사진 주고받음")
    img_dir = FOLDER / "정리"
    img_dir.mkdir()
    front = img_dir / "가짜오_가짜상사.jpg"
    Image.new("RGB", (300, 180), "white").save(front)
    c5 = st.upsert({"front": str(front), "name": "가짜오", "company": "가짜상사", "emails": ["five@example.com"]})
    people = api.list_people()
    G.apply(st, api, [r for r in G.plan(st, people, str(FOLDER)) if r["kind"] == G.NEW_GOOGLE], str(FOLDER), people=people)
    people = api.list_people()
    rows5 = G.plan(st, people, str(FOLDER), drive=True)
    chk({r["kind"] for r in rows5} == {G.DRIVE_UP} and "front" in [r.get("side") for r in rows5],   # 인물 사진도 함께(261120-70)
        "F 드라이브를 켜면 명함 그림(·인물 사진) 올림 갈래", str([(r["kind"], r.get("side")) for r in rows5]))
    G.apply(st, api, rows5, str(FOLDER), drive_folder="가짜 폴더", people=people)
    G.run_media(st, api, str(FOLDER), drive_folder="가짜 폴더")   # 드라이브는 2단계(261120-71)
    rn5 = G.links(st)[c5]["rn"]
    urls = [u["value"] for u in SV["people"][rn5].get("urls") or []]
    chk("가짜 폴더" in SV["folders"] and SV["files"] and any("drive.google.com/file/d/" in u for u in urls)
        and any("drive.google.com" in u for u in P.card_by_id(st, c5)["urls"]),
        "F 드라이브 폴더에 올리고 명함·구글 연락처 누리집에 링크", str(urls))
    chk(not G.plan(st, api.list_people(), str(FOLDER), drive=True), "F 같은 그림은 다시 올리지 않음")

    # ── G ──
    print("=== G. 429·연결 끊기 ===")
    SV["fail429"] = 2
    chk(len(api.list_people()) == len(SV["people"]), "G 429 는 기다렸다 다시")

    # ── K ── 카톡 친구추가 방지(이름 앞 '#', §5.29)
    print("=== K. 카톡 친구추가 방지 ===")
    rn1 = G.links(st)[c1]["rn"]
    old1 = SV["people"][rn1]["names"][0]["unstructuredName"]
    c6 = P._insert_contact(st, {"name": "새가짜", "emails": ["six@example.com"]}, ["명함"])
    st.con.commit()
    SV["people"]["people/k2"] = person("people/k2", "#구글샵", emails=["shop@example.com"])
    people = api.list_people()
    rows6 = G.plan(st, people, str(FOLDER))
    r6 = [r for r in rows6 if r["card_id"] == c6]
    chk(r6 and r6[0]["kind"] == G.NEW_GOOGLE and r6[0]["kakao"] is True, "K 새로 보내는 명함은 기본 친구추가 방지", str(r6))
    G.apply(st, api, rows6, str(FOLDER), people=people)
    rn6 = G.links(st)[c6]["rn"]
    kshop = [c for c in G.all_cards(st) if c["name"] == "구글샵"]
    chk(SV["people"][rn6]["names"][0]["unstructuredName"] == "#새가짜" and P.card_by_id(st, c6)["name"] == "새가짜"
        and c6 in G.blocked_ids(st), "K 구글 이름 앞 '#', 명함 이름은 그대로·표시 켜짐", SV["people"][rn6]["names"][0]["unstructuredName"])
    chk(kshop and kshop[0]["id"] in G.blocked_ids(st), "K 구글에서 '#' 이름을 받아 오면 '#' 떼고 표시 켜짐")
    chk(SV["people"][rn1]["names"][0]["unstructuredName"] == old1 and c1 not in G.blocked_ids(st),
        "K 이미 구글에 있는 연락처('#' 없음)는 그대로")
    chk(not G.plan(st, api.list_people(), str(FOLDER)), "K 다시 계획하면 바꿀 것 없음('#' 는 이름 차이로 보지 않음)")
    G.kakao_set(st, [c6], False)
    G.kakao_set(st, [c1], True)
    people = api.list_people()
    rows7 = G.plan(st, people, str(FOLDER))
    chk(sorted((r["kind"], r["card_id"], r["kakao"]) for r in rows7) == sorted([(G.KAKAO_UP, c6, False), (G.KAKAO_UP, c1, True)]),
        "K 해제·설정은 다음 싱크에 '구글로' 갈래", str([(r["kind"], r["card_id"]) for r in rows7]))
    G.apply(st, api, rows7, str(FOLDER), people=people)
    chk(SV["people"][rn6]["names"][0]["unstructuredName"] == "새가짜" and SV["people"][rn1]["names"][0]["unstructuredName"] == "#" + old1,
        "K [반영] 하면 구글 이름 앞 '#' 를 떼고 붙임")
    SV["people"][rn6]["names"] = [{"unstructuredName": "#새가짜"}]          # 휴대폰에서 직접 '#' 를 붙임(나중)
    SV["people"][rn6]["metadata"] = {"sources": [{"type": "CONTACT", "updateTime": NOW()}]}
    time.sleep(0.01)
    rows8 = G.plan(st, api.list_people(), str(FOLDER))
    chk([(r["kind"], r["kakao"]) for r in rows8] == [(G.KAKAO_DOWN, True)], "K 구글에서 직접 바꾼 '#' 는 표시로 받음", str(rows8))
    G.apply(st, api, rows8, str(FOLDER))
    chk(c6 in G.blocked_ids(st) and not G.plan(st, api.list_people(), str(FOLDER)), "K 받은 뒤 바꿀 것 없음")
finally:
    st.close()

# ── H ── 화면
print("=== H. 화면 ===")
from viewer.widgets.bizcard_settings_dialog import BizcardSettingsDialog
from viewer.widgets.bizcard_gsync_dialog import GSyncDialog
A.disconnect()
SV["revoked"].clear()
st2 = S.BizcardStore(DB, ui=True)
sd = BizcardSettingsDialog(None, host=None, store=st2)
sd.show()
pump(timeout=0.3)
chk(sd.lbl_gsync.text() and not sd.btn_gdisconnect.isEnabled(), "H 연결 끊긴 뒤 묶음은 '연결 안 됨'", sd.lbl_gsync.text())
sd.ed_gcid.setText("fake-client-id")
sd.ed_gsec.setText("fake-secret")
QTest.mouseClick(sd.btn_gconnect, Qt.MouseButton.LeftButton)
chk(pump(lambda: sd._gworker is None and A.connected(), timeout=20), "H [구글 계정 연결]을 누르면 배경에서 로그인")
chk("fake.user@example.com" in sd.lbl_gsync.text() and sd.btn_gdisconnect.isEnabled(), "H 연결한 계정 메일이 보임", sd.lbl_gsync.text())
SV["people"]["people/h1"] = person("people/h1", "새구글", emails=["new@example.com"])
gaps, last = [], [time.monotonic()]
hb = QTimer()
hb.timeout.connect(lambda: (gaps.append(time.monotonic() - last[0]), last.__setitem__(0, time.monotonic())))
hb.start(20)
gd = GSyncDialog(None, db=DB, folder=str(FOLDER))
gd.show()
chk(pump(lambda: not gd.busy and gd.tree.topLevelItemCount() > 0, timeout=20), "H 미리보기 창이 계획을 보임")
hb.stop()
chk(max(gaps or [0]) < 1.0, "H 받는 동안 메인 정지 < 1초", "%.2f" % max(gaps or [0]))
n_before = st2.con.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
QTest.mouseClick(gd.btn_apply, Qt.MouseButton.LeftButton)
chk(pump(lambda: gd.result is not None, timeout=20), "H [반영]")
n_after = st2.con.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
chk(n_after == n_before + 1, "H [반영] 뒤 새 명함", "%d → %d" % (n_before, n_after))
chk(sd.chk_gkakao.isChecked(), "H 명함 환경설정 '새로 보낼 때 카톡 친구추가 방지' 는 처음 켜짐")
# 명함찾기 — 구분 콤보 '카톡 친구추가 방지' 와 목록 오른쪽 메뉴
from viewer.widgets.bizcard_find_dialog import BizcardFindDialog
from PyQt6.QtWidgets import QMenu
fd = BizcardFindDialog(None)
fd.show()
pump(timeout=0.5)
ki = fd.cb_kind.findData("kakao")
fd.cb_kind.setCurrentIndex(ki)
pump(timeout=0.5)
ids = {fd.card_at(r)["id"] if hasattr(fd, "card_at") else fd._rows[r]["id"] for r in range(len(fd._rows))}
chk(ki >= 0 and ids and ids == G.blocked_ids(st2) & ids and ids == G.blocked_ids(st2),
    "H 구분 콤보 '카톡 친구추가 방지' 는 표시가 켜진 명함만", str((ki, len(ids), len(G.blocked_ids(st2)))))
_oexec = QMenu.exec
QMenu.exec = lambda self, *a, **k: None
fd.table.selectRow(0)
pump(timeout=0.2)
sel = fd.selected_cards() or []
first = sel[0]["id"] if sel else None
fd._table_menu(fd.table.visualRect(fd.table.model().index(0, 1)).center())
QMenu.exec = _oexec
acts = {a.text(): a for a in fd._table_menu_obj.actions()} if getattr(fd, "_table_menu_obj", None) else {}
if "카톡 친구추가 방지 해제" in acts:
    acts["카톡 친구추가 방지 해제"].trigger()
pump(timeout=0.5)
chk("카톡 친구추가 방지" in acts and first is not None and first not in G.blocked_ids(st2)
    and all(c["id"] != first for c in fd._rows), "H 목록 오른쪽 메뉴 '카톡 친구추가 방지 해제' → 표시 꺼지고 거른 목록에서 빠짐", str(list(acts)))
fd.close()
QTest.mouseClick(sd.btn_gdisconnect, Qt.MouseButton.LeftButton)
chk(SV["revoked"] == ["RT_SECRET_1"] and not A.token_path().exists() and not A.connected() and not G.links(st2),
    "H [연결 끊기]는 구글에 철회 요청·토큰 파일·짝 기록 지움", str(SV["revoked"]))
sd.close()
st2.close()
srv.shutdown()
shutil.rmtree(TMP, ignore_errors=True)

print()
print("ALL PASS" if not fails else "FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
