# -*- coding: utf-8 -*-
"""중복 검토 '명함 고치기' (명함찾기 SOT §5.24.8 '명함 고치기') — 가짜 명함·임시 DB 만(명함 SOT §2.1).

오프스크린, 실제 설정·데이터 폴더를 쓰지 않는다(검사 작성 SOT §14.7.2).
A. '적용 전' 하위 줄 오른쪽 메뉴 = 대표로·명함 고치기, 대표 줄 = 명함 고치기
B. 명함 고치기 창 — 칸은 명함찾기 세부 칸과 같고, 번호 칸은 치는 대로 하이픈. 실제 키로 고쳐 [저장]
C. 명함 DB 가 고쳐짐(번호 적을 꼴·이름), 묶음은 그대로·체크와 '적용 후' 고침은 남음, 그 줄·합친 결과가 새 값
D. [취소] 는 바꾸지 않음
"""
import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QPoint
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox, QMenu, QDialog, QDialogButtonBox
from PyQt6.QtGui import QContextMenuEvent
from PyQt6.QtTest import QTest
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_dupe_edit_%d" % os.getpid())
fails = []
TMP = Path(tempfile.mkdtemp(prefix="bizcard_dupe_edit_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")


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


def type_ko(w, text):
    """한글 입력 — IME 처럼(검사 작성 SOT §14.7.2 의 24)."""
    from PyQt6.QtGui import QInputMethodEvent
    ev = QInputMethodEvent("", [])
    ev.setCommitString(text)
    QApplication.sendEvent(w, ev)


def finish():
    print("FAILURES: %d" % len(fails))
    for f in fails:
        print("  -", f)
    sys.stdout.flush()
    os._exit(1 if fails else 0)


try:
    from viewer.bizcard import people as P, store as S
    db = TMP / "local" / "bizcard.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    st = S.BizcardStore(db)
    P.apply_import(st, [{"name": "홍길동", "company": "가나다", "phones": [("cell", "010-0000-0001")], "emails": [], "urls": []}],
                   "주소록", "remember")
    P.apply_import(st, [{"name": "홍길똥", "company": "가나다", "phones": [("cell", "010-0000-0001"), ("work", "02-0000-0002")],
                         "emails": ["hong@example.com"], "urls": []}], "주소록", "google")
    ids = [r[0] for r in st.con.execute("SELECT id FROM cards ORDER BY id").fetchall()]
    st.close()
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    from viewer.widgets import bizcard_find_dialog as FD
    from viewer.widgets import bizcard_dupe_dialog as DD
    fd = FD.BizcardFindDialog(None, db=db)
    fd.show()
    pump(lambda: fd.table.rowCount() >= 2)
    dd = fd.open_dupes(exec_=False)
    pump(lambda: dd is not None and dd.before.topLevelItemCount() == 1, timeout=5)
    top = dd.before.topLevelItem(0)
    child = top.child(0)
    gi, rep_id = top.data(0, Qt.ItemDataRole.UserRole)
    _gi, cid = child.data(0, Qt.ItemDataRole.UserRole)

    menus = []
    QMenu.exec = lambda self, *a, **k: menus.append([x.text() for x in self.actions() if not x.isSeparator()]) or None

    def right_click(it):
        vp = dd.before.viewport()
        pos = dd.before.visualItemRect(it).center()
        QApplication.sendEvent(vp, QContextMenuEvent(QContextMenuEvent.Reason.Mouse, pos, vp.mapToGlobal(pos)))
        pump(None)
        return getattr(dd, "_last_menu", None)

    print("=== A. 오른쪽 메뉴 ===")
    menus.clear()
    m_child = right_click(child)
    chk(menus and menus[-1] == ["대표로", "명함 고치기"], "A 하위 줄 — 대표로·명함 고치기", repr(menus[-1:] ))
    menus.clear()
    right_click(top)
    chk(menus and menus[-1] == ["명함 고치기"], "A 대표 줄 — 명함 고치기", repr(menus[-1:]))

    print("\n=== B·C. 고쳐 저장 ===")
    dd.set_edit(gi, "title", "부장")                 # '적용 후' 고침이 남는지 볼 값
    chk_before = dict(dd.chk)
    seen = {}

    def fake_exec(self):
        seen["fields"] = [self.eds[k] is not None for k, _l in FD.FIELDS]
        seen["keys"] = list(self.eds)
        ed = self.eds["cell"]
        ed.setFocus()
        ed.selectAll()
        QTest.keyClick(ed, Qt.Key.Key_Delete)
        QTest.keyClicks(ed, "01000009999")
        seen["cell_typed"] = ed.text()
        nm = self.eds["name"]
        nm.setFocus()
        nm.selectAll()
        QTest.keyClick(nm, Qt.Key.Key_Delete)
        type_ko(nm, "홍길동")
        bb = self.findChild(QDialogButtonBox)
        QTest.mouseClick(bb.button(QDialogButtonBox.StandardButton.Save), Qt.MouseButton.LeftButton)
        return self.result()
    DD.CardEditDialog.exec = fake_exec
    if m_child is not None:
        act = next((a for a in m_child.actions() if a.text() == "명함 고치기"), None)
        act.trigger() if act is not None else None
    pump(None)
    chk(seen.get("keys") == [k for k, _l in FD.FIELDS], "B 칸은 명함찾기 세부 칸과 같음", repr(seen.get("keys")))
    chk(seen.get("cell_typed") == "010-0000-9999", "B 휴대폰 칸 치는 대로 하이픈", repr(seen.get("cell_typed")))
    st = S.BizcardStore(db)
    c = P.card_by_id(st, cid)
    st.close()
    chk(c is not None and c["name"] == "홍길동" and ("cell", "010-0000-9999") in [tuple(x) for x in c["phones"]]
        and ("work", "02-0000-0002") in [tuple(x) for x in c["phones"]], "C 명함 DB 가 고쳐짐(이름·번호, 다른 번호는 그대로)",
        repr(c and (c["name"], c["phones"])))
    # 261120-56(사용자 결정 261121): 고친 뒤 다시 묶는다 — 이어 주던 휴대폰을 바꾼 명함은 빠지고, '적용 후' 고침은 새로
    chk(dd.before.topLevelItemCount() == 0 and not dd.edits, "C 고친 뒤 다시 묶음 — 이어 주던 번호를 바꾼 명함은 빠짐(261120-56)",
        repr((dd.before.topLevelItemCount(), dd.edits)))
    st = S.BizcardStore(db)                               # D 를 위해 묶음을 되살림(이어 주던 휴대폰을 다시 넣음)
    rep_cells = [tuple(x) for x in P.card_by_id(st, rep_id)["phones"] if x[0] == "cell"][:1]
    P.update_card(st, cid, {"phones": [tuple(x) for x in P.card_by_id(st, cid)["phones"]] + rep_cells})
    st.close()
    dd.reload()
    gi = 0
    rep_id = dd.rep.get(0, rep_id)

    print("\n=== D. 취소 ===")
    def cancel_exec(self):
        self.eds["name"].setText("바뀌면안됨")
        bb = self.findChild(QDialogButtonBox)
        QTest.mouseClick(bb.button(QDialogButtonBox.StandardButton.Cancel), Qt.MouseButton.LeftButton)
        return self.result()
    DD.CardEditDialog.exec = cancel_exec
    chk(dd.edit_card(gi, rep_id) is False, "D [취소] 하면 False")
    st = S.BizcardStore(db)
    chk(P.card_by_id(st, rep_id)["name"] == "홍길동", "D [취소] 는 명함을 바꾸지 않음")
    st.close()
    dd.close()
    fd.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "예외 없이 끝남")
finish()
