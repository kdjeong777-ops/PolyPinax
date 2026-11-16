# -*- coding: utf-8 -*-
"""261116-11: 썸네일을 옮기면 쪽 번호가 곧바로 새 순서로 (책갈피창·저장 SOT §4.7.7, 사용자 결정 A).

사용자 보고: "썸네일의 위치를 이동시 자동으로 페이지 번호가 바뀌지 않아. 저장해야 바뀌어."
결정 A: 썸네일 번호 띠와 본문 쪽 칸은 지금 목록 순서(저장 뒤 번호), 순서가 바뀐 쪽 툴팁에 '원래 p.N'.
메뉴의 (p.N)·파일 쪽으로 하는 일은 그대로(저장 전에는 원래 쪽).

띠는 구현과 무관하게 **그림으로** 견준다 — 같은 크기 쪽이면 같은 번호의 띠는 같은 그림이다
(옮기기 전 n째 줄의 띠 = 옮긴 뒤 n째 줄의 띠). 수정 전 코드는 띠가 원래 쪽 번호라 어긋난다.
실제 키(Alt+↑·Delete·쪽 칸에 쓰고 Enter)로 움직인다.
"""
import os, sys, tempfile, shutil
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")   # 오프스크린은 글꼴이 없어 띠 숫자가 그려지지 않는다
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pathlib import Path

import fitz
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
import modal_guard
modal_guard.install(label=lambda: "썸네일 쪽 번호")
QCoreApplication.setApplicationName("polypdf_thumb_renum_%d" % os.getpid())
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def spin(n=8):
    for _ in range(n):
        app.processEvents(); QTest.qWait(30)


