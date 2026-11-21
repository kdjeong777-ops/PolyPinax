# -*- coding: utf-8 -*-
"""구글 주소록 싱크 — OAuth 2.0 설치 앱 루프백 + PKCE, 토큰 보관 (명함 SOT §5.29 '연결'·'토큰', §2.1 의 7).

앱은 구글 비밀번호를 보지 않는다: 기본 브라우저로 구글 로그인 화면을 열고, 구글이 `127.0.0.1:<빈 포트>` 로 넘긴 인가 코드를
토큰으로 바꾼다. 갱신 토큰만 DPAPI(`secure_store.protect_text`)로 잠가 설정 폴더에 — DPAPI 를 못 쓰면 저장하지 않는다(평문 금지).
네트워크는 모두 배경 일꾼에서 부른다(응답성 SOT §4). 오류 글에 토큰·명함 값을 싣지 않는다(§2.1 의 3).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

# 서버 주소 — 검사는 이 PC 안의 가짜 서버로 바꿔 끼운다(§5.29 '서버 주소')
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

SCOPE_CONTACTS = "https://www.googleapis.com/auth/contacts"
SCOPE_DRIVE = "https://www.googleapis.com/auth/drive.file"      # 이 앱이 만든 파일만(비민감 범위)
SCOPE_ID = ("openid", "email")                                  # 연결한 계정 메일을 보이려고만
BUILT_CLIENT_ID = ""            # 검증받은 ID 를 빌드에 넣는 자리(§5.29 '클라이언트 ID' — 지금은 비어 있음)
BUILT_CLIENT_SECRET = ""
LOGIN_TIMEOUT = 300             # 로그인을 이 초 안에 마치지 않으면 그만둔다
HTTP_TIMEOUT = 30
TOKEN_FILE = "bizcard_google.json"

META_ID, META_SECRET = "gsync_client_id", "gsync_client_secret"   # 명함 DB meta — 비밀은 DPAPI 로 잠가


class AuthError(Exception):
    """연결 실패 — 글은 갈래만(값·토큰 없음)."""


def _dir():
    from viewer import settings_store
    return settings_store.settings_dir()


def token_path():
    return _dir() / TOKEN_FILE


# ── 클라이언트 ID ──
def client(store=None) -> tuple:
    """(id, secret) — 명함 환경설정 칸(명함 DB meta)이 먼저, 비면 빌드에 넣은 값."""
    cid = sec = ""
    if store is not None:
        cid = str(store.meta_get(META_ID, "") or "").strip()
        sec = str(store.meta_get(META_SECRET, "") or "")
        if sec:
            from viewer import secure_store
            sec = secure_store.unprotect_text(sec)
            if sec.startswith(secure_store.DPAPI_PREFIX):
                sec = ""                               # 다른 PC·계정에서 온 잠긴 값 — 다시 넣어야 함
    return (cid or BUILT_CLIENT_ID), (sec if cid else BUILT_CLIENT_SECRET)


def set_client(store, cid: str, secret: str) -> bool:
    """칸 값을 명함 DB meta 에 — 비밀은 DPAPI 로 잠가, 잠글 수 없으면 비밀은 저장하지 않는다(False)."""
    from viewer import secure_store
    store.meta_set(META_ID, (cid or "").strip())
    if not secret:
        store.meta_set(META_SECRET, "")
        return True
    locked = secure_store.protect_text(secret)
    if not str(locked).startswith(secure_store.DPAPI_PREFIX):
        store.meta_set(META_SECRET, "")
        return False
    store.meta_set(META_SECRET, locked)
    return True


# ── 토큰 파일 ──
def load_state() -> dict:
    """{'refresh': 잠긴 값, 'email': 연결한 계정 메일, 'scopes': [...]} — 없으면 {}."""
    try:
        return json.loads(token_path().read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def connected() -> bool:
    return bool(load_state().get("refresh"))


def account_email() -> str:
    return str(load_state().get("email") or "")


def _save_state(refresh: str, email: str, scopes) -> bool:
    from viewer import secure_store
    locked = secure_store.protect_text(refresh)
    if not str(locked).startswith(secure_store.DPAPI_PREFIX):
        return False                                    # 평문 저장 금지 — 이번 실행 동안만 메모리에
    p = token_path()
    tmp = p.with_name(p.name + ".part")
    tmp.write_text(json.dumps({"refresh": locked, "email": email or "", "scopes": list(scopes or [])}), encoding="utf-8")
    os.replace(str(tmp), str(p))
    return True


def _refresh_token() -> str:
    st = load_state()
    v = st.get("refresh") or ""
    if not v:
        return _MEM.get("refresh", "")
    from viewer import secure_store
    t = secure_store.unprotect_text(v)
    return "" if t.startswith(secure_store.DPAPI_PREFIX) else t


_MEM = {}                       # DPAPI 를 못 쓸 때의 갱신 토큰·접근 토큰(이 실행만)
_LOCK = threading.Lock()


# ── HTTP ──
def _post(url: str, data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode("ascii")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        raise AuthError("http %d" % e.code)
    except Exception as e:
        raise AuthError(type(e).__name__)


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _jwt_email(id_token: str) -> str:
    """id_token 의 메일(표시용만 — 서명 확인은 하지 않는다, 구글 토큰 응답에서 바로 받은 것)."""
    try:
        part = id_token.split(".")[1]
        part += "=" * (-len(part) % 4)
        return str(json.loads(base64.urlsafe_b64decode(part)).get("email") or "")
    except Exception:
        return ""


def scopes(drive: bool = False) -> list:
    return [SCOPE_CONTACTS] + ([SCOPE_DRIVE] if drive else []) + list(SCOPE_ID)


def login(cid: str, secret: str, drive: bool = False, open_url=None, timeout: float = LOGIN_TIMEOUT,
          cancel=None) -> str:
    """루프백 로그인 — 브라우저를 열고 인가 코드를 받아 토큰으로 바꿔 보관. 반환 = 연결한 계정 메일. 배경에서 부른다.
    open_url = 브라우저 열기(기본 webbrowser.open — 검사는 바꿔 끼운다). cancel() 이 True 면 그만둔다."""
    from http.server import BaseHTTPRequestHandler, HTTPServer
    if not cid:
        raise AuthError("no client id")
    verifier = _b64(secrets.token_bytes(48))
    challenge = _b64(hashlib.sha256(verifier.encode("ascii")).digest())
    state = secrets.token_urlsafe(16)
    got = {}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] == state and ("code" in q or "error" in q):
                got["code"] = q.get("code", [""])[0]
                got["error"] = q.get("error", [""])[0]
                from viewer.i18n import tr
                msg = tr("로그인이 끝났습니다 — 이 창을 닫고 PolyCardex 로 돌아가세요.")
            else:
                msg = "..."
            b = ("<html><meta charset='utf-8'><body style='font-family:sans-serif'>%s</body></html>" % msg).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def log_message(self, *a):            # 콘솔·로그에 주소(코드)를 남기지 않는다
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    srv.timeout = 0.5
    redirect = "http://127.0.0.1:%d" % srv.server_address[1]
    sc = scopes(drive)
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": redirect, "response_type": "code", "scope": " ".join(sc),
        "code_challenge": challenge, "code_challenge_method": "S256", "state": state,
        "access_type": "offline", "prompt": "consent"})
    if open_url is None:
        import webbrowser
        open_url = webbrowser.open
    try:
        open_url(url)
        t0 = time.monotonic()
        while "code" not in got and time.monotonic() - t0 < timeout:
            if cancel is not None and cancel():
                raise AuthError("cancelled")
            srv.handle_request()
    finally:
        srv.server_close()
    if not got.get("code"):
        raise AuthError(got.get("error") or "timeout")
    tok = _post(TOKEN_URL, {"code": got["code"], "client_id": cid, "client_secret": secret or "",
                            "redirect_uri": redirect, "grant_type": "authorization_code", "code_verifier": verifier})
    refresh = tok.get("refresh_token") or ""
    if not refresh:
        raise AuthError("no refresh token")
    email = _jwt_email(tok.get("id_token") or "")
    with _LOCK:
        _MEM["access"] = (tok.get("access_token") or "", time.time() + float(tok.get("expires_in") or 0) - 60)
        if not _save_state(refresh, email, sc):
            _MEM["refresh"] = refresh
    return email


def access_token(cid: str, secret: str) -> str:
    """접근 토큰 — 메모리에 살아 있으면 그것, 아니면 갱신 토큰으로 새로(배경에서)."""
    with _LOCK:
        a = _MEM.get("access")
        if a and a[0] and a[1] > time.time():
            return a[0]
    rt = _refresh_token()
    if not rt:
        raise AuthError("not connected")
    tok = _post(TOKEN_URL, {"refresh_token": rt, "client_id": cid, "client_secret": secret or "",
                            "grant_type": "refresh_token"})
    at = tok.get("access_token") or ""
    if not at:
        raise AuthError("no access token")
    with _LOCK:
        _MEM["access"] = (at, time.time() + float(tok.get("expires_in") or 0) - 60)
    return at


def granted_drive() -> bool:
    return SCOPE_DRIVE in (load_state().get("scopes") or [])


def disconnect() -> bool:
    """[연결 끊기] — 구글에 철회 요청(실패해도) + 토큰 파일·메모리 지움. 반환 = 철회 요청이 받아들여졌는지."""
    rt = _refresh_token()
    ok = False
    if rt:
        try:
            _post(REVOKE_URL, {"token": rt})
            ok = True
        except AuthError:
            ok = False
    with _LOCK:
        _MEM.clear()
    try:
        token_path().unlink()
    except OSError:
        pass
    return ok
