# -*- coding: utf-8 -*-
"""구글 People API·Drive API REST (구글 싱크 SOT §5.29) — 표준 urllib 만, 배경에서 부른다.

요청마다 시간 상한 `HTTP_TIMEOUT`, 429·5xx 는 `RETRY_WAITS` 만큼 기다려 다시. 오류 글은 HTTP 상태·갈래만(명함 값·토큰 없음, §2.1 의 3).
"""
from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request

PEOPLE_BASE = "https://people.googleapis.com"
DRIVE_BASE = "https://www.googleapis.com"
HTTP_TIMEOUT = 30
RETRY_WAITS = (1, 2, 4)
RATE_WAITS = (5, 10, 20, 40, 60)                 # 요청 한도(429) — Retry-After 가 없을 때 쉬는 초(끝 값을 되풀이, 261120-71)
RATE_TRIES = 12                                  # 429 를 이만큼 연달아 받으면 그때 실패(약 10분 — 배경 일꾼 안에서만 기다린다)
# 추가 칸(구글 싱크 SOT §5.29 '오가는 칸', 261122-25) — 생일·별명·기념일·관계·메신저·직업·사용자 칸(둘째부터 주소는 addresses 에)
EXTRA_FIELDS = "birthdays,nicknames,events,relations,imClients,occupations,userDefined"
PERSON_FIELDS = "names,organizations,phoneNumbers,emailAddresses,addresses,urls,biographies,photos,memberships,metadata," + EXTRA_FIELDS
UPDATE_BASE = "names,organizations,phoneNumbers,emailAddresses,addresses,urls,biographies"   # 추가 칸을 받은 적 없는 명함(§5.29 '추가 칸 처음')
UPDATE_FIELDS = UPDATE_BASE + "," + EXTRA_FIELDS
FOLDER_MIME = "application/vnd.google-apps.folder"


class ApiError(Exception):
    """status = HTTP 상태(네트워크면 0), reason = 구글 오류 `reason` 한 낱말(예: storageQuotaExceeded) — 값·토큰은 싣지 않는다."""

    def __init__(self, what: str, status: int = 0, reason: str = ""):
        super().__init__(what)
        self.status = status
        self.reason = reason


def _reason(e) -> str:
    """HTTPError 본문에서 구글 오류 reason 한 낱말만(구글 싱크 SOT §5.29 '못 올렸을 때', 261120-70)."""
    try:
        d = json.loads(e.read().decode("utf-8", "replace") or "{}").get("error") or {}
        errs = d.get("errors") or []
        return str((errs[0].get("reason") if errs else "") or d.get("status") or "")[:40]
    except Exception:
        return ""


