# -*- coding: utf-8 -*-
"""261122-15: 사진 모드 인물 자동 해시태그 — 얼굴이 하나 이상이면 #인물, 딱 하나면 #인물1 도 (태그 SOT §5.7 '인물 판정', 사진 보기 SOT §4.42).

실제 MainWindow 로(오프스크린, 실제 설정 폴더를 쓰지 않는다 — 검사 작성 SOT §14.7.2 의 3). 사진은 검사가 만든다(실제 사용자 사진 없음).
얼굴 찾기(윈도우 내장 `face_thumb.faces`)는 가짜로 바꿔 끼운다 — 그림 색으로 얼굴 수를 정한다(PC 마다 얼굴 찾기 유무가 달라 검사가 흔들리지 않게).
A. 규칙 — 얼굴 수 → 태그(0 = 없음, 1 = 인물·인물1, 2 이상 = 인물)
B. 작은 얼굴은 세지 않는다(FACE_MIN_FRAC), 얼굴 찾기를 못 쓰면 None(판정 '아직')
C. 사진 모드 폴더 열기 — 색인 훑기 뒤 인물 워커가 붙인다(부분 `people`), 스크린샷은 판정하지 않는다, 판정 표시(색인 `people`)로 다시 열면 다시 보지 않는다
D. 사용자가 뗀 인물 태그는 다시 판정해도 붙지 않는다(거절)
E. 설정 `photo_people` 끄면 붙이지 않는다 · 환경설정 체크
"""
import os, sys, tempfile, shutil, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2 의 3
from PyQt6.QtWidgets import QApplication
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_photo_people_%d" % os.getpid())
import modal_guard
modal_guard.install(label=lambda: "사진 인물 태그", echo=False)   # 검사 작성 SOT §14.7.2 의 6
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def pump(cond=None, timeout=15.0):
    t = time.monotonic()
    while time.monotonic() - t < timeout:
        app.processEvents()
        if cond is not None and cond():
            return True
        if cond is None and time.monotonic() - t > 0.3:
            return True
        time.sleep(0.01)
    return False


def photo(path, color, size=(1200, 900), fmt="JPEG"):
    from PIL import Image
    im = Image.new("RGB", size, color)
    ex = Image.Exif()
    ex[0x010F], ex[0x0110] = "Apple", "iPhone 15 Pro"            # 카메라 사진(스크린샷이 아니다)
    if fmt == "PNG":
        im.save(path, "PNG")
    else:
        im.save(path, "JPEG", exif=ex)


