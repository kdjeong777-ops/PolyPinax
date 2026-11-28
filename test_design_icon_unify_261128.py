# -*- coding: utf-8 -*-
"""아이콘 통일 — 꼴 넷(단색 라인·파란 라인·색 그림·형식 배지), 글리프·이모지·남의 로고 PNG 없음 (디자인 SOT §4.8, 261128-10).

A. 소스 전체 — 단추·탭·메뉴 항목 글자(QPushButton·QToolButton·_SlimButton·_mk_btn·QAction·addAction·addTab·setText·
   setTabText)에 금지 글리프·이모지(◀▶▲▼❮❯∧∨↑↓←→✎↻↶↷⏸●💾📋📥🖌🗑⭐⛶🖥⏱🔊👁📌📄📁🔎🖼 …)가 없다(예외: SOT §4.8 목록),
   `resources` 아이콘 PNG(Word·Excel 로고·연필·취소·클립보드·발표 시계 …)를 읽지 않고 그 파일도 없다
B. 실제 위젯 그림(밝게) — 검색 막대 이전/다음·쪽 이동 묶음·책갈피 조작 단추가 파란 꺾쇠(ACCENT["play"]), 글자 없음 ·
   단어장 [Word]·텍스트 창 [Word 저장] = 워드 배지 색, 검색결과 [저장] = 엑셀 배지 색, 스크린샷 [PDF 저장] = PDF 배지 색,
   책갈피창 [저장] = 파란 플로피, 변환 창 형식 단추 = 형식 배지
C. 다크로 바꾸면(apply_theme 과 같은 setStyle·setPalette) 위 그림이 다크 색으로 다시 칠해진다
"""
import gc, os, re, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PyQt6.QtCore import QStandardPaths, QCoreApplication
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QStyleFactory, QWidget
from PyQt6.QtGui import QColor, QPalette

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_icon_unify_%d" % os.getpid())
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


# ── A. 소스 검사 ─────────────────────────────────────────────
BANNED = re.compile("[\U0001F300-\U0001FAFF☀-✒✔-➿⬀-⯿⏩-⏺"
                    "←-⇿▲-▷▹-▽▿-◁∧∨‹›]")   # ✓(2713)·▸(25B8)·▾(25BE) 는 허용(§4.8 예외)
CALL = re.compile(r"(?:QPushButton|QToolButton|_SlimButton|_mk_btn|QAction|addAction|addTab|setText|setTabText)\(\s*"
                  r"(?:[^\"'()]*?,\s*)?(?:tr\()?\s*f?([\"'])(.*?)(?<!\\)\1")
ALLOW = {                                                        # SOT §4.8 '글자로 두는 것'
    ("widgets/law_search_dialog.py", "✕"), ("widgets/kcsc_search_dialog.py", "✕"), ("widgets/kipo_search_dialog.py", "✕"),   # §2.7 패널 닫기
    ("lite_controller.py", "🔋"),                                # 상태 표시줄 글자 배지
    ("widgets/crop_dialog.py", "✂"),                             # 목록 항목 표지
}
root = os.path.join(HERE, "viewer")
bad = []
for dp, _dn, fns in os.walk(root):
    for fn in fns:
        if not fn.endswith(".py") or fn == "icons.py":
            continue
        path = os.path.join(dp, fn)
        rel = os.path.relpath(path, root).replace("\\", "/")
        for i, line in enumerate(open(path, encoding="utf-8"), 1):
            if line.lstrip().startswith("#"):
                continue
            for m in CALL.finditer(line):
                txt = m.group(2).strip()
                for ch in set(BANNED.findall(txt)):
                    if "←" <= ch <= "⇿" and not (txt.startswith(ch) or txt.endswith(ch)):
                        continue                         # 문장 안 화살표('설정 → …', '왼쪽→오른쪽')는 글자
                    if (rel, ch) not in ALLOW:
                        bad.append(f"{rel}:{i} {ch} {m.group(2)[:30]!r}")
chk(not bad, "A1 단추·탭·메뉴 글자에 금지 글리프·이모지가 없다(SOT §4.8)", "\n    " + "\n    ".join(bad[:40]))
OLD_PNG = ("icon_word", "excel", "icon_edit", "icon_edit_blue", "icon_edit_red", "icon_cancel", "icon_bookmark_edit",
           "icon_clipboard", "icon_pres_timer", "icon_save", "icon_mp3", "icon_broom", "icon_eraser_thin", "icon_eraser_thick",
           "icon_eraser_page", "icon_select_box", "icon_vocab_add", "screenshot")
uses = []
for dp, _dn, fns in os.walk(root):
    for fn in fns:
        if fn.endswith(".py"):
            src = open(os.path.join(dp, fn), encoding="utf-8").read()
            uses += [f"{fn}:{n}" for n in OLD_PNG if re.search(r"resource_path\(\s*[\"']%s\.png" % n, src)]
chk(not uses, "A2 resources 아이콘 PNG 를 읽지 않는다", str(uses))
left = [n for n in OLD_PNG if os.path.exists(os.path.join(HERE, "resources", n + ".png"))]
chk(not left, "A3 옛 아이콘 PNG(남의 로고 포함)가 resources 에 없다", str(left))

