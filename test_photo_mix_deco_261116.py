# -*- coding: utf-8 -*-
"""261116-25 섞은 사진 칸 꾸미기·흐리게 끄기·사진 열 때 편집 모드 (사진 보기 SOT §4.47·§4.48, D23·D24).

실제 MainWindow 로(오프스크린, 실제 설정 폴더를 쓰지 않는다 — 검사 작성 SOT §14.7.2 의 3). 단추·메뉴 항목·마우스는 실제 것으로.
A. PDF 모드에서 편집을 끈 채 보기 탭 `2단` ▾ PIX → 편집 모드가 켜지고(설정 '시작 모드' = 편집) 섞은 사진 칸에 꾸미기 줄이 보인다
B. 섞은 사진 칸이 활성이면 PDF 전용 명령(`tools.merge`)이 흐리게 꺼지고(보인 채), 왼쪽 PDF 칸을 누르면 되살아난다
C. 섞은 사진 칸(창 폴더 밖의 다른 폴더 사진)에 색상버튼·마우스로 선을 긋고 [저장] → **그 사진 폴더의** page_meta.json 에 남는다
D. 다시 긋고 편집을 끄며 '되돌리기(버림)' → 그 폴더 사이드카는 그대로(선 하나)
E. 설정 '시작 모드' = 보기 이면 사진을 열어도 편집 모드를 켜지 않는다
F. 설정 = 편집, 편집을 끈 채 사진 모드로 들어가면 켜진다 · 섞은 2단을 놓으면 PDF 전용 명령이 되살아나 있다
"""
import os, sys, tempfile, shutil, time, json
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pathlib import Path
from PyQt6.QtCore import QStandardPaths, QCoreApplication, QPoint, QPointF, QEvent, Qt
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2 의 3
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_mix_deco_%d" % os.getpid())
import modal_guard
modal_guard.install(label=lambda: "섞은 칸 꾸미기")
import test_fixtures
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


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


def norm(p):
    return os.path.normcase(str(Path(str(p)))) if p else None


def mouse(mv, kind, p, buttons):
    vp = mv.view.viewport()
    mv.eventFilter(vp, QMouseEvent(kind, QPointF(p), Qt.MouseButton.LeftButton, buttons, Qt.KeyboardModifier.NoModifier))


def stroke(mv, a, b):
    pr = mv._page_view_rect()
    p0, p1 = mv._norm_to_view(a[0], a[1], pr), mv._norm_to_view(b[0], b[1], pr)
    mouse(mv, QEvent.Type.MouseButtonPress, p0, Qt.MouseButton.LeftButton); pump(lambda: False, 0.05)
    for k in range(1, 7):
        q = QPoint(int(p0.x() + (p1.x() - p0.x()) * k / 6), int(p0.y() + (p1.y() - p0.y()) * k / 6))
        mouse(mv, QEvent.Type.MouseMove, q, Qt.MouseButton.LeftButton); pump(lambda: False, 0.02)
    mouse(mv, QEvent.Type.MouseButtonRelease, p1, Qt.MouseButton.NoButton); pump(lambda: False, 0.1)


def side_drawings(folder, name):
    f = Path(folder) / "page_meta.json"
    if not f.exists():
        return []
    d = json.loads(f.read_text(encoding="utf-8"))
    rec = (d.get("files") or {}).get(name) or {}
    return (rec.get("drawings") or {}).get("0") or []


