# -*- coding: utf-8 -*-
"""다른 앱(MSIX 패키지) 안에서 띄운 실행 막기 (응답성 SOT §4 ⑤·명함 SOT §5.7, 261122-1 덧붙임) — Qt 없음.

Claude 데스크톱 앱처럼 MSIX 로 깔린 앱 안(터미널 패널·Run 단추·그 자식)에서 PolyPDF 를 띄우면 Windows 가 %LOCALAPPDATA%·%APPDATA%
를 그 앱의 가상 사본(`%LOCALAPPDATA%\\Packages\\<앱>\\LocalCache\\…`)과 합쳐 보여 준다 — 본 파일(bizcard.db·settings.json)은 실제
폴더 것을 쓰면서 SQLite 의 -wal·-shm 은 가상 사본에 따로 만든다. 같은 DB 를 앱 밖(설치본·바로가기)에서도 쓰면 WAL 이 두 벌이
되어 DB 가 깨진다(사용자 명함 DB 손상 261123, 가짜 DB 로 재현). 그 자식 프로세스는 패키지 이름(`GetCurrentPackageFullName`)이
없다고 나오는데도 돌려 쓰기를 받는다(261123 실측) — 그래서 **설정·데이터 폴더에 표식 파일을 써 보고 가상 사본 쪽에 생기는지** 본다.
돌려 써지면 실제 설정 폴더를 열기 **전에** 알리고 끝낸다. 시험 프로필(`POLYPDF_PROFILE`)·오프스크린 검사·`POLYPDF_IN_PACKAGE_OK=1`
은 막지 않는다.
"""
from __future__ import annotations

import glob
import os
import sys

from viewer.i18n import tr

ALLOW_ENV = "POLYPDF_IN_PACKAGE_OK"
QUIET_ENV = "POLYPDF_GUARD_QUIET"            # 알림 창 없이 끝냄(검사)
APPMODEL_ERROR_NO_PACKAGE = 15700


def package_name() -> str:
    """이 프로세스의 앱 패키지 이름 — 패키지 밖이거나 Windows 가 아니면 ''(자식 프로세스는 돌려 쓰기를 받아도 '' 일 수 있다)."""
    if sys.platform != "win32":
        return ""
    try:
        import ctypes
        from ctypes import wintypes
        fn = ctypes.windll.kernel32.GetCurrentPackageFullName
        fn.argtypes = [ctypes.POINTER(wintypes.UINT), wintypes.LPWSTR]
        fn.restype = wintypes.LONG
        n = wintypes.UINT(0)
        if fn(ctypes.byref(n), None) == APPMODEL_ERROR_NO_PACKAGE:
            return ""
        buf = ctypes.create_unicode_buffer(max(1, n.value))
        return buf.value if fn(ctypes.byref(n), buf) == 0 else "?"
    except Exception:
        return ""


def _kind_rel(path: str):
    """path 가 %LOCALAPPDATA%·%APPDATA% 아래면 ('Local'|'Roaming', 상대 경로), 아니면 None."""
    p = os.path.normcase(os.path.abspath(path))
    for kind, var in (("Local", "LOCALAPPDATA"), ("Roaming", "APPDATA")):
        base = os.environ.get(var) or ""
        if not base:
            continue
        b = os.path.normcase(os.path.abspath(base))
        if p == b or p.startswith(b + os.sep):
            return kind, os.path.relpath(p, b)
    return None


def redirected(path: str) -> bool:
    """이 폴더에 새로 만든 파일이 다른 앱의 가상 사본(`Packages\\*\\LocalCache\\<Local|Roaming>\\…`)으로 가는가 — 표식 파일을 써 보고
    지운다. 없는 폴더는 보지 않는다(만들지 않음). 알 수 없으면 False."""
    kr = _kind_rel(path)
    la = os.environ.get("LOCALAPPDATA") or ""
    if kr is None or not la or sys.platform != "win32" or not os.path.isdir(path):
        return False
    probe = os.path.join(path, ".pkgprobe_%d" % os.getpid())
    try:
        with open(probe, "w") as f:
            f.write("x")
    except OSError:
        return False
    try:
        pat = os.path.join(glob.escape(la), "Packages", "*", "LocalCache", kr[0], glob.escape(kr[1]), os.path.basename(probe))
        return bool(glob.glob(pat))
    finally:
        try:
            os.remove(probe)
        except OSError:
            pass


def exempt(env=None) -> bool:
    env = os.environ if env is None else env
    return bool(env.get("POLYPDF_PROFILE") or env.get(ALLOW_ENV) == "1" or env.get("QT_QPA_PLATFORM") == "offscreen")


def data_dirs(*app_ids) -> list:
    """앱이 쓰는 설정 폴더(%APPDATA%\\LocalTools\\<앱>)·도구 자료 폴더(%LOCALAPPDATA%\\<앱>, 명함 DB) — Qt 없이."""
    out = []                                      # 새·옛 이름 모두(개발 실행은 옛 이름 폴더를 함께 쓸 수 있다 — main.dev_profile_dirs)
    for app_id in app_ids:
        if os.environ.get("APPDATA"):
            out.append(os.path.join(os.environ["APPDATA"], "LocalTools", app_id))
        if os.environ.get("LOCALAPPDATA"):
            out.append(os.path.join(os.environ["LOCALAPPDATA"], app_id))
    return out


def blocked(app_ids, env=None) -> bool:
    """실제 설정·DB 를 쓰면 안 되는 실행인가 — 시험 프로필·오프스크린·허용 표시가 아니고, 설정·자료 폴더가 다른 앱 사본으로 돌려 써짐."""
    if exempt(env):
        return False
    return any(redirected(d) for d in data_dirs(*app_ids))


def stop_if_blocked(app_ids) -> None:
    """돌려 써지면 알리고(Qt 없이 Windows 알림 창) 끝낸다 — 설정 폴더를 정하기 전에 부른다."""
    if not blocked(app_ids):
        return
    msg = tr("PolyPDF 를 다른 앱(Claude 앱의 터미널·실행 단추 등) 안에서 띄웠습니다 — 이렇게 띄우면 설정·명함 DB 의 보조 파일이 "
             "따로 만들어져 자료가 깨질 수 있어 끝냅니다.\n\n탐색기에서 run.bat 을 두 번 누르거나 보통 PowerShell 창에서 띄우세요.")
    try:
        sys.stderr.write(msg + "\n")
        sys.stderr.flush()
    except Exception:
        pass
    if os.environ.get(QUIET_ENV) != "1":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, msg, "PolyPDF", 0x30)
        except Exception:
            pass
    os._exit(3)
