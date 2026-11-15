# -*- coding: utf-8 -*-
"""261115-14: 스크롤 캡처 (스크린샷 SOT §3.2).

A. 캡처 모드 메뉴 — '스크롤 캡처' 가 '영역 캡처' 바로 아래, 단추 이름, _do_capture 가 스크롤 캡처로
B. 이어 붙이기 — 합성 그림(줄마다 다른 색)을 겹치게 잘라 넣으면 원래 그림과 같은 한 장
C. 고정 머리말·바닥글·스크롤 막대 띠가 있어도 몸통만 잇고 머리·바닥은 한 번씩
D. 진행 — 끝까지 내리면 '화면이 더 안 바뀜' 으로 끝, 결과 = 내용 전체
E. 휠을 받지 않는 창 — 한 화면만 남고 이유 'noscroll'(안내 문구)
F. 중간 멈춤 — 멈추면 그때까지 찍은 것이 결과(버리지 않음)
G. 겹침 못 찾음(너무 많이 움직임) — 거기까지 남김 · 크기 상한 — 'full', 높이 상한 안
H. 실제 경로 — 앱 안 스크롤 창 위 영역으로 _capture_scroll: 휠(QWheelEvent)·찍기(창 grab)·합성 워커·스트립·클립보드·멈춤 띠는 영역 밖
I. 응답성 — 상한 크기 결과의 메인 일(스트립 카드 + 클립보드 형식 만들기) < 1초
J. (덧붙임) 영역 고르기 없이 '캡처할 곳을 누르세요' 덮개 → 누른 스크롤 칸이 대상(폭 전체, 덮개 위젯이 겹쳐도)·첫 누름은 위젯에 안 감,
   진행 중 한 번 더 누르면 끝(부분 결과)·그 누름도 안 감·끝나면 가로채기 정리, Esc(앱 안 키) = 끝, 덮개 Esc·오른쪽 클릭 = 취소,
   PolyPDF 밖·스크롤 아닌 곳 = 안내만, 다른 프로그램 길(SendInput·GetAsyncKeyState·전역 훅·화면 찍기) 없음
K. (261115-17) PDF 본문 — 한 쪽씩·이어 보기·2장 보기 모두 다섯 쪽을 마지막 쪽 끝까지 쪽 렌더로 이어 붙임(간격 = 화면),
   중간 멈춤 = 그때까지의 쪽, 크기 상한 'full', 한 걸음 메인 일 < 1초
L. (261115-21) 첫 쪽만으로 MAX_PIXELS 를 넘는 배율 — 배율을 낮춰 상한 안 크기로 렌더(결과가 비지 않음, 메인 < 1초)
M. (261115-21) [💾 PDF 저장] 툴팁 = 지금 걸린 키(종전 '(Ctrl+S)' 고정), 단축키를 바꾸면 따라감 · J 에 안내 문구의 앱 이름 = PolyPinax
"""
import os, sys, time, random
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtCore import QStandardPaths, Qt, QPoint, QRect, QEventLoop, QTimer, QCoreApplication
QStandardPaths.setTestModeEnabled(True)
QCoreApplication.setApplicationName("polypdf_shot_scroll_%d" % os.getpid())   # 검사 작성 SOT §14.7.2 의 3
from PyQt6.QtWidgets import QApplication, QScrollArea, QLabel, QToolButton
from PyQt6.QtGui import QImage, QColor, QPixmap, QPainter

app = QApplication.instance() or QApplication(sys.argv[:1])
import modal_guard
modal_guard.install(label=lambda: "스크롤 캡처", echo=False)   # §14.7.2 의 6
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


try:
    from viewer import scroll_capture as sc
except Exception as e:                      # 수정 전 코드 — 모듈이 없다
    sc = None
    print("모듈 없음:", e)


def tall(w=240, h=2400, seed=7):
    """줄마다 다른 색 + 몇 줄은 흰 줄(같은 줄이 여럿 — 실제 문서처럼)."""
    rnd = random.Random(seed)
    img = QImage(w, h, QImage.Format.Format_RGB32)
    p = QPainter(img)
    for y in range(h):
        c = QColor("white") if (y % 37) < 6 else QColor(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
        p.setPen(c)
        p.drawLine(0, y, w - 1, y)
    p.end()
    return img


def same_img(a, b, cols=None):
    a = a.convertToFormat(QImage.Format.Format_RGB32)
    b = b.convertToFormat(QImage.Format.Format_RGB32)
    if cols is not None:                     # 왼쪽 cols 칸만(스크롤 막대 띠 빼고)
        a = a.copy(0, 0, cols, a.height())
        b = b.copy(0, 0, cols, b.height())
    return a.size() == b.size() and a == b


def wait_until(fn, ms=15000):
    t0 = time.monotonic()
    while not fn() and (time.monotonic() - t0) * 1000 < ms:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 30)
        time.sleep(0.005)
    return fn()


