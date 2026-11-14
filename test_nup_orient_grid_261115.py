# -*- coding: utf-8 -*-
"""261115-1: 다단 — 용지 방향(세로/가로)과 가로·세로 쪽수(각 1~6)를 사용자가 정한다 (마스터 §11.10.3).

A. 엔진 — 방향 × 쪽수 조합: 칸 수 = 가로×세로, 가로로 먼저 채움, 용지 크기·방향은 고른 방향(원본 방향과 무관)
B. 옛 설정 — orient·cols·rows 가 없으면 `nup`·원본 방향으로 종전 칸·용지 그대로
C. 실제 `build_twoup` — 시트 수 = ceil(쪽 수 / (가로×세로)), 시트 방향 = 고른 방향(섞인 문서도)
D. 설정 창 실제 조작(키 입력) — 빠른 선택 → 드롭다운 채움, 드롭다운 → '사용자 지정', 방향 → 쪽수 맞바꿈,
   옛 스타일 열기, get_settings·미리보기 값
"""
import os, sys, tempfile, shutil, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pathlib import Path
import fitz
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_nuporient261115_%d" % os.getpid())

fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def spin(sec=0.2):
    t0 = time.time()
    while time.time() - t0 < sec:
        app.processEvents(); time.sleep(0.01)


def pick(cmb, data):
    """콤보를 키보드(↑↓)로 그 값까지 옮긴다 — 사용자가 고르는 것과 같은 신호."""
    target = next((i for i in range(cmb.count()) if cmb.itemData(i) == data), -1)
    assert target >= 0, (cmb.objectName(), data)
    cmb.setFocus(); spin(0.02)
    guard = 0
    while cmb.currentIndex() != target and guard < 20:
        QTest.keyClick(cmb, Qt.Key.Key_Down if cmb.currentIndex() < target else Qt.Key.Key_Up)
        guard += 1
    spin(0.05)


