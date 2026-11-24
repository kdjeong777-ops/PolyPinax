# -*- coding: utf-8 -*-
"""261122-15: 사진 모드 인물 자동 해시태그 — 얼굴이 하나 이상이면 #인물, 딱 하나면 #인물1 도 (태그 SOT §5.7 '인물 판정', 사진 보기 SOT §4.42).

실제 MainWindow 로(오프스크린, 실제 설정 폴더를 쓰지 않는다 — 검사 작성 SOT §14.7.2 의 3). 사진은 검사가 만든다(실제 사용자 사진 없음).
얼굴 찾기(공용 `viewer/win_face.detect`·`available`, 261122-19 — 종전 명함 `face_thumb.faces`)는 가짜로 바꿔 끼운다 — 그림 색으로 얼굴 수를 정한다(PC 마다 얼굴 찾기 유무가 달라 검사가 흔들리지 않게).
A. 규칙 — 얼굴 수 → 태그(0 = 없음, 1 = 인물·인물1, 2 이상 = 인물)
B. 작은 얼굴은 세지 않는다(FACE_MIN_FRAC), 얼굴 찾기를 못 쓰면 None(판정 '아직')
C. 사진 모드 폴더 열기 — 색인 훑기 뒤 인물 워커가 붙인다(부분 `people`), 스크린샷은 판정하지 않는다, 판정 표시(색인 `people`)로 다시 열면 다시 보지 않는다
D. 사용자가 뗀 인물 태그는 다시 판정해도 붙지 않는다(거절)
E. 설정 `photo_people` 끄면 붙이지 않는다 · 환경설정 체크
G. (261122-19) 얼굴 찾기 일시 오류(None)는 '얼굴 없음' 으로 굳지 않는다 — 그 사진은 '아직', 다음 훑기에 다시 · 잇따른 오류는 PEOPLE_ERR_MAX 에서 멈춤
F. (261122-19) 자동 칸 차례 meta·kind·people·ocr · 환경설정에서 끄고 저장하면 돌던 종류·인물 워커를 곧바로 멈춘다(붙은 태그는 그대로)
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
    from viewer import win_face
    win_face.available = lambda: False
    chk(callable(getattr(PT, "people_tag", None)) and PT.people_tag(str(y)) is None, "B 얼굴 찾기를 못 쓰는 PC — None(판정 '아직')")
    chk(PT.people_tag(str(y), lambda img: None) is None, "B 그 사진만의 일시 오류(None) — 0 이 아니라 None(261122-19)",
        str(PT.people_tag(str(y), lambda img: None)))

    # ── C ──
    print("=== C. 사진 모드 폴더 열기 ===")
    win_face.detect = fake_faces                       # 가짜 얼굴 찾기(검사 안에서만)
    win_face.available = lambda: True
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

    # ── F (261122-19) ──
    print("=== F. 자동 칸 차례 · 끄면 돌던 워커 멈춤 ===")
    Q = str(pix / "order.jpg")
    for part, tg in (("ocr", ["영수증"]), ("people", ["인물"]), ("kind", ["서류"]), ("meta", ["2026-11-05"])):
        tags.set_auto_part(Q, part, tg)
    chk(tags.get_auto(Q) == ["2026-11-05", "서류", "인물", "영수증"], "F 자동 칸 차례 meta·kind·people·ocr(태그 SOT §5.7 '저장')",
        str(tags.get_auto(Q)))

    class _W:
        def __init__(self):
            self.cancelled = False

        def request_cancel(self):
            self.cancelled = True

    def gate(**kw):                                    # 환경설정 [적용]·[확인] 의 실제 길
        wk, wp = _W(), _W()
        mw._photo_kinder, mw._photo_peopler = wk, wp
        mw._settings_apply(dict(mw._prefs, **dict(dict(photo_auto_tag=True, photo_kind_ocr=True, photo_people=True), **kw)))
        return wk, wp
    wk, wp = gate()
    chk(not wk.cancelled and not wp.cancelled and mw._photo_peopler is wp, "F 모두 켬 — 돌던 워커는 그대로")
    wk, wp = gate(photo_people=False)
    chk(wp.cancelled and mw.__dict__.get("_photo_peopler") is None and not wk.cancelled,
        "F photo_people 끄고 저장 — 돌던 인물 워커만 곧바로 멈춘다", "%s %s" % (wp.cancelled, wk.cancelled))
    wk, wp = gate(photo_kind_ocr=False)
    chk(wk.cancelled and not wp.cancelled, "F photo_kind_ocr 끄고 저장 — 종류 워커만 멈춘다", "%s %s" % (wk.cancelled, wp.cancelled))
    wk, wp = gate(photo_auto_tag=False)
    chk(wk.cancelled and wp.cancelled, "F 사진 자동 해시태그를 끄면 둘 다 멈춘다", "%s %s" % (wk.cancelled, wp.cancelled))
    chk("인물" in tags.get(str(TWO)), "F 끈 뒤에도 이미 붙은 #인물 은 그대로", str(tags.get(str(TWO))))
    mw._photo_kinder = mw._photo_peopler = None

    # ── G (261122-19) ──
    print("=== G. 얼굴 찾기 일시 오류 ===")
    mw._settings_apply(dict(mw._prefs, photo_auto_tag=True, photo_people=True, photo_kind_ocr=False))
    ERR = pix / "err.jpg"
    photo(ERR, (230, 30, 30))                          # 얼굴 하나 색 — 그런데 이번 훑기에서는 오류
    for i in range(6):
        photo(pix / ("err%d.jpg" % i), (230, 30, 30))  # 오류가 PEOPLE_ERR_MAX 보다 많이 잇따르게
    calls = []

    def flaky(img):
        calls.append(1)
        return None                                    # 일시 오류
    win_face.detect = flaky
    started.clear()
    mw._photo_index_start()                            # 새 사진을 색인 — 끝나면 인물 워커(실제 길)
    chk(pump(lambda: "done" in started, timeout=60), "G 오류 훑기도 끝난다", str(started))
    pump(timeout=0.8)
    chk(not tags.get_auto_part(str(ERR), "people"), "G 오류 난 사진에 태그 없음", str(tags.get_auto(str(ERR))))
    con = photo_index.connect()
    try:
        left = [Path(p).name for _k, p in photo_index.people_todo(con, photo_index.norm_folder(pix), PT.PEOPLE_VER)]
        prow = con.execute("SELECT people FROM photos WHERE name=?", ("err.jpg",)).fetchone()
    finally:
        con.close()
    chk("err.jpg" in left, "G 오류 난 사진은 판정 '아직'(people NULL) — '사람 없음' 으로 굳지 않는다", "%s %s" % (left, prow))
    # 잇따른 오류 상한 — 워커 한 번을 직접(폴더 감시가 훑기를 한 번 더 부를 수 있어 앱 길로는 횟수가 흔들린다)
    from viewer.photo_controller import PhotoPeopleWorker
    calls.clear()
    PhotoPeopleWorker(str(pix), detect=flaky).run()
    chk(len(calls) == PT.PEOPLE_ERR_MAX, "G 잇따른 오류는 PEOPLE_ERR_MAX 에서 그 훑기를 멈춘다", str(len(calls)))
    win_face.detect = fake_faces                       # 오류가 풀린 뒤 다음 훑기
    started.clear()
    mw._photo_people_start(str(mw._folder))
    chk(pump(lambda: "done" in started, timeout=60), "G 다음 훑기")
    pump(timeout=0.8)
    chk(tags.get_auto_part(str(ERR), "people") == ["인물", "인물1"], "G 다음 훑기에서 다시 판정해 붙인다", str(tags.get_auto(str(ERR))))
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
