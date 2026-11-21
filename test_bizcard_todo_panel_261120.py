# -*- coding: utf-8 -*-
"""명함찾기 할 일 칸 — 탭 줄 오른쪽 (명함 SOT §5.24.10, 261120-34) — 가짜 명함·가짜 할 일만(명함 SOT §2.1).

오프스크린, 실제 설정·데이터 폴더를 쓰지 않는다(검사 작성 SOT §14.7.2). 실제 클릭·키 입력.
A. 배치 — 할 일 탭이면 위 띠 오른쪽에 할 일 칸(폭 = 사진창), 명함 그림 위 끝 = 세부내용 위 끝, 할 일 탭이 아니면 칸 숨김·사람 칸이 끝까지
B. 기록 — 최신부터, 고쳐 [저장] = 새 기록(옛 기록 그대로), ◀▶ 로 이동, 탭 '내용' = 최신 기록
C. 체크·기한(탭 기간 안)·해시태그(기록 전용)·[삭제] = 보던 기록 하나
D. 옛 할 일 — 내용이 첫 기록으로(한 번만), 할 일 고치기 창에서 내용을 바꾸면 새 기록, 엑셀 '해시태그' 열
"""
import os, sys, tempfile, time, datetime
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QPoint
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtTest import QTest
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_todopanel_%d" % os.getpid())
fails = []
TMP = Path(tempfile.mkdtemp(prefix="bizcard_todopanel_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
TODAY = datetime.date.today()
D = lambda n: (TODAY + datetime.timedelta(days=n)).isoformat()


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


def click(w):
    QTest.mouseClick(w, Qt.MouseButton.LeftButton)
    pump(None)


try:
    from viewer.bizcard import people as P, store as S
    db = TMP / "local" / "bizcard.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    st = S.BizcardStore(db)
    P.apply_import(st, [{"name": "홍길동", "company": "가나다", "phones": [("cell", "010-0000-0001")], "emails": [], "urls": []},
                        {"name": "김철수", "company": "라마바", "phones": [("cell", "010-0000-0002")], "emails": [], "urls": []}],
                   "주소록", "google")
    ids = [r[0] for r in st.con.execute("SELECT id FROM cards ORDER BY id").fetchall()]
    P.fav_init(st, "즐겨찾기")
    # 옛 판이 만든 할 일 — 기록 표 없이 내용만(D)
    st.con.execute("DROP TABLE IF EXISTS todo_notes")
    pos = st.con.execute("SELECT IFNULL(MAX(pos), -1) + 1 FROM fav_groups").fetchone()[0]
    g_old = st.con.execute("INSERT INTO fav_groups(name, pos, todo, t_memo, t_start, t_end) VALUES(?,?,1,?,?,?)",
                           ("가짜 옛 할 일", pos, "옛 내용", D(-10), D(10))).lastrowid
    st.con.commit()
    P.fav_init(st, "즐겨찾기")
    old_notes = P.todo_notes(st, g_old)
    chk(len(old_notes) == 1 and old_notes[0]["body"] == "옛 내용" and old_notes[0]["made"] == D(-10),
        "D 옛 할 일 내용이 첫 기록으로(수정일 = 탭 시작일)", repr(old_notes))
    P.fav_init(st, "즐겨찾기")
    chk(len(P.todo_notes(st, g_old)) == 1, "D 옮기기는 한 번만")
    gid = P.todo_add(st, {"title": "가짜 보고서", "memo": "첫 내용", "start": D(-3), "end": D(20)}, ids, "…")
    chk(len(P.todo_notes(st, gid)) == 1, "D 새 할 일의 처음 내용 = 기록 하나(두 번 들어가지 않음)")
    st.meta_set("fav_tab", gid)
    st.close()

    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    from viewer.widgets import bizcard_find_dialog as FD
    dlg = FD.BizcardFindDialog(None, db=db)
    dlg.resize(1500, 900)
    dlg.show()
    pump(lambda: dlg.table.rowCount() >= 2)
    pump(lambda: dlg.todo_panel.isVisible(), timeout=3)
    tp = dlg.todo_panel

    print("=== A. 배치 ===")
    chk(tp.isVisible() and tp.lbl_title.text() == "가짜 보고서", "A 할 일 탭이면 위 띠 오른쪽에 할 일 칸(제목)")
    y_pic = dlg.photo_split.mapTo(dlg, QPoint(0, 0)).y()
    y_det = dlg.detail_box.mapTo(dlg, QPoint(0, 0)).y()
    chk(abs(y_pic - y_det) <= 2, "A 명함 그림 위 끝 = 세부내용 위 끝", "%d %d" % (y_pic, y_det))
    x_tp = tp.mapTo(dlg, QPoint(0, 0)).x()
    x_ph = dlg.photo_split.mapTo(dlg, QPoint(0, 0)).x()
    chk(abs(x_tp - x_ph) <= 3 and abs(tp.width() - dlg.photo_split.width()) <= 3, "A 할 일 칸 폭·자리 = 사진창",
        "%d %d %d %d" % (x_tp, x_ph, tp.width(), dlg.photo_split.width()))
    fav_w_todo = dlg.fav.width()

    print("\n=== B. 기록 ===")
    chk(tp.ed_body.toPlainText() == "첫 내용" and tp.lbl_pos.text() == "1/1" and not tp.btn_save.isEnabled(),
        "B 최신 기록·n/m·바꾼 것 없으면 [저장] 꺼짐")
    tp.ed_body.setFocus()
    cur = tp.ed_body.textCursor()
    cur.movePosition(cur.MoveOperation.End)
    tp.ed_body.setTextCursor(cur)
    type_ko(tp.ed_body, " 고침")
    chk(tp.btn_save.isEnabled(), "B 고치면 [저장] 켜짐")
    click(tp.btn_save)
    s2 = S.BizcardStore(db)
    notes = P.todo_notes(s2, gid)
    memo = P.todo_info(s2, gid)["memo"]
    s2.close()
    chk(len(notes) == 2 and notes[0]["body"] == "첫 내용 고침" and notes[1]["body"] == "첫 내용" and notes[0]["made"] == TODAY.isoformat(),
        "B [저장] = 오늘 날짜 새 기록, 옛 기록 그대로", repr([n["body"] for n in notes]))
    chk(memo == "첫 내용 고침", "B 탭 '내용' = 최신 기록")
    chk(tp.lbl_pos.text() == "1/2" and not tp.btn_next.isEnabled() and tp.btn_prev.isEnabled(), "B 최신에서 ◀ 만 켜짐")
    click(tp.btn_prev)
    chk(tp.ed_body.toPlainText() == "첫 내용" and tp.lbl_pos.text() == "2/2", "B ◀ = 이전 기록")
    click(tp.btn_next)
    chk(tp.ed_body.toPlainText() == "첫 내용 고침", "B ▶ = 다음 기록")

    print("\n=== C. 체크·기한·해시태그·삭제 ===")
    chk(tp.d_start.minimumDate().toString("yyyy-MM-dd") == D(-3) and tp.d_end.maximumDate().toString("yyyy-MM-dd") == D(20),
        "C 기한은 탭 기간 안(날짜 칸 최소·최대)")
    click(tp.chk_done)
    tp.ed_tags.setFocus()
    QTest.keyClicks(tp.ed_tags, "#report submit")
    click(tp.btn_save)
    s2 = S.BizcardStore(db)
    notes = P.todo_notes(s2, gid)
    s2.close()
    chk(len(notes) == 3 and notes[0]["done"] and notes[0]["tags"] == ["report", "submit"] and not notes[1]["done"],
        "C 체크·해시태그도 새 기록에(옛 기록 그대로)", repr([(n["done"], n["tags"]) for n in notes]))
    click(tp.btn_prev)
    click(tp.btn_del)                                    # 가운데(2번째) 기록 지우기
    s2 = S.BizcardStore(db)
    notes = P.todo_notes(s2, gid)
    s2.close()
    chk(len(notes) == 2 and [n["body"] for n in notes] == ["첫 내용 고침", "첫 내용"], "C [삭제] = 보던 기록 하나만",
        repr([n["body"] for n in notes]))

    print("\n=== A2. 할 일 탭이 아니면 ===")
    i_fav = next(i for i in range(dlg.fav_tabs.count()) if dlg.fav_tabs.tabData(i) not in (gid, g_old, FD.RECENT))
    click_pt = dlg.fav_tabs.tabRect(i_fav).center()
    QTest.mouseClick(dlg.fav_tabs, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, click_pt)
    pump(None)
    chk(not tp.isVisible() and dlg.fav.width() > fav_w_todo + 100, "A2 즐겨찾기 탭이면 할 일 칸 숨김·사람 칸이 끝까지",
        "%s %d %d" % (tp.isVisible(), dlg.fav.width(), fav_w_todo))

    print("\n=== D. 할 일 고치기·엑셀 ===")
    dlg.todo_edit(gid, {"title": "가짜 보고서", "memo": "창에서 고친 내용", "start": D(-3), "end": D(20)})
    s2 = S.BizcardStore(db)
    notes = P.todo_notes(s2, gid)
    s2.close()
    chk(notes and notes[0]["body"] == "창에서 고친 내용" and len(notes) == 3, "D 할 일 고치기 창에서 내용을 바꾸면 새 기록",
        repr([n["body"] for n in notes]))
    out = TMP / "할일.xlsx"
    dlg.export_todos(str(out))
    pump(lambda: getattr(dlg, "last_todo_export", None) is not None, timeout=20)
    from openpyxl import load_workbook
    ws = load_workbook(str(out)).active
    rows = [[(c.value or "") for c in r] for r in ws.iter_rows()]
    hi = rows[0].index("해시태그") if "해시태그" in rows[0] else -1
    r_rep = next((r for r in rows[1:] if r[3] == "가짜 보고서"), None)
    chk(hi == 5 and r_rep is not None and r_rep[hi] == "#report #submit",
        "D 엑셀 '해시태그' 열 = 최신 기록의 태그(창에서 내용만 고친 새 기록은 앞 기록의 태그를 이어받음)",
        repr((rows[0], r_rep)))
    dlg.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "예외 없이 끝남")
finish()
