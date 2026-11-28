# -*- coding: utf-8 -*-
"""PDF 서식 체크박스 켜고 끄기 — 보류와 [저장] 때 쓰기 (편집 꾸밈 SOT §4.6.14 '서식 체크박스', 261128-13).

- 꾸미기 체크 도구로 PDF 의 **서식 체크박스·라디오 단추**(Acrobat 서식 필드)를 누르면 표시를 그리지 않고 그 필드의 값을 바꾼다
  (사용자 결정 '그 필드를 켜기' — 다른 뷰어·양식 제출에서도 체크로 보인다).
- 바꾼 값은 **보류**(`set_pending`)로 두었다가 그 파일의 다음 편집 모드 [저장] 이 PDF 를 만들 때 그 임시 파일에 `write_fields` 로 쓴다
  — 문서 정보 고침(`doc_meta`)과 같은 길(책갈피창·저장 SOT §4.7.5). 보류는 이번 실행 동안만(메모리).
- 화면에는 연 문서(메모리)에 `apply_pending` 으로 덧입혀 보인다(저장 전 크롭·회전과 같은 꼴, `pdf_doc`).
- 필드는 **(필드 이름, 켬 상태 이름)** 으로 가린다 — 저장 길은 PDF 를 다시 쓰므로(책갈피 쓰기·쪽 다시 만들기) xref·쪽 번호는 바뀐다.
  라디오 단추는 같은 이름에 켬 상태가 단추마다 달라 두 값으로 하나를 가린다.
- Qt 를 쓰지 않는다 — `write_fields` 는 배경 작업·검사에서 그대로 부른다.
"""
from __future__ import annotations

import threading

_PENDING: dict = {}               # norm_key(경로) → {"path": 경로, "fields": {(필드 이름, 켬 상태): bool}}
_VER: dict = {}                   # norm_key(경로) → 바뀐 횟수(화면 캐시 꼬리표)
_ORIG: dict = {}                  # norm_key(경로) → {열쇠: 파일의 원래 값} — 다시 누르면 보류를 지우려고
_LOCK = threading.Lock()


def _key(path) -> str:
    from viewer.pathutil import norm_key
    return norm_key(str(path))


# ── 보류 ────────────────────────────────────────────────────────────────
def set_pending(path, fkey, on: bool, original: bool | None = None) -> None:
    """한 필드(`toggle_at` 의 열쇠 — (이름, 켬 상태))를 보류에 넣는다. 파일의 원래 값(`original`, 주지 않으면 처음 바꿀 때의
    반대 값을 기억해 둔다)으로 돌아가면 그 보류를 지운다. 라디오 단추를 켜면 같은 이름의 다른 보류는 지운다."""
    k = _key(path)
    with _LOCK:
        ent = _PENDING.setdefault(k, {"path": str(path), "fields": {}})
        orig = _ORIG.setdefault(k, {})
        fk = (str(fkey[0]), str(fkey[1]))
        if original is None:
            original = orig.setdefault(fk, not bool(on))
        if on:
            for other in [o for o in ent["fields"] if o[0] == fk[0] and o != fk]:
                ent["fields"].pop(other, None)
        if bool(on) == bool(original):
            ent["fields"].pop(fk, None)
        else:
            ent["fields"][fk] = bool(on)
        if not ent["fields"]:
            _PENDING.pop(k, None)
        _VER[k] = _VER.get(k, 0) + 1


def pending(path) -> dict:
    """그 파일의 보류 {(이름, 켬 상태): 켬} (없으면 {})."""
    with _LOCK:
        ent = _PENDING.get(_key(path))
        return dict(ent["fields"]) if ent else {}


def has_pending(path=None) -> bool:
    with _LOCK:
        return bool(_PENDING.get(_key(path))) if path is not None else bool(_PENDING)


def pending_paths() -> list:
    with _LOCK:
        return [ent["path"] for ent in _PENDING.values()]


def version(path) -> int:
    with _LOCK:
        return _VER.get(_key(path), 0)


def clear_pending(path=None) -> None:
    """그 파일(없으면 모두)의 보류를 지운다 — 저장 성공·버림."""
    with _LOCK:
        keys = list(_PENDING) if path is None else [_key(path)]
        for k in keys:
            _ORIG.pop(k, None)
            if _PENDING.pop(k, None) is not None:
                _VER[k] = _VER.get(k, 0) + 1