def fake_faces(img):
    """그림 가운데 색 → 얼굴: 빨강 = 하나, 초록 = 둘, 노랑 = 큰 얼굴 하나 + 작은 얼굴 둘, 그 밖 = 없음."""
    r, g, b = img.convert("RGB").getpixel((img.width // 2, img.height // 2))
    W, H = img.size
    big = (W * 0.3, H * 0.2, H * 0.3, H * 0.3)
    if r > 200 and g < 80:
        return [big]
    if g > 200 and r < 80:
        return [big, (W * 0.6, H * 0.2, H * 0.3, H * 0.3)]
    if r > 200 and g > 200 and b < 80:
        return [big, (5, 5, 6, 6), (40, 5, 8, 8)]
    return []


tmp = Path(tempfile.mkdtemp(prefix="polypdf_people_"))
try:
    from viewer import photo_tags as PT
    # ── A ──
    print("=== A. 규칙 ===")
    pt = getattr(PT, "people_tags", None)
    chk(callable(pt), "A photo_tags.people_tags 가 있다")
    if callable(pt):
        chk(pt(0) == [] and pt(1) == ["인물", "인물1"] and pt(2) == ["인물"] and pt(5) == ["인물"],
            "A 0 = 없음 · 1 = 인물·인물1 · 2 이상 = 인물", str([pt(0), pt(1), pt(2)]))

    # ── B ──
    print("=== B. 작은 얼굴·얼굴 찾기 없음 ===")
    y = tmp / "yellow.jpg"
    photo(y, (240, 230, 20))
    fc = getattr(PT, "face_count", None)
    chk(callable(fc) and fc(str(y), fake_faces) == 1, "B 작은 얼굴(짧은 변의 FACE_MIN_FRAC 미만)은 세지 않는다",
        str(fc(str(y), fake_faces) if callable(fc) else None))
    from viewer.bizcard import face_thumb
    saved = face_thumb._no_detector
    face_thumb._no_detector = True
    chk(callable(getattr(PT, "people_tag", None)) and PT.people_tag(str(y)) is None, "B 얼굴 찾기를 못 쓰는 PC — None(판정 '아직')")
    face_thumb._no_detector = saved

    # ── C ──
    print("=== C. 사진 모드 폴더 열기 ===")
    face_thumb.faces = fake_faces                      # 가짜 얼굴 찾기(검사 안에서만)
    face_thumb._no_detector = False
    pix = tmp / "pix"
    pix.mkdir()
    ONE, TWO, NONE = pix / "one.jpg", pix / "two.jpg", pix / "none.jpg"
    photo(ONE, (230, 30, 30))
    photo(TWO, (30, 230, 30))
    photo(NONE, (30, 30, 230))
    SS = pix / "Screenshot_2026.png"
    photo(SS, (230, 30, 30), size=(1080, 2340), fmt="PNG")       # 얼굴 색이라도 스크린샷은 판정하지 않는다

    from viewer.app import MainWindow
    mw = MainWindow(); mw._skip_save_on_close = True
    mw.resize(1200, 800); mw.show(); pump()
    mw._prefs["photo_kind_ocr"] = False                # 종류(OCR)는 이 검사와 무관 — 느리다
    chk(mw._prefs.get("photo_people") is True, "E 설정 photo_people 기본 켬", str(mw._prefs.get("photo_people")))
    started = []
    real_start = getattr(mw, "_photo_people_start", None)
    if callable(real_start):
        def _ps(folder):
            real_start(folder)
            w = mw.__dict__.get("_photo_peopler")
            started.append(w)
            if w is not None:
                w.finished.connect(lambda: started.append("done"))
        mw._photo_people_start = _ps
    mw._prefs.setdefault("picture", {})["view_kind"] = "mixed"
    mw._photo_apply_view_kind()
    mw._set_photo_mode(True)
    mw.open_folder(pix)
    chk(pump(lambda: "done" in started, timeout=60), "C 색인 훑기 뒤 인물 워커가 돌고 끝난다", str(started))
    pump(timeout=1.0)
    tags = mw.bookmark_tree._tags
    chk(tags.get_auto_part(str(ONE), "people") == ["인물", "인물1"], "C 얼굴 하나 — #인물·#인물1", str(tags.get_auto(str(ONE))))
    chk(tags.get_auto_part(str(TWO), "people") == ["인물"], "C 얼굴 둘 — #인물", str(tags.get_auto(str(TWO))))
    chk(not tags.get_auto_part(str(NONE), "people"), "C 얼굴 없음 — 붙이지 않는다", str(tags.get_auto(str(NONE))))
    chk(not tags.get_auto_part(str(SS), "people"), "C 스크린샷은 판정하지 않는다", str(tags.get_auto(str(SS))))
    from viewer import photo_index
    con = photo_index.connect()
    try:
        left = photo_index.people_todo(con, photo_index.norm_folder(pix), PT.PEOPLE_VER) if hasattr(photo_index, "people_todo") else None
    finally:
        con.close()
    chk(left == [], "C 판정한 사진은 색인 `people` 로 표시 — 다시 보지 않는다", str(left))
    names = sorted(x["name"] for x in photo_index.search("#인물1", folder=pix))
    chk(names == ["one.jpg"], "C 색인 글로 #인물1 찾기", str(names))

    # ── D ──
    print("=== D. 뗀 태그는 다시 붙지 않는다 ===")
    tags.reject(str(ONE), ["인물1"])
    con = photo_index.connect()
    try:
        con.execute("UPDATE photos SET people=NULL")    # 사진이 바뀐 것처럼 판정을 '아직' 으로
        con.commit()
    finally:
        con.close()
    started.clear()
    mw._photo_people_start(str(mw._folder))
    chk(pump(lambda: "done" in started, timeout=60), "D 다시 판정")
    pump(timeout=1.0)
    chk(tags.get_auto(str(ONE)).count("인물1") == 0 and "인물" in tags.get(str(ONE)), "D 뗀 #인물1 은 다시 붙지 않고 #인물 은 남는다",
        str(tags.get(str(ONE))))

    # ── E ──
    print("=== E. 설정 끄기 ===")
    NEW = pix / "new.jpg"
    photo(NEW, (230, 30, 30))
    mw._prefs["photo_people"] = False
    started.clear()
    mw._photo_people_start(str(mw._folder))
    pump(timeout=1.5)
    chk(started == [None] and not tags.get_auto_part(str(NEW), "people"), "E 끄면 인물 워커를 돌리지 않는다", str(started))
    from viewer.widgets.settings_dialog import SettingsDialog
    sd = SettingsDialog(dict(mw._prefs, photo_people=False), mw, host=mw)
    cb = getattr(sd, "chk_photo_people", None)
    chk(cb is not None and not cb.isChecked(), "E 환경설정에 '사람이 있으면 #인물' 체크(지금 값)")
    if cb is not None:
        cb.setChecked(True)
        chk(sd.result_prefs().get("photo_people") is True, "E 체크를 켜면 저장 값도 켬")
    sd.deleteLater()
except Exception:
    import traceback
    traceback.print_exc()
    fails.append("예외")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n=== " + ("ALL PASS" if not fails else f"FAILURE ({len(fails)})") + " ===")
for m in fails:
    print(" -", m)
sys.stdout.flush()
os._exit(1 if fails else 0)          # Qt 소멸 단계 충돌을 피한다(MainWindow 검사 관례)
