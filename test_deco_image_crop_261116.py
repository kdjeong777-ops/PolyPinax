# -*- coding: utf-8 -*-
"""261116-24: 편집 모드 사진 꾸밈 `크롭` — Word 처럼 보이는 범위만, Shift+손잡이 = 그 점만(모양 펴기) (마스터 §4.6.11 '크롭').

실제 마우스·키 이벤트로 손잡이를 끈다. 수정 전 코드에는 `start_image_crop`·`deco_crop` 이 없어 실패한다.
A 네모 크롭(오른쪽 변) — 자리·그림·원본 보관   B 다시 크롭하면 잘린 바깥이 돌아와 넓힐 수 있다   C 크롭 해제
D Esc 취소·틀 밖 누르기 적용   E Shift+꼭짓점 = 그 점만 → 배경에서 펴서 넣음   F 돌린 사진은 끔
G 옆 파일 — 원래 그림은 blobs 로 한 번   H 벡터 조각(등록 이미지) 네모 크롭은 벡터 그대로 잘림
"""
import os, sys, tempfile, shutil, base64, io, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pathlib import Path
from PyQt6.QtWidgets import QApplication

fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra)
    if not cond:
        fails.append(msg)


app = QApplication.instance() or QApplication(sys.argv)
# 사용자 실제 설정 폴더를 쓰지 않는다 — 검사 작성 SOT §14.7.2 의 3
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QPoint, QPointF, QEvent
QStandardPaths.setTestModeEnabled(True)
QCoreApplication.setApplicationName("polypdf_deco_crop_%d" % os.getpid())
from PyQt6.QtGui import QImage, QPixmap, QColor, QMouseEvent
from PyQt6.QtTest import QTest
from PIL import Image
import test_fixtures as _fx
from viewer.page_meta import PageMetaStore
from viewer.widgets.main_view import MainView
from viewer.settings_store import settings_dir

root = Path(tempfile.mkdtemp(prefix="polypdf_decocrop_"))
pdf = root / "doc.pdf"
shutil.copy(Path(_fx.text_pdf()), pdf)
sdir = Path(settings_dir())


def quad_image():
    """200×100 — 왼쪽 위 빨강·오른쪽 위 초록·왼쪽 아래 파랑·오른쪽 아래 노랑."""
    img = QImage(200, 100, QImage.Format.Format_ARGB32)
    for (x, y, c) in ((0, 0, "#ff0000"), (100, 0, "#00ff00"), (0, 50, "#0000ff"), (100, 50, "#ffff00")):
        for yy in range(y, y + 50):
            for xx in range(x, x + 100):
                img.setPixelColor(xx, yy, QColor(c))
    return QPixmap.fromImage(img)


def pil(b64):
    return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")


def send(vp, typ, pos, button=Qt.MouseButton.LeftButton, mods=Qt.KeyboardModifier.NoModifier):
    btns = Qt.MouseButton.NoButton if typ == QEvent.Type.MouseButtonRelease else Qt.MouseButton.LeftButton
    ev = QMouseEvent(typ, QPointF(pos), QPointF(vp.mapToGlobal(pos)), button, btns, mods)
    QApplication.sendEvent(vp, ev)
    app.processEvents()


def drag(mv, a, b, mods=Qt.KeyboardModifier.NoModifier):
    vp = mv.view.viewport()
    send(vp, QEvent.Type.MouseButtonPress, a, mods=mods)
    for k in range(1, 6):
        send(vp, QEvent.Type.MouseMove, QPoint(int(a.x() + (b.x() - a.x()) * k / 5), int(a.y() + (b.y() - a.y()) * k / 5)), mods=mods)
    send(vp, QEvent.Type.MouseButtonRelease, b, mods=mods)


def handle(mv, i):
    c = mv._crop_edit
    q = c._to_v(mv._page_view_rect(), c.pts[i])
    return QPoint(int(round(q.x())), int(round(q.y())))