# ── B·C. 실제 위젯 ──────────────────────────────────────────
from viewer import theme
from viewer.widgets import icons
from viewer.widgets.icons import ACCENT, FILE_KIND_COLOR


def set_theme(dark):
    """MainWindow.apply_theme 과 같은 차례 — theme.set_dark → setStyle(GC 멈춤) → setPalette."""
    theme.set_dark(dark)
    gc.collect(); gc.disable()
    try:
        app.setStyle(QStyleFactory.create("Fusion"))
    finally:
        gc.enable()
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(45, 45, 48) if dark else QColor(240, 240, 240))
    app.setPalette(p)
    app.processEvents()


def has_color(icon, want, tol=36, share=0.04):
    """그림의 불투명 화소 중 want 색에 가까운 것이 share 이상."""
    if icon is None or icon.isNull():
        return False
    img = icon.pixmap(32, 32).toImage()
    w = QColor(want)
    n = hit = 0
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() < 160:
                continue
            n += 1
            if abs(c.red() - w.red()) + abs(c.green() - w.green()) + abs(c.blue() - w.blue()) <= tol:
                hit += 1
    return n > 0 and hit / n >= share


set_theme(False)
from viewer.widgets.search_panel import SearchBar, SearchResults
from viewer.widgets.page_nav import PageNav
from viewer.widgets.study_panel import StudyPanel
from viewer.widgets.bookmark_tree import BookmarkTree
from viewer.widgets.strip import MiniStrip

holder = QWidget()
sb, sr, nav, sp, bt = SearchBar(holder), SearchResults(holder), PageNav(holder), StudyPanel(holder), BookmarkTree(holder)
try:
    from viewer.widgets.text_panel import TextPanel
    tp = TextPanel(holder)
except Exception as e:                         # 텍스트 창이 무거운 의존을 못 찾으면 그 줄만 빼고 알린다
    tp = None
    print("NOTE - TextPanel 을 만들 수 없음:", e)
strip = MiniStrip("스크린샷", max_items=5, extra_widgets=[])
holder.show(); app.processEvents()

BLUE = lambda d: ACCENT["play"][d]
KIND = lambda k, d: FILE_KIND_COLOR[k][d]


def check_all(d, tag):
    chk(all(b.text() == "" and has_color(b.icon(), BLUE(d)) for b in (sb.btn_prev, sb.btn_next)),
        f"{tag}1 검색 막대 이전/다음 = 파란 꺾쇠, 글자 없음", repr((sb.btn_prev.text(), sb.btn_next.text())))
    chk(all(b.text() == "" and has_color(b.icon(), BLUE(d)) for b in (nav.btn_prev, nav.btn_next)),
        f"{tag}2 쪽 이동 묶음 ‹ › = 파란 꺾쇠", repr((nav.btn_prev.text(), nav.btn_next.text())))
    arrows = getattr(bt, "_arrow_btns", [])
    chk(len(arrows) == 4 and all(b.text() == "" and has_color(b.icon(), BLUE(d)) for b, _n in arrows),
        f"{tag}3 책갈피 조작 ‹ › ∧ ∨ = 파란 꺾쇠", str(len(arrows)))
    chk(has_color(sp.btn_word.icon(), KIND("DOCX", d), share=0.3) and sp.btn_word.text() == "",
        f"{tag}4 단어장 [Word] = 워드 형식 배지(종전 MS 로고 PNG)")
    chk(has_color(sr.btn_excel.icon(), KIND("XLSX", d), share=0.3), f"{tag}5 검색결과 [저장] = 엑셀 형식 배지")
    if tp is not None:
        chk(has_color(tp.btn_word.icon(), KIND("DOCX", d), share=0.3), f"{tag}6 텍스트 창 [Word 저장] = 워드 형식 배지")
    chk(has_color(bt.btn_save.icon(), BLUE(d), share=0.2) and "💾" not in bt.btn_save.text(),
        f"{tag}7 책갈피창 [저장] = 파란 플로피(파일 탭과 같은 그림)", repr(bt.btn_save.text()))
    chk(not strip.clear_btn.icon().isNull() and strip.clear_btn.text() == "", f"{tag}8 스크린샷 칸 전체 삭제 = 그린 휴지통")


check_all(False, "B")
set_theme(True)
check_all(True, "C")
set_theme(False)

# 변환 창 형식 단추 = 형식 배지
from viewer.widgets.convert_dialog import ConvertDialog
from viewer import convert
try:
    dlg = ConvertDialog(None, page_count=3, prefs={})
except TypeError:
    dlg = None
if dlg is not None:
    want = {".docx": "DOCX", ".hwpx": "HWPX", ".pptx": "PPTX", ".xlsx": "XLSX", ".txt": "TXT"}
    rows = [(k, b) for k, b in dlg._fmt_btn.items()]
    okk = rows and all(has_color(b.icon(), KIND(want[convert.fmt(k).ext], False), share=0.3) for k, b in rows
                       if convert.fmt(k).ext in want)
    chk(okk, "B9 변환 창 문서 형식 단추 = 형식 배지", str([k for k, _b in rows]))
else:
    print("NOTE - ConvertDialog 인자가 달라 B9 를 건너뜀")

print("ALL PASS" if not fails else f"{len(fails)} FAIL")
sys.exit(1 if fails else 0)