SRC = tall()
VH = 500


class FakeWin:
    """내용 SRC 를 높이 VH 로 보여 주는 창 — 휠 한 칸 = per 줄, 끝에서 멈춘다."""

    def __init__(self, src=SRC, per=40, head=0, foot=0, bar=0, frozen=False, jump=None):
        self.src, self.per, self.head, self.foot, self.bar = src, per, head, foot, bar
        self.frozen, self.jump = frozen, jump
        self.off = 0
        self.wheels = 0

    def maxoff(self):
        return self.src.height() - VH

    def wheel(self, n):
        self.wheels += 1
        if self.frozen:
            return
        d = self.jump if self.jump else self.per * n
        self.off = min(self.maxoff(), self.off + d)

    def grab(self):
        w = self.src.width()
        img = QImage(w + self.bar, VH + self.head + self.foot, QImage.Format.Format_RGB32)
        img.fill(QColor("white"))
        p = QPainter(img)
        if self.head:
            p.fillRect(0, 0, w + self.bar, self.head, QColor("#334455"))
        p.drawImage(QRect(0, self.head, w, VH), self.src, QRect(0, self.off, w, VH))
        if self.foot:
            p.fillRect(0, self.head + VH, w + self.bar, self.foot, QColor("#aa5500"))
        if self.bar:                         # 스크롤 막대 — 손잡이가 위치 따라 움직인다
            p.fillRect(w, 0, self.bar, img.height(), QColor("#dddddd"))
            ty = int((img.height() - 40) * self.off / max(1, self.maxoff()))
            p.fillRect(w + 2, ty, self.bar - 4, 40, QColor("#777777"))
        p.end()
        return img


def result_of(st):
    return sc.compose(st.segments())


def run_fake(fw, stop_after=None):
    run = sc.ScrollCaptureRun(fw.grab, fw.wheel, dpr=1.0, wait_ms=5, settle_ms=2)
    out = {}
    run.finished.connect(lambda r: out.setdefault("r", r))
    if stop_after:
        run.progress.connect(lambda n, h: run.stop() if n >= stop_after else None)
    run.start()
    wait_until(lambda: "r" in out, 30000)
    return run, out.get("r")