A4S, A4L = 595.28, 841.89
root = Path(tempfile.mkdtemp(prefix="nuporient261115_"))
try:
    from viewer.twoup import _grid_layout, _grid_dims, merge_twoup_settings, build_twoup
    port = fitz.Rect(0, 0, 595, 842)
    land = fitz.Rect(0, 0, 842, 595)

    # A — 방향 × 쪽수
    bad = []
    for orient in ("portrait", "landscape"):
        for cols in (1, 2, 3, 6):
            for rows in (1, 2, 5, 6):
                for src in (port, land):
                    s = merge_twoup_settings({"orient": orient, "cols": cols, "rows": rows, "page_size": "A4"})
                    ow, oh, boxes = _grid_layout(src, s)
                    want = (A4S, A4L) if orient == "portrait" else (A4L, A4S)
                    if (round(ow, 1), round(oh, 1)) != (round(want[0], 1), round(want[1], 1)):
                        bad.append(("용지", orient, cols, rows, ow, oh)); continue
                    if len(boxes) != cols * rows:
                        bad.append(("칸 수", orient, cols, rows, len(boxes))); continue
                    if cols > 1 and not boxes[1].x0 > boxes[0].x0 + 1:
                        bad.append(("가로 먼저", orient, cols, rows)); continue
                    if rows > 1 and not boxes[cols].y0 > boxes[0].y0 + 1:
                        bad.append(("다음 줄", orient, cols, rows)); continue
    chk(not bad, "A 방향 세로/가로 × 가로·세로 쪽수 — 칸 수·가로 먼저·용지 크기(원본 방향과 무관)", str(bad[:4]))
    s = merge_twoup_settings({"orient": "landscape", "cols": 3, "rows": 2, "page_size": "Letter"})
    ow, oh, _b = _grid_layout(port, s)
    chk((ow, oh) == (792.0, 612.0), "A2 Letter 가로 용지", str((ow, oh)))

    # B — 옛 설정(키 없음) = 종전 규칙
    legacy = {1: {"p": (1, 1, A4S, A4L), "l": (1, 1, A4L, A4S)},
              2: {"p": (2, 1, A4L, A4S), "l": (1, 2, A4S, A4L)},
              4: {"p": (2, 2, A4S, A4L), "l": (2, 2, A4S, A4L)},
              6: {"p": (2, 3, A4S, A4L), "l": (2, 3, A4S, A4L)},
              8: {"p": (2, 4, A4S, A4L), "l": (2, 4, A4S, A4L)}}
    badB = []
    for nup, d in legacy.items():
        for k, src in (("p", port), ("l", land)):
            got = _grid_dims(src, merge_twoup_settings({"nup": nup}))
            if tuple(round(x, 2) for x in got) != tuple(round(x, 2) for x in d[k]):
                badB.append((nup, k, got))
    chk(not badB, "B 옛 nup 설정은 종전 칸·용지 그대로", str(badB))
    from viewer import twoup as tw
    chk(hasattr(tw, "grid_spec") and tw.grid_spec(merge_twoup_settings({"nup": 6}), port) == ("portrait", 2, 3)
        and tw.grid_spec(merge_twoup_settings({"nup": 2}), port) == ("landscape", 2, 1),
        "B2 grid_spec 이 옛 값을 (방향, 가로, 세로) 로 푼다")
    # B3 — 자동(사용자 지시 '자동·가로·세로'): 옛 1·2-up 은 창에서 자동 1×1·1×2 로 보이고, 그 값의 칸·용지가 종전과 같다
    badA = []
    for nup in (1, 2, 4, 6, 8):
        ch = tw.grid_choice(merge_twoup_settings({"nup": nup}))
        new = merge_twoup_settings({"orient": ch[0], "cols": ch[1], "rows": ch[2]})
        for src in (port, land, fitz.Rect(0, 0, 612, 792), fitz.Rect(0, 0, 1190, 842)):
            a = _grid_dims(src, merge_twoup_settings({"nup": nup}))
            b = _grid_dims(src, new)
            if tuple(round(x, 2) for x in a) != tuple(round(x, 2) for x in b):
                badA.append((nup, ch, tuple(src), a, b))
    chk(not badA, "B3 옛 nup 을 창 값(1·2-up=자동)으로 바꿔 저장해도 칸·용지가 종전과 같다", str(badA[:3]))
    chk(tw.grid_spec(merge_twoup_settings({"orient": "auto", "cols": 1, "rows": 1}), land)[0] == "landscape"
        and tw.grid_spec(merge_twoup_settings({"orient": "auto", "cols": 1, "rows": 1}), port)[0] == "portrait",
        "B4 자동 1×1 — 원본 방향대로")

    # C — 실제 만들기
    src_pdf = root / "mix.pdf"
    d = fitz.open()
    for i in range(13):
        w, h = (842, 595) if i in (4, 9) else (595, 842)
        d.new_page(width=w, height=h).insert_text((72, 300), "P%d" % (i + 1))
    d.save(str(src_pdf)); d.close()
    ITEM = [{"type": "pdf", "path": str(src_pdf), "name": "mix"}]
    base = {"make_cover": False, "make_toc": False}
    for cfg, n_want, land_want in ((dict(base, orient="landscape", cols=3, rows=2), 3, True),
                                   (dict(base, orient="portrait", cols=5, rows=1), 3, False),
                                   (dict(base, orient="portrait", cols=1, rows=1), 13, False),
                                   (dict(base, orient="landscape", cols=6, rows=6), 1, True),
                                   (dict(base, nup=6), 3, False)):
        out = str(root / ("o_%s_%s_%s.pdf" % (cfg.get("orient", "old"), cfg.get("cols", 0), cfg.get("rows", 0))))
        build_twoup(ITEM, cfg, out)
        o = fitz.open(out)
        lands = [p.rect.width > p.rect.height for p in o]
        chk(o.page_count == n_want and all(x == land_want for x in lands),
            "C %s — 시트 %d장·%s" % ({k: cfg[k] for k in cfg if k in ("orient", "cols", "rows", "nup")},
                                   n_want, "가로" if land_want else "세로"), str((o.page_count, lands)))
        o.close()
    # C2 — 자동 1×2 는 짝마다 원본 방향을 따른다(종전 2-up 과 같은 시트들)
    oa, ob = str(root / "auto12.pdf"), str(root / "old2.pdf")
    build_twoup(ITEM, dict(base, orient="auto", cols=1, rows=2), oa)
    build_twoup(ITEM, dict(base, nup=2), ob)
    da, db = fitz.open(oa), fitz.open(ob)
    sa = [(round(p.rect.width), round(p.rect.height)) for p in da]
    sb = [(round(p.rect.width), round(p.rect.height)) for p in db]
    chk(sa == sb and len(set(sa)) == 2, "C2 자동 1×2 = 종전 2-up(섞인 문서에서 시트마다 방향)", str((sa, sb)))
    da.close(); db.close()

    # D — 설정 창 실제 조작
    from viewer.widgets.twoup_dialog import TwoUpSettingsDialog
    sp = root / "port.pdf"
    d = fitz.open()
    for i in range(4):
        d.new_page(width=595, height=842)
    d.save(str(sp)); d.close()
    dlg = TwoUpSettingsDialog({}, None, sample=str(sp))
    dlg.show(); spin(0.3)
    chk([dlg.cmb_cols.itemData(i) for i in range(dlg.cmb_cols.count())] == [1, 2, 3, 4, 5, 6]
        and [dlg.cmb_rows.itemData(i) for i in range(dlg.cmb_rows.count())] == [1, 2, 3, 4, 5, 6],
        "D1 가로·세로 쪽수 드롭다운 1~6")
    chk([dlg.cmb_orient.itemData(i) for i in range(dlg.cmb_orient.count())] == ["auto", "portrait", "landscape"]
        and dlg.cmb_orient.toolTip(),
        "D2 용지 방향은 자동·세로·가로 셋(자동 설명 툴팁)")
    chk((dlg.cmb_orient.currentData(), dlg.cmb_cols.currentData(), dlg.cmb_rows.currentData(),
         dlg.cmb_nup.currentData()) == ("auto", 1, 2, 2),
        "D3 옛 기본값(2-up) = 자동 1×2 로 보여 준다",
        str((dlg.cmb_orient.currentData(), dlg.cmb_cols.currentData(), dlg.cmb_rows.currentData())))
    pick(dlg.cmb_orient, "landscape")          # 자동 → 세로(그대로) → 가로(맞바꿈)
    chk((dlg.cmb_cols.currentData(), dlg.cmb_rows.currentData(), dlg.cmb_nup.currentData()) == (2, 1, 2),
        "D3b 자동 1×2 → 가로 2×1, 빠른 선택 2장 그대로")
    pick(dlg.cmb_nup, 6)
    chk((dlg.cmb_cols.currentData(), dlg.cmb_rows.currentData()) == (3, 2), "D4 가로 방향에서 6장 → 3×2",
        str((dlg.cmb_cols.currentData(), dlg.cmb_rows.currentData())))
    pick(dlg.cmb_orient, "portrait")
    chk((dlg.cmb_cols.currentData(), dlg.cmb_rows.currentData(), dlg.cmb_nup.currentData()) == (2, 3, 6),
        "D5 방향을 세로로 → 쪽수 맞바꿈 2×3, 빠른 선택 6장 그대로")
    pick(dlg.cmb_cols, 4)
    g = dlg.get_settings()
    chk(dlg.cmb_nup.currentData() == 0 and dlg.cmb_nup.currentText() == "사용자 지정",
        "D6 드롭다운을 직접 바꾸면 '사용자 지정'", dlg.cmb_nup.currentText())
    chk((g.get("orient"), g.get("cols"), g.get("rows"), g.get("nup")) == ("portrait", 4, 3, 12),
        "D7 get_settings = 방향·가로·세로·nup(곱)", str((g.get("orient"), g.get("cols"), g.get("rows"), g.get("nup"))))
    spin(0.5)
    pb = dlg.preview._base
    chk((pb.get("orient"), pb.get("cols"), pb.get("rows")) == ("portrait", 4, 3), "D8 미리보기도 같은 값",
        str((pb.get("orient"), pb.get("cols"), pb.get("rows"))))
    pick(dlg.cmb_orient, "landscape")
    chk((dlg.cmb_cols.currentData(), dlg.cmb_rows.currentData(), dlg.cmb_nup.currentData()) == (3, 4, 0),
        "D9 사용자 지정에서도 방향을 바꾸면 맞바꿈(3×4), 콤보는 사용자 지정")
    pick(dlg.cmb_rows, 2)
    chk(dlg.cmb_nup.currentData() == 6, "D10 드롭다운이 빠른 선택과 같아지면(가로 3×2) 콤보도 6장")
    pick(dlg.cmb_nup, 8)                       # 바로 아래가 '사용자 지정' — 키 한 번으로 고른다
    chk((dlg.cmb_cols.currentData(), dlg.cmb_rows.currentData()) == (4, 2), "D11a 가로 방향 8장 → 4×2")
    pick(dlg.cmb_nup, 0)
    chk((dlg.cmb_cols.currentData(), dlg.cmb_rows.currentData()) == (4, 2), "D11 '사용자 지정' 을 골라도 드롭다운은 그대로")
    pick(dlg.cmb_orient, "auto")               # 가로 → 세로(맞바꿈 2×4) → 자동(그대로)
    chk((dlg.cmb_cols.currentData(), dlg.cmb_rows.currentData(), dlg.cmb_nup.currentData()) == (2, 4, 8),
        "D11b 가로 4×2 → 자동 2×4(세로 용지 기준), 빠른 선택 8장")
    g = dlg.get_settings()
    chk((g.get("orient"), g.get("cols"), g.get("rows"), g.get("nup")) == ("auto", 2, 4, 8), "D11c 자동도 저장된다",
        str((g.get("orient"), g.get("cols"), g.get("rows"))))
    dlg.apply_settings({"nup": 6})
    chk((dlg.cmb_orient.currentData(), dlg.cmb_cols.currentData(), dlg.cmb_rows.currentData(),
         dlg.cmb_nup.currentData()) == ("portrait", 2, 3, 6), "D12 옛 스타일 nup 6 → 세로 2×3")
    dlg.apply_settings({"nup": 1})
    chk((dlg.cmb_orient.currentData(), dlg.cmb_cols.currentData(), dlg.cmb_rows.currentData(),
         dlg.cmb_nup.currentData()) == ("auto", 1, 1, 1), "D12b 옛 스타일 nup 1 → 자동 1×1")
    dlg.apply_settings({"orient": "landscape", "cols": 5, "rows": 4, "nup": 20})
    chk((dlg.cmb_orient.currentData(), dlg.cmb_cols.currentData(), dlg.cmb_rows.currentData(),
         dlg.cmb_nup.currentData()) == ("landscape", 5, 4, 0), "D13 새 스타일은 그 값 그대로(사용자 지정)")
    dlg.close()
except Exception:
    import traceback
    traceback.print_exc()
    fails.append("예외")
finally:
    try:
        from viewer.twoup import clear_preview_cache
        clear_preview_cache()
    except Exception:
        pass
    shutil.rmtree(str(root), ignore_errors=True)

print("\n=== " + ("ALL PASS" if not fails else "FAILURE (%d)" % len(fails)) + " ===")
for m in fails:
    print(" -", m)
sys.stdout.flush()
os._exit(1 if fails else 0)
