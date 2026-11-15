# -*- coding: utf-8 -*-
"""(보안 SOT §11 'DB') 서명 자리 기록(`signing\\drafts.json`)을 메인 스레드에서 쓰지 않는다 — 배경 쓰기 줄(`bg_write`)
(261115-19, 응답성 SOT §4.8·보안 SOT §3.10 '기록').

종전에는 `sign_drafts._save` 가 메인에서 tmp 쓰기 + `os.replace` 를 했다 — 자리 놓기·끌어 옮기기·크기·지우기·자리 옵션마다.
백신이 바꿔 끼운 파일을 붙들면 그동안 창이 선다(메인 `os.replace` 21.4초 이력, 2026-11-15 전체 SOT 점검에서 찾음).

M. 메인 스레드에서 `set_drafts`(놓기·옮기기·지우기)·`set_signed`·`relocate` 를 불러도 메인의 파일 쓰기(`open` 쓰기 모드·`os.replace`) 0번(수정 전 코드는 실패)
R. 쓰기가 끝나기 전에 다시 읽어도(`drafts`·`signed`·`out_of`) 마지막 값 · `flush` 뒤 디스크도 같은 값
C. 여러 스레드가 동시에 서로 다른 파일의 자리를 바꿔도 하나도 잃지 않는다(읽고-고치고-쓰기 차례 — 수정 전 코드는 실패)
X. 자리를 놓은 직후 `flush()` → `os._exit`(main.py 의 끝 길) — 새 프로세스가 그 자리를 읽는다
"""
import builtins, io, json, os, subprocess, sys, tempfile, threading
os.environ["QT_QPA_PLATFORM"] = "offscreen"          # 검사 작성 SOT §14.7
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PyQt6.QtCore import QStandardPaths
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2 의 3

tmp = tempfile.mkdtemp(prefix="polypdf_drbg_")
from viewer import settings_store
settings_store._DIR_OVERRIDE = os.path.join(tmp, "cfg")     # 실제 설정 폴더를 쓰지 않는다
os.makedirs(settings_store._DIR_OVERRIDE, exist_ok=True)
from viewer import bg_write, sign_drafts as sd

fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


docs = os.path.join(tmp, "docs")
os.makedirs(docs)
a = os.path.join(docs, "계약서.pdf")
b = os.path.join(docs, "계약서_서명.pdf")
store = sd._path()


def draft(i, x):
    return {"id": "d%d" % i, "page": 0, "rect": [x, 100, x + 80, 140], "kind": "sign", "image": "", "field": "", "fp": ""}


# ── M 메인 스레드 파일 쓰기 감시 ─────────────────────────────────
main_writes = []
_open, _replace, _io_open = builtins.open, os.replace, io.open


def _is_main():
    return threading.current_thread() is threading.main_thread()


def _spy_open(file, mode="r", *a_, **k):
    if _is_main() and any(c in str(mode) for c in "wax+"):
        main_writes.append(("open", str(file)))
    return _open(file, mode, *a_, **k)


def _spy_replace(src, dst, *a_, **k):
    if _is_main():
        main_writes.append(("replace", str(dst)))
    return _replace(src, dst, *a_, **k)


builtins.open, os.replace, io.open = _spy_open, _spy_replace, _spy_open
try:
    sd.set_drafts(a, [draft(1, 50)])                              # 놓기
    for x in range(60, 160, 10):                                  # 끌어 옮기기(잇단 저장)
        sd.set_drafts(a, [draft(1, x)])
    sd.set_drafts(a, [draft(1, 150), draft(2, 300)])               # 하나 더
    sd.set_signed(b, a, 1234, "ab" * 32, [draft(1, 150)])          # 확정 기록
    sd.relocate([(b, os.path.join(docs, "계약서_서명2.pdf"))])     # 이름 바꾸기
finally:
    builtins.open, os.replace, io.open = _open, _replace, _io_open
chk(not main_writes, "M 놓기·옮기기·확정 기록·이름 바꾸기가 메인에서 파일을 쓰지 않는다", "%d번 %s" % (len(main_writes), main_writes[:4]))

# ── R 쓰기 전 다시 읽기·디스크 ─────────────────────────────────
b2 = os.path.join(docs, "계약서_서명2.pdf")
r1 = [d["rect"][0] for d in sd.drafts(a)]
s1 = sd.signed(b2)
chk(r1 == [150.0, 300.0] and s1 is not None and s1["base_len"] == 1234 and sd.signed(b) is None,
    "R 쓰기가 끝나기 전에 다시 읽어도 마지막 자리·옮긴 확정 기록", str((r1, s1 and s1["base_len"])))
chk(bg_write.flush(timeout=10), "R 배경 쓰기가 끝난다")
disk = json.loads(_open(store, encoding="utf-8").read())
chk([d["rect"][0] for d in disk[sd.key(a)]["drafts"]] == [150.0, 300.0] and sd.key(b2) in disk,
    "R flush 뒤 디스크도 같은 값")
sd.clear(a)
chk(sd.drafts(a) == [] and bg_write.flush(timeout=10) and sd.key(a) not in json.loads(_open(store, encoding="utf-8").read()),
    "R 모두 지우기도 디스크까지")

# ── C 여러 스레드가 동시에 ────────────────────────────────────
paths = [os.path.join(docs, "m%02d.pdf" % i) for i in range(20)]
ths = [threading.Thread(target=sd.set_drafts, args=(p, [draft(i, 10 + i)])) for i, p in enumerate(paths)]
for t in ths:
    t.start()
for t in ths:
    t.join()
bg_write.flush(timeout=10)
disk = json.loads(_open(store, encoding="utf-8").read())
lost = [i for i, p in enumerate(paths) if sd.key(p) not in disk]
chk(not lost and all(sd.drafts(p) and sd.drafts(p)[0]["id"] == "d%d" % i for i, p in enumerate(paths)),
    "C 스무 스레드가 동시에 자리를 바꿔도 하나도 잃지 않는다", "잃음 %s" % lost)

# ── X 앱 끝(main.py: flush → os._exit) 직전 놓은 자리 ───────────
c = os.path.join(docs, "끝.pdf")
child = r'''
import os, sys
sys.path.insert(0, %r)
from PyQt6.QtCore import QStandardPaths
QStandardPaths.setTestModeEnabled(True)
from viewer import settings_store
settings_store._DIR_OVERRIDE = %r
from viewer import bg_write, sign_drafts as sd
sd.set_drafts(%r, [{"id": "x1", "page": 2, "rect": [1, 2, 3, 4], "kind": "image", "fp": "ff"}])
bg_write.flush()
os._exit(0)
''' % (HERE, settings_store._DIR_OVERRIDE, c)
subprocess.run([sys.executable, "-c", child], timeout=60)
sd._LOAD_MEMO.clear()
got = sd.drafts(c)
chk(got and got[0]["id"] == "x1" and got[0]["page"] == 2, "X 놓은 직후 앱이 끝나도(flush → os._exit) 다시 열면 자리가 있다", str(got))

import shutil
shutil.rmtree(tmp, ignore_errors=True)
print()
print("=== ALL PASS ===" if not fails else "=== FAIL %d ===\n  " % len(fails) + "\n  ".join(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