class Api:
    """token() = 접근 토큰을 주는 함수(gsync_auth.access_token). sleep 은 검사가 바꿔 끼운다."""

    def __init__(self, token, sleep=time.sleep):
        self._token, self._sleep = token, sleep

    # ── HTTP ──
    def _req(self, method: str, url: str, body=None, raw: bytes = None, ctype: str = "application/json") -> bytes:
        data = raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else None)
        n429 = 0
        i = 0
        while i <= len(RETRY_WAITS):
            req = urllib.request.Request(url, data=data, method=method)
            req.add_header("Authorization", "Bearer " + self._token())
            if data is not None:
                req.add_header("Content-Type", ctype)
            try:
                with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
                    return r.read()
            except urllib.error.HTTPError as e:
                if e.code == 429 and n429 < RATE_TRIES:     # 한도 — 실패로 끝내지 않고 쉬었다 이어 감(구글 싱크 SOT §5.29 '네트워크', 261120-71)
                    try:
                        wait = float((e.headers or {}).get("Retry-After") or 0)
                    except (TypeError, ValueError):
                        wait = 0
                    self._sleep(wait or RATE_WAITS[min(n429, len(RATE_WAITS) - 1)])
                    n429 += 1
                    continue
                if e.code >= 500 and i < len(RETRY_WAITS):
                    self._sleep(RETRY_WAITS[i])
                    i += 1
                    continue
                raise ApiError("http %d" % e.code, e.code, _reason(e))
            except Exception as e:
                if i < len(RETRY_WAITS):
                    self._sleep(RETRY_WAITS[i])
                    i += 1
                    continue
                raise ApiError(type(e).__name__)
        raise ApiError("retry")

    def _json(self, method, url, body=None):
        b = self._req(method, url, body)
        return json.loads(b.decode("utf-8") or "{}") if b else {}

    # ── People ──
    def list_people(self) -> list:
        """내 주소록 연락처 전부(쪽마다 1000)."""
        out, tok = [], ""
        while True:
            q = {"personFields": PERSON_FIELDS, "pageSize": 1000}
            if tok:
                q["pageToken"] = tok
            d = self._json("GET", PEOPLE_BASE + "/v1/people/me/connections?" + urllib.parse.urlencode(q))
            out += d.get("connections") or []
            tok = d.get("nextPageToken") or ""
            if not tok:
                return out

    def create(self, person: dict) -> dict:
        return self._json("POST", PEOPLE_BASE + "/v1/people:createContact?personFields=" + PERSON_FIELDS, person)

    def batch_create(self, persons: list) -> list:
        """새 연락처 여럿을 한 요청으로(최대 200 — `gsync.BATCH`, 261120-71). 반환 = 만든 사람들(보낸 차례)."""
        body = {"contacts": [{"contactPerson": p} for p in persons], "readMask": PERSON_FIELDS}
        d = self._json("POST", PEOPLE_BASE + "/v1/people:batchCreateContacts", body)
        return [x.get("person") or {} for x in d.get("createdPeople") or []]

    def batch_update(self, persons: dict, fields: str = UPDATE_FIELDS) -> dict:
        """연락처 여럿 고치기 한 요청으로 {resourceName: 사람(etag 포함)} → {resourceName: 고친 사람}(최대 200, 261120-71).
        fields = 고칠 칸(추가 칸을 받은 적 없는 명함은 `UPDATE_BASE` — 구글 추가 칸을 지우지 않게, 261122-25)."""
        body = {"contacts": persons, "updateMask": fields, "readMask": PERSON_FIELDS}
        d = self._json("POST", PEOPLE_BASE + "/v1/people:batchUpdateContacts", body)
        return {rn: (x.get("person") or {}) for rn, x in (d.get("updateResult") or {}).items()}

    def update(self, resource: str, person: dict, fields: str = UPDATE_FIELDS) -> dict:
        q = urllib.parse.urlencode({"updatePersonFields": fields, "personFields": PERSON_FIELDS})
        return self._json("PATCH", PEOPLE_BASE + "/v1/%s:updateContact?%s" % (resource, q), person)

    def delete(self, resource: str) -> None:
        self._req("DELETE", PEOPLE_BASE + "/v1/%s:deleteContact" % resource)

    def update_photo(self, resource: str, jpeg: bytes) -> dict:
        return self._json("PATCH", PEOPLE_BASE + "/v1/%s:updateContactPhoto" % resource,
                          {"photoBytes": base64.b64encode(jpeg).decode("ascii"), "personFields": "photos,metadata"})

    # ── 라벨(contactGroups — 같은 contacts 권한, 구글 싱크 SOT §5.29 '라벨', 261120-61) ──
    def list_groups(self) -> list:
        """[{resourceName, name, groupType}] — 시스템 라벨(SYSTEM_CONTACT_GROUP)도 함께, 거르기는 부르는 쪽이."""
        out, tok = [], ""
        while True:
            q = {"pageSize": 1000, "groupFields": "name,groupType"}
            if tok:
                q["pageToken"] = tok
            d = self._json("GET", PEOPLE_BASE + "/v1/contactGroups?" + urllib.parse.urlencode(q))
            out += d.get("contactGroups") or []
            tok = d.get("nextPageToken") or ""
            if not tok:
                return out

    def create_group(self, name: str) -> dict:
        return self._json("POST", PEOPLE_BASE + "/v1/contactGroups", {"contactGroup": {"name": name}})

    def modify_members(self, group: str, add=(), remove=()) -> dict:
        body = {}
        if add:
            body["resourceNamesToAdd"] = list(add)
        if remove:
            body["resourceNamesToRemove"] = list(remove)
        return self._json("POST", PEOPLE_BASE + "/v1/%s/members:modify" % group, body)

    def delete_group(self, group: str) -> None:
        self._req("DELETE", PEOPLE_BASE + "/v1/%s?deleteContacts=false" % group)   # 라벨만 — 연락처는 그대로

    def delete_photo(self, resource: str) -> None:
        self._req("DELETE", PEOPLE_BASE + "/v1/%s:deleteContactPhoto" % resource)

    def get_bytes(self, url: str) -> bytes:
        return self._req("GET", url)

    # ── Drive (drive.file — 이 앱이 만든 파일만) ──
    def ensure_folder(self, name: str) -> str:
        q = "name = '%s' and mimeType = '%s' and trashed = false" % (name.replace("'", "\\'"), FOLDER_MIME)
        d = self._json("GET", DRIVE_BASE + "/drive/v3/files?" + urllib.parse.urlencode({"q": q, "fields": "files(id)"}))
        fs = d.get("files") or []
        if fs:
            return fs[0]["id"]
        return self._json("POST", DRIVE_BASE + "/drive/v3/files?fields=id", {"name": name, "mimeType": FOLDER_MIME})["id"]

    def list_folder(self, folder_id: str) -> list:
        """폴더 안 파일 [{id, name, md5Checksum}] — 지난번 올린 기록이 없는 파일을 다시 올리지 않게(구글 싱크 SOT §5.29 '드라이브', 261122-6)."""
        out, token = [], ""
        q = "'%s' in parents and trashed = false" % folder_id.replace("'", "\\'")
        while True:
            args = {"q": q, "fields": "nextPageToken, files(id, name, md5Checksum)", "pageSize": 1000}
            if token:
                args["pageToken"] = token
            d = self._json("GET", DRIVE_BASE + "/drive/v3/files?" + urllib.parse.urlencode(args))
            out += d.get("files") or []
            token = d.get("nextPageToken") or ""
            if not token:
                return out

    def upload(self, path: str, name: str, folder_id: str, file_id: str = "") -> str:
        """파일 올리기(있으면 내용만 바꿈) — 반환 = 파일 id."""
        with open(path, "rb") as f:
            content = f.read()
        bound = "polycardex_%d" % int(time.time() * 1000)
        meta = {"name": name} if file_id else {"name": name, "parents": [folder_id]}
        body = (("--%s\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n" % bound).encode("ascii")
                + json.dumps(meta, ensure_ascii=False).encode("utf-8")
                + ("\r\n--%s\r\nContent-Type: image/jpeg\r\n\r\n" % bound).encode("ascii") + content
                + ("\r\n--%s--" % bound).encode("ascii"))
        if file_id:
            url = DRIVE_BASE + "/upload/drive/v3/files/%s?uploadType=multipart&fields=id" % file_id
            method = "PATCH"
        else:
            url = DRIVE_BASE + "/upload/drive/v3/files?uploadType=multipart&fields=id"
            method = "POST"
        b = self._req(method, url, raw=body, ctype="multipart/related; boundary=" + bound)
        return json.loads(b.decode("utf-8"))["id"]


def drive_link(file_id: str) -> str:
    return "https://drive.google.com/file/d/%s/view" % file_id
