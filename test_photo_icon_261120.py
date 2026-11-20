# -*- coding: utf-8 -*-
"""261120-16: 사진 파일 아이콘·명함 바깥 아이콘 — 앱 아이콘과 같은 꼴, 색·안 그림만 다르게 (디자인 SOT §4.7, 사진 SOT §4.45).

사용자 보고: 그림 파일을 이 프로그램으로 등록하니 모두 붉은 PDF 아이콘이라 구분이 어렵다.
원인: 사진 ProgID 의 DefaultIcon 이 `"exe",0`(앱 대표 아이콘 = PDF).

A. 아이콘 파일 — polypix·polycardex 의 png·ico 가 있고 ico 는 정사각 16~256, 바탕 색이 파랑·보라(빨강 아님),
   16px 에서도 평균 색상이 PDF 아이콘과 멀다, 저장소 파일 = `scripts/make_app_icons.py` 결과(그림을 바꾸면 다시 돌렸는지)
B. 새로 등록(`photo_default.prepare`, 가짜 레지스트리) — DefaultIcon 이 polypix.ico, 탐색기에 알림
C. 이미 등록한 PC(`photo_default.fix_icons`) — 옛 `"exe",0` 을 고치고 한 번 알림, 다시 부르면 그대로·알림 없음, 등록 없는 ProgID 는 만들지 않음
D. 실행 파일이 바뀌어 명령을 고칠 때(`pdf_default.repair_user_progids`) — 사진 ProgID 아이콘 = polypix.ico, PDF 는 exe
E. 빌드본 시작(`main._repair_progids`)이 fix_icons 를 부른다
"""
import colorsys
import inspect
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PIL import Image                                   # noqa: E402

fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


class FakeReg:
    """pdf_default.Reg 와 같은 꼴 — (뿌리, 경로, 이름) → 값. 실제 레지스트리는 건드리지 않는다."""

    def __init__(self):
        self.d = {}

    def get(self, root, path, name=""):
        return self.d.get((root, path.lower(), name))

    def set(self, root, path, name, value, none_type=False):
        self.d[(root, path.lower(), name)] = value

    def delete_value(self, root, path, name):
        return self.d.pop((root, path.lower(), name), None) is not None

    def delete_tree(self, root, path):
        for k in [k for k in self.d if k[0] == root and k[1].startswith(path.lower())]:
            del self.d[k]


def mean_hue(im):
    """불투명하고 채도가 높은 픽셀의 평균 색상(0~1, 원형 평균)과 그 개수."""
    import math
    xs = ys = n = 0
    px = im.convert("RGBA")
    data = px.get_flattened_data() if hasattr(px, "get_flattened_data") else px.getdata()
    for r, g, b, a in data:
        if a < 200:
            continue
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s < 0.45 or v < 0.25:
            continue
        xs += math.cos(2 * math.pi * h); ys += math.sin(2 * math.pi * h); n += 1
    return ((math.atan2(ys, xs) / (2 * math.pi)) % 1.0 if n else -1), n


def hue_gap(a, b):
    d = abs(a - b) % 1.0
    return min(d, 1 - d)


RES = os.path.join(HERE, "resources")

# ── A ──
print("=== A. 아이콘 파일 ===")
want_hue = {"polypix": colorsys.rgb_to_hsv(0x15 / 255, 0x65 / 255, 0xc0 / 255)[0],
            "polycardex": colorsys.rgb_to_hsv(0x7b / 255, 0x3f / 255, 0xb3 / 255)[0]}
pdf_hue16 = mean_hue(Image.open(os.path.join(RES, "icon.ico")).resize((16, 16)))[0]
for name in ("polypix", "polycardex"):
    png, ico = os.path.join(RES, name + ".png"), os.path.join(RES, name + ".ico")
    chk(os.path.exists(png) and os.path.exists(ico), "A %s png·ico 가 있다" % name)
    if not os.path.exists(ico):
        continue
    with Image.open(ico) as im:
        sizes = set(im.info.get("sizes") or [])
    chk({(s, s) for s in (16, 24, 32, 48, 256)} <= sizes, "A %s.ico 정사각 16·24·32·48·256" % name, str(sorted(sizes)))
    h, n = mean_hue(Image.open(png))
    chk(n > 1000 and hue_gap(h, want_hue[name]) < 0.04, "A %s 바탕 색 = 정한 색(빨강 아님)" % name, "hue=%.3f n=%d" % (h, n))
    with Image.open(ico) as im:
        im.size = (16, 16)
        im16 = im.convert("RGBA")
    h16, _ = mean_hue(im16)
    chk(hue_gap(h16, pdf_hue16) > 0.15, "A %s 16px 에서도 PDF 아이콘과 색이 멀다" % name, "%.3f vs %.3f" % (h16, pdf_hue16))
    # 안 그림 — 종이 가운데 아래(산 기슭·어깨)는 흰색, 'PDF' 자리의 위쪽 가운데(옛 D 자리) 둘레는 바탕색
    sq = Image.open(png).convert("RGBA")
    off = (sq.height - 468) // 2
    r, g, b, a = sq.getpixel((225, 300 + off))
    chk(min(r, g, b) > 235, "A %s 안 그림(흰색)이 종이 가운데 아래까지 크게" % name, str((r, g, b)))