if sc is not None:
    # ── B. 이어 붙이기 ──────────────────────────────────────────────
    st = sc.RowStitcher()
    offs = [0, 300, 600, 900, 1200]
    rs = [st.add(SRC.copy(0, o, SRC.width(), VH)) for o in offs]
    res = result_of(st)
    chk(rs == ["first"] + ["added"] * 4 and same_img(res, SRC.copy(0, 0, SRC.width(), 1200 + VH)),
        "B 겹치게 자른 그림들을 원래 한 장으로 잇는다", f"{rs} {res.size()}")
    chk(st.add(SRC.copy(0, 1200, SRC.width(), VH)) == "same", "B 같은 화면이면 'same'")

    # ── C. 고정 머리·바닥·스크롤 막대 ─────────────────────────────────
    fw = FakeWin(per=50, head=40, foot=30, bar=16)
    st = sc.RowStitcher()
    for k in range(5):
        r = st.add(fw.grab())
        fw.wheel(5)
    res = result_of(st)
    exp_h = 40 + (fw.off - 250) + VH + 30         # 마지막 add 뒤 한 번 더 내렸으니 마지막 찍은 off = fw.off-250
    want = QImage(SRC.width(), exp_h, QImage.Format.Format_RGB32)
    p = QPainter(want)
    p.fillRect(0, 0, SRC.width(), 40, QColor("#334455"))
    p.drawImage(QRect(0, 40, SRC.width(), exp_h - 70), SRC, QRect(0, 0, SRC.width(), exp_h - 70))
    p.fillRect(0, exp_h - 30, SRC.width(), 30, QColor("#aa5500"))
    p.end()
    chk(res.height() == exp_h and same_img(res, want, cols=SRC.width()),
        "C 고정 머리말·바닥글은 한 번씩, 스크롤 막대 손잡이가 움직여도 몸통을 잇는다", f"{res.size()} want h {exp_h}")

    # ── D. 끝까지 → 끝 ───────────────────────────────────────────────
    fw = FakeWin(per=40)
    run, why = run_fake(fw)
    res = result_of(run.stitcher)
    chk(why == "end" and same_img(res, SRC), "D 끝까지 내리면 '더 안 바뀜' 으로 끝나고 결과 = 내용 전체",
        f"{why} {res.size()} frames {run.stitcher.frames}")
    chk(run.notches != sc.FIRST_NOTCHES, "D 첫 이음 뒤 휠 칸 수를 몸통 높이에 맞춘다", str(run.notches))

    # ── E. 휠을 받지 않는 창 ─────────────────────────────────────────
    fw = FakeWin(frozen=True)
    run, why = run_fake(fw)
    res = result_of(run.stitcher)
    chk(why == "noscroll" and res.height() == VH and fw.wheels == sc.SAME_END,
        "E 휠을 받지 않는 창 — 한 화면만, 이유 'noscroll'", f"{why} {res.size()} wheels {fw.wheels}")

    # ── F. 중간 멈춤 ─────────────────────────────────────────────────
    fw = FakeWin(per=20)
    run, why = run_fake(fw, stop_after=3)
    res = result_of(run.stitcher)
    chk(why == "stopped" and run.stitcher.frames == 3 and VH < res.height() < SRC.height()
        and same_img(res, SRC.copy(0, 0, SRC.width(), res.height())),
        "F 멈추면 그때까지 찍은 것이 결과(버리지 않음)", f"{why} frames {run.stitcher.frames} {res.size()}")

    # ── G. 겹침 못 찾음 · 상한 ───────────────────────────────────────
    fw = FakeWin(jump=VH + 100)
    run, why = run_fake(fw)
    chk(why == "nomatch" and result_of(run.stitcher).height() == VH, "G 겹침을 못 찾으면 거기까지 남김", str(why))
    st = sc.RowStitcher(max_h=900)
    rr = [st.add(SRC.copy(0, o, SRC.width(), VH)) for o in (0, 300, 600, 900)]
    h = result_of(st).height()
    chk("full" in rr and h <= 900 and same_img(result_of(st), SRC.copy(0, 0, SRC.width(), h)),
        "G 크기 상한에 닿으면 'full', 상한까지만 잇는다", f"{rr} h {h}")

    # ── A. 메뉴 자리 ──────────────────────────────────────────────────
from viewer.app import MainWindow
mw = MainWindow(); mw.move(900, 0); mw.resize(900, 700); mw.show(); app.processEvents()
dd = QToolButton()
mw._rebuild_capture_menu(dd)
names = [a.text() for a in dd.menu().actions()] if dd.menu() else []
ok_pos = "영역 캡처" in names and "스크롤 캡처" in names and names.index("스크롤 캡처") == names.index("영역 캡처") + 1
chk(ok_pos, "A 캡처 모드 메뉴 — '스크롤 캡처' 가 '영역 캡처' 바로 아래", str(names[:5]))
mw._cap_mode = "scroll"
chk(mw._capture_mode_label() == "스크롤 캡처", "A 단추 이름 '스크롤 캡처'", mw._capture_mode_label())
called = []
_orig = getattr(mw, "_capture_scroll", None)
mw._capture_scroll = lambda view=None, grect=None, gpos=None: called.append(view)
mw.page_thumbs.selected_pages = lambda: []
mw._do_capture(mw.main_view)
chk(called == [mw.main_view], "A 캡처 단추가 스크롤 캡처로 간다", str(called))
if _orig is not None:
    del mw._capture_scroll

