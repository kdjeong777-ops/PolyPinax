# -*- coding: utf-8 -*-
"""(보안 SOT §11 'PW') PDF 암호 기억(`pdf_pw.json`)을 메인 스레드에서 쓰지 않는다 — 배경 쓰기 줄(`bg_write`) (261114-17, 응답성 SOT §4.8·보안 SOT §7.2).

종전에는 `secure_store._save` 가 메인에서 tmp 쓰기 + `os.replace` 를 했다 — `_finalize_save` 가 저장한 파일로 암호를 옮길 때,
암호 창 '기억', 이름 바꾸기 `relocate`. 백신이 바꿔 끼운 파일을 붙들면 그동안 창이 선다(메인 `os.replace` 21.4초 이력).

M. 메인 스레드에서 `remember_password`·`relocate`·`forget_password` 를 불러도 메인의 파일 쓰기(`open` 쓰기 모드·`os.replace`) 0번(수정 전 코드는 실패)
R. 쓰기 전에 다시 열어도(`recall_password`) 기억한 암호 · `flush` 뒤 디스크에 그 키 — 평문 암호는 파일에 없다
C. 여러 스레드가 동시에 서로 다른 파일을 기억해도 하나도 잃지 않는다(읽고-고치고-쓰기 차례)
X. 기억한 직후 `flush()` → `os._exit`(main.py 의 끝 길) — 새 프로세스가 그 암호를 다시 꺼낸다
"""
import builtins, json, os, subprocess, sys, tempfile, threading
os.environ["QT_QPA_PLATFORM"] = "offscreen"          # 검사 작성 SOT §14.7
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PyQt6.QtCore import QStandardPaths
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2 의 3

tmp = tempfile.mkdtemp(prefix="polypdf_pwbg_")
from viewer import settings_store
settings_store._DIR_OVERRIDE = os.path.join(tmp, "cfg")     # 실제 설정 폴더를 쓰지 않는다
os.makedirs(settings_store._DIR_OVERRIDE, exist_ok=True)
from viewer import bg_write, secure_store

fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


if not secure_store.available():
    print("SKIP - DPAPI(pywin32) 가 없는 환경 — 암호 기억 자체를 하지 않는다(보안 SOT §7.2)")
    sys.exit(0)

docs = os.path.join(tmp, "docs")
os.makedirs(docs)


def mkpdf(name, size=40):
    p = os.path.join(docs, name)
    with open(p, "wb") as fh:
        fh.write(b"%PDF-1.4\n" + b"x" * size + b"\n%%EOF\n")
    return p


a, b = mkpdf("a.pdf"), mkpdf("b.pdf", 80)
store = str(secure_store._store_path())

# ── M 메인 스레드 파일 쓰기 감시 ─────────────────────────────────
main_writes = []
_open, _replace = builtins.open, os.replace


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


# Path.write_text 도 builtins.open 이 아니라 io.open 을 쓴다 — 둘 다 감시한다
import io
_io_open = io.open
builtins.open, os.replace, io.open = _spy_open, _spy_replace, _spy_open
try:
    ok1 = secure_store.remember_password(a, "pw-alpha!")
    new_b = os.path.join(docs, "b2.pdf")
    secure_store.remember_password(b, "pw-beta!")
    _replace(b, new_b)                                   # 이름 바꾸기 흉내(감시 밖에서 옮김)
    secure_store.relocate(b, new_b)
    secure_store.forget_password(a)
    secure_store.remember_password(a, "pw-alpha2!")
finally:
    builtins.open, os.replace, io.open = _open, _replace, _io_open
chk(ok1 and not main_writes, "M 기억·옮기기·잊기가 메인에서 파일을 쓰지 않는다", "%d번 %s" % (len(main_writes), main_writes[:4]))

# ── R 다시 열기 왕복 ───────────────────────────────────────────
chk(secure_store.recall_password(a) == "pw-alpha2!" and secure_store.recall_password(new_b) == "pw-beta!",
    "R 쓰기가 끝나기 전에 다시 열어도 기억한 암호(잊은 뒤 다시 기억한 값·옮긴 파일)")
chk(bg_write.flush(timeout=10), "R 배경 쓰기가 끝난다")
raw = _open(store, encoding="utf-8").read()
data = json.loads(raw)
chk(secure_store._key(a) in data and secure_store._key(new_b) in data and "pw-alpha2!" not in raw and "pw-beta!" not in raw,
    "R 디스크에 두 키 — 평문 암호는 없다(DPAPI 암호문만)", raw[:120])

# ── C 여러 스레드가 동시에 ────────────────────────────────────
many = [mkpdf("m%02d.pdf" % i, 10 + i) for i in range(20)]
ths = [threading.Thread(target=secure_store.remember_password, args=(p, "pw-%d!" % i)) for i, p in enumerate(many)]
for t in ths:
    t.start()
for t in ths:
    t.join()
bg_write.flush(timeout=10)
data = json.loads(_open(store, encoding="utf-8").read())
lost = [i for i, p in enumerate(many) if secure_store._key(p) not in data]
chk(not lost and all(secure_store.recall_password(p) == "pw-%d!" % i for i, p in enumerate(many)),
    "C 스무 스레드가 동시에 기억해도 하나도 잃지 않는다", "잃음 %s" % lost)

# ── X 앱 끝(main.py: flush → os._exit) 직전 기억 ────────────────
c = mkpdf("exit.pdf", 99)
child = r'''
import os, sys
sys.path.insert(0, %r)
from viewer import settings_store
settings_store._DIR_OVERRIDE = %r
from viewer import bg_write, secure_store
secure_store.remember_password(%r, "pw-exit!")
bg_write.flush()
os._exit(0)
''' % (HERE, settings_store._DIR_OVERRIDE, c)
subprocess.run([sys.executable, "-c", child], timeout=60)
chk(secure_store.recall_password(c) == "pw-exit!", "X 기억한 직후 앱이 끝나도(flush → os._exit) 다시 열면 암호가 있다")

import shutil
shutil.rmtree(tmp, ignore_errors=True)
print()
print("=== ALL PASS ===" if not fails else "=== FAIL %d ===\n  " % len(fails) + "\n  ".join(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