root = Path(tempfile.mkdtemp(prefix="polypdf_renum261116_"))
try:
    src = root / "M.pdf"
    d = fitz.open()
    for i in range(8):
        d.new_page().insert_text((72, 72), f"PAGE {i + 1}")
    d.save(str(src)); d.close()
    other = root / "O.pdf"
    d = fitz.open()
    d.new_page().insert_text((72, 72), "OTHER 1")
    d.save(str(other)); d.close()
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    _boxes = []
    QMessageBox.information = staticmethod(lambda *a, **k: (_boxes.append(a[1:3]), QMessageBox.StandardButton.Ok)[1])
    QMessageBox.warning = staticmethod(lambda *a, **k: (_boxes.append(a[1:3]), QMessageBox.StandardButton.Ok)[1])
    from viewer.app import MainWindow
    from viewer.history import HistoryItem
    mw = MainWindow(); mw.resize(1300, 1400); mw.show(); app.processEvents()
    mw.open_folder(root); spin(15)
    mw._load_main(HistoryItem(str(src), 0, "", "bookmark")); spin(10)
    if not mw._in_edit():
        mw.bookmark_tree.btn_edit.setChecked(True); spin(4)
    pt, L, mv = mw.page_thumbs, mw.page_thumbs.list, mw.main_view

    def band(row):
        """그 줄 카드의 번호 띠 그림(아래 NUM_BAND 줄)."""
        it = L.item(row)
        ic = it.icon()
        if ic.isNull():
            return None
        img = ic.pixmap(ic.availableSizes()[0], 1.0).toImage()
        return img.copy(0, img.height() - pt.NUM_BAND, img.width(), pt.NUM_BAND)

    def wait_icons(rows):
        for _ in range(60):
            pt._render_visible(); spin(2)
            if all(not L.item(r).icon().isNull() for r in rows) and not pt.thumbs_busy():
                return True
        return False

    def tip(row):
        return L.item(row).data(Qt.ItemDataRole.ToolTipRole)

    def click(row):
        it = L.item(row); L.setCurrentItem(it); L.itemClicked.emit(it); spin()

    chk(wait_icons(range(8)), "준비 — 8장 썸네일이 그려짐")
    before = [band(r) for r in range(8)]
    chk(all(before[a] != before[b] for a in range(8) for b in range(a + 1, 8)), "준비 — 번호 띠 그림이 쪽마다 다르다")

    # ① 7쪽을 Alt+↑ 세 번 → [1,2,3,7,4,5,6,8], 띠는 1..8 그대로
    click(6); L.setFocus()
    for _ in range(3):
        QTest.keyClick(L, Qt.Key.Key_Up, Qt.KeyboardModifier.AltModifier); spin()
    chk(pt.current_nav_ids() == [0, 1, 2, 6, 3, 4, 5, 7], "① 준비 — 7쪽을 넷째로", str(pt.current_nav_ids()))
    wait_icons(range(8))
    same = [r for r in range(8) if band(r) == before[r]]
    chk(same == list(range(8)), "① 옮긴 뒤 띠 번호가 곧바로 1..8 (저장 전)", "같은 줄=%s" % same)
    chk(tip(3) == "원래 p.7" and tip(4) == "원래 p.4" and not tip(0) and not tip(7),
        "① 순서가 바뀐 쪽 툴팁에 '원래 p.N'", "%r %r %r %r" % (tip(3), tip(4), tip(0), tip(7)))
    chk(mv.current_page() == 6 and mv.spin_page.value() == 4 and mv.lbl_page_total.text() == "/ 8",
        "① 본문 쪽 칸은 4 / 8 (본문은 원래 7쪽)",
        "page=%d spin=%d %s" % (mv.current_page(), mv.spin_page.value(), mv.lbl_page_total.text()))

    # ② 쪽 칸에 5 를 쓰고 Enter → 목록 다섯째(원래 4쪽)
    sp = mv.spin_page
    sp.setFocus(); sp.selectAll()
    QTest.keyClicks(sp, "5"); QTest.keyClick(sp, Qt.Key.Key_Return); spin()
    chk(mv.current_page() == 3 and sp.value() == 5, "② 쪽 칸 5 → 목록 다섯째 쪽(원래 4쪽)",
        "page=%d spin=%d" % (mv.current_page(), sp.value()))

    # ③ 맨 위를 Delete → 7장, 띠 1..7
    click(0); L.setFocus()
    QTest.keyClick(L, Qt.Key.Key_Delete); spin()
    wait_icons(range(7))
    same = [r for r in range(7) if band(r) == before[r]]
    chk(L.count() == 7 and same == list(range(7)), "③ 지운 뒤 띠 1..7", "같은 줄=%s" % same)
    chk(mv.lbl_page_total.text() == "/ 7" and sp.value() == mv.page_nav.spin.value(),
        "③ 본문 쪽 칸 전체 / 7", mv.lbl_page_total.text())

    # ④ 다른 파일 쪽을 끼움 → 쪽 칸 / 8, 그 쪽을 누르면 그 자리 번호
    pt.insert_external_pages(2, str(other), [0]); spin()
    srow = next(r for r in range(L.count()) if isinstance(L.item(r).data(Qt.ItemDataRole.UserRole), (tuple, list)))
    wait_icons(range(8))
    click(srow)
    chk(pt.is_staged_page(mv.current_page()) and sp.value() == srow + 1 and mv.lbl_page_total.text() == "/ 8",
        "④ 끼운 쪽 = 자리 번호 / 8", "row=%d spin=%d %s" % (srow, sp.value(), mv.lbl_page_total.text()))
    chk((L.item(srow).data(pt.BAND_ROLE) or (None,) * 9)[8] == "%d · 붙여넣기" % (srow + 1), "④ 끼운 쪽 띠 'n · 붙여넣기'")
    rest = [r for r in range(8) if r != srow]
    same = [r for r in rest if band(r) == before[r]]
    chk(same == rest, "④ 끼운 뒤 나머지 띠가 자리 번호", "row=%d 같은 줄=%s" % (srow, same))

    # ⑤ 되돌리기(끼움 취소) → 다시 / 7
    mw.action_edit_undo(); spin(6)
    chk(L.count() == 7 and mv.lbl_page_total.text() == "/ 7", "⑤ 되돌리기 뒤 쪽 칸 / 7",
        "count=%d %s" % (L.count(), mv.lbl_page_total.text()))
    wait_icons(range(7))
    same = [r for r in range(7) if band(r) == before[r]]
    chk(same == list(range(7)), "⑤ 되돌리기 뒤 띠 1..7", "같은 줄=%s" % same)

    # ⑥ 저장(_finalize_save 한 길) 뒤 — 쪽 번호 = 목록 순서, 툴팁 없음
    click(2)
    mw.bookmark_tree._op_save(file_path=str(src)); spin(15)
    chk(not pt.is_page_dirty() and mv.spin_page.value() == mv.current_page() + 1 and mv.lbl_page_total.text() == "/ 7",
        "⑥ 저장 뒤 쪽 칸 = 쪽 번호", "page=%d spin=%d %s" % (mv.current_page(), mv.spin_page.value(), mv.lbl_page_total.text()))
    wait_icons(range(7))
    chk(all(band(r) == before[r] for r in range(7)) and not any(tip(r) for r in range(7)),
        "⑥ 저장 뒤 띠 1..7·'원래 p.N' 없음")
    chk(not _boxes, "경고 창 없음", str(_boxes))
finally:
    shutil.rmtree(root, ignore_errors=True)

print("\n=== " + ("ALL PASS" if not fails else f"FAILURE ({len(fails)})") + " ===")
for m in fails:
    print(" -", m)
sys.stdout.flush()
os._exit(1 if fails else 0)
