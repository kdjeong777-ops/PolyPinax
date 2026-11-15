# -*- coding: utf-8 -*-
"""261115-9: 다단 기본 — 표지·목차 끔 (마스터 §11.10.5).

사용자 지시: "다단 기본 설정은 표지만들기, 목차만들기는 기본 체크되지 않은 상태로 스타일을 설정해"

A. 기본 전체 스타일 셋은 make_cover·make_toc 를 거짓으로 적어 두고, DEFAULT_TWOUP 도 거짓
B. 설정 창 — 빈 설정(PDF 병합 창이 처음 여는 값)으로 열면 두 체크 꺼짐, 두 값이 없는 스타일(이미 넣은 기본 셋)을
   목록에서 고르면 꺼짐, 저장한 스타일의 참은 그대로 켜짐
C. 인쇄 창 — 기본 스타일을 고른 다단 설정(_nup_settings)으로 build_twoup 하면 앞장(표지·목차) 없이 본문 시트만,
   값이 없는 설정도 같다(build_twoup 은 DEFAULT_TWOUP 을 씌운다), 참을 적으면 앞장이 붙는다
"""
import os, sys, tempfile, shutil, faulthandler
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(180, exit=True)
import fitz
from PyQt6.QtCore import QStandardPaths
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv[:1])
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


tmp = tempfile.mkdtemp(prefix="nupcover261115_")
try:
    from viewer.twoup import DEFAULT_TWOUP, NUP_STYLE_DEFAULTS, default_nup_styles, build_twoup
    from viewer.widgets.twoup_dialog import TwoUpSettingsDialog
    from viewer.widgets.nup_preset import NupPresetMixin

    # ── A ──
    for nm, vals in NUP_STYLE_DEFAULTS:
        chk(vals.get("make_cover") is False and vals.get("make_toc") is False,
            f"A 기본 스타일 '{nm}' 표지·목차 거짓으로 적어 둠", str({k: vals.get(k) for k in ("make_cover", "make_toc")}))
    chk(DEFAULT_TWOUP["make_cover"] is False and DEFAULT_TWOUP["make_toc"] is False,
        "A DEFAULT_TWOUP 표지·목차 거짓")

    # ── B ──
    old_seeded = [{k: v for k, v in p.items() if k not in ("make_cover", "make_toc")} for p in default_nup_styles()]
    mine = dict(default_nup_styles()[1], name="내 스타일", make_cover=True, make_toc=True)
    presets = old_seeded + [mine]
    api = {"get_presets": lambda: presets}
    for init, lab in ((None, "병합 창 처음(None)"), ({}, "빈 설정")):
        d = TwoUpSettingsDialog(init, None, preset_api=api)
        chk(not d.chk_cover.isChecked() and not d.chk_toc.isChecked(), f"B {lab} → 표지·목차 체크 꺼짐")
        d.done(0)
    d = TwoUpSettingsDialog({"make_cover": True, "make_toc": True}, None, preset_api=api)
    chk(d.chk_cover.isChecked() and d.chk_toc.isChecked(), "B 시작 값이 참이면 켜짐(종전 창 값 그대로)")
    i_old = d.cmb_preset.findText(old_seeded[0]["name"])
    d.cmb_preset.setCurrentIndex(i_old); d.cmb_preset.activated.emit(i_old)
    chk(not d.chk_cover.isChecked() and not d.chk_toc.isChecked(),
        "B 두 값이 없는 스타일(이미 넣은 기본 셋) 고르기 → 꺼짐")
    i_mine = d.cmb_preset.findText("내 스타일")
    d.cmb_preset.setCurrentIndex(i_mine); d.cmb_preset.activated.emit(i_mine)
    chk(d.chk_cover.isChecked() and d.chk_toc.isChecked(), "B 사용자가 켜서 저장한 스타일은 그대로 켜짐")
    gs = d.get_settings()
    chk(gs.get("make_cover") is True and gs.get("make_toc") is True, "B 창 값에 두 값을 적어 둔다")
    d.done(0)

    # ── C ── (인쇄 창 프리셋 고르기 길: _nup_settings = dict(스타일))
    src = os.path.join(tmp, "src.pdf")
    doc = fitz.open()
    for i in range(4):
        pg = doc.new_page(width=595, height=842); pg.insert_text((72, 100), f"page {i + 1}")
    doc.set_toc([[1, "one", 1], [1, "two", 3]])
    doc.save(src); doc.close()
    item = [{"path": src, "name": "src"}]

    class _Fake(NupPresetMixin):
        pass
    fk = _Fake()

    class _Cmb:
        def __init__(self, p): self.p = p
        def currentData(self): return self.p

    class _Chk:
        def setChecked(self, v): self.v = v
    fk.chk_nup = _Chk()

    def sheets(s, tag):
        out = os.path.join(tmp, tag + ".pdf")
        build_twoup(item, s, out)
        with fitz.open(out) as o:
            return o.page_count

    fk.cmb_preset = _Cmb(old_seeded[0]); fk._on_preset_pick()        # 2장 — 4쪽 → 본문 2장
    n_style = sheets(fk._nup_settings, "style")
    chk(n_style == 2, "C 이미 넣은 기본 스타일(두 값 없음)로 인쇄 → 본문 2장만(앞장 없음)", f"장 수 {n_style}")
    fk.cmb_preset = _Cmb(default_nup_styles()[0]); fk._on_preset_pick()
    n_new = sheets(fk._nup_settings, "style_new")
    chk(n_new == 2, "C 새 기본 스타일로 인쇄 → 본문 2장만", f"장 수 {n_new}")
    n_on = sheets(dict(old_seeded[0], make_cover=True, make_toc=True), "on")
    chk(n_on > 2, "C 참을 적으면 앞장(표지·목차)이 붙는다", f"장 수 {n_on}")
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
os._exit(1 if fails else 0)
