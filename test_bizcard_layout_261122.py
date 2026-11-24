# -*- coding: utf-8 -*-
"""명함창 배치 다듬기 (명함찾기 SOT §5.24.1 '세부 해시태그'·'아래 줄', §5.24.10 '배치' 줄 맞춤, 디자인 SOT §2.7 '#' 단추, 261120-75).
가짜 명함·임시 DB 만.

A 세부 칸 맨 아래 해시태그 칸 — '#태그' 만(이름·#명함 없음), '(주소록에서…)' 글 없음, 고쳐 [저장] 하면 DB 태그(#명함 은 남음)
B 아래 줄 — 고른 명단 없음, 진행 글은 왼쪽 정렬
C 할 일 칸 줄 맞춤 — 위 끝 = 탭 줄 위 끝, 내용 칸 위 끝 = 사람 칸 위 끝, 아래 끝 = 사람 칸 아래 끝
D '#' 단추 — '#' 와 메뉴 화살표가 다 들어가는 폭(주 창·명함찾기 같은 위젯)
"""
import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QPoint
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QLabel
from PyQt6.QtTest import QTest
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_layout_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_layout_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


def pump(cond=None, timeout=3.0):
    t = time.monotonic()
    while time.monotonic() - t < timeout:
        app.processEvents()
        if cond is not None and cond():
            return True
        time.sleep(0.01)
    return False


def top(w, ref):
    return w.mapTo(ref, QPoint(0, 0)).y()


try:
    from viewer.bizcard import people as P, store as S
    db = TMP / "local" / "bizcard.db"
    st = S.BizcardStore(db)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    a = P._insert_contact(st, {"name": "가짜일", "company": "가짜사", "phones": [("cell", "010-0000-0001")]}, ["명함", "골프"])
    st.con.commit()
    P.fav_init(st, "즐겨찾기")
    g = P.todo_add(st, {"title": "가짜할일", "memo": "", "start": "2026-11-01", "end": ""}, [a], "…")
    st.close()
    from viewer.widgets import bizcard_find_dialog as FD
    fd = FD.BizcardFindDialog(None, db=db)
    fd.resize(1400, 900)
    fd.show()
    pump(lambda: fd.table.rowCount() == 1)
    fd.table.setCurrentCell(0, 0)
    pump()

    # ── A ──
    print("=== A. 세부 해시태그 칸 ===")
    et = getattr(fd, "ed_tags", None)
    texts = [w.text() for w in fd.findChildren(QLabel) if w.isVisible()]
    chk(et is not None and et.isVisible() and et.text() == "#골프", "A 세부 칸 해시태그 — 이름·#명함 없이", repr(et and et.text()))
    chk(not any("주소록에서 가져온 명함" in t for t in texts), "A '(주소록에서…)' 글 없음")
    chk(et is not None and top(et, fd) > top(fd.ed_memo, fd), "A 메모 아래(종전 파일 글 자리)")
    if et is not None:
        et.setFocus()
        et.selectAll()
        QTest.keyClick(et, Qt.Key.Key_End)
        et.setText("#골프 #가짜새")                       # 한글 키 입력은 오프스크린에서 막혀 setText 뒤 실제 키 하나
        QTest.keyClick(et, Qt.Key.Key_Space)
        QTest.keyClick(et, Qt.Key.Key_Backspace)
        chk(fd.btn_save.isEnabled(), "A 고치면 [저장] 켜짐")
        QTest.mouseClick(fd.btn_save, Qt.MouseButton.LeftButton)
        pump(lambda: not fd.btn_save.isEnabled())
        tags = P.card_by_id(fd._store(), a)["tags"]
        chk({"명함", "골프", "가짜새"} <= set(tags), "A [저장] 하면 DB 태그(#명함 남음, 회사 자동 태그는 기존대로)", str(tags))

    # ── B ──
    print("\n=== B. 아래 줄 ===")
    chk(getattr(fd, "lbl_picked", None) is None, "B 고른 명단 없음")
    fd.lbl_media.setText("구글에 사진 올리는 중 1/3")
    fd.lbl_media.setVisible(True)
    pump()
    x = fd.lbl_media.mapTo(fd, QPoint(0, 0)).x()
    chk(x < 40, "B 진행 글은 왼쪽 정렬", str(x))
    fd.lbl_media.setVisible(False)

    # ── C ──
    print("\n=== C. 할 일 칸 줄 맞춤 ===")
    i = next(i for i in range(fd.fav_tabs.count()) if fd.fav_tabs.tabData(i) == g)
    fd.fav_tabs.setCurrentIndex(i)
    pump()
    tp = fd.todo_panel
    vals = (top(fd.fav_tabs, fd), top(tp, fd), top(fd.fav, fd), top(tp.scroll, fd),
            top(fd.fav, fd) + fd.fav.height(), top(tp, fd) + tp.height())
    chk(tp.isVisible() and abs(vals[0] - vals[1]) <= 1, "C 위 끝 = 탭 줄 위 끝", str(vals))
    chk(abs(vals[2] - vals[3]) <= 1, "C 내용 칸 위 끝 = 사람 칸 위 끝", str(vals))
    chk(abs(vals[4] - vals[5]) <= 1, "C 아래 끝 = 사람 칸 아래 끝", str(vals))
    fd.resize(1200, 760)
    pump()
    vals2 = (top(fd.fav_tabs, fd), top(tp, fd), top(fd.fav, fd), top(tp.scroll, fd),
             top(fd.fav, fd) + fd.fav.height(), top(tp, fd) + tp.height())
    chk(abs(vals2[0] - vals2[1]) <= 1 and abs(vals2[2] - vals2[3]) <= 1 and abs(vals2[4] - vals2[5]) <= 1, "C 창 크기를 바꿔도 맞음", str(vals2))

    # ── D ──
    print("\n=== D. '#' 단추 ===")
    from viewer.widgets.bookmark_tree import BookmarkTree
    bt = BookmarkTree()
    bt.show()
    pump()
    for name, b in (("명함찾기", fd.btn_tags), ("주 창", bt.btn_tag)):
        fm = b.fontMetrics()
        need = fm.horizontalAdvance("#99") + 16           # 글 + 메뉴 화살표 자리(최소)
        chk(b.width() >= need, "D %s '#' 단추 폭에 글·화살표가 다 들어감" % name,
            str((b.width(), need, b.sizeHint().width())))
    fd.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외")
print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
