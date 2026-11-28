# -*- coding: utf-8 -*-
"""261128-3(디자인 SOT §2.9.5, 사용자 지시·결정 '단추 이름·이름 변경·삭제'): 즐겨찾기 탭 폴더·파일 단추 오른쪽 누름.

종전: 단추 위 오른쪽 누름은 리본 바탕 메뉴('리본 메뉴 보이기'·'모음 메뉴 관리')뿐 — 이름을 고치거나 지울 수 없었다.
수정 전 코드로 A 가 실패한다.

A. 실제 단추 위 오른쪽 누름(QContextMenuEvent) → 메뉴 `단추 이름`·`이름 변경`·`삭제`·`항목 관리`
B. `단추 이름` → short 가 저장되고 단추 글이 바뀐다 · 비우면 short 가 빠진다
C. `이름 변경` → name 이 저장된다(▾ 목록 글)
D. `삭제` → 확인에 '아니요' 면 그대로, '예' 면 목록·단추에서 빠지고 설정에 저장
E. 단추가 아닌 리본 바탕 오른쪽 누름은 종전 리본 메뉴
"""
import os, sys, faulthandler, tempfile, shutil
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(180, exit=True)

from pathlib import Path
from PyQt6.QtCore import QStandardPaths, QPoint, Qt
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtGui import QContextMenuEvent
from PyQt6.QtWidgets import QApplication, QMenu, QInputDialog, QMessageBox, QToolButton
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
from PyQt6.QtCore import QCoreApplication as _QCA
_QCA.setApplicationName("polypdf_fav_ctx_%d" % os.getpid())     # 검사 작성 SOT §14.7.2 의 3
import modal_guard
modal_guard.install(label=lambda: "즐겨찾기 단추 메뉴", echo=False)   # §14.7.2 의 6 — 필요한 답은 아래에서 다시 끼운다
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


# 메뉴 exec 를 붙잡아 고를 항목을 정한다 — 메뉴 내용은 실제 그대로
_menus = []
_pick = {"text": None}


def _fake_exec(self, *a, **k):
    _menus.append([x.text() for x in self.actions() if not x.isSeparator()])
    for x in self.actions():
        if _pick["text"] is not None and x.text() == _pick["text"]:
            x.trigger()
            return x
    return None


QMenu.exec = _fake_exec
_answers = {"text": ("", True), "yes": QMessageBox.StandardButton.No}
QInputDialog.getText = staticmethod(lambda *a, **k: _answers["text"])
QMessageBox.question = staticmethod(lambda *a, **k: _answers["yes"])


def fav_buttons(mw):
    row = mw._ribbon.row("fav")
    return {b.text(): b for b in row.buttons() if isinstance(b, QToolButton) and not b.property("ribbonMark")}


def right_click(w, pos=None):
    pos = pos or QPoint(w.width() // 2, w.height() // 2)
    ev = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, pos, w.mapToGlobal(pos))
    QApplication.sendEvent(w, ev)
    QTest.qWait(40)


root = Path(tempfile.mkdtemp(prefix="polypdf_favctx_"))
try:
    import test_fixtures as _fx
    from viewer.app import MainWindow
    d1 = root / "폴더1"; d1.mkdir(); d2 = root / "폴더2"; d2.mkdir()
    f1 = d1 / "파일1.pdf"; shutil.copy(_fx.text_pdf(), f1)
    saved = []
    mw = MainWindow()
    mw._save_settings_now = lambda: saved.append([dict(f) for f in mw._favorites])
    mw.resize(1920, 900); mw.show(); QTest.qWait(100)
    mw._favorites = [{"kind": "folder", "name": "폴더1", "folder": str(d1)},
                     {"kind": "folder", "name": "폴더2", "folder": str(d2)},
                     {"kind": "file", "name": "파일1", "file": str(f1), "folder": str(d1)}]
    mw._refresh_favorites_menu(); QTest.qWait(50)
    mw._ribbon.select("fav"); QTest.qWait(50)

    # A
    btns = fav_buttons(mw)
    chk("폴더1" in btns and "파일1" in btns, "폴더·파일 단추가 있다", list(btns))
    _menus.clear(); _pick["text"] = None
    right_click(btns["폴더1"])
    want = ["단추 이름", "이름 변경", "삭제", "항목 관리"]
    chk(bool(_menus) and _menus[-1] == want, "A 단추 오른쪽 누름 → 단추 이름·이름 변경·삭제·항목 관리", _menus)

    # B 단추 이름
    _pick["text"] = "단추 이름"; _answers["text"] = ("짧게", True)
    right_click(fav_buttons(mw)["폴더1"]); QTest.qWait(60)
    f = mw._favorites[0]
    chk(f.get("short") == "짧게", "B 단추 이름 → short 저장", f)
    chk("짧게" in fav_buttons(mw), "B 단추 글이 바뀐다", list(fav_buttons(mw)))
    chk(bool(saved) and saved[-1][0].get("short") == "짧게", "B 설정에 저장", saved[-1:] if saved else None)
    _answers["text"] = ("", True)
    right_click(fav_buttons(mw)["짧게"]); QTest.qWait(60)
    chk("short" not in mw._favorites[0], "B 비우면 short 가 빠진다(자동 이름)", mw._favorites[0])

    # C 이름 변경
    _pick["text"] = "이름 변경"; _answers["text"] = ("새파일이름", True)
    right_click(fav_buttons(mw)["파일1"]); QTest.qWait(60)
    names = [x.get("name") for x in mw._favorites]
    chk("새파일이름" in names and "파일1" not in names, "C 이름 변경 → name 저장", names)
    drop = [a.text() for a in mw.menu_fav_files.actions()]
    chk(any("새파일이름" in t for t in drop), "C ▾ 목록 글도 바뀐다", drop)

    # D 삭제
    _pick["text"] = "삭제"; _answers["yes"] = QMessageBox.StandardButton.No
    right_click(fav_buttons(mw)["폴더2"]); QTest.qWait(60)
    chk(len(mw._favorites) == 3, "D 확인에 '아니요' 면 그대로", len(mw._favorites))
    _answers["yes"] = QMessageBox.StandardButton.Yes
    n_saved = len(saved)
    right_click(fav_buttons(mw)["폴더2"]); QTest.qWait(60)
    chk([x.get("name") for x in mw._favorites] == ["폴더1", "새파일이름"], "D '예' 면 목록에서 빠진다",
        [x.get("name") for x in mw._favorites])
    chk("폴더2" not in fav_buttons(mw), "D 단추에서도 빠진다", list(fav_buttons(mw)))
    chk(len(saved) > n_saved, "D 설정에 저장")

    # E 바탕
    _pick["text"] = None; _menus.clear()
    right_click(mw._ribbon.row("fav"), QPoint(2, 5))   # 왼쪽 빈 칸
    chk(bool(_menus) and "리본 메뉴 보이기" in _menus[-1], "E 리본 바탕 오른쪽 누름은 종전 메뉴", _menus)
    mw.close()
finally:
    shutil.rmtree(root, ignore_errors=True)

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
sys.stdout.flush()
os._exit(1 if fails else 0)
