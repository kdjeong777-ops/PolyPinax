# -*- coding: utf-8 -*-
"""명함 변경 기록·되살리기 (명함 SOT §5.30, 261120-64) — 가짜 명함·임시 DB 만(§2.1).

A 고치기·지우기·합치기·구글 싱크가 모두 기록에 남음(출처), 고친 시각만 바뀐 것은 안 남음
B 기간·종류(지운 것·고친 것)·출처 거르기, 되살릴 값 = 기간이 시작되기 전 모습
C 그 기간 뒤에 또 바뀐 명함은 표시·처음 꺼짐
D 되살리면 지운 명함이 돌아오고 고친 칸이 옛 값으로, 되살리기도 기록(출처 restore)
E 180일 지난 기록은 지움
F 창 — [주소록] 메뉴 '변경 기록·되살리기', 체크한 줄만 [되살리기](배경)
"""
import os, sys, tempfile, time, json
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtTest import QTest
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_history_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_history_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
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
    from viewer.bizcard import people as P, store as S
    try:
        from viewer.bizcard import history as H
    except Exception:
        H = None
    chk(H is not None, "history 모듈이 있다")
    db = TMP / "local" / "bizcard.db"
    st = S.BizcardStore(db)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    a = P._insert_contact(st, {"name": "가짜일", "company": "가짜사", "phones": [("cell", "010-0000-0001")]}, ["명함"])
    b = P._insert_contact(st, {"name": "가짜이", "company": "가짜사", "phones": [("cell", "010-0000-0002")]}, ["명함"])
    c = P._insert_contact(st, {"name": "가짜삼", "phones": [("cell", "010-0000-0003")]}, ["명함"])
    st.con.commit()
    t0 = time.time()
    time.sleep(0.02)

    # ── A ──
    print("=== A. 남기기 ===")
    P.update_card(st, a, {"company": "가짜새사"})               # 직접 고침
    st.con.execute("UPDATE cards SET updated=? WHERE id=?", (time.time(), b))   # 시각만
    st.con.commit()
    if H:
        with H.source(st, "sync"):
            P.update_card(st, b, {"title": "부장"})
    st.delete_card(c)                                          # 지움
    rows = st.con.execute("SELECT card_id, kind, src FROM card_history ORDER BY id").fetchall() if H else []
    got = [(r[0], r[1], r[2]) for r in rows]
    chk(got == [(a, "edit", "edit"), (b, "edit", "sync"), (c, "delete", "edit")], "A 고침·싱크·지움이 기록(시각만은 안 남음)", str(got))
    t1 = time.time()
    time.sleep(0.02)

    # ── B·C ──
    print("\n=== B·C. 거르기·겹침 ===")
    P.update_card(st, a, {"company": "가짜더새사"})            # 기간 뒤에 또 바뀜
    ents = H.entries(st, t0, t1) if H else []
    by = {e["card_id"]: e for e in ents}
    chk(set(by) == {a, b, c} and by[c]["kind"] == "delete" and by[a]["kind"] == "edit", "B 기간 안 명함 셋·종류", str(ents))
    chk(by.get(a, {}).get("row", {}).get("company") == "가짜사", "B 되살릴 값 = 기간 시작 전 모습", str(by.get(a)))
    chk(by.get(a, {}).get("later") is True and not by.get(b, {}).get("later"), "C 그 뒤 또 바뀐 명함 표시", str([(e["card_id"], e["later"]) for e in ents]))
    chk([e["card_id"] for e in H.entries(st, t0, t1, kinds={"delete"})] == [c] if H else False, "B 지운 것만")
    chk(sorted(e["card_id"] for e in H.entries(st, t0, t1, srcs={"sync"})) == [b] if H else False, "B 출처 거르기(싱크)")

    # ── D ──
    print("\n=== D. 되살리기 ===")
    n = H.restore(st, [by[a], by[c]]) if H else 0
    ca, cc = P.card_by_id(st, a), P.card_by_id(st, c)
    chk(n == 2 and ca["company"] == "가짜사" and cc and cc["name"] == "가짜삼" and cc["phones"] == [("cell", "010-0000-0003")],
        "D 고친 칸은 옛 값으로·지운 명함은 돌아옴(같은 id)", str((n, ca and ca["company"], cc)))
    srcs = [r[0] for r in st.con.execute("SELECT src FROM card_history WHERE card_id=? ORDER BY id DESC LIMIT 1", (a,))]
    chk(srcs == ["restore"], "D 되살리기도 기록(되돌릴 수 있음)", str(srcs))
    hit = [r for r in P.find(st, "가짜삼")]
    chk(len(hit) == 1, "D 되살린 명함이 찾기에도", str(len(hit)))

    # ── E ──
    print("\n=== E. 보존 180일 ===")
    st.con.execute("UPDATE card_history SET at=? WHERE card_id=?", (time.time() - 181 * 86400, b))
    st.con.commit()
    gone = H.prune(st) if H else 0
    left = st.con.execute("SELECT COUNT(*) FROM card_history WHERE card_id=?", (b,)).fetchone()[0] if H else -1
    chk(gone >= 1 and left == 0, "E 180일 지난 기록 지움", str((gone, left)))
    st.close()

    # ── F ──
    print("\n=== F. 창 ===")
    from viewer.widgets import bizcard_find_dialog as FD
    fd = FD.BizcardFindDialog(None, db=db)
    fd.show()
    pump(lambda: fd.table.rowCount() >= 3)
    acts = [x.text() for x in fd.vcard_menu.actions()]
    chk("변경 기록·되살리기" in acts, "F [주소록] 메뉴 '변경 기록·되살리기'", str(acts))
    st2 = S.BizcardStore(db)
    P.update_card(st2, b, {"name": "가짜이바뀜"})
    st2.close()
    dlg = fd.open_history(exec_=False) if hasattr(fd, "open_history") else None
    if dlg is not None:
        pump(lambda: dlg.tree.topLevelItemCount() > 0)
        items = [dlg.tree.topLevelItem(i) for i in range(dlg.tree.topLevelItemCount())]
        target = next((it for it in items if dlg.items[it.data(0, Qt.ItemDataRole.UserRole)]["card_id"] == b), None)   # 줄 글 = 되살릴 값(바뀌기 전)
        for it in items:
            it.setCheckState(0, Qt.CheckState.Checked if it is target else Qt.CheckState.Unchecked)
        QTest.mouseClick(dlg.btn_restore, Qt.MouseButton.LeftButton)
        pump(lambda: getattr(dlg, "last_restored", None) is not None, timeout=10)
        st3 = S.BizcardStore(db)
        chk(target is not None and dlg.last_restored == 1 and P.card_by_id(st3, b)["name"] == "가짜이", "F 체크한 줄만 [되살리기]",
            str((target is not None, getattr(dlg, "last_restored", None), P.card_by_id(st3, b)["name"])))
        st3.close()
        dlg.close()
    else:
        chk(False, "F open_history 가 있다")
    fd.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외")
print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