try:
    sys.path.insert(0, os.path.join(HERE, "scripts"))
    import make_app_icons as mai
    for name in ("polypix", "polycardex"):
        a = mai.square(mai.render(name)).tobytes()
        b = Image.open(os.path.join(RES, name + ".png")).convert("RGBA").tobytes()
        chk(a == b, "A %s.png = make_app_icons.py 결과(다시 돌려 커밋했는지)" % name)
except Exception as e:                                   # noqa: BLE001
    chk(False, "A make_app_icons.py 가 있다", repr(e))

# ── B ──
print("=== B. 새로 등록 ===")
from viewer import photo_default as phd                  # noqa: E402
from viewer import pdf_default as pdd                    # noqa: E402
from viewer.resources_path import resource_path          # noqa: E402
ICO = resource_path("polypix.ico")
EXE = r"C:\Fake\PolyPinax.exe"
notes = []
_old_notify = getattr(phd, "notify_assoc_changed", None)
if _old_notify:
    phd.notify_assoc_changed = lambda: notes.append(1)
reg = FakeReg()
phd.prepare(EXE, True, reg)
icon_key = r"Software\Classes\%s\DefaultIcon" % phd.PROG_ID
chk(bool(ICO) and reg.get(pdd.HKCU, icon_key) == '"%s",0' % ICO, "B 사진 ProgID 아이콘 = polypix.ico", str(reg.get(pdd.HKCU, icon_key)))
chk(len(notes) == 1, "B 등록하면 탐색기에 알린다", str(notes))

# ── C ──
print("=== C. 이미 등록한 PC ===")
fix = getattr(phd, "fix_icons", None)
chk(callable(fix), "C photo_default.fix_icons 가 있다")
if callable(fix):
    reg = FakeReg()
    for pid in ("PolyPix.photo", "PolyPDF.photo"):
        reg.set(pdd.HKCU, r"Software\Classes\%s\shell\open\command" % pid, "", '"%s" "%%1"' % EXE)
        reg.set(pdd.HKCU, r"Software\Classes\%s\DefaultIcon" % pid, "", '"%s",0' % EXE)
    cnt = []
    done = fix(reg, EXE, notify=lambda: cnt.append(1))
    chk(len(done) == 2 and all(reg.get(pdd.HKCU, r"Software\Classes\%s\DefaultIcon" % p) == '"%s",0' % ICO
                               for p in ("PolyPix.photo", "PolyPDF.photo")), "C 옛 exe 아이콘을 polypix.ico 로 고친다", str(done))
    chk(cnt == [1], "C 고쳤으면 한 번 알린다", str(cnt))
    cnt.clear()
    chk(fix(reg, EXE, notify=lambda: cnt.append(1)) == [] and cnt == [], "C 다시 부르면 그대로·알림 없음")
    reg2 = FakeReg()
    fix(reg2, EXE, notify=lambda: None)
    chk(reg2.d == {}, "C 등록이 없는 PC 에는 아무것도 만들지 않는다", str(reg2.d))

# ── D ──
print("=== D. 실행 파일이 바뀌어 명령을 고칠 때 ===")
reg = FakeReg()
OLD = r"C:\Gone\PolyPDF.exe"
for pid in (pdd.PROG_ID, "PolyPix.photo"):
    reg.set(pdd.HKCU, r"Software\Classes\%s\shell\open\command" % pid, "", '"%s" "%%1"' % OLD)
    reg.set(pdd.HKCU, r"Software\Classes\%s\DefaultIcon" % pid, "", '"%s",0' % OLD)
pdd.repair_user_progids(reg, EXE, exists=lambda p: False)
chk(reg.get(pdd.HKCU, r"Software\Classes\PolyPix.photo\DefaultIcon") == '"%s",0' % ICO, "D 사진 ProgID 아이콘 = polypix.ico",
    str(reg.get(pdd.HKCU, r"Software\Classes\PolyPix.photo\DefaultIcon")))
chk(reg.get(pdd.HKCU, r"Software\Classes\%s\DefaultIcon" % pdd.PROG_ID) == '"%s",0' % EXE, "D PDF ProgID 아이콘은 그대로 exe")

# ── E ──
print("=== E. 빌드본 시작 ===")
import main                                              # noqa: E402
chk("fix_icons(Reg(), sys.executable)" in inspect.getsource(main._repair_progids), "E main._repair_progids 가 fix_icons 를 부른다")

print("\n=== " + ("ALL PASS" if not fails else f"FAILURE ({len(fails)})") + " ===")
for m in fails:
    print(" -", m)
sys.stdout.flush()
os._exit(1 if fails else 0)
