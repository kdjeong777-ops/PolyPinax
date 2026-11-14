# -*- coding: utf-8 -*-
"""261115-5: 다단 설정 창 — 여백 스타일·크롭 스타일 (마스터 §11.10.4).

A. preset_api 없음 — 기본 항목(보통·좁게·넓게 / 없음·상하좌우·상하·좌우)+사용자 지정, 처음 값에 맞는 이름, 단추 꺼짐
B. 고르기(키 입력) → 그 묶음 칸만 채움, 칸(키 입력)·끌기 → 사용자 지정 / 맞는 이름, 사용자 지정 골라도 칸 그대로
C. 전체 스타일 적용(apply_settings) → 두 콤보가 맞는 이름
D. 앱(MainWindow) — 처음 한 번 기본 항목 심기, 저장(새 이름 끝·같은 이름 그 자리)·▲▼·삭제가 설정에 남음,
   지운 기본 항목은 다시 안 생김, _apply_prefs(환경설정 [확인])를 지나도 남음
"""
import os, sys, tempfile, shutil, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pathlib import Path
import fitz
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtWidgets import QApplication, QMessageBox, QInputDialog
from PyQt6.QtTest import QTest
import modal_guard
modal_guard.install(label=lambda: "다단 여백·크롭 스타일", echo=False)   # §14.7.2 의 6 — 필요한 답(이름·예)은 아래에서 다시 끼운다

app =QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_nupparts261115_%d" % os.getpid())

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
    """콤보를 키보드(↑↓)로 그 글자 항목까지 옮긴다."""
    target = cmb.findText(text)
    assert target >= 0, (text, [cmb.itemText(i) for i in range(cmb.count())])
    cmb.setFocus(); spin(0.02)
    guard = 0
    while cmb.currentIndex() != target and guard < 30:
        QTest.keyClick(cmb, Qt.Key.Key_Down if cmb.currentIndex() < target else Qt.Key.Key_Up)
        guard += 1
    spin(0.05)


