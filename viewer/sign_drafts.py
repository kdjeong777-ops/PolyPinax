# -*- coding: utf-8 -*-
"""서명 자리(초안) 기록 — `signing\\drafts.json` (보안 SOT §3.10 '기록').

파일 경로(정규화)마다 둘 중 하나:
- `{"drafts": [...], "out": "<결과 파일>"}` — 아직 확정 안 한 자리. `out` 은 서명 편집에서 왔을 때만(확정 결과를 그 파일로).
- `{"signed": {"src", "base_len", "base_sha", "drafts"}}` — 확정해 만든 서명 파일. 서명 편집이 바탕·자리를 되살릴 때 쓴다.

`drafts[]` = `{"id", "page", "rect": [x0, y0, x1, y1], "kind": "sign"|"image", "image": "<옛 서명 그림 이름>", "field": "<빈 칸 이름>",
"fp": "<그림만 자리의 디지털 ID — 그 ID 의 서명 그림, 261031-1>"}` —
`rect` 는 **그림 상자**, 보이는 쪽 좌표(fitz `page.rect`, `/Rotate` 적용 뒤). 쓰기는 배경 쓰기 줄(`bg_write` — 원자적, 261115-19),
깨진 파일은 옆에 보관(sign_store 와 같은 규칙).
"""
from __future__ import annotations

import json
import os
import threading
import uuid

from viewer import bg_write
from viewer.i18n import tr

FILE = "drafts.json"
KINDS = ("sign", "image")
# 261115-19(응답성 SOT §4.8): 쓰기는 배경 쓰기 줄(bg_write) — 끌기·크기·놓기마다 메인 os.replace 를 하지 않는다.
#   읽고-고치고-쓰기는 이 자물쇠로 차례대로(secure_store 와 같은 방식, 261114-17)
_LOCK = threading.RLock()


_PATH_MEMO: dict = {}
_LOAD_MEMO: dict = {}


