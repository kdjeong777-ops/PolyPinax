# -*- coding: utf-8 -*-
"""261115-6: 다단 설정 기본값 (마스터 §11.10.4·§11.10.5).

A. 여백 스타일 — 순서 보통·넓게·좁게·없음, 없음 = 0, 기본값(DEFAULT_TWOUP) = 좁게, 새 설정 창 처음 값 = 좁게
B. 기본 전체 스타일 셋 — 칸·방향·면·여백·채움, 실제 build_twoup 시트 수·방향
C. 앱 — 빈 설정에 셋을 넣음, 기존 사용자 스타일 뒤에 같은 이름 없는 것만, 기존 여백 목록에 '없음' 한 번,
   지운 뒤 다시 안 생김, nup_seed_ver 가 저장 허용목록(_apply_prefs)·저장 페이로드에 남음
D. 설정 창에서 '6장·양면·여백없음·늘이기' 고르기(키 입력) → 칸 값·여백 스타일 '없음'·채움 늘이기
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
import modal_guard
modal_guard.install(label=lambda: "다단 기본값", echo=False)   # §14.7.2 의 6

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_nupdefaults261115_%d" % os.getpid())

fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def spin(sec=0.2):
    t0 = time.time()
    while time.time() - t0 < sec:
        app.processEvents(); time.sleep(0.01)


def pick_text(cmb, text):
    target = cmb.findText(text)
    assert target >= 0, (text, [cmb.itemText(i) for i in range(cmb.count())])
    cmb.setFocus(); spin(0.02)
    guard = 0
    while cmb.currentIndex() != target and guard < 40:
        QTest.keyClick(cmb, Qt.Key.Key_Down if cmb.currentIndex() < target else Qt.Key.Key_Up)
        guard += 1
    spin(0.05)


M = ("margin_top", "margin_bottom", "margin_left", "margin_right", "gap", "gap_v")
S2, S4, S6 = "2장·양면·여백좁게", "4장·양면·여백좁게", "6장·양면·여백없음·늘이기"
root = Path(tempfile.mkdtemp(prefix="nupdefaults261115_"))
try:
    from viewer import twoup as tw
    # A
    names = [p["name"] for p in tw.default_part_styles("margin")]
    chk(names == ["보통", "넓게", "좁게", "없음"], "A1 여백 스타일 순서", str(names))
    by = {p["name"]: tuple(p[k] for k in M) for p in tw.default_part_styles("margin")}
    chk(by["없음"] == (0, 0, 0, 0, 0, 0), "A2 없음 = 여백·간격 0")
    chk(tuple(tw.DEFAULT_TWOUP[k] for k in M) == by["좁게"] == (18, 30, 14, 14, 8, 8), "A3 기본값 = 좁게",
        str(tuple(tw.DEFAULT_TWOUP[k] for k in M)))
    chk(by["보통"] == (36, 48, 28, 28, 16, 16), "A4 보통은 종전 값 그대로")

    # B
    st = {p["name"]: p for p in tw.default_nup_styles()}
    chk(list(st) == [S2, S4, S6], "B1 기본 전체 스타일 셋·순서", str(list(st)))
    chk(tw.duplex_choice(st[S2]) == "short" and tw.duplex_choice(st[S4]) == "long"
        and tw.duplex_choice(st[S6]) == "long", "B2 면 — 2장 짧은 쪽, 4·6장 긴 쪽")
    chk(tuple(st[S2][k] for k in M) == by["좁게"] and tuple(st[S4][k] for k in M) == by["좁게"]
        and tuple(st[S6][k] for k in M) == by["없음"], "B3 여백 — 좁게·좁게·없음")
    chk(st[S6].get("fit_mode") == "stretch" and "fit_mode" not in st[S2], "B4 6장만 늘이기")
    chk(tw.grid_choice(st[S2]) == ("auto", 1, 2) and tw.grid_choice(st[S4]) == ("portrait", 2, 2)
        and tw.grid_choice(st[S6]) == ("portrait", 2, 3), "B5 칸 — 자동 1×2·세로 2×2·세로 2×3")
    src = root / "a4x12.pdf"
    d = fitz.open()
    for i in range(12):
        d.new_page(width=595, height=842).insert_text((60, 80), "P%d" % (i + 1), fontsize=30)
    d.save(str(src)); d.close()
    ITEM = [{"type": "pdf", "path": str(src), "name": "a4"}]
    for nm, n_want, land_want in ((S2, 6, True), (S4, 3, False), (S6, 2, False)):
        out = str(root / ("o%d.pdf" % n_want))
        cfg = dict(st[nm], make_cover=False, make_toc=False)
        tw.build_twoup(ITEM, cfg, out)
        o = fitz.open(out)
        lands = [p.rect.width > p.rect.height for p in o]
        chk(o.page_count == n_want and all(x == land_want for x in lands), "B6 %s → 시트 %d장·%s" % (
            nm, n_want, "가로" if land_want else "세로"), "%d %s" % (o.page_count, lands))
        o.close()

    # C
    from viewer.app import MainWindow
    mw = MainWindow(); mw._skip_save_on_close = True
    mw._prefs.pop("nup_seed_ver", None)
    mw._prefs["merge_presets"] = [{"name": "내 스타일", "nup": 2}, {"name": S4, "nup": 4, "gap": 99}]
    mw._prefs["nup_margin_presets"] = [{"name": "보통"}, {"name": "좁게"}, {"name": "넓게"}]   # 261115-5 때 심은 목록
    api = mw._merge_preset_api()
    got = [p["name"] for p in api["get_presets"]()]
    chk(got == ["내 스타일", S4, S2, S6], "C1 기존 스타일 뒤에 같은 이름 없는 것만", str(got))
    chk(next(p for p in mw._prefs["merge_presets"] if p["name"] == S4).get("gap") == 99, "C2 같은 이름 사용자 스타일은 그대로")
    chk([p["name"] for p in mw._prefs["nup_margin_presets"]] == ["보통", "좁게", "넓게", "없음"]
        and mw._prefs.get("nup_seed_ver") == tw.NUP_SEED_VER, "C3 기존 여백 목록에 '없음' 한 번·판 번호")
    api["delete_preset"](S2)
    api["delete_part"]("margin", "없음")
    got = [p["name"] for p in api["get_presets"]()]
    chk(S2 not in got and "없음" not in [p["name"] for p in api["get_parts"]("margin")], "C4 지운 기본 항목은 다시 안 생긴다")
    mw._apply_prefs({})
    chk(mw._prefs.get("nup_seed_ver") == tw.NUP_SEED_VER, "C5 환경설정 [확인](_apply_prefs)을 지나도 판 번호",
        str(mw._prefs.get("nup_seed_ver")))
    chk(S2 not in [p["name"] for p in api["get_presets"]()], "C6 그 뒤에도 다시 안 생긴다")
    pay = (mw._build_settings_payload().get("preferences") or {})
    chk(pay.get("nup_seed_ver") == tw.NUP_SEED_VER, "C7 settings.json 저장 페이로드에 판 번호")
    mw._prefs.pop("nup_seed_ver", None); mw._prefs["merge_presets"] = []
    mw._prefs.pop("nup_margin_presets", None)
    chk([p["name"] for p in api["get_presets"]()] == [S2, S4, S6], "C8 빈 설정 → 셋")
    chk([p["name"] for p in api["get_parts"]("margin")] == ["보통", "넓게", "좁게", "없음"], "C9 목록 없으면 새 순서 전체")

    # D
    from viewer.widgets.twoup_dialog import TwoUpSettingsDialog
    dlg = TwoUpSettingsDialog({}, None, preset_api=api, sample=str(src))
    dlg.show(); spin(0.3)
    chk(dlg.preview.cmb_margin_style.currentText() == "좁게", "D1 새 창 처음 여백 스타일 = 좁게",
        dlg.preview.cmb_margin_style.currentText())
    pick_text(dlg.cmb_preset, S6)
    g = dlg.get_settings()
    chk(tuple(g[k] for k in M) == (0, 0, 0, 0, 0, 0) and g["fit_mode"] == "stretch"
        and (g["orient"], g["cols"], g["rows"]) == ("portrait", 2, 3) and tw.duplex_choice(g) == "long",
        "D2 6장 스타일 고르기 → 칸 값", str({k: g[k] for k in ("fit_mode", "orient", "cols", "rows", "duplex")}))
    chk(dlg.preview.cmb_margin_style.currentText() == "없음", "D3 여백 스타일 '없음' 으로 보인다",
        dlg.preview.cmb_margin_style.currentText())
    dlg.close()
    mw.close()
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
