# -*- coding: utf-8 -*-
"""꾸미기 체크 — 서명 왼쪽 단추, 칸 맞춤·기본 크기·모양·색, 서식 체크박스 켜기 (편집 꾸밈 SOT §4.6.14, 261128-13).

A 단추 자리 — 꾸미기 줄 이미지 넣기 · 체크 · 서명 차례, 그린 아이콘
B 실제 단추·마우스 — 그린 칸(□)을 누르면 칸 가운데·칸의 75% 크기, 빈 곳은 누른 자리 가운데 4 mm,
  벡터 조각(`pdf`)·모양 표지(`check`), 선 굵기 = 크기 × W_FRAC(벡터 조각에서), 켜진 채 반복·Esc 로 끔
C ▾ 모양(● 꽉 찬 원)·크기(5 mm) · 색 = 고른 스타일 색(없으면 검정)
D 서식 체크박스 — 누르면 표시를 넣지 않고 보류(form_fill), 연 문서에 켜짐, 다시 누르면 보류가 사라짐, [저장] 길(write_fields)로 파일에 켜짐,
  라디오 단추는 같은 무리의 다른 단추를 끈다
E 실제 MainWindow — 체크 도구로 서식 체크박스를 누르고(실제 마우스) 책갈피창 [저장] → 파일에 켜짐, 보류가 빈다
수정 전 코드에는 체크 단추·check_mark·form_fill 이 없어 실패한다.
"""
import os, sys, tempfile, shutil
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pathlib import Path
from PyQt6.QtWidgets import QApplication

fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


app = QApplication.instance() or QApplication(sys.argv[:1])
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QPoint
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
QCoreApplication.setApplicationName("polypdf_check_%d" % os.getpid())
from PyQt6.QtTest import QTest
import fitz
import time
import modal_guard
modal_guard.install(label=lambda: "꾸미기 체크", echo=False)   # 검사 작성 SOT §14.7.2 — 뜬 창에 서지 않게


def pump(cond=None, timeout=10.0):
    t = time.monotonic()
    while time.monotonic() - t < timeout:
        app.processEvents()
        if cond is not None and cond():
            return True
        if cond is None and time.monotonic() - t > 0.3:
            return True
        time.sleep(0.01)
    return False

root = Path(tempfile.mkdtemp(prefix="polypdf_check_"))
PT_MM = 72 / 25.4
BOX = fitz.Rect(100, 100, 100 + 5 * PT_MM, 100 + 5 * PT_MM)     # 5 mm 칸


def make_pdf(path):
    d = fitz.open()
    p = d.new_page(width=595, height=842)
    p.draw_rect(BOX, color=(0, 0, 0), width=0.8)                  # 그린 칸
    p.insert_text((BOX.x1 + 6, BOX.y1 - 2), "agree", fontsize=10)
    for name, typ, r in (("chk", fitz.PDF_WIDGET_TYPE_CHECKBOX, (100, 300, 114, 314)),
                         ("yn", fitz.PDF_WIDGET_TYPE_RADIOBUTTON, (100, 400, 114, 414)),
                         ("yn", fitz.PDF_WIDGET_TYPE_RADIOBUTTON, (160, 400, 174, 414))):
        w = fitz.Widget(); w.field_type = typ; w.field_name = name; w.rect = fitz.Rect(*r); w.field_value = False
        p.add_widget(w)
    tmp = str(path) + ".0.pdf"
    d.save(tmp); d.close()
    d = fitz.open(tmp)                                            # 라디오 켬 상태 이름을 단추마다 다르게(실제 양식처럼)
    rad = [w.xref for w in d[0].widgets() if w.field_type == fitz.PDF_WIDGET_TYPE_RADIOBUTTON]
    for xr, nm in zip(rad, ("Yes", "No")):
        d.update_object(xr, d.xref_object(xr).replace("/False", "/" + nm).replace("/AS /" + nm, "/AS /Off"))
    d.save(str(path)); d.close()


