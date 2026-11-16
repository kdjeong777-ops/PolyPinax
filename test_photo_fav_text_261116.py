# -*- coding: utf-8 -*-
"""261116-6·-7 사진 모드 — 즐겨찾기 더하기 알림·같은 것 막기, 글쓰기 첫 크기·글자 투명도 (사진 보기 SOT §4.7·§4.19, 마스터 §4.6.1).

실제 MainWindow 로(오프스크린, 실제 설정 폴더를 쓰지 않는다 — 검사 작성 SOT §14.7.2 의 3).
A. PDF 모드에 등록한 폴더도 사진 모드에서 등록된다(목록이 따로). 같은 모드에 같은 폴더를 또 더하면 이름 창 없이 '이미 있습니다' — 늘지 않는다
B. 넷째 폴더를 더하면 상태 막대가 '▾ 목록 4번째'(단추는 앞 3개)라고 알린다 — 종전에는 아무 알림 없이 ▾ 목록에만 들어가 '등록이 안 된다'로 보였다
C. 같은 사진 파일 즐겨찾기도 두 번 만들지 않는다
D. 3,000px 높이 사진에서 글쓰기 도구로 빈 곳을 누르면(실제 QMouseEvent) 첫 글자 크기 = 스타일 크기 × 사진 높이 ÷ 842 — 종전엔 18pt = 높이 0.6%
E. 고른 글상자에서 50% 빨강 색상버튼을 누르면(실제 단추) 글자가 그 색·투명도 — 화면에 분홍으로(종전엔 늘 검정: drawContents 가 펜 색을 안 씀),
   평탄화 사본에도 분홍으로 구워진다(종전엔 MuPDF 의 미리 곱한 알파를 한 번 더 곱해 어두웠다)
"""
import os, sys, tempfile, shutil, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pathlib import Path
from PyQt6.QtCore import QStandardPaths, QCoreApplication, QPointF, QEvent, Qt
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2 의 3
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_fav_text_%d" % os.getpid())
import modal_guard
modal_guard.install(label=lambda: "사진 즐겨찾기·글쓰기")
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


def click(mv, nx, ny):
    vp = mv.view.viewport()
    p = mv._norm_to_view(nx, ny, mv._page_view_rect())
    for kind, buttons in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
                          (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)):
        mv.eventFilter(vp, QMouseEvent(kind, QPointF(p), Qt.MouseButton.LeftButton, buttons, Qt.KeyboardModifier.NoModifier))
        pump(timeout=0.1)