def type_spin(sp, value):
    sp.setFocus(); spin(0.02)
    QTest.keyClick(sp, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(sp, str(value))
    QTest.keyClick(sp, Qt.Key.Key_Tab)
    spin(0.05)


def names(cmb):
    return [cmb.itemText(i) for i in range(cmb.count())]


M = ("margin_top", "margin_bottom", "margin_left", "margin_right", "gap", "gap_v")
C = ("crop_top", "crop_bottom", "crop_left", "crop_right")
root = Path(tempfile.mkdtemp(prefix="nupparts261115_"))
try:
    sp = root / "s.pdf"
    d = fitz.open()
    for i in range(4):
        d.new_page(width=595, height=842)
    d.save(str(sp)); d.close()
    from viewer.widgets.twoup_dialog import TwoUpSettingsDialog

    # A
    dlg = TwoUpSettingsDialog({}, None, sample=str(sp))
    dlg.show(); spin(0.3)
    pv = dlg.preview
    chk(hasattr(pv, "cmb_margin_style") and hasattr(pv, "cmb_crop_style"), "A0 여백·크롭 스타일 콤보가 있다")
    cm, cc = pv.cmb_margin_style, pv.cmb_crop_style
    chk(names(cm) == ["보통", "좁게", "넓게", "사용자 지정"], "A1 여백 스타일 기본 항목", str(names(cm)))
    chk(names(cc) == ["없음", "상하좌우", "상하", "좌우", "사용자 지정"], "A2 크롭 스타일 기본 항목", str(names(cc)))
    chk(cm.currentText() == "보통" and cc.currentText() == "없음", "A3 처음 값(종전 기본값)에 맞는 이름",
        cm.currentText() + "/" + cc.currentText())
    btns = pv.part_buttons("margin") + pv.part_buttons("crop")
    chk(len(btns) == 8 and not any(b.isEnabled() for b in btns), "A4 preset_api 없으면 ▲▼·저장·삭제 꺼짐")

    # B
    pick_text(cm, "좁게")
    v = pv.values()
    chk(tuple(v[k] for k in M) == (18, 30, 14, 14, 8, 8), "B1 좁게 → 여백·간격 칸", str(tuple(v[k] for k in M)))
    chk(tuple(v[k] for k in C) == (0, 0, 0, 0) and cc.currentText() == "없음", "B2 크롭 칸은 그대로")
    type_spin(pv.sp["margin_top"], 20)
    chk(pv.values()["margin_top"] == 20 and cm.currentText() == "사용자 지정", "B3 칸을 바꾸면 사용자 지정", cm.currentText())
    type_spin(pv.sp["margin_top"], 18)
    chk(cm.currentText() == "좁게", "B4 값이 다시 맞으면 그 이름", cm.currentText())
    pick_text(cc, "상하")
    v = pv.values()
    chk(tuple(v[k] for k in C) == (5, 5, 0, 0), "B5 크롭 상하 → 5·5·0·0", str(tuple(v[k] for k in C)))
    pv.canvas.changed.emit("crop_left", 7); spin(0.05)
    chk(cc.currentText() == "사용자 지정", "B6 미리보기에서 끌면 사용자 지정", cc.currentText())
    pick_text(cc, "사용자 지정")
    chk(pv.values()["crop_left"] == 7, "B7 사용자 지정을 골라도 칸 그대로")
    g = dlg.get_settings()
    chk(g["margin_left"] == 14 and g["crop_left"] == 7, "B8 get_settings 에 값")

    # C
    dlg.apply_settings({"margin_top": 54, "margin_bottom": 66, "margin_left": 42, "margin_right": 42,
                        "gap": 24, "gap_v": 24, "crop_top": 0, "crop_bottom": 0, "crop_left": 5, "crop_right": 5})
    spin(0.05)
    chk(cm.currentText() == "넓게" and cc.currentText() == "좌우", "C1 전체 스타일 값에 맞는 이름",
        cm.currentText() + "/" + cc.currentText())
    dlg.apply_settings({"margin_top": 3, "crop_top": 9})
    chk(cm.currentText() == "사용자 지정" and cc.currentText() == "사용자 지정", "C2 맞는 것이 없으면 사용자 지정")
    dlg.close()

    # D — 앱
    from viewer.app import MainWindow
    mw = MainWindow(); mw._skip_save_on_close = True
    mw._prefs.pop("nup_margin_presets", None); mw._prefs.pop("nup_crop_presets", None)
    api = mw._merge_preset_api()
    chk(callable(api.get("get_parts")), "D0 preset_api 에 get_parts")
    lst = api["get_parts"]("margin")
    chk([p["name"] for p in lst] == ["보통", "좁게", "넓게"] and mw._prefs.get("nup_margin_presets"),
        "D1 처음 한 번 기본 항목을 심어 설정에 둔다", str(lst))
    dlg = TwoUpSettingsDialog({}, None, preset_api=api, sample=str(sp))
    dlg.show(); spin(0.3)
    pv = dlg.preview; cm = pv.cmb_margin_style
    up, dn, sv, de = pv.part_buttons("margin")
    chk(sv.isEnabled() and de.isEnabled() and not up.isEnabled() and dn.isEnabled(), "D2 api 있으면 단추 켜짐(맨 위 ▲ 꺼짐)")
    type_spin(pv.sp["gap"], 30)
    QInputDialog.getText = staticmethod(lambda *a, **k: ("내 여백", True))
    QTest.mouseClick(sv, Qt.MouseButton.LeftButton); spin(0.1)
    st = mw._prefs["nup_margin_presets"]
    chk([p["name"] for p in st] == ["보통", "좁게", "넓게", "내 여백"] and st[3]["gap"] == 30,
        "D3 새 이름 저장 → 목록 끝, 값", str([(p["name"], p.get("gap")) for p in st]))
    chk(cm.currentText() == "내 여백", "D4 저장한 이름을 보인다", cm.currentText())
    QTest.mouseClick(up, Qt.MouseButton.LeftButton); spin(0.1)
    chk([p["name"] for p in mw._prefs["nup_margin_presets"]] == ["보통", "좁게", "내 여백", "넓게"]
        and cm.currentText() == "내 여백", "D5 ▲ 로 한 칸 위, 계속 골라 둠")
    pick_text(cm, "좁게")
    type_spin(pv.sp["margin_top"], 19)
    QInputDialog.getText = staticmethod(lambda *a, **k: ("좁게", True))
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    QTest.mouseClick(sv, Qt.MouseButton.LeftButton); spin(0.1)
    st = mw._prefs["nup_margin_presets"]
    chk([p["name"] for p in st].index("좁게") == 1 and st[1]["margin_top"] == 19, "D6 같은 이름은 그 자리에서 덮어쓰기(기본 항목도)")
    pick_text(cm, "보통")
    QTest.mouseClick(de, Qt.MouseButton.LeftButton); spin(0.1)
    chk("보통" not in [p["name"] for p in mw._prefs["nup_margin_presets"]] and cm.findText("보통") < 0,
        "D7 기본 항목도 삭제")
    chk("보통" not in [p["name"] for p in api["get_parts"]("margin")], "D8 지운 기본 항목은 다시 안 생긴다")
    cc = pv.cmb_crop_style
    cu, cd_, cs, cdel = pv.part_buttons("crop")
    pick_text(cc, "좌우")
    QTest.mouseClick(cd_, Qt.MouseButton.LeftButton); spin(0.1)
    chk([p["name"] for p in mw._prefs["nup_crop_presets"]] == ["없음", "상하좌우", "상하", "좌우"][:3] + ["좌우"]
        and not cd_.isEnabled(), "D9 맨 아래면 ▼ 꺼짐")
    dlg.close()
    before = (list(mw._prefs["nup_margin_presets"]), list(mw._prefs["nup_crop_presets"]))
    mw._apply_prefs({})
    chk((mw._prefs.get("nup_margin_presets"), mw._prefs.get("nup_crop_presets")) == before,
        "D10 환경설정 [확인](_apply_prefs)을 지나도 남는다")
    pay = (mw._build_settings_payload().get("preferences") or {})
    chk(pay.get("nup_margin_presets") == before[0] and pay.get("nup_crop_presets") == before[1],
        "D10b settings.json 저장 페이로드에 두 목록")
    mw._prefs["nup_crop_presets"] = []
    chk(api["get_parts"]("crop") == [], "D11 빈 목록은 빈 채로(다시 심지 않음)")
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