pdf = root / "form.pdf"
make_pdf(pdf)
try:
    from viewer import check_mark, form_fill
    from viewer.page_meta import PageMetaStore
    from viewer.widgets.main_view import MainView
    st = PageMetaStore(root)
    mv = MainView()
    mv._img_resolver = lambda f, p: st.get_images(f, p)
    mv._img_setter = lambda f, p, imgs: st.set_images(f, p, imgs)
    mv.resize(1000, 1100); mv.show()
    mv.load_document(pdf, 0); app.processEvents()
    mv.set_draw_mode(True); app.processEvents()

    # ── A 단추 자리 ──
    hb = mv._draw_bar.layout()
    order = [hb.itemAt(i).widget() for i in range(hb.count())]
    chk(mv._check_btn in order and order.index(mv._check_btn) == order.index(mv._image_btn) + 1
        and order.index(mv.btn_sign) == order.index(mv._check_btn) + 1, "A1 꾸미기 줄 차례 — 이미지 넣기 · 체크 · 서명")
    chk(not mv._check_btn.icon().isNull() and mv._check_btn.text() == "", "A2 체크 단추는 그린 아이콘")

    # ── B 단추·마우스 ──
    QTest.mouseClick(mv._check_btn, Qt.MouseButton.LeftButton); app.processEvents()
    chk(mv._draw_kind == "check" and mv._draw_tool == ("check", "v"), "B1 단추를 누르면 체크 도구(✓)", str(mv._draw_tool))
    pr = mv._page_view_rect()
    pw, ph = mv.page_size_pt()

    def click_pt(x, y):
        at = QPoint(int(pr.left() + pr.width() * x / pw), int(pr.top() + pr.height() * y / ph))
        QTest.mouseClick(mv.view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at)
        app.processEvents()

    click_pt(BOX.x0 + 4, BOX.y0 + 5)                              # 칸 안 한쪽을 눌러도
    chk(len(mv._img_objects) == 1, "B2 칸을 누르면 체크 하나", str(len(mv._img_objects)))
    if mv._img_objects:
        o = mv._img_objects[0]
        side = BOX.width * check_mark.BOX_FIT
        cx = (o["rect"][0] + o["rect"][2] / 2) * pw; cy = (o["rect"][1] + o["rect"][3] / 2) * ph
        chk(abs(o["rect"][2] * pw - side) < 0.6 and abs(o["rect"][3] * ph - side) < 0.6,
            "B3 칸의 75% 크기", f"{o['rect'][2] * pw:.2f} vs {side:.2f}")
        chk(abs(cx - (BOX.x0 + BOX.x1) / 2) < 0.6 and abs(cy - (BOX.y0 + BOX.y1) / 2) < 0.6, "B4 칸 가운데", f"{cx:.1f},{cy:.1f}")
        ex = o.get("extra") or {}
        chk(ex.get("check") == "v" and ex.get("pdf"), "B5 모양 표지·벡터 조각을 꾸밈에 든다")
        import base64
        with fitz.open(stream=base64.b64decode(ex["pdf"]), filetype="pdf") as q:
            ws = [d.get("width") or 0 for d in q[0].get_drawings()]
            chk(ws and abs(max(ws) - side * check_mark.W_FRAC) < 0.15, "B6 선 굵기 = 크기 × W_FRAC", str(ws))
    click_pt(400, 600)                                            # 칸이 없는 곳
    chk(len(mv._img_objects) == 2, "B7 켜진 채 다시 누르면 또 넣는다")
    if len(mv._img_objects) == 2:
        o = mv._img_objects[1]
        cx = (o["rect"][0] + o["rect"][2] / 2) * pw; cy = (o["rect"][1] + o["rect"][3] / 2) * ph
        chk(abs(o["rect"][2] * pw - 4 * PT_MM) < 0.6 and abs(cx - 400) < 1 and abs(cy - 600) < 1,
            "B8 칸이 없으면 누른 자리 가운데 4 mm", f"{o['rect'][2] * pw / PT_MM:.2f} mm @ {cx:.0f},{cy:.0f}")
    QTest.keyClick(mv.view, Qt.Key.Key_Escape); app.processEvents()
    chk(mv._draw_kind != "check", "B9 Esc 로 체크 도구를 끈다", str(mv._draw_kind))

    # ── C ▾ 모양·크기·색 ──
    mv._rebuild_check_menu()
    acts = {a.text(): a for a in mv._check_menu.actions()}
    dot = [a for a in mv._check_menu.actions() if a.data() == "dot" and not a.icon().isNull()]
    big = [a for t, a in acts.items() if "5 mm" in t]
    chk(bool(dot) and bool(big), "C1 ▾ 에 모양(그 모양 그림)·크기", str(list(acts)))
    if dot and big:
        dot[0].trigger(); big[0].trigger(); app.processEvents()
        chk(mv._draw_tool == ("check", "dot") and mv._check_mm == 5.0, "C2 ▾ 에서 고르면 그것으로 도구가 켜진다", str(mv._draw_tool))
        mv._pen_idx = 1; mv._apply_tool()                         # 고른 스타일(선 2 파랑)
        click_pt(450, 700)
        o = mv._img_objects[-1]
        from PyQt6.QtGui import QColor
        img = o["pix"].toImage()
        c = img.pixelColor(img.width() // 2, img.height() // 2)
        want = QColor(mv._active_pen()["color"])
        chk(o["extra"].get("check") == "dot" and abs(o["rect"][2] * pw - 5 * PT_MM) < 0.6
            and abs(c.red() - want.red()) + abs(c.green() - want.green()) + abs(c.blue() - want.blue()) < 40,
            "C3 꽉 찬 원·5 mm·고른 스타일 색", f"{c.name()} vs {want.name()}")
        mv._pen_idx = None; mv._apply_tool()
        click_pt(450, 760)
        img = mv._img_objects[-1]["pix"].toImage()
        c = img.pixelColor(img.width() // 2, img.height() // 2)
        chk(c.red() + c.green() + c.blue() < 60, "C4 스타일을 안 골랐으면 검정", c.name())

    # ── D 서식 체크박스 ──
    seen = []
    mv.formCheckRequested.connect(lambda k, on: seen.append((tuple(k), on)))
    n0 = len(mv._img_objects)
    mv.pick_check(kind="v")
    click_pt(107, 307)
    chk(len(mv._img_objects) == n0 and seen == [(("chk", "Yes"), True)],
        "D1 서식 체크박스를 누르면 표시를 넣지 않고 켜기를 알린다", str(seen))
    # 앱 처리(_on_form_check) 와 같은 차례 — 보류 + 연 문서에 덧입힘
    form_fill.set_pending(str(pdf), ("chk", "Yes"), True)
    form_fill.apply_fields(mv._doc.doc, {("chk", "Yes"): True}); mv._doc.apply_form_pending()
    chk(form_fill.pending(str(pdf)) == {("chk", "Yes"): True}, "D2 보류에 들어간다")
    hit = form_fill.toggle_at(mv._doc.doc[0], 107, 307)
    chk(hit is not None and hit[1] is True, "D3 연 문서에서 켜져 보인다", str(hit))
    seen.clear(); click_pt(107, 307)
    chk(seen == [(("chk", "Yes"), False)], "D4 다시 누르면 끄기를 알린다", str(seen))
    form_fill.set_pending(str(pdf), ("chk", "Yes"), False)
    chk(not form_fill.has_pending(str(pdf)), "D5 원래 값으로 돌아가면 보류가 사라진다")
    form_fill.set_pending(str(pdf), ("chk", "Yes"), True)
    form_fill.set_pending(str(pdf), ("yn", "No"), True)
    out = root / "saved.pdf"
    shutil.copy(pdf, out)
    n = form_fill.write_fields(out, form_fill.pending(str(pdf)), source=str(pdf))
    with fitz.open(str(out)) as q:
        vals = {(w.field_name, form_fill.on_state(w)): form_fill.is_on(w) for w in q[0].widgets()}
    chk(n >= 2 and vals.get(("chk", "Yes")) and vals.get(("yn", "No")) and not vals.get(("yn", "Yes")),
        "D6 [저장] 길로 파일에 켜진다(라디오는 하나만)", str(vals))
    form_fill.clear_pending()
    mv.close()

    # ── E 실제 MainWindow — [저장] 길 ──
    from viewer.app import MainWindow
    folder = root / "docs"; folder.mkdir()
    pe = folder / "양식.pdf"
    make_pdf(pe)
    mw = MainWindow(); mw._skip_save_on_close = True
    mw.resize(1400, 900); mw.show(); pump()
    bt = mw.bookmark_tree
    mw.open_folder(folder)
    pump(lambda: sum(1 for _ in bt._iter_file_nodes()) == 1)
    mw.open_pdf(pe); pump()
    bt.btn_edit.setChecked(True); pump()
    m2 = mw.main_view
    QTest.mouseClick(m2._check_btn, Qt.MouseButton.LeftButton); pump()
    pr2 = m2._page_view_rect(); pw2, ph2 = m2.page_size_pt()
    QTest.mouseClick(m2.view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(int(pr2.left() + pr2.width() * 107 / pw2), int(pr2.top() + pr2.height() * 307 / ph2)))
    pump()
    chk(form_fill.pending(str(pe)) == {("chk", "Yes"): True}, "E1 실제 앱 — 서식 체크박스를 누르면 보류", str(form_fill.pending(str(pe))))
    bt._op_save(str(pe), quiet=True)
    pump(lambda: not form_fill.has_pending(str(pe)), 15)
    with fitz.open(str(pe)) as q:
        on = {w.field_name: form_fill.is_on(w) for w in q[0].widgets() if w.field_name == "chk"}
    chk(on.get("chk") is True and not form_fill.has_pending(str(pe)), "E2 [저장] 하면 파일에 켜지고 보류가 빈다", str(on))
    mw.close()
finally:
    shutil.rmtree(root, ignore_errors=True)

print("ALL PASS" if not fails else f"{len(fails)} FAIL")
sys.stdout.flush()
os._exit(1 if fails else 0)
