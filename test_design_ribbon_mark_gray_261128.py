# -*- coding: utf-8 -*-
"""261128-1(디자인 SOT §2.9.7 ★, 사용자 지시·결정 '회색조 아이콘'): 리본 분류명(바깥 왼쪽 표시) 그림은 색이 없다.

종전 결함(사용자 보고): 파일 탭 `열기`·`저장`, 즐겨찾기 탭 `등록 폴더`·`등록 파일` 분류명 그림이 색 아이콘이라
누르는 단추처럼 보였다. 수정 전 코드로 A 가 실패한다(노란 폴더·파란 플로피의 채도).

A. 밝게·다크 둘 다 — 실제 리본 줄에 놓인 분류명 `QLabel` 의 픽마프 픽셀이 무채색(채도 ≈ 0)
B. 그 회색은 테마 토큰 `ribbon.MARK_GRAY` 범위 안 — 테마를 바꾸면 다시 칠해진다(밝게와 다크의 값이 다르다)
C. 실제 누르는 단추 그림(즐겨찾기 `추가` 폴더 단추)은 색 그대로
D. 분류명은 단추가 아니다(QLabel — 눌림·마우스 올림 반응 없음)
"""
import os, sys, faulthandler, tempfile, shutil
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(180, exit=True)

from pathlib import Path
from PyQt6.QtCore import QStandardPaths
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QLabel, QToolButton
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
from PyQt6.QtCore import QCoreApplication as _QCA
_QCA.setApplicationName("polypdf_mark_gray_%d" % os.getpid())   # 검사 작성 SOT §14.7.2 의 3
import modal_guard
modal_guard.install(label=lambda: "분류명 회색조", echo=False)      # §14.7.2 의 6
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def stats(img):
    """불투명 픽셀의 (최대 채도 0~255, 회색 최소, 회색 최대, 픽셀 수)."""
    from PyQt6.QtGui import QImage
    img = img.convertToFormat(QImage.Format.Format_ARGB32)     # 미리곱한 값이 아닌 실제 색으로 읽는다
    sat, lo, hi, n = 0, 255, 0, 0
    for y in range(img.height()):
        for x in range(img.width()):
            c = QColor.fromRgba(img.pixel(x, y))
            if c.alpha() < 128:
                continue
            r, g, b = c.red(), c.green(), c.blue()
            sat = max(sat, max(r, g, b) - min(r, g, b))
            lo, hi = min(lo, r), max(hi, r)
            n += 1
    return sat, lo, hi, n


def marks(row):
    out = []
    for a in row.actions():
        if a.property("ribbonMark"):
            w = row.widgetForAction(a)
            if isinstance(w, QLabel) and w.pixmap() is not None and not w.pixmap().isNull():
                out.append((a.toolTip(), w))
    return out


root = Path(tempfile.mkdtemp(prefix="polypdf_markgray_"))
try:
    import test_fixtures as _fx
    from viewer.app import MainWindow
    from viewer.widgets import ribbon as R
    d1 = root / "폴더1"; d1.mkdir()
    f1 = d1 / "파일1.pdf"
    shutil.copy(_fx.text_pdf(), f1)

    mw = MainWindow()
    mw.resize(1920, 900); mw.show(); QTest.qWait(100)
    mw._favorites = [{"kind": "folder", "name": "폴더1", "folder": str(d1)},
                     {"kind": "file", "name": "파일1", "file": str(f1), "folder": str(d1)}]
    mw._refresh_favorites_menu()
    QTest.qWait(80)

    seen = {}
    for mode in ("light", "dark"):
        mw.apply_theme(mode); QTest.qWait(80)
        dark = mode == "dark"
        gray = getattr(R, "MARK_GRAY", None)
        found = []
        for key in ("file", "fav"):
            mw._ribbon.select(key); QTest.qWait(50)
            found += marks(mw._ribbon.row(key))
        chk(len(found) >= 4, f"[{mode}] 그림 분류명 넷(열기·저장·등록 폴더·등록 파일)이 리본에 있다", [t for t, _ in found])
        for tip, w in found:
            sat, lo, hi, n = stats(w.pixmap().toImage())
            chk(n > 10 and sat <= 6, f"A [{mode}] '{tip}' 분류명 그림이 무채색", f"채도 {sat}, 픽셀 {n}")
            if gray is not None:
                g0, g1 = QColor(gray[dark][0]).red(), QColor(gray[dark][1]).red()
                chk(g0 - 2 <= lo and hi <= g1 + 2, f"B [{mode}] '{tip}' 회색이 MARK_GRAY 범위 안", f"{lo}~{hi} / {g0}~{g1}")
            else:
                chk(False, "B ribbon.MARK_GRAY 토큰이 있다")
            seen.setdefault(tip, []).append((lo, hi))
            chk(not isinstance(w, QToolButton), f"D [{mode}] '{tip}' 분류명은 단추가 아니다")
        # C: 실제 누르는 단추(추가 › 폴더)는 색 그대로
        mw._ribbon.select("fav"); QTest.qWait(30)
        row = mw._ribbon.row("fav")
        a_add = (mw._fav_add_acts or {}).get("fav.add_folder")
        bw = row.widgetForAction(a_add) if a_add is not None else None
        if bw is not None:
            ic = bw.icon().pixmap(16, 16).toImage()
            chk(stats(ic)[0] > 60, f"C [{mode}] '추가' 폴더 단추 그림은 색 그대로", stats(ic))
        else:
            chk(False, f"C [{mode}] '추가' 폴더 단추를 찾는다")
        # E(261128-4): 글자 분류명은 MARK_FG — 실제 리본 줄에 놓인 QLabel 의 그려진 글 색
        fg = getattr(R, "MARK_FG", None)
        txt = []
        for key in ("fav", "tools"):
            mw._ribbon.select(key); QTest.qWait(30)
            row = mw._ribbon.row(key)
            for a in row.actions():
                w = row.widgetForAction(a) if a.property("ribbonMark") else None
                if isinstance(w, QLabel) and w.text():
                    txt.append((w.text(), w.palette().color(w.foregroundRole()).name()))
        chk(len(txt) >= 5, f"E [{mode}] 글자 분류명(최근·등록·추가·생성·PDF)이 리본에 있다", txt)
        for t, c in txt:
            chk(fg is not None and c == QColor(fg[dark]).name(), f"E [{mode}] '{t}' 글 색이 MARK_FG", c)
        # F(261128-4): 다크 띠와 그룹 바탕 차이가 커졌다(밝기 차 ≥ 20) — 실제 리본 줄 바탕 픽셀
        if dark:
            row = mw._ribbon.row("fav")
            img = row.grab().toImage()
            band = QColor.fromRgb(img.pixel(2, img.height() // 2))
            grp = QColor(R.GROUP_BG[True])
            chk(grp.lightness() - band.lightness() >= 20, "F [dark] 띠가 그룹 바탕보다 충분히 진하다",
                (band.name(), grp.name()))
    for tip, v in seen.items():
        chk(len(v) == 2 and v[0] != v[1], f"B '{tip}' 테마를 바꾸면 다시 칠해진다", v)
    mw.close()
finally:
    shutil.rmtree(root, ignore_errors=True)

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
sys.stdout.flush()
os._exit(1 if fails else 0)          # Qt 종료 단계 충돌(0xC0000409) 없이 — 다른 메인 창 검사와 같게
