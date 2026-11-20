# -*- coding: utf-8 -*-
"""기본 사진 앱으로 설정 — Windows 기본 앱 화면을 연다 (사진 보기 SOT §4.45, 261112-10 사용자 지시·결정).

PDF(`pdf_default`, 마스터 §14.10)와 같은 길이다 — Windows 는 앱이 기본 앱을 스스로 바꾸지 못하게 막으므로 **후보로 보이게만** 하고
그 화면을 연다. 다른 점:
- 설치 프로그램은 사진을 등록하지 않는다(사용자 결정 — `PolyPDF.iss` 그대로) → **설치판에서도 HKCU** 에 쓴다.
- 이름을 PDF 와 나눈다(ProgID `PolyPix.photo`·`Software\\PolyPinax\\PhotoCapabilities`·등록 값 `PolyPixPhoto` — 이름은 branding,
  이사 전 판은 `PolyPDF.photo`·`Software\\PolyPDF\\…`·`PolyPDFPhoto`) — 설치판의
  `기본 PDF 앱으로 설정` 이 옛 HKCU PDF 키를 지울 때 함께 지워지지 않고, HKLM 의 PDF 등록을 가리지 않는다.
- 후보 확장자 = 사진 모드가 여는 표 하나(`image_page.PHOTO_EXTS`).
레지스트리는 `pdf_default.Reg` 하나로만 만진다 — 검사는 가짜를 넘긴다(실제 레지스트리를 건드리지 않는다).
"""
from __future__ import annotations

from viewer.image_page import PHOTO_EXTS
from viewer.pdf_default import HKCU, REG_APPS, _cmd, open_settings  # noqa: F401 — open_settings 는 창 쪽이 이 모듈로 부른다

from viewer import branding as _br

# 261114-8(마스터 §1.1): 사진 ProgID 는 사진 모드 이름 — 이사 판부터 PolyPix.photo·PolyPixPhoto(옛 PolyPDF.photo 명령은
#   pdf_default.repair_user_progids 가 지금 실행 파일로 고쳐 사용자가 고른 기본 사진 앱이 그대로 열린다). 등록 키는 제품 단위 APP_ID.
APP = _br.PHOTO_APP                          # RegisteredApplications 값 이름 = 기본 앱 화면 URI 의 앱 이름(빈칸 없이)
PROG_ID = _br.PHOTO_PROG_ID
CAPS = r"Software\%s\PhotoCapabilities" % _br.APP_ID
PROG_KEY = r"Software\Classes\%s" % PROG_ID
URI_USER = "ms-settings:defaultapps?registeredAppUser=" + APP
URI_PLAIN = "ms-settings:defaultapps"
EXTS = tuple(sorted(PHOTO_EXTS))


ICON_FILE = "polypix.ico"                    # 261120-16(사진 SOT §4.45 '파일 아이콘', 디자인 SOT §4.7): 파랑 바탕·흰 산
SHCNE_ASSOCCHANGED = 0x08000000


def open_with_key(ext: str) -> str:
    return r"Software\Classes\%s\OpenWithProgids" % ext


def icon_value(exe: str, ico: str | None = None) -> str:
    """사진 ProgID 의 `DefaultIcon` 값 — 실행본 자원의 `polypix.ico`, 없으면 종전대로 exe 의 대표 아이콘."""
    if ico is None:
        from viewer.resources_path import resource_path
        ico = resource_path(ICON_FILE)
    return '"%s",0' % (ico or exe)


def notify_assoc_changed() -> None:
    """탐색기에 파일 연결(아이콘)이 바뀌었다고 알린다 — 알리지 않으면 아이콘 캐시가 옛 그림을 계속 보인다."""
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, 0, None, None)
    except Exception:
        pass


def fix_icons(reg, exe: str, ico: str | None = None, notify=notify_assoc_changed) -> list:
    """261120-16: 이미 등록한 PC — HKCU 에 있는 사진 ProgID(옛 이름 포함)의 아이콘이 `icon_value` 와 다르면 고친다.
    등록이 없는 ProgID 는 건드리지 않는다(새로 만들지 않는다). 하나라도 고쳤으면 탐색기에 알린다. 고친 키 목록."""
    want = icon_value(exe, ico)
    done = []
    for pid in _br.ALL_PHOTO_PROG_IDS:
        base = r"Software\Classes\%s" % pid
        if not reg.get(HKCU, base + r"\shell\open\command"):
            continue
        key = base + r"\DefaultIcon"
        if reg.get(HKCU, key) != want:
            reg.set(HKCU, key, "", want)
            done.append(key)
    if done:
        notify()
    return done


def write_user_keys(reg, exe: str, desc: str, app_name: str, app_desc: str, ico: str | None = None) -> None:
    """HKCU 에 사진 후보 등록 — 다시 부르면 이 exe 로 고쳐 쓴다(휴대용 폴더를 옮긴 경우)."""
    reg.set(HKCU, PROG_KEY, "", desc)
    reg.set(HKCU, PROG_KEY + r"\DefaultIcon", "", icon_value(exe, ico))
    reg.set(HKCU, PROG_KEY + r"\shell\open\command", "", _cmd(exe))
    reg.set(HKCU, CAPS, "ApplicationName", app_name)
    reg.set(HKCU, CAPS, "ApplicationDescription", app_desc)
    for ext in EXTS:
        reg.set(HKCU, open_with_key(ext), PROG_ID, None, none_type=True)
        reg.set(HKCU, CAPS + r"\FileAssociations", ext, PROG_ID)
    reg.set(HKCU, REG_APPS, APP, CAPS)


def prepare(exe: str, frozen: bool, reg, desc: str = "Photo (PolyPinax)", app_name: str = "PolyPinax Photo",
            app_desc: str = "PolyPinax") -> dict:
    """→ {"kind": "dev"|"user", "uris": [...]}. 개발 실행(파이썬)은 쓰지 않는다 — `main.py` 를 연결하면 파이썬이 열린다."""
    if not frozen:
        return {"kind": "dev", "uris": []}
    write_user_keys(reg, exe, desc, app_name, app_desc)
    notify_assoc_changed()                    # 261120-16: 새 아이콘이 탐색기에 곧바로 보이게
    return {"kind": "user", "uris": [URI_USER, URI_PLAIN]}


def split_args(args) -> tuple:
    """명령줄 인자 → (PDF 목록, 사진 목록). 있는 파일만. PDF 가 하나라도 있으면 사진은 쓰지 않는다(PDF 가 먼저 — §4.45)."""
    import os
    pdfs, photos = [], []
    for a in args:
        if not a or a.startswith("--"):
            continue
        ext = os.path.splitext(a)[1].lower()
        if ext == ".pdf" and os.path.exists(a):
            pdfs.append(a)
        elif ext in PHOTO_EXTS and os.path.isfile(a):
            photos.append(a)
    return (pdfs, [] if pdfs else photos)