def _path() -> str:
    """261115-12(응답성 SOT §4.7 ⑤): 본문을 그릴 때마다(`sign_draft_layer.reposition`) 불린다 — 폴더 만들기(`mkdir`)를
    설정 폴더마다 한 번만. 시험이 설정 폴더를 바꾸면(테스트 모드·덮어쓰기) 그 폴더로 다시 만든다."""
    try:
        from PyQt6.QtCore import QStandardPaths
        from viewer import settings_store
        k = (str(getattr(settings_store, "_DIR_OVERRIDE", None)),
             QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
    except Exception:
        k = None
    p = _PATH_MEMO.get(k) if k is not None else None
    if p is None or not os.path.isdir(os.path.dirname(p)):
        from viewer import sign_store
        p = str(sign_store.root() / FILE)
        if k is not None:
            _PATH_MEMO[k] = p
    return p


def key(path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _load() -> dict:
    """261115-12: 파일이 그대로면(경로·수정 시각·크기) 읽어 둔 것을 **사본으로** — 그릴 때마다 열어 읽지 않는다.
    261115-19: 배경 줄에 아직 쓰지 않은 글이 있으면 그것(같은 프로세스 안에서 순서가 어긋나지 않게)."""
    p = _path()
    pend = bg_write.pending_text(p)
    if pend is not None:
        try:
            raw = json.loads(pend)
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}
    try:
        st = os.stat(p)
        sig = (p, st.st_mtime_ns, st.st_size)
    except OSError:
        _LOAD_MEMO.clear()
        return {}
    if _LOAD_MEMO.get("sig") == sig:
        return json.loads(_LOAD_MEMO["raw"])
    try:
        with open(p, encoding="utf-8") as f:
            text = f.read()
        raw = json.loads(text)
        raw = raw if isinstance(raw, dict) else {}
        _LOAD_MEMO.update(sig=sig, raw=json.dumps(raw, ensure_ascii=False))
        return raw
    except FileNotFoundError:
        return {}
    except OSError:
        return {}
    except Exception:
        try:
            os.replace(p, p[:-5] + ".broken.json")
        except Exception:
            pass
        return {}


def _save(data: dict) -> None:
    # 261115-19: 직렬화만 여기(부르는 스레드) — 원자적 쓰기(tmp + os.replace)는 배경 줄이 한다
    bg_write.submit(_path(), json.dumps(data, ensure_ascii=False, indent=1))
    _LOAD_MEMO.clear()


def new_id() -> str:
    return uuid.uuid4().hex[:10]


def _clean(d: dict) -> dict:
    r = [float(v) for v in (d.get("rect") or (0, 0, 0, 0))][:4]
    return {"id": str(d.get("id") or new_id()), "page": int(d.get("page", 0)), "rect": r,
            "kind": d.get("kind") if d.get("kind") in KINDS else "sign",
            "image": str(d.get("image") or ""), "field": str(d.get("field") or ""),
            "fp": str(d.get("fp") or ""),                 # 261031-1: 그림만 자리의 디지털 ID(그 ID 의 서명 그림)
            "auto": bool(d.get("auto"))}                  # 261031-6: 클릭으로 놓아 실제 크기를 따르는 자리


# ---- 아직 확정 안 한 자리 ----------------------------------------------------------

def drafts(path) -> list:
    e = _load().get(key(path)) or {}
    return [_clean(d) for d in (e.get("drafts") or []) if isinstance(d, dict)]


def out_of(path) -> str:
    """서명 편집에서 온 자리면 그 결과 파일(확정하면 그 파일을 바꾼다), 아니면 ''."""
    return str((_load().get(key(path)) or {}).get("out") or "")


def set_drafts(path, items, out: str | None = None) -> None:
    k = key(path)
    items = [_clean(d) for d in items]
    with _LOCK:
        data = _load()
        e = dict(data.get(k) or {})
        if out is not None:
            e["out"] = str(out or "")
        if items:
            e["drafts"] = items
        else:
            e.pop("drafts", None)
            e.pop("out", None)
        if e:
            data[k] = e
        else:
            data.pop(k, None)
        _save(data)


def clear(path) -> None:
    set_drafts(path, [])


# ---- 확정한 서명 파일 -----------------------------------------------------------

def set_signed(out, src, base_len: int, base_sha: str, items) -> None:
    k = key(out)
    with _LOCK:
        data = _load()
        e = dict(data.get(k) or {})
        e["signed"] = {"src": str(src), "base_len": int(base_len), "base_sha": str(base_sha),
                       "drafts": [_clean(d) for d in items]}
        data[k] = e
        _save(data)


def signed(path) -> dict | None:
    s = (_load().get(key(path)) or {}).get("signed")
    if not isinstance(s, dict):
        return None
    try:
        return {"src": str(s.get("src") or ""), "base_len": int(s.get("base_len") or 0),
                "base_sha": str(s.get("base_sha") or ""),
                "drafts": [_clean(d) for d in (s.get("drafts") or []) if isinstance(d, dict)]}
    except Exception:
        return None


# ---- 이름 바꾸기·옮기기(마스터 §4.7.14 filesRelocated) ------------------------------

def relocate(pairs) -> None:
    """[(옛 경로, 새 경로), …] — 항목 키와 그 안의 경로(`out`·`src`)를 따라 바꾼다."""
    pairs = [(key(a), str(b)) for a, b in pairs]
    if not pairs:
        return
    m = {a: b for a, b in pairs}
    with _LOCK:
        data = _load()
        changed = False
        for a, b in pairs:
            if a in data:
                data[key(b)] = data.pop(a)
                changed = True
        for e in data.values():
            if not isinstance(e, dict):
                continue
            if e.get("out") and key(e["out"]) in m:
                e["out"] = m[key(e["out"])]
                changed = True
            s = e.get("signed")
            if isinstance(s, dict) and s.get("src") and key(s["src"]) in m:
                s["src"] = m[key(s["src"])]
                changed = True
        if changed:
            _save(data)


def default_out(path) -> str:
    """결과 파일 이름 — 같은 폴더 `<이름>_서명.pdf`(SOT §3.4). 다국어 기본 파일 이름 규칙(다국어 SOT)대로 `tr`."""
    from pathlib import Path
    p = Path(str(path))
    return str(p.with_name(tr("{stem}_서명.pdf").format(stem=p.stem)))
