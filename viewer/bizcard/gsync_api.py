# -*- coding: utf-8 -*-
"""구글 People API·Drive API REST (명함 SOT §5.29) — 표준 urllib 만, 배경에서 부른다.

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
PERSON_FIELDS = "names,organizations,phoneNumbers,emailAddresses,addresses,urls,biographies,photos,metadata"
UPDATE_FIELDS = "names,organizations,phoneNumbers,emailAddresses,addresses,urls,biographies"
FOLDER_MIME = "application/vnd.google-apps.folder"


class ApiError(Exception):
    def __init__(self, what: str, status: int = 0):
        super().__init__(what)
        self.status = status


class Api:
    """token() = 접근 토큰을 주는 함수(gsync_auth.access_token). sleep 은 검사가 바꿔 끼운다."""

    def __init__(self, token, sleep=time.sleep):
        self._token, self._sleep = token, sleep

    # ── HTTP ──
    def _req(self, method: str, url: str, body=None, raw: bytes = None, ctype: str = "application/json") -> bytes:
        data = raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else None)
        for i in range(len(RETRY_WAITS) + 1):
            req = urllib.request.Request(url, data=data, method=method)
            req.add_header("Authorization", "Bearer " + self._token())
            if data is not None:
                req.add_header("Content-Type", ctype)
            try:
                with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
                    return r.read()
            except urllib.error.HTTPError as e:
                if (e.code == 429 or e.code >= 500) and i < len(RETRY_WAITS):
                    self._sleep(RETRY_WAITS[i])
                    continue
                raise ApiError("http %d" % e.code, e.code)
            except Exception as e:
                if i < len(RETRY_WAITS):
                    self._sleep(RETRY_WAITS[i])
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

    def update(self, resource: str, person: dict) -> dict:
        q = urllib.parse.urlencode({"updatePersonFields": UPDATE_FIELDS, "personFields": PERSON_FIELDS})
        return self._json("PATCH", PEOPLE_BASE + "/v1/%s:updateContact?%s" % (resource, q), person)

    def delete(self, resource: str) -> None:
        self._req("DELETE", PEOPLE_BASE + "/v1/%s:deleteContact" % resource)

    def update_photo(self, resource: str, jpeg: bytes) -> dict:
        return self._json("PATCH", PEOPLE_BASE + "/v1/%s:updateContactPhoto" % resource,
                          {"photoBytes": base64.b64encode(jpeg).decode("ascii"), "personFields": "photos,metadata"})

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
