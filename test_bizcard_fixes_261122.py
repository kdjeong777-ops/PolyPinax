# -*- coding: utf-8 -*-
"""명함 전체 점검 결함 고침 (261120-68, 점검 261120-67 의 1~7) — 가짜 명함·임시 DB·임시 파일만(명함 SOT §2.1).

A 되살리기는 기록에 있는 칸만 — 기록 뒤 늘어난 칸은 지금 값 그대로(§5.30 '되살린 뒤')
B gsync.init 은 열린 쓰기 도중에 커밋하지 않는다(§5.7 google_link)
C 번호 종류 바로잡기가 실패하면 알리고 meta 에 세며, 세 번이면 더는 저절로 하지 않는다(§5.11)
D 환경설정 라벨 체크는 _tagkey 로 비교(공백·대소문자 무시, §5.29 '라벨')
E PolyCardex Host._trash_bg — 휴지통은 배경 스레드(§5.27 '경계')
F 메인 스레드 DB 일 — 되살리기 창 목록 읽기·변경 기록 정리·환경설정 해시태그 모으기는 배경
G 색 — bookmark_tree '#' 단추는 theme.tag_button_style, 즐겨찾기 빈 그림은 다크에서 다른 색
"""
import os, sys, tempfile, time, json, threading
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_fixes_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_fixes_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
WARN = []
QMessageBox.warning = staticmethod(lambda *a, **k: WARN.append(a[2] if len(a) > 2 else "") or QMessageBox.StandardButton.Ok)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
MAIN = threading.main_thread()
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


