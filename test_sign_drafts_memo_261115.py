# -*- coding: utf-8 -*-
"""261115-12: 서명 자리 기록(`sign_drafts`) — 본문을 그릴 때마다 파일을 다시 읽지 않는다 (응답성 SOT §4.7 ⑤).

`sign_draft_layer.reposition` 이 그린 쪽마다 `drafts(path)` 를 불러 `drafts.json` 을 열고 폴더를 두 번 만들었다
(큰 폴더 ↓ 연타 정지 표본에 `settings_dir → mkdir`·`sign_drafts._load` 가 잡혔다).

A. 같은 파일을 여러 번 물어도 파일은 한 번만 연다
B. 돌려준 것을 고쳐도 다음 읽기에 번지지 않는다(사본)
C. 쓰면(set_drafts) 다음 읽기가 새 내용
D. 다른 프로세스가 파일을 바꾸면(수정 시각·크기) 다시 읽는다
"""
import os, sys, json, time, builtins
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv[:1])
QStandardPaths.setTestModeEnabled(True)               # 검사 작성 SOT §14.7.2 의 3
QCoreApplication.setApplicationName("polypdf_sign_memo_%d" % os.getpid())
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


try:
    from viewer import sign_drafts as sd
    p = sd._path()
    pdf = os.path.join(os.path.dirname(p), "x.pdf")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({sd.key(pdf): {"drafts": [{"id": "a1", "page": 0, "rect": [1, 2, 3, 4]}]}}, f)
    opened = []
    _orig_open = builtins.open

    def _spy(file, *a, **k):
        if str(file) == p:
            opened.append(1)
        return _orig_open(file, *a, **k)
    builtins.open = _spy
    try:
        for _ in range(5):
            d = sd.drafts(pdf)
    finally:
        builtins.open = _orig_open
    chk(len(d) == 1 and d[0]["id"] == "a1", "준비 — 자리 하나를 읽는다", str(d))
    chk(len(opened) <= 1, "A ★ 다섯 번 물어도 파일은 한 번만 연다", str(len(opened)))

    raw = sd._load()
    raw[sd.key(pdf)]["drafts"].clear()
    chk(len(sd.drafts(pdf)) == 1, "B 돌려준 것을 고쳐도 다음 읽기에 번지지 않는다")

    data = sd._load()
    data[sd.key(pdf)]["drafts"].append({"id": "b2", "page": 1, "rect": [0, 0, 1, 1]})
    sd._save(data)
    chk([x["id"] for x in sd.drafts(pdf)] == ["a1", "b2"], "C 쓰면 다음 읽기가 새 내용", str(sd.drafts(pdf)))

    from viewer import bg_write                                    # 261115-19: 우리 쓰기는 배경 줄 — 디스크에 닿은 뒤에 남이 바꾼다
    bg_write.flush()
    time.sleep(0.05)
    with open(p, "w", encoding="utf-8") as f:                      # 다른 프로세스가 바꿈
        json.dump({sd.key(pdf): {"drafts": [{"id": "z9", "page": 2, "rect": [0, 0, 2, 2]}]}}, f)
    chk([x["id"] for x in sd.drafts(pdf)] == ["z9"], "D 파일이 바뀌면 다시 읽는다", str(sd.drafts(pdf)))
    os.remove(p)
    chk(sd.drafts(pdf) == [], "D 파일이 없어지면 빈 목록")
except Exception:
    import traceback
    traceback.print_exc()
    fails.append("예외")

print("\n=== " + ("ALL PASS" if not fails else f"FAILURE ({len(fails)})") + " ===")
for m in fails:
    print(" -", m)
sys.stdout.flush()
os._exit(1 if fails else 0)