tmp = Path(tempfile.mkdtemp(prefix="polypdf_mix_deco_"))
try:
    from PIL import Image
    pdfs, pics = tmp / "문서", tmp / "사진"
    pdfs.mkdir(); pics.mkdir()
    a_pdf = pdfs / "가.pdf"
    shutil.copy(test_fixtures.text_pdf(), a_pdf)
    ph = []
    for i, c in enumerate(((200, 60, 60), (60, 200, 60))):
        p = pics / ("p%d.jpg" % (i + 1))
        Image.new("RGB", (800, 600), c).save(p)
        ph.append(p)

    from viewer.app import MainWindow
    mw = MainWindow(); mw._skip_save_on_close = True
    mw.resize(1400, 900); mw.show(); pump()
    mw._prefs.setdefault("picture", {})["view_kind"] = "mixed"
    mw._prefs["open_edit_mode"] = True
    mw._photo_apply_view_kind()
    top, bot = mw.bookmark_tree, mw.bookmark_tree_right
    answer = {"v": "save"}
    mw._confirm_edit_save = lambda switching=False: answer["v"]

    # 사진 모드의 기억 — 사진 폴더에서 p1, 그 뒤 PDF 모드
    mw._set_photo_mode(True); pump()
    mw.open_folder(pics); pump(lambda: len(mw._photo_tree_list()) == 2)
    mw._on_bookmark_activated(str(ph[0]), 0); pump()
    top.btn_edit.setChecked(False); pump()
    mw._set_photo_mode(False); pump()
    mw.open_folder(pdfs); pump(lambda: len(top.ordered_pdf_files() or []) == 1)
    mw._on_bookmark_activated(str(a_pdf), 0); pump(lambda: norm(mw._mv[0].current_file()) == norm(a_pdf))
    top.btn_edit.setChecked(False); pump()
    chk(not mw._photo_mode and not top.is_edit_mode(), "준비 — PDF 모드·편집 꺼짐")

    # A — ▾ PIX
    kinds = {a.objectName(): a for a in mw._view_acts["split"].menu().actions()}
    kinds["split_kind_pix"].trigger(); pump(lambda: mw._mv[1].current_file() is not None)
    mv1 = mw._mv[1]
    pump(lambda: mv1._draw_bar.isVisible(), 3)
    chk(mw._mix_on_now() and norm(mv1.current_file()) == norm(ph[0]), "A 섞은 2단 — 오른쪽 p1", str(mv1.current_file()))
    chk(top.is_edit_mode(), "A 사진 칸 2단을 띄우면 편집 모드(설정 = 편집)")
    chk(mv1._draw_bar.isVisible() and mw._mv[0]._draw_bar.isVisible(), "A 섞은 사진 칸에도 꾸미기 줄",
        "%s %s" % (mv1._draw_bar.isVisible(), mw._mv[0]._draw_bar.isVisible()))

    # B — 흐리게 끄기
    merge = mw._cmds.get("tools.merge")
    chk(mw._active_pane == 1 and merge is not None and not merge.isEnabled() and merge.isVisible(),
        "B 섞은 사진 칸 활성 — PDF 전용 명령 흐리게(보인 채)", "%s %s" % (merge.isEnabled(), merge.isVisible()) if merge else "없음")
    QTest.mouseClick(mw._mv[0].view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(40, 40)); pump()
    chk(mw._active_pane == 0 and merge is not None and merge.isEnabled(), "B 왼쪽 PDF 칸을 누르면 되살아남")
    QTest.mouseClick(mv1.view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(40, 40)); pump()
    chk(mw._active_pane == 1 and merge is not None and not merge.isEnabled(), "B 다시 오른쪽 — 흐리게")

    # C — 선 긋고 [저장]
    mv1._draw_pen_btns[0].click(); pump()
    chk(mv1._draw_kind == "line", "C 준비 — 색상버튼 = 선긋기", str(mv1._draw_kind))
    stroke(mv1, (0.2, 0.3), (0.7, 0.6))
    chk(len(mv1._page_strokes) == 1, "C 섞은 사진 칸에 선이 그어진다", str(len(mv1._page_strokes)))
    top.btn_save.click()                              # 저장은 배경 작업을 거친다 — 사이드카·두 칸을 기다린다
    pump(lambda: len(side_drawings(pics, "p1.jpg")) == 1 and mv1.current_file() is not None
         and mw._mv[0].current_file() is not None, 15)
    got = side_drawings(pics, "p1.jpg")
    chk(len(got) == 1, "C [저장] → 사진 폴더의 page_meta.json 에 선 하나", str(got)[:120])
    chk(not (pdfs / "page_meta.json").exists() or not side_drawings(pdfs, "p1.jpg"), "C PDF 폴더 사이드카에는 없음")

    # 저장 길(위 창 PDF 의 꾸밈 거울 `_mirror_to_pdf`)이 두 창을 비웠다가 — 활성 창(섞은 사진 칸)도 되살린다(책갈피창·저장 SOT §4.7.20)
    chk(norm(mv1.current_file()) == norm(ph[0]) and norm(mw._mv[0].current_file()) == norm(a_pdf) and mw._mix_on_now(),
        "C 저장 뒤 두 칸 그대로(오른쪽 p1·왼쪽 PDF)", "%s %s" % (mv1.current_file(), mw._mv[0].current_file()))
    if mv1._draw_kind != "line":                     # 다시 연 뒤 도구가 풀렸으면 색상버튼으로 다시
        mv1._draw_pen_btns[0].click(); pump()
    # D — 다시 긋고 버림
    stroke(mv1, (0.3, 0.7), (0.8, 0.2))
    chk(len(mv1._page_strokes) == 2, "D 두 번째 선", str(len(mv1._page_strokes)))
    answer["v"] = "discard"
    top.btn_edit.setChecked(False); pump()
    chk(not top.is_edit_mode() and len(side_drawings(pics, "p1.jpg")) == 1, "D 편집 끄며 버림 — 사이드카는 선 하나 그대로",
        str(len(side_drawings(pics, "p1.jpg"))))
    answer["v"] = "save"

    # E — 설정 '보기' 면 켜지 않음
    mw._prefs["open_edit_mode"] = False
    mw._on_bookmark_activated_right(str(ph[1]), 0); pump(lambda: norm(mv1.current_file()) == norm(ph[1]))
    chk(norm(mv1.current_file()) == norm(ph[1]) and not top.is_edit_mode(), "E 시작 모드 = 보기 — 사진을 열어도 편집 꺼진 채")

    # F — 사진 모드 들어가기
    mw._prefs["open_edit_mode"] = True
    mw.act_split.setChecked(False); pump()
    chk(not mw._mix_on_now() and merge.isEnabled(), "F 섞은 2단을 놓으면 PDF 전용 명령 되살아남")
    mw._set_photo_mode(True); pump()
    chk(mw._photo_mode and top.is_edit_mode(), "F 사진 모드에 들어가면 편집 모드(설정 = 편집)")
    mw.close(); pump()
except Exception:
    import traceback
    traceback.print_exc()
    fails.append("예외")
finally:
    shutil.rmtree(str(tmp), ignore_errors=True)

print("\n=== " + ("ALL PASS" if not fails else "FAILURE (%d)" % len(fails)) + " ===")
for m in fails:
    print(" -", m)
sys.stdout.flush()
os._exit(1 if fails else 0)
