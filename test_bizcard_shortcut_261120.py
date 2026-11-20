# -*- coding: utf-8 -*-
"""명함 프로그램 따로 실행 — 설치 프로그램 바로가기 (명함 SOT §5.27 '바로가기', 261120-5).

A. 설치 프로그램 [Icons] 에 PolyCardex 바로가기 — 시작 메뉴 하나 + 바탕 화면 하나(바탕 화면 선택 `desktopicon` 과 함께),
   대상은 같은 실행 파일, 인자 `--bizcard`, 이름은 `standalone.APP_TITLE`
B. 앱 ID — 바로가기 `AppUserModelID` 가 main 이 `--bizcard` 때 정하는 ID(`APP_USER_MODEL_ID + '.Bizcard'`)와 같다(작업 표시줄 한 단추)
C. 아이콘 — `IconFilename` 이 가리키는 `resources/polycardex.ico` 가 저장소에 있고 여러 크기, 창 아이콘 `polycardex.png` 도 있다,
   명함 프로그램 시작(`_run_bizcard`)이 그 PNG 를 창 아이콘으로
D. 휴대용 zip — 표식 파일 안내에 `--bizcard` 가 있다(릴리스 워크플로)
"""
import os, re, sys, inspect
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PyQt6.QtCore import QStandardPaths
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2

fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


iss = open(os.path.join(HERE, "installer", "PolyPDF.iss"), encoding="utf-8").read()
icons = iss[iss.index("\n[Icons]"):iss.index("\n[Registry]")]
lines = [ln for ln in icons.splitlines() if ln.strip() and not ln.lstrip().startswith(";")]
card = [ln for ln in lines if "--bizcard" in ln]
defs = dict(re.findall(r'^#define (\w+) "([^"]*)"', iss, re.M))

# ── A ──
print("=== A. 바로가기 ===")
from viewer.bizcard import standalone
grp = [ln for ln in card if ln.startswith('Name: "{group}\\')]
dsk = [ln for ln in card if ln.startswith('Name: "{autodesktop}\\')]
chk(len(grp) == 1 and len(dsk) == 1, "A 시작 메뉴 하나·바탕 화면 하나", str(card))
chk(all('Filename: "{app}\\{#MyAppExe}"' in ln and 'Parameters: "--bizcard"' in ln for ln in card),
    "A 대상은 같은 실행 파일, 인자 --bizcard")
chk(dsk and "Tasks: desktopicon" in dsk[0] and grp and "Tasks:" not in grp[0], "A 바탕 화면은 바탕 화면 선택과 함께, 시작 메뉴는 늘")
chk(defs.get("MyCardName") == standalone.APP_TITLE and all("{#MyCardName}" in ln for ln in card),
    "A 바로가기 이름 = standalone.APP_TITLE", str(defs.get("MyCardName")))

# ── B ──
print("=== B. 앱 ID ===")
import main
src = inspect.getsource(main.main)
suf = re.search(r'_set_app_user_model_id\("([^"]+)" if bizcard', src)
chk(suf is not None, "B main 이 --bizcard 때 붙이는 ID 꼬리를 찾는다", src[:0])
want = 'AppUserModelID: "LocalTools.{#MyAppId}%s"' % (suf.group(1) if suf else "?")
chk(card and all(want in ln for ln in card), "B 바로가기 앱 ID = main 의 명함 프로그램 ID", want)
from viewer import branding as _br
blk = iss[iss.index("#ifdef MOVED"):iss.index("#else")] if _br.MOVED else iss[iss.index("#else"):]
my_id = re.search(r'^\s*#define MyAppId "([^"]+)"', blk, re.M).group(1)
chk("LocalTools." + my_id == main.APP_USER_MODEL_ID, "B 설치 프로그램 MyAppId 가 앱의 ID 와 같은 판", my_id)

# ── C ──
print("=== C. 아이콘 ===")
m = re.search(r'IconFilename: "\{app\}\\_internal\\resources\\([^"]+)"', card[0] if card else "")
ico = os.path.join(HERE, "resources", m.group(1)) if m else ""
chk(m and all(m.group(0) in ln for ln in card), "C 두 바로가기 모두 resources 의 자기 아이콘", str(card))
sizes = set()
if ico and os.path.exists(ico):
    from PIL import Image
    with Image.open(ico) as im:
        sizes = set(im.info.get("sizes") or [])
chk({(16, 16), (32, 32), (48, 48), (256, 256)} <= sizes, "C .ico 가 저장소에 있고 여러 크기", str(sorted(sizes)))
png = os.path.join(HERE, "resources", "polycardex.png")
chk(os.path.exists(png), "C 창 아이콘 polycardex.png 가 있다")
chk('resource_path("polycardex.png")' in inspect.getsource(main._run_bizcard), "C 명함 프로그램 창 아이콘 = polycardex.png")

# ── D ──
print("=== D. 휴대용 ===")
yml = open(os.path.join(HERE, ".github", "workflows", "release.yml"), encoding="utf-8").read()
seg = yml[yml.index("portable mode marker"):yml.index("Out-File -FilePath \"$pst")]
chk("--bizcard" in seg and "PolyCardex" in seg, "D 휴대용 표식 안내에 PolyCardex = --bizcard")
chk(all(ord(ch) < 128 for ch in seg), "D 표식 글은 ASCII 만(261010-2 — 한글은 CI 에서 깨짐)")

print()
print("ALL PASS" if not fails else "FAILURES: %d" % len(fails))
sys.exit(1 if fails else 0)
