# -*- coding: utf-8 -*-
"""다른 앱(MSIX) 안 실행 막기·끝낼 때 WAL 정리 (응답성 SOT §4 ⑤·명함 SOT §5.7, 261122-1 덧붙임) — 임시 폴더·가짜 DB 만.

A. 시험 프로필·오프스크린·허용 표시는 막지 않음
B. 돌려 쓰기 판정 — 표식 파일이 다른 앱 가상 사본(Packages\\*\\LocalCache\\…)에 생기면 True, 없는 폴더는 보지 않고 만들지도 않음,
   %LOCALAPPDATA%·%APPDATA% 밖은 False. (이 PC 가 돌려 쓰는 환경이면 실제로 돌려 써지는 폴더로도 확인)
C. main.main() 은 돌려 써지면 QApplication 을 만들기 전에 끝냄(설정 폴더를 열지 않음)
D. 명함 DB 연결을 닫으면 -wal 이 비고, close_all 은 열린 연결을 모두 닫음
"""
import os, sys, tempfile, shutil, glob
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


try:
    from viewer import pkg_guard as G
    print("=== A ===")
    chk(G.exempt({"POLYPDF_PROFILE": "test"}) and G.exempt({"QT_QPA_PLATFORM": "offscreen"}) and G.exempt({G.ALLOW_ENV: "1"})
        and not G.exempt({}), "A 시험 프로필·오프스크린·허용 표시만 막지 않음")

    print("\n=== B ===")
    la = os.environ.get("LOCALAPPDATA", "")
    win = os.environ.get("SystemRoot", r"C:\Windows")
    chk(G._kind_rel(win) is None and G.redirected(win) is False, "B %LOCALAPPDATA%·%APPDATA% 밖은 판정 안 함")
    ghost = os.path.join(la, "pcx_guard_none_%d" % os.getpid())
    chk(G.redirected(ghost) is False and not os.path.exists(ghost), "B 없는 폴더는 보지 않고 만들지도 않음")
    name = "pcx_guard_%d" % os.getpid()
    pkgs = glob.glob(os.path.join(glob.escape(la), "Packages", "*", "LocalCache", "Local"))
    if pkgs:
        pkgs.sort(key=lambda p: "claude" not in p.lower())   # 이 세션을 띄운 앱(Claude) 쪽 먼저
        priv = os.path.join(pkgs[0], name)
        os.makedirs(priv, exist_ok=True)              # 가상 사본 쪽에 폴더가 먼저 있는 꼴(사용자 PC 와 같음)
        d = os.path.join(la, name)
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, "x.txt")
        open(probe, "w").write("x")
        virt = bool(glob.glob(os.path.join(glob.escape(la), "Packages", "*", "LocalCache", "Local", name, "x.txt")))   # 실제로 돌려 써지나
        os.remove(probe)
        got = G.redirected(d)
        chk(got == virt, "B 표식 파일이 가상 사본에 생기는지로 판정(이 환경 %s)" % ("돌려 써짐" if virt else "안 돌려 써짐"), str((got, virt)))
        left = [f for f in os.listdir(d) if f.startswith(".pkgprobe_")] + [f for f in os.listdir(priv) if f.startswith(".pkgprobe_")]
        chk(not left, "B 표식 파일은 지움", str(left))
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(priv, ignore_errors=True)
    else:
        print("(이 PC 에 앱 가상 사본 폴더 없음 — 실제 돌려 쓰기 확인은 건너뜀)")

    print("\n=== C main.main ===")
    import main as M
    from PyQt6.QtWidgets import QApplication
    calls = []
    _b, _x = G.blocked, os._exit
    G.blocked = lambda ids, env=None: calls.append(tuple(ids)) or True
    os.environ[G.QUIET_ENV] = "1"

    class Stop(Exception):
        pass

    def fake_exit(code):
        raise Stop(code)
    os._exit = fake_exit
    try:
        M.main()
        rc = None
    except Stop as e:
        rc = e.args[0]
    finally:
        G.blocked, os._exit = _b, _x
    from viewer import branding as B
    chk(rc == 3 and QApplication.instance() is None and calls and set(calls[0]) == {B.APP_ID, B.OLD_ID},
        "C 돌려 써지면 QApplication 전에 끝냄(새·옛 이름 폴더 모두 봄)", str((rc, calls)))

    print("\n=== D WAL 정리 ===")
    from viewer.bizcard import store as S, people as P
    tmp = tempfile.mkdtemp(prefix="pkg_wal_")
    db = os.path.join(tmp, "bizcard.db")
    st = S.BizcardStore(db)
    st2 = S.BizcardStore(db)
    P._insert_contact(st, {"name": "가짜", "phones": [("cell", "010-0000-1111")]}, ["명함"])
    st.con.commit()
    wal = db + "-wal"
    before = os.path.getsize(wal) if os.path.exists(wal) else 0
    n = S.close_all()
    after = os.path.getsize(wal) if os.path.exists(wal) else 0
    chk(before > 0 and after == 0 and n >= 2 and not S._OPEN, "D 닫으면 -wal 이 비고 close_all 은 열린 연결을 모두 닫음", str((before, after, n)))
    shutil.rmtree(tmp, ignore_errors=True)
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외")
print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
