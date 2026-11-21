# -*- coding: utf-8 -*-
"""명함찾기 수정일·메모 수정 기록·메모 날짜 (명함 SOT §5.9 '수정일'·'메모 기록'·'메모 날짜', §5.24.9) — 가짜 명함만(§2.1).

오프스크린, 실제 설정·데이터 폴더를 쓰지 않는다(검사 작성 SOT §14.7.2). 실제 키 입력·[저장] 누름.
A. 목록 끝 열 '수정일' — 고친 적 없으면 스캔일
B. 메모 밖 칸(휴대폰)을 고쳐 저장 → 수정일 = 오늘, 메모 맨 위 '[오늘 수정] 휴대폰'(옛 값 없음), 메모 칸에도 보임
C. 같은 날 메일도 고치면 같은 줄에 '휴대폰·메일', 메모만 고치면 수정일·기록 그대로(다른 명함)
D. 메모를 쓰기 시작하면(한글 입력) 맨 위 '오늘 ' 뒤에 — 한 번만, 가운데를 고칠 땐 넣지 않음
E. 명함 환경설정 '메모' 체크 둘(처음 켬) — 끄면 기록·날짜 없음, 수정일은 그대로 바뀜
"""
import os, sys, tempfile, time, datetime
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtTest import QTest
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_memo_%d" % os.getpid())
fails = []
TMP = Path(tempfile.mkdtemp(prefix="bizcard_memo_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
TODAY = datetime.date.today().isoformat()


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
    P.apply_import(st, [{"name": "홍길동", "company": "가나다", "phones": [("cell", "010-0000-0001")], "emails": ["a@example.com"],
                         "urls": [], "memo": ""},
                        {"name": "김철수", "company": "라마바", "phones": [("cell", "010-0000-0002")], "emails": [], "urls": [],
                         "memo": "옛 메모"}], "주소록", "google")
    st.con.execute("UPDATE cards SET scanned='2020-01-01'")
    st.con.commit()
    hong = next(c for c in P.find(st, "") if c["name"] == "홍길동")
    kim = next(c for c in P.find(st, "") if c["name"] == "김철수")
    st.close()
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Discard)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    from viewer.widgets import bizcard_find_dialog as FD
    dlg = FD.BizcardFindDialog(None, db=db)
    dlg.show()
    pump(lambda: dlg.table.rowCount() >= 2)

    def pick(c):
        dlg.table.setCurrentCell(dlg.row_of_id(c["id"]), 0)
        pump(lambda: dlg._card is not None and dlg._card["id"] == c["id"], timeout=3)

    def date_of(c):
        r = dlg.row_of_id(c["id"])
        return dlg.table.item(r, FD.C_DATE).text() if r >= 0 else ""

    def retype(ed, keys):
        ed.setFocus()
        ed.selectAll()
        QTest.keyClick(ed, Qt.Key.Key_Delete)
        QTest.keyClicks(ed, keys)

    def save():
        QTest.mouseClick(dlg.btn_save, Qt.MouseButton.LeftButton)
        pump(None)

    def db_card(c):
        s = S.BizcardStore(db)
        try:
            return P.card_by_id(s, c["id"])
        finally:
            s.close()

    print("=== A. 수정일 열 ===")
    hd = dlg.table.model().headerData(FD.C_DATE, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
    chk(hd == "수정일", "A 목록 끝 열 머리말 = 수정일", repr(hd))
    chk(date_of(hong) == "2020-01-01", "A 고친 적 없으면 스캔일", date_of(hong))

    print("\n=== B. 칸 고쳐 저장 ===")
    pick(hong)
    retype(dlg.eds["cell"], "01000000009")
    save()
    c = db_card(hong)
    chk(date_of(hong) == TODAY and (c or {}).get("edited") == TODAY, "B 휴대폰을 고치면 수정일 = 오늘", date_of(hong))
    first = (c.get("memo") or "").split("\n")[0] if c else ""
    chk(first == "[%s 수정] 휴대폰" % TODAY and "010-0000-0001" not in (c.get("memo") or ""),
        "B 메모 맨 위 '[오늘 수정] 휴대폰' — 옛 값 없음", repr(first))
    chk(dlg.ed_memo.toPlainText().split("\n")[0] == first, "B 메모 칸에도 바로 보임")

    print("\n=== C. 같은 날 또·메모만 ===")
    retype(dlg.eds["email"], "b@example.com")
    save()
    c = db_card(hong)
    chk((c.get("memo") or "").split("\n")[0] == "[%s 수정] 휴대폰·메일" % TODAY and (c.get("memo") or "").count("수정]") == 1,
        "C 같은 날 메일도 고치면 같은 줄에 '휴대폰·메일'", repr((c.get("memo") or "")[:40]))
    pick(kim)
    ed = dlg.ed_memo
    ed.setFocus()
    cur = ed.textCursor()
    cur.movePosition(cur.MoveOperation.End)
    ed.setTextCursor(cur)
    QTest.keyClicks(ed, "x")                           # 가운데(끝)에서 고침 — 날짜 없음
    save()
    k2 = db_card(kim)
    chk(date_of(kim) == "2020-01-01" and not (k2.get("edited") or "") and "수정]" not in (k2.get("memo") or ""),
        "C 메모만 고치면 수정일·기록 그대로", repr((date_of(kim), k2.get("memo"))))
    chk((k2.get("memo") or "") == "옛 메모x", "D 가운데를 고칠 땐 날짜를 넣지 않음", repr(k2.get("memo")))

    print("\n=== D. 메모 날짜 ===")
    pick(hong)
    pick(kim)                                           # 다른 명함을 거쳐 다시 — 한 명함을 보는 동안 한 번
    ed.setFocus()
    cur = ed.textCursor()
    cur.movePosition(cur.MoveOperation.Start)
    ed.setTextCursor(cur)
    type_ko(ed, "가")
    type_ko(ed, "나")
    txt = ed.toPlainText()
    chk(txt.startswith(TODAY + " 가나\n옛 메모"), "D 맨 앞에서 쓰기 시작하면 '오늘 ' 뒤에(한 번만)", repr(txt[:30]))
    ed.selectAll()
    QTest.keyClick(ed, Qt.Key.Key_Delete)
    type_ko(ed, "다")
    chk(ed.toPlainText() == "다", "D 같은 명함에서 지우고 다시 쓰면 날짜를 다시 넣지 않음", repr(ed.toPlainText()))
    dlg._set_dirty(False)

    print("\n=== E. 명함 환경설정 ===")
    from viewer.widgets.bizcard_settings_dialog import BizcardSettingsDialog
    s = S.BizcardStore(db)
    sd = BizcardSettingsDialog(None, None, s)
    sd.show()
    pump(None)
    chk(getattr(sd, "chk_memo_log", None) is not None and sd.chk_memo_log.isChecked() and sd.chk_memo_date.isChecked(),
        "E '메모' 체크 둘, 처음 켬")
    if getattr(sd, "chk_memo_log", None) is not None:
        QTest.mouseClick(sd.chk_memo_log, Qt.MouseButton.LeftButton)
        sd.chk_memo_date.setFocus()
        QTest.keyClick(sd.chk_memo_date, Qt.Key.Key_Space)   # 곧바로 두 번째 마우스 누름은 두 번 누르기로 잡혀 바뀌지 않는다
        sd.apply()
    chk(not P.memo_opt(s, P.MEMO_LOG_KEY) and not P.memo_opt(s, P.MEMO_DATE_KEY), "E 끄면 명함 DB 에 꺼짐")
    s.close()
    pick(hong)
    pick(kim)
    retype(dlg.eds["title"], "Manager")
    ed.setFocus()
    cur = ed.textCursor()
    cur.movePosition(cur.MoveOperation.Start)
    ed.setTextCursor(cur)
    type_ko(ed, "라")
    save()
    k3 = db_card(kim)
    chk((k3.get("edited") or "") == TODAY and "수정]" not in (k3.get("memo") or "") and not (k3.get("memo") or "").startswith(TODAY),
        "E 끄면 기록·날짜 없음, 수정일은 바뀜", repr((k3.get("edited"), (k3.get("memo") or "")[:20])))
    dlg.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "예외 없이 끝남")
finish()
