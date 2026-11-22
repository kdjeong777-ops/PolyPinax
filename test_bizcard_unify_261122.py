# -*- coding: utf-8 -*-
"""명함 이름·동작 통일 (261120-69, 점검 261120-67 의 10~12) — 가짜 명함·임시 DB 만(명함 SOT §2.1).

A 할 일 기록 [삭제] 는 변경 기록에 남고, 변경 기록 창 [적용] 으로 되살아남(탭이 남아 있을 때) — 탭이 지워졌으면 못 한 수로
B 미리보기 → [적용] 공통 — 중복 검토·구글 싱크·되살리기 단추 글이 '적용', 기본 단추 아님(디자인 SOT §2.7)
"""
import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtTest import QTest
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_unify_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_unify_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
INFO = []
QMessageBox.information = staticmethod(lambda *a, **k: INFO.append(a[2] if len(a) > 2 else "") or QMessageBox.StandardButton.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
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
    from viewer.bizcard import people as P, store as S, history as H
    db = TMP / "local" / "bizcard.db"
    st = S.BizcardStore(db)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    a = P._insert_contact(st, {"name": "가짜일", "phones": [("cell", "010-0000-0001")]}, ["명함"])
    st.con.commit()
    P.fav_init(st, "즐겨찾기")
    g1 = P.todo_add(st, {"title": "가짜할일하나", "memo": "", "start": "2026-11-01", "end": ""}, [a], "…")
    g2 = P.todo_add(st, {"title": "가짜할일둘", "memo": "", "start": "2026-11-01", "end": ""}, [a], "…")
    P.notes_table(st)
    n1 = P.note_add(st, g1, {"body": "가짜 첫 줄"}, "2026-11-02")
    n2 = P.note_add(st, g2, {"body": "가짜 둘째"}, "2026-11-02")
    t0 = time.time()
    time.sleep(0.02)

    # ── A ──
    print("=== A. 할 일 기록 삭제 → 변경 기록 → 되살리기 ===")
    P.note_delete(st, n1)
    P.note_delete(st, n2)
    P.fav_delete_group(st, g2)                             # 둘째 탭은 지움 — 그 기록은 되살릴 곳이 없다
    st.close()
    from viewer.widgets import bizcard_find_dialog as FD
    fd = FD.BizcardFindDialog(None, db=db)
    fd.show()
    pump(lambda: fd.table.rowCount() >= 1)
    dlg = fd.open_history(exec_=False)
    pump(lambda: dlg.tree.topLevelItemCount() >= 2, timeout=5)
    tops = [dlg.tree.topLevelItem(i).text(0) for i in range(dlg.tree.topLevelItemCount())]
    chk(any("할 일 기록" in t and "가짜할일하나" in t for t in tops), "A 지운 할 일 기록이 변경 기록 창에(할 일 기록 · 탭 이름)", str(tops))
    chk(dlg.btn_restore.text() == "적용", "B 되살리기 창 단추 '적용'", dlg.btn_restore.text())
    for i in range(dlg.tree.topLevelItemCount()):
        it = dlg.tree.topLevelItem(i)
        it.setCheckState(0, Qt.CheckState.Checked if "할 일 기록" in it.text(0) else Qt.CheckState.Unchecked)
    INFO.clear()
    QTest.mouseClick(dlg.btn_restore, Qt.MouseButton.LeftButton)
    pump(lambda: dlg.last_restored is not None, timeout=10)
    st2 = S.BizcardStore(db)
    back = [r[0] for r in st2.con.execute("SELECT body FROM todo_notes WHERE id=?", (n1,))]
    gone = st2.con.execute("SELECT COUNT(*) FROM todo_notes WHERE id=?", (n2,)).fetchone()[0]
    st2.close()
    chk(dlg.last_restored == 1 and len(back) == 1 and "가짜 첫 줄" in back[0] and gone == 0, "A 탭이 남은 기록만 같은 id 로 되살아남", str((dlg.last_restored, back, gone)))
    chk(INFO and "1건은 되살리지 못했습니다" in INFO[-1], "A 탭이 지워진 기록은 못 한 수로 알림", str(INFO))
    dlg.close()

    # ── B ──
    print("\n=== B. [적용] 공통 ===")
    dd = fd.open_dupes(exec_=False)
    pump(lambda: hasattr(dd, "btn_apply"))
    from viewer.widgets.bizcard_gsync_dialog import GSyncDialog
    gd = GSyncDialog(fd, db=db, start=False)
    chk(dd.btn_apply.text() == "적용" and gd.btn_apply.text() == "적용", "B 중복 검토·구글 싱크 단추 '적용'",
        str((dd.btn_apply.text(), gd.btn_apply.text())))
    flags = [(b.text(), b.isDefault(), b.autoDefault()) for b in (dd.btn_apply, gd.btn_apply, dlg.btn_restore)]
    chk(not any(x[1] or x[2] for x in flags), "B 기본 단추 아님", str(flags))
    gd.close()
    dd.close()
    fd.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외")
print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