def relocate(old, new) -> None:
    """이름 변경·이동 뒤 보류를 새 경로로(책갈피창·저장 SOT §4.7.14)."""
    with _LOCK:
        ent = _PENDING.pop(_key(old), None)
        if _key(old) in _ORIG:
            _ORIG[_key(new)] = _ORIG.pop(_key(old))
        if ent:
            ent["path"] = str(new)
            _PENDING[_key(new)] = ent
            _VER[_key(new)] = _VER.get(_key(new), 0) + 1


# ── 찾기·바꾸기 ─────────────────────────────────────────────────────────
def _is_toggle(w) -> bool:
    import fitz
    return w.field_type in (fitz.PDF_WIDGET_TYPE_CHECKBOX, fitz.PDF_WIDGET_TYPE_RADIOBUTTON)


def is_on(w) -> bool:
    """체크박스·라디오 위젯이 켜져 있는가."""
    v = w.field_value
    if isinstance(v, bool):
        return v
    s = str(v or "Off")
    return s != "Off" and (s == on_state(w) or s not in ("", "False", "false", "0"))


def on_state(w) -> str:
    """위젯의 켬 상태 이름(체크박스 'Yes'·'On', 라디오는 단추마다 다르다)."""
    try:
        states = w.button_states() or {}
        ons = [s for s in (states.get("normal") or states.get("down") or []) if s != "Off"]
        if ons:
            return str(ons[0])
    except Exception:
        pass
    try:
        return str(w.on_state())
    except Exception:
        return "Yes"


def field_key(w) -> tuple:
    return (str(w.field_name or ""), on_state(w))


def toggle_at(page, x: float, y: float):
    """쪽 좌표(pt — PDF 쪽 좌표, 회전 전) (x, y) 를 덮는 체크박스·라디오 위젯 → (열쇠, 지금 켬, 테두리 상자) 또는 None."""
    import fitz
    p = fitz.Point(x, y)
    for w in page.widgets() or []:
        try:
            if _is_toggle(w) and w.rect.contains(p):
                return field_key(w), is_on(w), tuple(w.rect)
        except Exception:
            continue
    return None


def _set(w, on: bool) -> None:
    w.field_value = on_state(w) if on else "Off"
    w.update()


def apply_fields(doc, fields: dict) -> int:
    """fitz 문서(메모리)에 {(이름, 켬 상태): 켬} 을 덧입힌다 — 바꾼 수. 라디오 단추를 켜면 같은 이름의 다른 단추는 끈다."""
    want = {(str(a), str(b)): bool(v) for (a, b), v in (fields or {}).items()}
    if not want:
        return 0
    radio_on = {a for (a, _b), v in want.items() if v}
    n = 0
    for pg in range(doc.page_count):
        for w in doc[pg].widgets() or []:
            if not _is_toggle(w):
                continue
            try:
                fk = field_key(w)
                if fk in want:
                    goal = want[fk]
                elif fk[0] in radio_on and w.field_type != 2:      # 2 = 체크박스 — 라디오만 무리 끄기
                    goal = False
                else:
                    continue
                if is_on(w) != goal:
                    _set(w, goal)
                    n += 1
            except Exception:
                continue
    return n


def apply_pending(doc, path) -> int:
    return apply_fields(doc, pending(path))


def write_fields(pdf_path, fields: dict, password: str | None = None, source=None) -> int:
    """`pdf_path`(저장 길의 **임시 파일**)의 서식 체크박스에 값을 쓴다 — 덧붙여 저장(암호화 그대로).
    암호 문서면 `password`, 없으면 `source`(원본 경로)로 이번 실행에서 연 암호. 반환 = 바꾼 필드 수. **배경 스레드에서만**."""
    import fitz
    if not fields:
        return 0
    doc = fitz.open(str(pdf_path))
    try:
        if doc.needs_pass:
            pw = password
            if pw is None:
                try:
                    from viewer import secure_store
                    pw = secure_store.get_session(str(source or pdf_path))
                except Exception:
                    pw = None
            if not (pw and doc.authenticate(pw)):
                raise RuntimeError("암호를 몰라 서식 체크박스를 쓰지 못했습니다")
        n = apply_fields(doc, fields)
        if n:
            doc.saveIncr()
        return n
    finally:
        doc.close()