try:
    from viewer.bizcard import people as P, store as S, history as H, gsync as G
    db = TMP / "local" / "bizcard.db"
    st = S.BizcardStore(db)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    a = P._insert_contact(st, {"name": "가짜일", "company": "가짜사", "title": "과장", "phones": [("cell", "010-0000-0001")]}, ["명함", "Golf Club"])
    st.con.commit()

    # ── A ──
    print("=== A. 되살리기는 기록에 있는 칸만 ===")
    t0 = time.time()
    time.sleep(0.02)
    P.update_card(st, a, {"company": "가짜새사", "title": "부장"})
    ent = [e for e in H.entries(st, t0, time.time() + 1) if e["card_id"] == a][0]
    ent = dict(ent)
    ent["row"] = {k: v for k, v in ent["row"].items() if k != "title"}   # 옛 판 기록 — 'title' 칸이 없던 때
    H.restore(st, [ent])
    c = P.card_by_id(st, a)
    chk(c["company"] == "가짜사" and c["title"] == "부장", "A 기록에 없는 칸(title)은 지금 값 그대로, 있는 칸만 되살림",
        str((c["company"], c["title"])))

    # ── B ──
    print("\n=== B. gsync.init 은 열린 쓰기 도중에 커밋하지 않음 ===")
    st.close()
    st = S.BizcardStore(db)
    st.con.execute("UPDATE cards SET memo='가짜 도중' WHERE id=?", (a,))
    G.links(st)                                           # 합치기 도중 짝 읽기와 같은 길
    st.con.rollback()
    memo = st.con.execute("SELECT memo FROM cards WHERE id=?", (a,)).fetchone()[0]
    chk(memo != "가짜 도중", "B 짝 읽기(init)가 도중 쓰기를 커밋하지 않음 — 되돌리면 사라짐", repr(memo))
    st.meta_set(P.KINDS_FIXED_KEY, None)                  # C 를 위해 — 아직 안 바로잡은 DB
    st.close()

    # ── C ──
    print("\n=== C. 번호 종류 바로잡기 실패 ===")
    from viewer.widgets import bizcard_find_dialog as FD
    _orig_fix = P.fix_kinds_all
    P.fix_kinds_all = lambda *a_, **k_: (_ for _ in ()).throw(RuntimeError("가짜 실패"))
    seen = {}
    for i in range(4):
        WARN.clear()
        fd = FD.BizcardFindDialog(None, db=db)
        fd.show()
        pump(lambda: bool(WARN), timeout=3)
        seen[i] = list(WARN)
        st2 = fd._store()
        seen["fail%d" % i] = st2.meta_get("phone_kinds_fail", 0)
        fd.close()
        pump(lambda: False, timeout=0.2)
    P.fix_kinds_all = _orig_fix
    chk(seen[0] and seen["fail0"] == 1, "C 실패하면 알리고 meta 에 셈", str((seen[0], seen["fail0"])))
    chk(seen["fail2"] == 3 and not seen[3] and seen["fail3"] == 3, "C 세 번이면 더는 저절로 하지 않음(알림도 없음)",
        str((seen["fail2"], seen[3], seen["fail3"])))

    # ── D ──
    print("\n=== D. 환경설정 라벨 비교 = _tagkey ===")
    st = S.BizcardStore(db)
    st.meta_set(G.OPT_LABELS, ["golfclub"])               # 공백 없이 적힌 고른 라벨
    from viewer.widgets.bizcard_settings_dialog import BizcardSettingsDialog
    dlg = BizcardSettingsDialog(None, host=None, store=st)
    lw = dlg.lst_glabels
    pump(lambda: any(lw.item(i).text() == "Golf Club" for i in range(lw.count())), timeout=3)
    from PyQt6.QtCore import Qt
    it = next((lw.item(i) for i in range(lw.count()) if lw.item(i).text() == "Golf Club"), None)
    chk(it is not None and it.checkState() == Qt.CheckState.Checked, "D 'Golf Club' 은 고른 'golfclub' 과 같은 태그(체크됨)",
        str(it and it.checkState()))
    dlg.close()

    # ── F ──
    print("\n=== F. 메인 스레드 DB 일은 배경 ===")
    where = {}
    _e, _p, _t = H.entries, H.maybe_prune, getattr(P, "all_tags", None)

    def rec(name, fn):
        def w(*a_, **k_):
            where.setdefault(name, []).append(threading.current_thread() is MAIN)
            return fn(*a_, **k_)
        return w
    H.entries = rec("entries", _e)
    H.maybe_prune = rec("prune", _p)
    if _t is not None:
        P.all_tags = rec("tags", _t)
    st.meta_set(H.PRUNE_KEY, 0)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    st.close()
    fd = FD.BizcardFindDialog(None, db=db)
    fd.show()
    pump(lambda: "prune" in where, timeout=3)
    hd = fd.open_history(exec_=False)
    pump(lambda: "entries" in where and hd.tree.topLevelItemCount() > 0, timeout=5)
    sd = fd.open_settings(exec_=False)
    pump(lambda: "tags" in where, timeout=3)
    chk(where.get("prune") == [False], "F 변경 기록 정리는 배경", str(where.get("prune")))
    chk(where.get("entries") and not any(where["entries"]) and hd.tree.topLevelItemCount() > 0, "F 되살리기 창 목록 읽기는 배경(나무는 채워짐)",
        str(where.get("entries")))
    chk(where.get("tags") and not any(where["tags"]), "F 환경설정 해시태그 모으기는 배경(people.all_tags)", str(where.get("tags")))
    H.entries, H.maybe_prune = _e, _p
    if _t is not None:
        P.all_tags = _t
    hd.close()
    sd.close()

    # ── G ──
    print("\n=== G. 색 ===")
    from viewer import theme
    _ts = theme.tag_button_style
    theme.tag_button_style = lambda on: "QPushButton{color:#123456;}" if on else ""
    from viewer.widgets.bookmark_tree import BookmarkTree
    bt = BookmarkTree()
    bt._tag_active = True
    bt._style_tag_button()
    chk("#123456" in bt.btn_tag.styleSheet(), "G 주 창 '#' 단추는 theme.tag_button_style 하나", bt.btn_tag.styleSheet())
    theme.tag_button_style = _ts
    from PyQt6.QtGui import QColor
    theme.set_dark(False)
    light = FD._rounded(None, "가").toImage().pixelColor(4, 30)
    theme.set_dark(True)
    dark = FD._rounded(None, "가").toImage().pixelColor(4, 30)
    theme.set_dark(False)
    chk(light.name() != dark.name() and dark.lightness() < light.lightness(), "G 즐겨찾기 빈 그림 — 다크에서 어두운 바탕",
        str((light.name(), dark.name())))

    # ── E ──
    print("\n=== E. PolyCardex 휴지통은 배경 ===")
    from viewer.bizcard import standalone as SA
    import viewer.widgets.bookmark_tree as BTM
    host = SA.Host()
    f = TMP / "가짜_지울것.jpg"
    f.write_bytes(b"x")
    thr = []
    _tf = BTM._trash_fn
    BTM._trash_fn = lambda: (lambda p: (thr.append(threading.current_thread() is MAIN), os.remove(p)))
    res = host._trash_bg([str(f)], photo=True) if hasattr(host, "_trash_bg") else None
    BTM._trash_fn = _tf
    chk(res is not None and res.get(str(f)) is None and not f.exists() and thr == [False], "E Host._trash_bg — 배경에서 지우고 {경로: None}",
        str((res, f.exists(), thr)))
    fd.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외")
print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