tmp = Path(tempfile.mkdtemp(prefix="polypdf_fav_text_"))
try:
    from PIL import Image
    folders = []
    for n in ("_samples", "둘", "셋", "넷"):
        f = tmp / n
        f.mkdir()
        Image.new("RGB", (64, 48), (200, 200, 200)).save(f / "p.jpg")
        folders.append(f)
    big = folders[0] / "큰.jpg"
    Image.new("RGB", (2000, 3000), (255, 255, 255)).save(big, quality=95)

    from viewer.widgets import favorites_dialog as fd
    asked = []
    fd.AddFavoriteDialog.exec = lambda dlg: (asked.append(1), fd.AddFavoriteDialog.DialogCode.Accepted)[1]
    infos = []
    QMessageBox.information = staticmethod(lambda parent, title, text, *a, **k: infos.append(text) or QMessageBox.StandardButton.Ok)
    from viewer.app import MainWindow
    mw = MainWindow(); mw._skip_save_on_close = True
    mw.resize(1300, 900); mw.show(); pump()
    mw._prefs.setdefault("picture", {})["view_kind"] = "mixed"
    mw._photo_apply_view_kind()
    bt = mw.bookmark_tree

    # A — PDF 모드에 먼저 등록
    mw.open_folder(folders[0]); pump()
    mw._add_current_folder_favorite(); pump()
    chk(len(mw._favorites) == 1, "A PDF 모드 폴더 즐겨찾기")
    mw._set_photo_mode(True); pump()
    chk(mw._photo_mode and mw._favorites == [], "A 사진 모드 목록은 따로(비어 있음)")
    mw.open_folder(folders[0]); pump()
    n0 = len(asked)
    bt.favoriteRequested.emit(); pump()                  # 책갈피창 우클릭 '현재 폴더를 즐겨찾기에 추가' 길
    chk(len(mw._favorites) == 1 and len(asked) == n0 + 1, "A PDF 모드에 같은 폴더가 있어도 사진 모드에 등록된다")
    infos.clear()
    mw._add_current_folder_favorite(); pump()
    chk(len(mw._favorites) == 1 and len(asked) == n0 + 1, "A 같은 모드 같은 폴더는 또 만들지 않는다(이름 창도 없음)", str(len(mw._favorites)))
    chk(infos and "_samples" in infos[-1], "A '이미 즐겨찾기에 있습니다' 알림에 그 이름", str(infos))

    # B — 넷째는 ▾ 목록 (상태 막대 글은 배경 색인 알림이 곧 덮으므로 부른 글을 기록해 본다)
    shown = []
    _orig_show = mw.status.showMessage
    mw.status.showMessage = lambda text, *a: (shown.append(text), _orig_show(text, *a))[1]
    for f in folders[1:]:
        mw.open_folder(f); pump()
        mw._add_current_folder_favorite(); pump()
    msg = next((t for t in reversed(shown) if "넷" in t), "")
    chk(len(mw._favorites) == 4, "B 폴더 넷")
    chk("4" in msg and "▾" in msg and "넷" in msg, "B 넷째를 더하면 '▾ 목록 4번째' 알림", msg)

    # C — 같은 사진 파일
    mw.open_folder(folders[0]); pump(lambda: sum(1 for _ in bt._iter_file_nodes()) == 2)
    mw._add_file_favorite(str(big)); pump()
    k = len(mw._favorites)
    mw._add_file_favorite(str(big)); pump()
    chk(len(mw._favorites) == k == 5, "C 같은 사진 파일 즐겨찾기는 한 번만", str(k))

    # D — 첫 글자 크기
    mw._on_bookmark_activated(str(big), 0); pump(timeout=1.0)
    mv = mw.main_view
    bt.btn_edit.setChecked(True); pump(timeout=0.3)
    mv._pen_idx = None
    mv._draw_kind = "text"; mv._apply_tool(); pump(timeout=0.1)
    click(mv, 0.2, 0.2)
    ed = mv._text_editor
    chk(ed is not None, "D 사진 위 빈 곳을 누르면 글상자")
    if ed is not None:
        st = mv._page_strokes[mv._text_edit_idx]
        base = float(mv._text_defaults.get("size_pt", 18.0))
        want = round(base * 3000 / 842.0, 1)
        chk(abs(float(st.get("size_pt")) - min(200.0, want)) < 0.2, "D 첫 글자 크기 = 스타일 × 사진 높이 ÷ 842",
            "%s vs %s" % (st.get("size_pt"), want))
        QTest.keyClicks(ed, "AB"); pump(timeout=0.2)          # 한글·기호는 QTest.keyClicks 가 오프스크린에서 죽는다 — ASCII
        mv._commit_text_editor(); pump(timeout=0.2)

    # E — 색상버튼 따라가기(사용자 결정 A): 고른 글상자에 50% 빨강 펜을 누르면 글자가 그 색·투명도 — 화면과 평탄화
    strokes = mv._page_strokes
    chk(bool(strokes), "E 준비 — 글상자가 남아 있다")
    if strokes:
        st = strokes[-1]
        st.update(size_pt=150.0, text="■■")                  # 칸을 넓게 채우는 글(입력은 ASCII 만 되므로 값으로)
        mv._draw_kind = "select"; mv._apply_tool()
        mv._stroke_selected = len(strokes) - 1
        mv.set_main_pens([{"name": "반투명 빨강", "color": "#ff0000", "width": 3, "alpha": 50}])
        mv._pen_idx = None
        mv._draw_pen_btns[0].click(); pump(timeout=0.2)     # 실제 색상버튼
        chk(st.get("color") == "#ff0000" and int(st.get("text_alpha", 100)) == 50, "E 고른 글상자 글자 = 누른 색상버튼 색·투명도",
            "%s %s" % (st.get("color"), st.get("text_alpha")))
        w, h = mv._text_natural_size(st, mv._page_view_rect())
        mv._text_apply_size(st, mv._page_view_rect(), w, h, keep="tl")
        mv._stroke_selected = -1
        mv._save_page_strokes(); mv._draw_overlay.update(); pump(timeout=0.3)
        img = mv.view.grab().toImage()
        off = mv._draw_overlay.mapTo(mv.view, mv._draw_overlay.rect().topLeft())   # 오버레이 좌표 → view 좌표
        pr = mv._page_view_rect()
        rc = list(st["rect"])
        px = []
        for y in range(int(pr.top() + rc[1] * pr.height()) + off.y(), int(pr.top() + rc[3] * pr.height()) + off.y(), 2):
            for x in range(int(pr.left() + rc[0] * pr.width()) + off.x(), int(pr.left() + rc[2] * pr.width()) + off.x(), 2):
                if 0 <= x < img.width() and 0 <= y < img.height():
                    c = img.pixelColor(x, y)
                    px.append((c.red(), c.green(), c.blue()))
        ink = [c for c in px if c[1] < 230]                    # 흰 바탕이 아닌 점(글자)
        pink = [c for c in ink if c[0] > 235 and 90 <= c[1] <= 170 and 90 <= c[2] <= 170]
        chk(ink and len(pink) >= len(ink) // 2, "E 화면 — 글자가 50% 빨강(흰 바탕 위 분홍), 종전엔 검정",
            "점 %d, 분홍 %d, 예 %s" % (len(ink), len(pink), ink[:3]))
        stroke = {k: v for k, v in st.items()}
        mw._confirm_close_edit = lambda: True
        mv._page_strokes = []; mv._stroke_selected = -1
        bt.btn_edit.setChecked(False); pump(timeout=0.3)
        store = mw._ensure_page_meta_store()                  # [저장] 한 꾸밈과 같은 자리(사이드카)
        store.set_drawings(str(big), 0, [stroke]); store.save()
        mw._photo_flatten(str(big))
        pump(lambda: not mw.__dict__.get("_photo_flat_busy"), timeout=20); pump(timeout=0.3)
        outs = [p for p in folders[0].iterdir() if "평탄화" in p.name]
        chk(len(outs) == 1, "E 평탄화 사본", str([p.name for p in outs]))
        if outs:
            with Image.open(outs[0]) as im:
                im = im.convert("RGB")
                x0, y0, x1, y1 = (int(rc[0] * 2000), int(rc[1] * 3000), int(rc[2] * 2000), int(rc[3] * 3000))
                ink = []
                for y in range(y0, y1, 3):
                    for x in range(x0, x1, 3):
                        c = im.getpixel((x, y))
                        if c[1] < 230:
                            ink.append(c)
                pink = [c for c in ink if c[0] > 235 and 90 <= c[1] <= 170]
                chk(ink and len(pink) >= len(ink) // 2,
                    "E 평탄화 — 50% 빨강으로 구워진다(미리 곱한 알파를 두 번 곱해 어두운 (192,128,128) 아님)",
                    "점 %d, 분홍 %d, 예 %s" % (len(ink), len(pink), ink[:3]))
    mw._confirm_close_edit = lambda: True
    mw.close()
except Exception:
    import traceback
    traceback.print_exc()
    fails.append("예외")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
print("ALL PASS" if not fails else "FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
