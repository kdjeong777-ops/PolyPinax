# -*- coding: utf-8 -*-
"""261115-7: 인쇄 창 '다단 인쇄' — 프린터 옵션 처음 값은 다단 설정, 사용자가 바꿀 수 있다 (마스터 §11.10.1).

사용자 지시: "프린터로 다단인쇄시 프린터.옵션을 다단인쇄의 설정으로 초기 세팅을 변경하되,
            사용자가 변경시 해당 변경사항 적용하여 프린트할 수 있게"

A. 다단을 켜면 용지·단면/양면·인쇄 크기(맞춤)·방향 자동이 다단 설정 값, 콤보는 잠기지 않는다
B. 켠 뒤 사용자가 바꾼 값(키 입력)이 인쇄에 넘기는 값(duplex_mode·page_size·size_mode)에 남는다,
   단면/양면을 바꾸면 다단 설정의 인쇄 면도 바뀐다(제본 여백·홀수 시작이 갈리지 않게)
C. 스타일을 다시 고르면 다시 맞춘다, 끄면 켜기 전 네 값으로 되돌린다
D. 양면을 못 한다고 알리는 프린터 → 양면 항목 꺼짐·단면, 모름(None)이면 막지 않음
"""
import os, sys, tempfile, shutil, faulthandler, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(180, exit=True)
from pathlib import Path

import fitz
from PyQt6.QtCore import QStandardPaths, Qt
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPageSize
from PyQt6.QtPrintSupport import QPrinter
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def spin(sec=0.05):
    t0 = time.time()
    while time.time() - t0 < sec:
        app.processEvents(); time.sleep(0.01)


def pick(cmb, idx):
    """콤보를 키보드(↑↓)로 그 자리까지."""
    cmb.setFocus(); spin(0.02)
    guard = 0
    while cmb.currentIndex() != idx and guard < 200:
        QTest.keyClick(cmb, Qt.Key.Key_Down if cmb.currentIndex() < idx else Qt.Key.Key_Up)
        guard += 1
    spin()