# ── H. 실제 경로 — 앱 안 스크롤 창 ──────────────────────────────────
if sc is not None:
    lab = QLabel()
    lab.setPixmap(QPixmap.fromImage(SRC))
    lab.resize(SRC.size())
    sa = QScrollArea()
    sa.setWidget(lab)
    sa.setWindowFlags(Qt.WindowType.Window)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    sa.move(100, 100)                       # 오프스크린 화면(800×800) 안 — widgetAt 이 찾게
    sa.resize(SRC.width() + 40, 420)
    sa.show(); app.processEvents()
    vp = sa.viewport()
    tl = vp.mapToGlobal(QPoint(0, 0))
    grect = QRect(tl.x(), tl.y(), SRC.width(), vp.height())
    clip = []
    mw._copy_image_to_clipboard = lambda img, *a, **k: clip.append(img)
    n0 = len(mw.shot_strip.all_paths())
    seen = {}
    real_panel = sc.ScrollCapturePanel.show

    def spy_show(self):
        seen["geo"] = self.frameGeometry()
        real_panel(self)
    sc.ScrollCapturePanel.show = spy_show
    mw._cap_copy = "original"
    mw._capture_scroll(None, grect=grect)
    run = getattr(mw, "_scroll_run", None)
    ok = wait_until(lambda: len(mw.shot_strip.all_paths()) > n0, 40000)
    del sc.ScrollCapturePanel.show
    paths = mw.shot_strip.all_paths()
    out = QImage(paths[-1]) if ok else QImage()
    reason = getattr(mw, "_scroll_reason", None)
    chk(ok and reason == "end", "H 앱 안 스크롤 창 — 끝까지 내리고 스트립에 한 장", f"ok {ok} reason {reason}")
    chk(sa.verticalScrollBar().value() == sa.verticalScrollBar().maximum() and sa.verticalScrollBar().maximum() > 0,
        "H 휠이 실제로 그 창을 끝까지 내렸다", f"{sa.verticalScrollBar().value()}/{sa.verticalScrollBar().maximum()}")
    chk(not out.isNull() and out.height() == SRC.height()
        and same_img(out, SRC.copy(0, 0, out.width(), SRC.height()), cols=SRC.width() - 20),
        "H 결과 그림 = 그 창 내용 전체", f"{out.size()} vs {SRC.size()}")
    chk(len(clip) == 1 and not clip[0].isNull(), "H 클립보드에도 넣는다", str(len(clip)))
    chk("geo" in seen and not seen["geo"].intersects(grect), "H 멈춤 띠는 영역 밖에", str(seen.get("geo")))
    chk(getattr(mw, "_scroll_panel", 1) is None and mw._scroll_run is None, "H 끝나면 멈춤 띠를 닫고 진행을 정리")
    chk(os.path.basename(paths[-1]).endswith("_S.png") if paths else False, "H 파일 이름 접미 _S", paths[-1] if paths else "")

    # 멈춤 띠의 [멈춤] — 실제 단추 클릭으로 멈추고 그때까지 남김
    sa.verticalScrollBar().setValue(0); app.processEvents()
    n1 = len(mw.shot_strip.all_paths())
    mw._capture_scroll(None, grect=grect)
    pnl = mw._scroll_panel
    wait_until(lambda: mw._scroll_run is None or mw._scroll_run.stitcher.frames >= 2, 20000)
    from PyQt6.QtTest import QTest
    if mw._scroll_panel is pnl:
        QTest.mouseClick(pnl.btn, Qt.MouseButton.LeftButton)
    ok2 = wait_until(lambda: len(mw.shot_strip.all_paths()) > n1, 20000)
    out2 = QImage(mw.shot_strip.all_paths()[-1]) if ok2 else QImage()
    chk(ok2 and mw._scroll_reason == "stopped" and vp.height() < out2.height() < SRC.height(),
        "H [멈춤] 을 누르면 그때까지 이은 것을 남긴다", f"{ok2} {getattr(mw, '_scroll_reason', None)} {out2.size()}")

    # ── J. 눌러 시작·한 번 더 눌러 끝 — PolyPDF 화면만 (261115-14 덧붙임) ──────
    from PyQt6.QtCore import QObject, QEvent
    from PyQt6.QtWidgets import QWidget, QPushButton
    import inspect

    class PressCount(QObject):
        n = 0

        def eventFilter(self, o, e):
            if e.type() == QEvent.Type.MouseButtonPress:
                PressCount.n += 1
            return False
    pc = PressCount()
    lab.installEventFilter(pc)
    # 다른 프로그램 길이 없다(백신 오인 방지 — 입력 넣기·키 상태 엿보기·전역 훅·화면 찍기)
    src = inspect.getsource(sc)
    app_src = inspect.getsource(MainWindow._capture_scroll)
    banned = [b for b in ("SendInput", "GetAsyncKeyState", "SetWindowsHookEx", "grabWindow", "ctypes")
              if b in src or b in app_src]
    gone = [n for n in ("win_wheel", "stop_keys_down", "clear_stop_keys", "screen_grab") if hasattr(sc, n)]
    chk(not banned and not gone, "J 다른 프로그램 길(SendInput·GetAsyncKeyState·전역 훅·화면 찍기)이 없다", f"{banned} {gone}")
    if not hasattr(sc, "ScrollPicker") or not hasattr(sc, "target_at"):
        chk(False, "J 눌러 시작(ScrollPicker·target_at) — 없음(수정 전 코드)")
    else:
        sa.verticalScrollBar().setValue(0); app.processEvents()
        vc = vp.mapToGlobal(vp.rect().center())
        tgt = QRect(vp.mapToGlobal(QPoint(0, 0)), vp.size())
        n2 = len(mw.shot_strip.all_paths())
        mw._capture_scroll(None)
        pk = getattr(mw, "_scroll_picker", None)
        ovs = list(pk.overlays) if pk else []
        chk(pk is not None and ovs and mw._scroll_run is None and any(o.isVisible() for o in ovs),
            "J 스크롤 캡처를 고르면 영역 고르기 없이 '캡처할 곳을 누르세요' 덮개", str(ovs))
        chk(any("캡처할 곳을 누르세요" in o.text for o in ovs), "J 덮개 안내 문구")
        ov = next((o for o in ovs if o.geometry().contains(vc)), None)
        if ov is not None:
            QTest.mouseClick(ov, Qt.MouseButton.LeftButton, pos=vc - ov.geometry().topLeft())
        started = wait_until(lambda: mw._scroll_run is not None, 5000)
        chk(started and getattr(mw, "_scroll_rect", None) == tgt and mw._scroll_picker is None,
            "J 누른 스크롤 칸(보이는 폭 전체)이 대상", f"{getattr(mw, '_scroll_rect', None)} vs {tgt}")
        chk(PressCount.n == 0, "J 첫 누름은 그 아래 위젯에 가지 않는다", str(PressCount.n))
        wait_until(lambda: mw._scroll_run is None or mw._scroll_run.stitcher.frames >= 2, 20000)
        if mw._scroll_run is not None:
            QTest.mouseClick(lab, Qt.MouseButton.LeftButton, pos=lab.mapFromGlobal(vc))
        ok3 = wait_until(lambda: len(mw.shot_strip.all_paths()) > n2, 20000)
        out3 = QImage(mw.shot_strip.all_paths()[-1]) if ok3 else QImage()
        chk(ok3 and mw._scroll_reason == "stopped" and vp.height() < out3.height() < SRC.height()
            and out3.width() == vp.width(),
            "J 진행 중 한 번 더 누르면 끝 — 그때까지 이은 것이 결과(폭 = 칸 폭)",
            f"{ok3} {getattr(mw, '_scroll_reason', None)} {out3.size()} vp {vp.size()}")
        chk(PressCount.n == 0, "J 끝내는 누름도 위젯에 가지 않는다", str(PressCount.n))
        app.processEvents()
        QTest.mouseClick(lab, Qt.MouseButton.LeftButton)
        chk(PressCount.n == 1, "J 끝난 뒤에는 누름이 다시 위젯에 간다(가로채기 정리)", str(PressCount.n))
        # Esc(앱 안 키) = 끝
        sa.verticalScrollBar().setValue(0); app.processEvents()
        n3 = len(mw.shot_strip.all_paths())
        mw._capture_scroll(None, gpos=vc)
        wait_until(lambda: mw._scroll_run is None or mw._scroll_run.stitcher.frames >= 2, 20000)
        if mw._scroll_run is not None:
            QTest.keyClick(lab, Qt.Key.Key_Escape)
        ok4 = wait_until(lambda: len(mw.shot_strip.all_paths()) > n3, 20000)
        chk(ok4 and mw._scroll_reason == "stopped", "J Esc(앱 안 키 이벤트)면 끝 — 그때까지 남김",
            f"{ok4} {getattr(mw, '_scroll_reason', None)}")
        # 위에 덮개 위젯이 겹쳐도 점을 담은 스크롤 칸으로
        cover = QWidget(sa)
        cover.setGeometry(vp.geometry())
        cover.show(); cover.raise_(); app.processEvents()
        r_cov = sc.target_at(vc)
        chk(sc.own_widget_at(vc) is cover and r_cov == (tgt, "ok"),
            "J 스크롤 칸 위에 덮개 위젯이 겹쳐도 그 칸이 대상", f"{sc.own_widget_at(vc)} {r_cov}")
        cover.hide(); cover.deleteLater(); app.processEvents()
        # PolyPDF 밖 · 스크롤되지 않는 곳 = 안내만
        mw.status.clearMessage()
        mw._capture_scroll(None, gpos=QPoint(5, 5))
        msg_out = mw.status.currentMessage()
        chk(mw._scroll_run is None and "화면에서만" in msg_out, "J PolyPDF 밖을 누르면 안내만(시작하지 않음)", msg_out)
        # 261115-21: 안내의 앱 이름은 제품 이름(이사 판부터 PolyPinax) — 번역 문구 안에는 원문 글자로(branding.py 머리 규칙)
        mw._capture_scroll(None)
        pk_n = mw._scroll_picker
        ov_txt = " ".join(o.text for o in (pk_n.overlays if pk_n else []))
        if pk_n is not None:
            pk_n.cancel()
        for _ in range(5):
            app.processEvents()
        chk("PolyPinax 화면에서만" in msg_out and "PolyPinax 화면의" in ov_txt,
            "J 안내·덮개 문구의 앱 이름 = PolyPinax", msg_out + " | " + ov_txt)
        plain = QWidget(); plain.setWindowFlags(Qt.WindowType.Window)
        QPushButton("x", plain).resize(180, 60)
        plain.move(20, 620); plain.resize(200, 100); plain.show(); app.processEvents()
        mw.status.clearMessage()
        mw._capture_scroll(None, gpos=plain.mapToGlobal(QPoint(50, 30)))
        msg_ns = mw.status.currentMessage()
        chk(mw._scroll_run is None and "스크롤되는 곳이 아닙니다" in msg_ns,
            "J 스크롤되지 않는 곳을 누르면 안내만", msg_ns)
        plain.close()
        # 취소 — Esc · 오른쪽 클릭
        for how in ("esc", "right"):
            mw._capture_scroll(None)
            pk = mw._scroll_picker
            ov = pk.overlays[0] if pk and pk.overlays else None
            if ov is not None and how == "esc":
                QTest.keyClick(ov, Qt.Key.Key_Escape)
            elif ov is not None:
                QTest.mouseClick(ov, Qt.MouseButton.RightButton, pos=QPoint(20, 20))
            wait_until(lambda: False, 400)

            def gone_or_hidden(w):
                try:
                    return not w.isVisible()
                except RuntimeError:            # 닫으며 지워짐(WA_DeleteOnClose)
                    return True
            chk(ov is not None and mw._scroll_picker is None and mw._scroll_run is None and gone_or_hidden(ov),
                "J 덮개에서 %s = 취소(시작하지 않음)" % ("Esc" if how == "esc" else "오른쪽 클릭"))
    sa.close()

    # ── K. PDF 본문 — 다른 쪽까지 이어서(쪽 렌더, 261115-17) ──────────────
    if not hasattr(sc, "PageCaptureRun"):
        chk(False, "K PDF 본문 쪽 잇기(PageCaptureRun) — 없음(수정 전 코드)")
    else:
        import tempfile, fitz
        from viewer.widgets.main_view import MainView
        tdir = tempfile.mkdtemp(prefix="shot_scroll_k_")
        kpdf = os.path.join(tdir, "five.pdf")
        d = fitz.open()
        cols = [(1, 0, 0), (0, .6, 0), (0, 0, 1), (.8, .5, 0), (.5, 0, .7)]
        for k in range(5):
            pg = d.new_page(width=300, height=400)
            pg.draw_rect(fitz.Rect(20, 20, 280, 380), color=cols[k], fill=cols[k])
            pg.insert_text((40, 60 + 40 * k), "PAGE %d" % (k + 1), fontsize=24, color=(1, 1, 1))
        d.save(kpdf); d.close()
        mv2 = MainView()
        mv2.setWindowFlags(Qt.WindowType.Window)
        mv2.move(100, 100); mv2.resize(420, 560); mv2.show(); app.processEvents()
        mv2.load_document(kpdf, 0)
        for _ in range(20):
            app.processEvents(); time.sleep(0.01)

        def run_pdf(mode, fit=None, stop_after=None):
            mv2.set_page_scroll_mode(mode)
            if fit:
                mv2.choose_fit(fit)
            mv2.go_to_page(0) if hasattr(mv2, "go_to_page") else None
            for _ in range(10):
                app.processEvents(); time.sleep(0.01)
            vp2 = mv2.view.viewport()
            mv2.view.verticalScrollBar().setValue(mv2.view.verticalScrollBar().minimum()); app.processEvents()
            c = vp2.mapToGlobal(vp2.rect().center())
            n0 = len(mw.shot_strip.all_paths())
            mw._capture_scroll(None, gpos=c)
            r = mw._scroll_run
            info = {"cls": type(r).__name__ if r else None, "zoom": mv2._zoom}
            if r is not None and stop_after:
                r.progress.connect(lambda n, h: r.stop() if n >= stop_after else None)
            if r is not None and hasattr(r, "max_step_s"):
                r.finished.connect(lambda _x: info.setdefault("max_step", r.max_step_s))
            ok = wait_until(lambda: len(mw.shot_strip.all_paths()) > n0, 30000)
            out = QImage(mw.shot_strip.all_paths()[-1]) if ok else QImage()
            return ok, out, info

        def expect_h(zoom, n, dpr=1.0):
            hs = [mv2._page_pixmap(i, zoom, dpr).height() for i in range(n)]
            return sum(hs) + int(round(mv2.CONT_GAP_PX * dpr)) * (n - 1), hs[0]

        for mode, fit, label in (("page", MainView.FIT_PAGE, "한 쪽씩 보기"),
                                 ("continuous", MainView.FIT_PAGE, "이어 보기"),
                                 ("page", MainView.FIT_PAGE_TWO, "2장 보기")):
            ok, out, info = run_pdf(mode, fit)
            want_h, h0 = expect_h(info["zoom"], 5)
            p0 = mv2._page_pixmap(0, info["zoom"], 1.0).toImage().convertToFormat(QImage.Format.Format_RGB32)
            p0.setDevicePixelRatio(1.0)
            top_same = (not out.isNull() and out.width() == p0.width()
                        and out.convertToFormat(QImage.Format.Format_RGB32).copy(0, 0, p0.width(), h0) == p0)
            chk(ok and info["cls"] == "PageCaptureRun" and mw._scroll_reason == "end" and mw._scroll_frames == 5
                and out.height() == want_h and top_same,
                "K %s — 다섯 쪽을 마지막 쪽 끝까지 이어 붙인다(쪽 그림 + 화면과 같은 간격)" % label,
                f"{ok} {info} {getattr(mw, '_scroll_reason', None)} frames {getattr(mw, '_scroll_frames', None)} "
                f"{out.size()} want h {want_h} top {top_same}")
            chk(info.get("max_step", 9) < 1.0, "K %s — 한 걸음(한 쪽)의 메인 일 < 1초" % label, str(info.get("max_step")))
        ok, out, info = run_pdf("page", MainView.FIT_PAGE, stop_after=2)
        want_h, _h0 = expect_h(info["zoom"], 2)
        chk(ok and mw._scroll_reason == "stopped" and mw._scroll_frames == 2 and out.height() == want_h,
            "K 중간에 멈추면 그때까지의 쪽이 결과", f"{getattr(mw, '_scroll_reason', None)} {getattr(mw, '_scroll_frames', None)} {out.size()}")
        # 쪽 가운데서 시작 — 보이는 높이부터
        mv2.set_page_scroll_mode("page"); mv2.choose_fit(MainView.FIT_WIDTH)
        for _ in range(10):
            app.processEvents(); time.sleep(0.01)
        sb2 = mv2.view.verticalScrollBar()
        sb2.setValue(min(sb2.maximum(), 120)); app.processEvents()
        off = sb2.value()
        vp2 = mv2.view.viewport()
        n0 = len(mw.shot_strip.all_paths())
        mw._capture_scroll(None, gpos=vp2.mapToGlobal(vp2.rect().center()))
        okm = wait_until(lambda: len(mw.shot_strip.all_paths()) > n0, 30000)
        outm = QImage(mw.shot_strip.all_paths()[-1]) if okm else QImage()
        want_m, _h0 = expect_h(mv2._zoom, 5)
        chk(okm and off > 0 and outm.height() == want_m - off,
            "K 쪽 가운데서 시작하면 화면 맨 위 높이부터", f"off {off} {outm.size()} want {want_m - off}")
        # 크기 상한
        src = sc.PdfPageSource(mv2)
        cap = sc.PageCaptureRun(src, max_h=900, step_ms=1)
        got = {}
        cap.finished.connect(lambda r: got.setdefault("r", r))
        cap.start()
        wait_until(lambda: "r" in got, 10000)
        hh = sum(h for _im, _y, h in cap.segments())
        chk(got.get("r") == "full" and hh <= 900 and cap.frames >= 2,
            "K 크기 상한에 닿으면 'full' — 상한까지만", f"{got} h {hh} frames {cap.frames}")
        # ── L. 첫 쪽만으로 상한을 넘는 배율 — 배율을 낮춰 상한 안에서 렌더(261115-21) ──
        srcL = sc.PdfPageSource(mv2)
        estL = srcL.est_size(srcL.start)
        lim = int(estL[0] * estL[1] / 4)               # 첫 쪽이 상한의 4배
        capL = sc.PageCaptureRun(srcL, max_pixels=lim, step_ms=1)
        gotL = {}
        capL.finished.connect(lambda r: gotL.setdefault("r", r))
        capL.start()
        wait_until(lambda: "r" in gotL, 10000)
        imgsL = [s for s in capL.segments() if s[0] is not None]
        bigL = max((s[0].width() * s[0].height() for s in imgsL), default=0)
        chk("r" in gotL and capL.frames >= 1 and 0 < bigL <= lim and capL.max_step_s < 1.0,
            "L 첫 쪽이 상한보다 커도 상한 안 크기로 렌더(배율을 낮춤) — 결과가 비지 않고 메인 < 1초",
            f"{gotL} frames {capL.frames} 렌더 {bigL} 상한 {lim} step {capL.max_step_s:.3f}")
        mv2.close()

    # ── M. [💾 PDF 저장] 툴팁 = 지금 걸린 키(단축키 설정을 따른다, 261115-21) ──
    from PyQt6.QtGui import QKeySequence
    tip0 = mw.btn_save_pdf.toolTip()
    k0 = mw._sc_key("save_shots_pdf")
    prefs = mw._prefs if isinstance(getattr(mw, "_prefs", None), dict) else {}
    old_sc = dict(prefs.get("shortcuts") or {})
    prefs["shortcuts"] = dict(old_sc, save_shots_pdf="Ctrl+Alt+P")
    mw._prefs = prefs
    mw._apply_shortcuts(prefs["shortcuts"])
    tip1 = mw.btn_save_pdf.toolTip()
    want1 = QKeySequence("Ctrl+Alt+P").toString(QKeySequence.SequenceFormat.NativeText)
    prefs["shortcuts"] = old_sc
    mw._apply_shortcuts(old_sc)
    chk("(Ctrl+S)" not in tip0 and bool(k0) and ("(" + k0 + ")") in tip0 and ("(" + want1 + ")") in tip1,
        "M [💾 PDF 저장] 툴팁이 지금 키를 보이고, 단축키를 바꾸면 따라간다", f"{tip0!r} → {tip1!r} (지금 키 {k0!r})")

    # ── I. 응답성 — 상한 크기 결과의 메인 일 ─────────────────────────
    from viewer import clipboard_util, screenshot as ss
    from PyQt6.QtGui import QFont
    W = 1500
    Hh = sc.MAX_PIXELS // W
    big = QImage(W, Hh, QImage.Format.Format_RGB32); big.fill(QColor("white"))
    p = QPainter(big); p.setFont(QFont("Malgun Gothic", 11))
    for y in range(20, Hh, 22):
        p.drawText(10, y, ("스크롤 캡처 응답성 줄 %d " % y) * 6)
    p.end()
    pth = ss.save_screenshot(big, source_name="big.png", suffix="_S")
    del mw._copy_image_to_clipboard
    mw._scroll_frames, mw._scroll_reason = 40, "full"
    t0 = time.perf_counter()
    mw._scroll_saved(str(pth), big)
    t_main = time.perf_counter() - t0
    t0 = time.perf_counter()
    clipboard_util.image_formats(big)             # Windows 클립보드 형식 만들기(실제 넣기는 하지 않음)
    t_fmt = time.perf_counter() - t0
    chk(t_main + t_fmt < 1.0, "I 상한 크기 결과의 메인 일 < 1초", "main %.2fs fmt %.2fs" % (t_main, t_fmt))
    chk(Hh <= sc.MAX_H, "I 상한 넓이·높이가 서로 맞다", f"{Hh}")

print("\n=== " + ("ALL PASS" if not fails else f"FAILURE ({len(fails)})") + " ===")
for m in fails:
    print(" -", m)
sys.stdout.flush()
os._exit(1 if fails else 0)