try:
    st = PageMetaStore(root)
    mv = MainView()
    mv._img_resolver = lambda f, p: st.get_images(f, p)
    mv._img_setter = lambda f, p, imgs: st.set_images(f, p, imgs)
    mv.resize(1000, 1100)
    mv.show()
    mv.load_document(pdf, 0)
    app.processEvents()
    mv.set_draw_mode(True)
    app.processEvents()
    mv.add_image_from_pixmap(quad_image())
    app.processEvents()
    o = mv._img_objects[0]
    rect0, data0 = list(o["rect"]), o["data"] or mv._pix_to_b64(o["pix"])
    pr = mv._page_view_rect()

    # ── A 네모 크롭 — 오른쪽 변 가운데(R=5)를 그림 폭 절반만큼 왼쪽으로 ──
    chk(mv.can_crop_image() and mv.start_image_crop() and mv._crop_edit is not None, "A0 고른 사진에 크롭 틀이 뜬다")
    a = handle(mv, 5)
    wpx = rect0[2] * pr.width()
    drag(mv, a, QPoint(int(a.x() - wpx / 2), a.y()))
    QTest.keyClick(mv.view, Qt.Key.Key_Return); app.processEvents()
    o = mv._img_objects[0]
    chk(mv._crop_edit is None, "A1 Enter 로 적용하고 틀을 닫는다")
    chk(abs(o["rect"][2] - rect0[2] / 2) < 0.01 and abs(o["rect"][0] - rect0[0]) < 1e-4 and abs(o["rect"][3] - rect0[3]) < 1e-4,
        "A2 왼쪽·위·높이는 그대로, 폭이 절반 — 종이 위 크기는 그대로 잘린 만큼만", f"{[round(v, 4) for v in o['rect']]} vs {[round(v, 4) for v in rect0]}")
    im = pil(o["data"]) if o.get("data") else None
    src_w = pil(data0).width
    chk(im is not None and abs(im.width - src_w / 2) <= 3 and im.getpixel((5, 5))[0] > 200 and im.getpixel((im.width - 5, 5))[1] < 60,
        "A3 보이는 그림 = 왼쪽 절반(빨강·파랑만)", str(im.size if im else None))
    ex = o.get("extra") or {}
    chk(ex.get("crop_src") == data0 and "crop" in ex, "A4 원래 그림을 꾸밈 안에 보관한다")
    chk(st.get_images(str(pdf), 0)[0].get("crop_src") == data0, "A5 옆 파일에도 원래 그림·크롭 값이 저장된다")

    # ── B 다시 크롭 — 잘린 바깥이 돌아와 넓힌다 ──
    mv._img_selected = 0
    mv.start_image_crop()
    c = mv._crop_edit
    chk(abs(c.full[2] - rect0[2]) < 1e-3 and abs(c.full[0] - rect0[0]) < 1e-3, "B1 다시 크롭하면 원래 그림 자리가 그대로 돌아온다",
        f"{c.full} vs {rect0}")
    a = handle(mv, 5)
    drag(mv, a, QPoint(int(a.x() + wpx), a.y()))          # 바깥으로 — 원래 그림 끝에서 멈춘다
    QTest.keyClick(mv.view, Qt.Key.Key_Return); app.processEvents()
    o = mv._img_objects[0]
    chk(abs(o["rect"][2] - rect0[2]) < 0.01, "B2 바깥으로 끌면 원래 폭까지만(그림 밖으로는 못 나간다)",
        f"{o['rect'][2]:.4f} vs {rect0[2]:.4f}")

    # ── C 크롭 해제 ──
    mv._img_selected = 0
    mv.start_image_crop()
    a = handle(mv, 6)                                       # 아래 변
    hpx = rect0[3] * pr.height()
    drag(mv, a, QPoint(a.x(), int(a.y() - hpx / 2)))
    QTest.keyClick(mv.view, Qt.Key.Key_Enter); app.processEvents()
    chk(mv.image_cropped(), "C0 아래 변 크롭(전제)")
    mv._img_selected = 0
    chk(mv.reset_image_crop(), "C1 크롭 해제")
    o = mv._img_objects[0]
    chk(o["data"] == data0 and all(abs(x - y) < 1e-4 for x, y in zip(o["rect"], rect0)) and "crop" not in (o.get("extra") or {}),
        "C2 원래 그림·원래 자리로, 크롭 값은 지운다")

    # ── D Esc 취소 · 틀 밖 누르기 적용 ──
    mv._img_selected = 0
    mv.start_image_crop()
    a = handle(mv, 7)
    drag(mv, a, QPoint(int(a.x() + wpx / 3), a.y()))
    QTest.keyClick(mv.view, Qt.Key.Key_Escape); app.processEvents()
    o = mv._img_objects[0]
    chk(mv._crop_edit is None and o["data"] == data0 and all(abs(x - y) < 1e-4 for x, y in zip(o["rect"], rect0)),
        "D1 Esc — 크롭 전 그대로")
    mv._img_selected = 0
    mv.start_image_crop()
    a = handle(mv, 7)
    drag(mv, a, QPoint(int(a.x() + wpx / 4), a.y()))
    out = QPoint(int(pr.left() + pr.width() * 0.95), int(pr.top() + pr.height() * 0.95))
    send(mv.view.viewport(), QEvent.Type.MouseButtonPress, out)
    send(mv.view.viewport(), QEvent.Type.MouseButtonRelease, out)
    o = mv._img_objects[0]
    chk(mv._crop_edit is None and o["rect"][0] > rect0[0] + 0.01, "D2 틀 밖을 누르면 적용", f"{o['rect'][0]:.4f}")
    mv._img_selected = 0
    mv.reset_image_crop()

    # ── E Shift+꼭짓점 = 그 점만 → 펴기(배경) ──
    mv._img_selected = 0
    mv.start_image_crop()
    a = handle(mv, 0)
    drag(mv, a, QPoint(int(a.x() + wpx / 5), int(a.y() + hpx / 4)), mods=Qt.KeyboardModifier.ShiftModifier)
    c = mv._crop_edit
    from viewer.widgets import deco_crop
    chk(not deco_crop.is_rect(c.pts) and abs(c.pts[1][1]) < 1e-6, "E1 Shift — 왼쪽 위 점만 옮기고 오른쪽 위는 그대로", str(c.pts[:2]))
    QTest.keyClick(mv.view, Qt.Key.Key_Return)
    t0 = time.time()
    while time.time() - t0 < 10 and "crop" not in (mv._img_objects[0].get("extra") or {}):
        app.processEvents(); time.sleep(0.02)
    o = mv._img_objects[0]
    ex = o.get("extra") or {}
    chk("crop" in ex and not deco_crop.is_rect([tuple(p) for p in ex["crop"]["pts"]]), "E2 배경에서 펴고 끝나면 바꿔 넣는다")
    im = pil(o["data"])
    chk(im.getpixel((2, 2))[0] > 180 and im.getpixel((im.width - 3, im.height - 3))[0] > 180
        and im.getpixel((im.width - 3, im.height - 3))[1] > 180, "E3 편 그림 — 왼쪽 위 빨강·오른쪽 아래 노랑", str(im.size))
    mv._img_selected = 0
    mv.start_image_crop()
    chk(not deco_crop.is_rect(mv._crop_edit.pts), "E4 다시 크롭하면 옮긴 점이 그대로 보인다")
    mv.finish_image_crop(False)
    mv._img_selected = 0
    mv.reset_image_crop()

    # ── F 돌린 사진(사용자 결정 '돌린 것도 포함') — 0°·90°·30° ──
    def dist(a, b):
        return ((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2) ** 0.5

    for ang in (0.0, 90.0, 30.0):
        o = mv._img_objects[0]
        o.update(rot=ang, rect=list(rect0), data=data0, pix=mv._b64_to_pix(data0), extra={})
        mv._img_selected = 0
        before = mv._img_handle_points(o, pr)
        chk(mv.can_crop_image() and mv.start_image_crop(), f"F1 {ang:g}° — 돌린 사진도 크롭 틀이 뜬다")
        hr, hl = handle(mv, 5), handle(mv, 7)
        chk(dist(QPointF(hr), before["r"]) < 2 and dist(QPointF(hl), before["l"]) < 2,
            f"F2 {ang:g}° — 손잡이가 돌린 사진의 오른쪽·왼쪽 변 가운데에 있다", f"{hr} vs {before['r']}")
        tgt = QPoint(int(round(hr.x() + (hl.x() - hr.x()) / 2)), int(round(hr.y() + (hl.y() - hr.y()) / 2)))
        drag(mv, hr, tgt)                                   # 돌린 축을 따라 오른쪽 변을 절반까지
        QTest.keyClick(mv.view, Qt.Key.Key_Return); app.processEvents()
        o = mv._img_objects[0]
        after = mv._img_handle_points(o, pr)
        chk(abs(float(o.get("rot", 0)) - ang) < 1e-6 and abs(pil(o["data"]).width - src_w / 2) <= 4,
            f"F3 {ang:g}° — 각도 그대로, 그림은 왼쪽 절반", str(pil(o["data"]).size))
        chk(dist(after["l"], before["l"]) < 2 and dist(after["tl"], before["tl"]) < 2 and dist(after["bl"], before["bl"]) < 2,
            f"F4 {ang:g}° — 자르지 않은 왼쪽 변은 보이는 자리 그대로(돌림 축이 바뀌어도)",
            f"l {after['l']} vs {before['l']}")
        chk(dist(after["r"], QPointF(tgt)) < 3, f"F5 {ang:g}° — 새 오른쪽 변은 놓은 자리", f"{after['r']} vs {tgt}")
        mv._img_selected = 0
        mv.start_image_crop()
        chk(dist(QPointF(handle(mv, 7)), before["l"]) < 2 and dist(QPointF(handle(mv, 5)), QPointF(tgt)) < 3,
            f"F6 {ang:g}° — 다시 크롭하면 원래 그림 자리·지금 틀이 돌린 채 그대로")
        a0 = handle(mv, 0)
        drag(mv, a0, QPoint(int(a0.x() + (hr.x() - hl.x()) / 8), int(a0.y() + (hr.y() - hl.y()) / 8)),
             mods=Qt.KeyboardModifier.ShiftModifier)
        c = mv._crop_edit
        chk(not deco_crop.is_rect(c.pts) and abs(c.pts[1][0] - 0.5) < 0.02 and abs(c.pts[1][1]) < 1e-6,
            f"F7 {ang:g}° — Shift+꼭짓점은 그 점만(돌린 좌표에서도 다른 점은 그대로)", str([tuple(round(v, 3) for v in p) for p in c.pts[:2]]))
        mv.finish_image_crop(False)
        mv._img_selected = 0
        mv.reset_image_crop()
        back = mv._img_handle_points(mv._img_objects[0], pr)
        chk(dist(back["l"], before["l"]) < 2 and dist(back["r"], before["r"]) < 2, f"F8 {ang:g}° — 크롭 해제하면 원래 자리로")
    mv._img_objects[0]["rot"] = 0.0

    # ── G 옆 파일 — 원래 그림은 blobs ──
    mv._img_selected = 0
    mv.start_image_crop()
    a = handle(mv, 5)
    drag(mv, a, QPoint(int(a.x() - wpx / 3), a.y()))
    mv.finish_image_crop(True)
    st.save()
    raw = st._data["files"]["doc.pdf"]["images"]["0"][0]
    from viewer import page_meta as _pm
    chk("crop_src" in _pm._BLOB_FIELDS and "crop_pdf" in _pm._BLOB_FIELDS
        and (str(raw.get("crop_src", "")).startswith("@") or len(str(raw.get("crop_src", ""))) <= _pm.BLOB_MIN),
        "G1 원래 그림(crop_src)·원래 조각(crop_pdf)도 큰 값이면 blobs 에 한 번", str(raw.get("crop_src", ""))[:8])
    big = "B" * (_pm.BLOB_MIN * 2)
    st.set_images(str(pdf), 1, [dict(raw, crop_src=big)])
    st.set_images(str(pdf), 2, [dict(raw, crop_src=big)])
    st.save()
    from viewer import bg_write
    bg_write.flush()                                         # 옆 파일 쓰기는 배경 줄(261108-15)
    chk(bg_write.read_text(root / "page_meta.json").count(big) == 1, "G2 같은 원래 그림을 두 쪽에 — 파일에는 한 번")

    # ── H 벡터 조각 네모 크롭 ──
    import fitz
    from viewer import stamp_core
    d = fitz.open()
    pg = d.new_page(width=200, height=60)
    pg.insert_text((10, 40), "LEFT", fontsize=24)
    pg.insert_text((120, 40), "RIGHT", fontsize=24)
    piece = d.tobytes()
    cut = stamp_core.crop_piece(piece, (0.0, 0.0, 0.5, 1.0))
    with fitz.open(stream=cut, filetype="pdf") as q:
        chk(abs(q[0].rect.width - 100) < 0.5 and "LEFT" in q[0].get_text("text", clip=q[0].rect),
            "H1 벡터 조각을 반만 — 폭 100pt, 왼쪽 글은 글자로", str(q[0].rect))
    o = mv._img_objects[0]
    o["extra"] = {"pdf": base64.b64encode(piece).decode("ascii")}
    o["data"] = mv._pix_to_b64(o["pix"])
    mv._img_selected = 0
    mv.start_image_crop()
    a = handle(mv, 5)
    drag(mv, a, QPoint(int(a.x() - wpx / 2), a.y()))
    mv.finish_image_crop(True)
    ex = mv._img_objects[0].get("extra") or {}
    chk(ex.get("crop_pdf") and ex.get("pdf") and ex["pdf"] != ex["crop_pdf"], "H2 네모 크롭 — 원래 조각은 보관하고 잘린 조각을 벡터로")
    mv._img_selected = 0
    mv.reset_image_crop()
    ex = mv._img_objects[0].get("extra") or {}
    chk(ex.get("pdf") and "crop_pdf" not in ex, "H3 크롭 해제 — 원래 벡터 조각으로")
finally:
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(sdir, ignore_errors=True)

print()
print("ALL PASS" if not fails else f"{len(fails)} FAIL: {fails}")
sys.exit(1 if fails else 0)