root = Path(tempfile.mkdtemp(prefix="polypdf_nupopts_"))
try:
    src = root / "원본.pdf"
    d = fitz.open()
    for i in range(8):
        d.new_page(width=595, height=842).insert_text((72, 72), f"page {i + 1}", fontsize=40)
    d.save(str(src)); d.close()

    from viewer.widgets.print_dialog import PrintScopeDialog
    dlg = PrintScopeDialog(8, 0, 0, 0, None, sample=str(src))
    dlg._printer_duplex_supported = lambda: True          # 이 PC 프린터와 무관하게
    dlg._apply_duplex_support()
    # 프린터가 없는 기계에서도 용지 목록이 있게(이름으로 찾는다)
    for nm, pid in (("A4", QPageSize.PageSizeId.A4), ("A3", QPageSize.PageSizeId.A3)):
        if dlg.cmb_paper.findText(nm) < 0:
            dlg.cmb_paper.addItem(nm, QPageSize(pid))
    dlg.show(); spin(0.2)
    # 켜기 전 사용자 값: 자동 용지 · 단면 · 실제 크기 · 방향 자동 끔
    dlg.cmb_paper.setCurrentIndex(0)
    dlg.cmb_duplex.setCurrentIndex(dlg.cmb_duplex.findData("none"))
    dlg.cmb_size.setCurrentIndex(1)
    dlg.chk_auto_orient.setChecked(False)
    before = dlg._printer_state()

    # A
    dlg._nup_settings = {"page_size": "A3", "duplex": True, "duplex_side": "short"}
    QTest.mouseClick(dlg.chk_nup, Qt.MouseButton.LeftButton); spin()
    chk(dlg.chk_nup.isChecked(), "A0 다단 체크(마우스)")
    chk(dlg.cmb_paper.currentText() == "A3", "A1 용지 = 다단 용지", dlg.cmb_paper.currentText())
    chk(dlg.cmb_duplex.currentData() == "short", "A2 단면/양면 = 다단 인쇄 면", str(dlg.cmb_duplex.currentData()))
    chk(dlg.size_mode()[0] == "fit" and dlg.auto_orient(), "A3 인쇄 크기 맞춤·방향 자동 켬")
    chk(dlg.cmb_duplex.isEnabled() and dlg.cmb_paper.isEnabled() and dlg.cmb_size.isEnabled()
        and dlg.chk_auto_orient.isEnabled(), "A4 잠그지 않는다")

    # B
    pick(dlg.cmb_duplex, dlg.cmb_duplex.findData("long"))
    chk(dlg.duplex_mode() == QPrinter.DuplexMode.DuplexLongSide, "B1 바꾼 면이 인쇄에 넘기는 값", str(dlg.duplex_mode()))
    ns = dlg.nup_settings()
    chk(ns["duplex"] is True and ns["duplex_side"] == "long", "B2 다단 설정의 인쇄 면도 긴 쪽", str((ns["duplex"], ns["duplex_side"])))
    pick(dlg.cmb_duplex, dlg.cmb_duplex.findData("none"))
    chk(dlg.nup_settings()["duplex"] is False, "B3 단면으로 바꾸면 다단도 단면")
    pick(dlg.cmb_paper, dlg.cmb_paper.findText("A4"))
    pick(dlg.cmb_size, 2)
    chk(dlg.page_size() is not None and dlg.page_size().name() == "A4" and dlg.size_mode()[0] == "scale",
        "B4 바꾼 용지·인쇄 크기가 남는다", str(dlg.size_mode()))
    chk(dlg.nup_settings().get("page_size") == "A3", "B5 용지는 한쪽으로만(다단 용지 그대로 — 맞춤으로 찍는다)")

    # C
    dlg.cmb_preset.addItem("A3 양면", {"name": "A3 양면", "page_size": "A3", "duplex": True, "duplex_side": "long"})
    dlg.cmb_preset.setCurrentIndex(dlg.cmb_preset.count() - 1)
    dlg.cmb_preset.activated.emit(dlg.cmb_preset.count() - 1); spin()
    chk(dlg.cmb_paper.currentText() == "A3" and dlg.cmb_duplex.currentData() == "long" and dlg.size_mode()[0] == "fit",
        "C1 스타일을 다시 고르면 다시 맞춘다")
    QTest.mouseClick(dlg.chk_nup, Qt.MouseButton.LeftButton); spin()
    chk(not dlg.chk_nup.isChecked() and dlg._printer_state() == before, "C2 끄면 켜기 전 네 값으로",
        str((dlg._printer_state(), before)))

    # D
    dlg._printer_duplex_supported = lambda: False
    dlg.cmb_duplex.setCurrentIndex(dlg.cmb_duplex.findData("long"))
    dlg._apply_duplex_support()
    m = dlg.cmb_duplex.model()
    offs = [not m.item(i).isEnabled() for i in range(dlg.cmb_duplex.count()) if dlg.cmb_duplex.itemData(i) != "none"]
    chk(all(offs) and dlg.cmb_duplex.currentData() == "none", "D1 양면 못 하는 프린터 → 양면 항목 꺼짐·단면")
    dlg._nup_settings = {"duplex": True, "duplex_side": "long"}
    QTest.mouseClick(dlg.chk_nup, Qt.MouseButton.LeftButton); spin()
    chk(dlg.cmb_duplex.currentData() == "none", "D2 다단이 양면이어도 그 프린터는 단면", str(dlg.cmb_duplex.currentData()))
    QTest.mouseClick(dlg.chk_nup, Qt.MouseButton.LeftButton); spin()
    dlg._printer_duplex_supported = lambda: None
    dlg._apply_duplex_support()
    chk(all(m.item(i).isEnabled() for i in range(dlg.cmb_duplex.count())), "D3 모름(None)이면 막지 않는다")
    dlg.done(0)
except Exception:
    import traceback
    traceback.print_exc()
    fails.append("예외")
finally:
    shutil.rmtree(root, ignore_errors=True)

print("\n=== " + ("ALL PASS" if not fails else f"FAILURE ({len(fails)})") + " ===")
for m_ in fails:
    print(" -", m_)
sys.stdout.flush()
os._exit(1 if fails else 0)
