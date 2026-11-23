# -*- coding: utf-8 -*-
"""다중 명함 사진 나누기 (명함 SOT §5.26, D31) — 합성한 가짜 그림만(명함 SOT §2.1: 실제 명함 값·사진을 쓰지 않는다).

실제 MainWindow 로(오프스크린, 실제 설정·데이터 폴더를 쓰지 않는다 — 검사 작성 SOT §14.7.2).
A. 찾기 — 어두운 바닥에 흰 명함 셋(기울기 포함)·붙은 둘·한 장·꽉 찬 명함·바닥 닿은 띠
B. 자르기·파일 — `<원본> 명함 01.jpg`, 원본은 `다중 원본`
C. 명함 읽기 창 — 열면 배경에서 세고 확인 창, 테두리 빼기(Delete)·그리기(끌기) 실제 이벤트, 나눠 읽기,
   이미 한 장으로 들어간 명함은 휴지통·DB 에서 지움, '나누지 않음' 은 다시 묻지 않음, [다중 명함 나누기] 단추
"""
import os, sys, tempfile, time, shutil
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QPoint
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtTest import QTest
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_multi_%d" % os.getpid())
fails = []
TMP = Path(tempfile.mkdtemp(prefix="bizcard_multi_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")


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


def finish():
    print("FAILURES: %d" % len(fails))
    for f in fails:
        print("  -", f)
    sys.stdout.flush()
    os._exit(1 if fails else 0)


from PIL import Image, ImageDraw
try:
    from viewer.bizcard import multisplit as M
except Exception as e:
    chk(False, "다중 명함 모듈이 있다", repr(e))
    finish()


def card(w=700, h=400, seed=0):
    """가짜 명함 — 흰 바탕 + 검은 글 줄 + 파란 로고 네모(실제 값 없음)."""
    im = Image.new("RGB", (w, h), (246, 246, 242))
    d = ImageDraw.Draw(im)
    d.rectangle([40, 40, 120, 110], fill=(30, 60, 160))
    for k in range(5):
        d.rectangle([160, 60 + k * 55, 160 + 300 + (seed * 37 + k * 53) % 200, 80 + k * 55], fill=(20, 20, 20))
    return im


def board(cards, size=(2000, 1500), bg=(58, 60, 66)):
    """어두운 바닥에 명함들 [(가운데 x, y, 각도, 폭, 높이)] — 회전해 붙임."""
    im = Image.new("RGB", size, bg)
    for i, (cx, cy, ang, w, h) in enumerate(cards):
        c = card(w, h, i).convert("RGBA").rotate(ang, expand=True, resample=Image.BICUBIC)
        im.paste(c, (int(cx - c.width / 2), int(cy - c.height / 2)), c)
    return im


try:
    F = TMP / "cards"
    F.mkdir()
    multi = board([(500, 350, 3, 700, 400), (1450, 380, -2, 700, 400), (520, 1050, 0, 700, 400)])
    multi.save(F / "photo_a.jpg", quality=92)
    touch = board([(1000, 500, 0, 700, 400), (1000, 900, 0, 700, 400), (1000, 1420, 0, 700, 400)], size=(2000, 1750))   # 위아래로 붙은 둘 + 떨어진 하나
    touch.save(TMP / "touch.jpg", quality=92)
    single = board([(1000, 750, 4, 900, 520)])
    single.save(F / "single_b.jpg", quality=92)
    card(1400, 800).save(F / "full_c.jpg", quality=92)
    strip = board([(500, 350, 0, 700, 400), (1450, 350, 0, 700, 400)])
    ImageDraw.Draw(strip).rectangle([0, 1200, 2000, 1500], fill=(240, 240, 240))      # 바닥에 닿은 밝은 띠(책상) — 명함 아님
    strip.save(TMP / "strip.jpg", quality=92)

    print("=== A. 찾기 ===")
    qa = M.find_cards(M.open_image(F / "photo_a.jpg"))
    chk(len(qa) == 3, "A 흰 명함 셋(기울기 포함)", str(len(qa)))
    ys = [sum(p[1] for p in q) / 4 for q in qa]
    xs = [sum(p[0] for p in q) / 4 for q in qa]
    chk(len(qa) == 3 and xs[0] < xs[1] and ys[2] > ys[0] + 400, "A 차례 — 위 줄 왼쪽→오른쪽, 그다음 아래 줄")
    qt = M.find_cards(M.open_image(TMP / "touch.jpg"))
    chk(len(qt) == 3, "A 위아래로 붙은 두 장도 한 장 크기로 나눠 셋", str(len(qt)))
    chk(len(M.find_cards(M.open_image(F / "single_b.jpg"))) == 1, "A 한 장 사진은 하나(다중 아님)")
    chk(len(M.find_cards(M.open_image(F / "full_c.jpg"))) == 0, "A 사진을 꽉 채운 명함은 찾지 않음(보통 명함 사진)")
    chk(len(M.find_cards(M.open_image(TMP / "strip.jpg"))) == 2, "A 가장자리에 닿은 큰 밝은 띠(책상)는 명함 아님")
    c0 = M.crop(M.open_image(F / "photo_a.jpg"), qa[0]) if qa else None
    chk(c0 is not None and 1.6 < c0.width / c0.height < 1.9 and abs(c0.width - 700) < 40,
        "A 잘라낸 그림은 반듯한 명함 크기(기울기 폄)", str(c0 and c0.size))
    if c0 is not None:
        px = c0.convert("L").load()
        chk(px[c0.width // 2, 8] > 200 and px[8, c0.height // 2] > 200, "A 테두리에 바닥색이 남지 않음")

    print("\n=== B. 자르기·파일 ===")
    FB = TMP / "b"
    FB.mkdir()
    shutil.copy(F / "photo_a.jpg", FB / "photo_a.jpg")
    made = M.split_file(FB / "photo_a.jpg")
    chk([Path(p).name for p in made] == ["photo_a 명함 01.jpg", "photo_a 명함 02.jpg", "photo_a 명함 03.jpg"]
        and not (FB / "photo_a.jpg").exists() and (FB / M.MULTI_DIR / "photo_a.jpg").exists(),
        "B 잘라낸 것은 같은 폴더 '<원본> 명함 01.jpg', 원본은 '다중 원본'", str([Path(p).name for p in made]))
    from viewer.bizcard.importer import scan_folder
    chk(sorted(it.base for it in scan_folder(FB)) == ["photo_a 명함 01", "photo_a 명함 02", "photo_a 명함 03"]
        and all(not it.back for it in scan_folder(FB)), "B 훑기는 한 장씩 앞면으로(원본은 빠짐)")
    chk(M.split_file(F / "single_b.jpg") == [] and (F / "single_b.jpg").exists(), "B 한 장 사진은 건드리지 않음")
    chk(M.candidates(FB) == [], "B 잘라낸 것은 다시 세지 않음")

    print("\n=== C. 명함 읽기 창 ===")
    from viewer.bizcard import recognize as R, store as S, people as P, apply as AP
    def fake_recognize(path, ui_lang="ko"):
        time.sleep(0.02)
        return R.CardResult(name="가짜", company="가짜회사", phones=[("cell", "010-0000-0009")], emails=["user@example.com"],
                            name_cands=[R.Cand("가짜", 4.0)], company_cands=[R.Cand("가짜회사", 2.0)], langs=("한글",))
    R.recognize = fake_recognize
    # 예전에 한 장으로 잘못 들어간 다중 사진 — 명함 행·정리본
    out = F / "정리"
    it_a = next(it for it in scan_folder(F) if it.base == "photo_a")
    AP.apply_cards([{"key": it_a.key, "front": it_a.front, "back": "", "pdf": "", "keep_back": False,
                     "name": "가짜", "company": "예전회사", "langs": ["한글"], "phones": [("cell", "010-0000-0001")]}], out)
    st = S.BizcardStore()
    old = st.card_by_src(it_a.key)
    old_out = os.path.realpath(old["front"]) if old else ""
    st.close()
    chk(old is not None and os.path.exists(old_out), "C 준비 — 예전 한 장짜리 명함 행·정리본")
    from viewer.app import MainWindow
    import modal_guard
    modal_guard.install(label=lambda: "다중 명함", echo=False)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    import viewer.widgets.bookmark_tree as _btm
    TR = TMP / "trash"
    TR.mkdir()
    _btm._trash_fn = lambda: (lambda p: shutil.move(p, str(TR / Path(p).name)))      # 시험용 휴지통
    mw = MainWindow(); mw._skip_save_on_close = True
    mw.show()
    pump(timeout=1.0)
    mw._action_bizcard_import(str(F))
    dlg = mw._bizcard_dlg
    chk(pump(lambda: dlg.multi_dlg is not None and dlg.multi_dlg.isVisible(), timeout=20),
        "C 창을 열면 배경에서 세고 다중 사진이 있으면 확인 창")
    md = dlg.multi_dlg
    if md is None:
        finish()
    chk(md.list.count() == 1 and len(md.view.quads) == 3 and md.list.item(0).checkState() == Qt.CheckState.Checked
        and "1" in md.lbl.text(), "C 확인 창 — 사진 하나·테두리 셋·체크, 예전 명함 지움 안내", md.lbl.text())
    md.resize(1000, 800)
    pump(timeout=0.2)
    v = md.view
    # 실제 마우스로 셋째 테두리를 눌러 고르고 Delete — 빼기
    q3 = v.quads[2]
    cpt = v.to_screen(sum(p[0] for p in q3) / 4, sum(p[1] for p in q3) / 4).toPoint()
    QTest.mouseClick(v, Qt.MouseButton.LeftButton, pos=cpt)
    QTest.keyClick(v, Qt.Key.Key_Delete)
    pump(timeout=0.1)
    chk(len(v.quads) == 2, "C 테두리를 눌러 Delete — 뺌", str(len(v.quads)))
    # 빈 곳(아래 오른쪽)을 끌어 새 테두리 — 바닥 일부를 명함으로(사람이 그린 것)
    a = v.to_screen(1150, 850).toPoint()
    b = v.to_screen(1850, 1250).toPoint()
    QTest.mousePress(v, Qt.MouseButton.LeftButton, pos=a)
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent, QPointF
    QApplication.sendEvent(v, QMouseEvent(QEvent.Type.MouseMove, QPointF(b), Qt.MouseButton.NoButton,
                                          Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    QTest.mouseRelease(v, Qt.MouseButton.LeftButton, pos=b)
    pump(timeout=0.1)
    chk(len(v.quads) == 3 and abs(v.quads[2][1][0] - v.quads[2][0][0] - 700) < 30, "C 빈 곳을 끌면 새 테두리(원래 해상도 좌표)",
        str(v.quads[-1] if v.quads else None))
    QTest.mouseClick(md.btn_ok, Qt.MouseButton.LeftButton)
    chk(pump(lambda: not dlg._multi_busy() and dlg.table.rowCount() == 5 and dlg.bar.value() == 5 and not dlg._pending, timeout=30),
        "C 나누면 폴더를 다시 훑어 읽음 — 잘라낸 셋 + 한 장 + 꽉 찬 명함", "%s %s %s %s" % (dlg.table.rowCount(), dlg.bar.value(), dlg._multi_busy(), len(dlg._pending)))
    names = sorted(os.listdir(F))
    chk("photo_a 명함 03.jpg" in names and "photo_a.jpg" not in names and (F / M.MULTI_DIR / "photo_a.jpg").exists(),
        "C 손으로 고친 테두리대로 셋을 자르고 원본은 '다중 원본'", str(names))
    st = S.BizcardStore()
    chk(st.card_by_src(it_a.key) is None and not os.path.exists(old_out) and (TR / Path(old_out).name).exists(),
        "C 예전 한 장짜리 명함은 DB 에서 지우고 정리본은 휴지통")
    st.close()
    dlg.close()
    pump(timeout=0.3)

    # '나누지 않음' 은 다시 묻지 않음, [다중 명함 나누기] 는 고른 줄을 다시 셈
    F2 = TMP / "cards2"
    F2.mkdir()
    multi.save(F2 / "photo_d.jpg", quality=92)
    mw._action_bizcard_import(str(F2))
    d2 = mw._bizcard_dlg
    pump(lambda: d2.multi_dlg is not None and d2.multi_dlg.isVisible(), timeout=20)
    if d2.multi_dlg is not None:
        d2.multi_dlg.reject_all()
    chk(pump(lambda: not d2._multi_busy() and d2.table.rowCount() == 1 and d2.bar.value() == 1 and not d2._pending, timeout=20)
        and (F2 / "photo_d.jpg").exists(), "C '나누지 않음' — 사진은 그대로 한 장으로 읽음")
    d2.close()
    pump(timeout=0.3)
    mw._action_bizcard_import(str(F2))
    d3 = mw._bizcard_dlg
    pump(lambda: d3.bar.value() == 1 and not d3._pending, timeout=20)
    chk(d3.multi_dlg is None, "C 다음에 열 때는 다시 묻지 않음")
    d3.table.selectRow(0)
    QTest.mouseClick(d3.btn_multi, Qt.MouseButton.LeftButton)
    chk(pump(lambda: d3.multi_dlg is not None and d3.multi_dlg.isVisible(), timeout=20) and len(d3.multi_dlg.view.quads) == 3,
        "C [다중 명함 나누기] 는 고른 줄을 다시 세어 확인 창")
    if d3.multi_dlg is not None:
        d3.multi_dlg.reject_all()
    pump(timeout=0.3)
    d3.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "예외 없이 끝남")
finish()
