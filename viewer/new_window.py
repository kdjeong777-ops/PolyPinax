"""261128-16(책갈피창·저장 SOT §4.9.5, 사용자 지시·결정): 새 창으로 열기 — 명령줄 만들기·읽기·띄우기 한 곳.

새 창은 프로그램을 하나 더 띄운다. 무엇을 열지는 명령줄로 넘긴다:
    --new-window [--folder <폴더>] [--page <쪽>] [--fit <맞춤>] [--scale <배율>] [--photo] [<파일>]
`--new-window` 가 있으면 `main.py` 가 모으기·사진 넘기기를 건너뛴다(방금 띄운 창이 다른 창으로 되돌아가지 않게).
가벼운 모듈 — 창을 만들기 전에 `main.py` 가 부른다(Qt 는 `launch` 안에서만).
"""
import os
import sys

FLAG = "--new-window"
_VALUED = ("--folder", "--page", "--fit", "--scale")


def build_args(file=None, folder=None, page=0, fit=None, scale=None, photo=False) -> list:
    """새 창 명령줄(실행 파일 뒤에 붙일 인자). 파일·폴더가 다 없으면 빈 목록 — 종전 새 창(인자 없이)."""
    if not file and not folder:
        return []
    out = [FLAG]
    if folder:
        out += ["--folder", str(folder)]
    if page:
        out += ["--page", str(int(page))]
    if fit:
        out += ["--fit", str(fit)]
    if scale:
        out += ["--scale", "%.4f" % float(scale)]
    if photo:
        out.append("--photo")
    if file:
        out.append(str(file))
    return out


def parse(args):
    """명령줄 → (새 창 옵션 dict 또는 None, 나머지 인자). `--new-window` 가 없으면 (None, 그대로)."""
    args = list(args or [])
    if FLAG not in args:
        return None, args
    opts = {"folder": None, "page": 0, "fit": None, "scale": None, "photo": False}
    rest = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == FLAG:
            pass
        elif a == "--photo":
            opts["photo"] = True
        elif a in _VALUED and i + 1 < len(args):
            v = args[i + 1]
            i += 1
            key = a[2:]
            try:
                if key == "page":
                    opts["page"] = max(0, int(v))
                elif key == "scale":
                    opts["scale"] = float(v)
                else:
                    opts[key] = v
            except ValueError:
                pass
        else:
            rest.append(a)
        i += 1
    if opts["folder"] and not os.path.isdir(opts["folder"]):
        opts["folder"] = None
    return opts, rest


def command(args) -> tuple:
    """(실행 파일, 인자) — 빌드본은 exe 하나, 개발판은 파이썬 + main.py."""
    if getattr(sys, "frozen", False):
        return sys.executable, list(args)
    return sys.executable, [os.path.abspath(sys.argv[0])] + list(args)


def launch(args) -> bool:
    """새 프로세스로 띄운다 — 성공 여부. PyQt6 는 (성공, pid) 를 돌려준다(튜플 자체는 늘 참, 261024-5)."""
    from PyQt6.QtCore import QProcess
    exe, argv = command(args)
    try:
        res = QProcess.startDetached(exe, argv)
    except Exception:
        return False
    return bool(res[0] if isinstance(res, tuple) else res)
