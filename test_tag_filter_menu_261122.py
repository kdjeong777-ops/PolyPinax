# -*- coding: utf-8 -*-
"""'#' 풀다운 공용 위젯 하나 (검색창 SOT §5.1 '공용 위젯 하나', 명함 SOT §5.24.1 '# 풀다운', 261120-69) — 가짜 명함·임시 폴더만.

A 주 창 파일 목록과 명함찾기가 같은 TagFilterMenu — 비우기 항목은 칸 이름 따라(검색 비우기·찾기 비우기)
B 명함은 '형식' 묶음을 숨김(사용자 지시 261122), 주 창은 보임
C 칸에 든 토큰은 알려진 태그일 때만 (0) 으로 남김 — 두 창 같은 규칙
D 명함 찾기 칸 #균열 은 짝 #crack 이 붙은 명함도(태그 SOT §8.9 — 주 창과 같게)
"""
import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QCheckBox, QRadioButton
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_tag_filter_menu_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="tag_filter_menu_"))
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


def pump(cond, timeout=10.0):
    t = time.monotonic()
    while time.monotonic() - t < timeout:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


def boxes(menu):
    out = {}
    for a in menu.actions():
        w = getattr(a, "defaultWidget", lambda: None)()
        if w is not None:
            for cb in w.findChildren(QCheckBox) + w.findChildren(QRadioButton):
                out[cb.text()] = cb
    return out


try:
    from viewer.widgets.tag_filter_menu import TagFilterMenu
    from viewer.widgets.bookmark_tree import BookmarkTree
    from viewer.bizcard import people as P, store as S
    db = TMP / "local" / "bizcard.db"
    st = S.BizcardStore(db)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    a = P._insert_contact(st, {"name": "가짜일", "phones": [("cell", "010-0000-0001")]}, ["명함", "보고서", "골프"])
    b = P._insert_contact(st, {"name": "가짜이", "phones": [("cell", "010-0000-0002")]}, ["명함", "crack"])
    st.con.commit()
    st.close()

    print("=== A·B. 같은 위젯·명함은 형식 숨김 ===")
    bt = BookmarkTree()
    bt._list_tag_counts = lambda: {"보고서": 1, "골프": 2}
    bt._rebuild_tag_menu()
    mb = boxes(bt._tag_menu)
    main_texts = [x.text() for x in bt._tag_menu.actions()]
    from viewer.widgets import bizcard_find_dialog as FD
    fd = FD.BizcardFindDialog(None, db=db)
    fd.show()
    pump(lambda: fd.table.rowCount() == 2)
    fd.tag_menu.aboutToShow.emit()
    cb_ = boxes(fd.tag_menu)
    card_texts = [x.text() for x in fd.tag_menu.actions()]
    chk(isinstance(getattr(bt, "_tag_filter", None), TagFilterMenu) and isinstance(getattr(fd, "tag_filter", None), TagFilterMenu),
        "A 두 창 모두 TagFilterMenu")
    chk("검색 비우기" in main_texts and "찾기 비우기" in card_texts, "A 비우기 항목은 칸 이름 따라", str((main_texts, card_texts)))
    chk("#보고서  (1)" in mb and "#골프  (2)" in mb, "B 주 창은 형식(보고서) 보임", str(sorted(mb)))
    chk("#골프  (1)" in cb_ and not any(k.startswith("#보고서") for k in cb_), "B 명함은 형식 묶음 숨김", str(sorted(cb_)))

    print("\n=== C. 칸 토큰 (0) 은 알려진 태그만 ===")
    fd.ed_find.setText("#골프 #없는꼬리")
    pump(lambda: fd.table.rowCount() == 0, timeout=3)
    fd.tag_menu.aboutToShow.emit()
    cb2 = boxes(fd.tag_menu)
    chk("#골프  (0)" in cb2 and not any("없는꼬리" in k for k in cb2), "C 명함 — 알려진 '골프' 만 (0), 모르는 토큰은 안 보임", str(sorted(cb2)))
    fd.ed_find.clear()
    pump(lambda: fd.table.rowCount() == 2, timeout=3)

    print("\n=== D. 짝 태그 ===")
    from viewer import tag_pairs as TP
    TP.shared().link("균열", "crack")
    fd.ed_find.setText("#균열")
    pump(lambda: fd.table.rowCount() == 1, timeout=3)
    names = [fd.table.model().card(r)["name"] for r in range(fd.table.rowCount())]
    chk(names == ["가짜이"], "D #균열 → 짝 #crack 붙은 명함", str(names))
    fd.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외")
print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
