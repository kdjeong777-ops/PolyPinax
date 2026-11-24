# -*- coding: utf-8 -*-
"""명함찾기 할 일 칸 — 탭 줄 오른쪽 (명함찾기 SOT §5.24.10, 261120-34·-39) — 가짜 명함·가짜 할 일만(명함 SOT §2.1).

오프스크린, 실제 설정·데이터 폴더를 쓰지 않는다(검사 작성 SOT §14.7.2). 실제 클릭·키·한글 입력.
A. 배치 — 할 일 탭이면 위 띠 오른쪽에 할 일 칸(폭 = 사진창), 명함 그림 위 끝 = 세부내용 위 끝, 해시태그 칸은 제목 오른쪽 같은 줄,
   할 일 탭이 아니면 칸 숨김·사람 칸이 끝까지
B. 줄 — 빈 자리를 누르면 새 줄(☐ · 오늘 · 글), Enter = 아래 새 줄, 빈 줄 Backspace = 지움, 체크하면 줄긋기, 날짜는 탭 기간 안
C. 기록 — 고쳐 [저장] = 새 기록(옛 기록 그대로), ◀▶, [삭제] = 보던 기록 하나, 탭 '내용' = 줄 글
D. 옛 할 일·옛 기록(-34 꼴: 내용 + 했음·끝 날짜) → 줄마다 한 항목, 할 일 고치기 창 → 새 기록, 엑셀 '내용' 칸에 줄
"""
import os, sys, tempfile, time, datetime, json
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


def click(w, pos=None):
    if pos is None:
        QTest.mouseClick(w, Qt.MouseButton.LeftButton)
    else:
        QTest.mouseClick(w, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pos)
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
                           ("가짜 옛 할 일", pos, "옛 첫 줄\n\n옛 둘째 줄", D(-10), D(10))).lastrowid
    st.con.commit()
    P.fav_init(st, "즐겨찾기")
    old_notes = P.todo_notes(st, g_old)
    chk(len(old_notes) == 1 and [i["text"] for i in old_notes[0]["items"]] == ["옛 첫 줄", "옛 둘째 줄"]
        and old_notes[0]["made"] == D(-10), "D 옛 할 일 내용 → 첫 기록, 줄마다 한 항목(빈 줄 버림)", repr(old_notes))
    P.fav_init(st, "즐겨찾기")
    chk(len(P.todo_notes(st, g_old)) == 1, "D 옮기기는 한 번만")
    # -34 꼴 기록(줄 목록 없음, 했음·끝 날짜) → 줄마다 체크 = 했음, 날짜 = 끝 날짜
    st.con.execute("INSERT INTO todo_notes(group_id, made, body, done, n_start, n_end, tags, ts) VALUES(?,?,?,?,?,?,?,?)",
                   (g_old, D(-1), "가짜 끝낸 일", 1, D(-5), D(3), "[]", time.time()))
    st.con.commit()
    it0 = P.todo_notes(st, g_old)[0]["items"]
    chk(it0 == [{"done": True, "due": D(3), "text": "가짜 끝낸 일"}], "D -34 꼴 기록 → 체크 = 했음·날짜 = 끝 날짜", repr(it0))
    gid = P.todo_add(st, {"title": "가짜 보고서", "memo": "첫 내용", "start": D(-3), "end": D(20)}, ids, "…")
    chk(len(P.todo_notes(st, gid)) == 1 and P.todo_notes(st, gid)[0]["items"][0]["text"] == "첫 내용",
        "D 새 할 일의 처음 내용 = 기록 하나·줄 하나")
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
    chk(abs(x_tp - x_ph) <= 3 and abs(tp.width() - dlg.photo_split.width()) <= 3, "A 할 일 칸 폭·자리 = 사진창")
    yt = tp.lbl_title.mapTo(tp, QPoint(0, tp.lbl_title.height() // 2)).y()
    yg = tp.ed_tags.mapTo(tp, QPoint(0, tp.ed_tags.height() // 2)).y()
    xt = tp.lbl_title.mapTo(tp, QPoint(tp.lbl_title.width(), 0)).x()
    xg = tp.ed_tags.mapTo(tp, QPoint(0, 0)).x()
    chk(abs(yt - yg) <= 4 and xg >= xt, "A 해시태그 칸은 제목 오른쪽 같은 줄", "%d %d %d %d" % (yt, yg, xt, xg))
    chk(not hasattr(tp, "chk_done") and not hasattr(tp, "d_start"), "A '했음'·기한 시작/끝 줄 없음")
    fav_w_todo = dlg.fav.width()

    print("\n=== B. 줄 ===")
    chk(len(tp.rows) == 1 and tp.rows[0].text.text() == "첫 내용" and not tp.btn_save.isEnabled(), "B 최신 기록의 줄·바꾼 것 없으면 [저장] 꺼짐")
    click(tp.click_area)
    chk(len(tp.rows) == 2 and tp.rows[1].date.date().toString("yyyy-MM-dd") == TODAY.isoformat() and not tp.rows[1].chk.isChecked()
        and tp.rows[1].text.hasFocus(), "B 빈 자리를 누르면 새 줄(☐ · 오늘) — 커서는 그 줄 글")
    type_ko(tp.rows[1].text, "테스트 실행")
    QTest.keyClick(tp.rows[1].text, Qt.Key.Key_Return)
    pump(None)
    chk(len(tp.rows) == 3 and tp.rows[2].text.hasFocus() and tp.rows[2].text.text() == "", "B Enter = 아래 새 줄")
    QTest.keyClick(tp.rows[2].text, Qt.Key.Key_Backspace)
    pump(None)
    chk(len(tp.rows) == 2 and tp.rows[1].text.hasFocus(), "B 빈 줄 Backspace = 그 줄 지움, 커서는 윗줄")
    QTest.keyClick(tp.rows[1].text, Qt.Key.Key_Up)
    chk(tp.rows[0].text.hasFocus(), "B ↑ = 윗줄")
    click(tp.rows[0].chk)
    chk(tp.rows[0].text.font().strikeOut(), "B 체크하면 그 줄 글에 줄긋기")
    chk(tp.rows[1].date.minimumDate().toString("yyyy-MM-dd") == D(-3) and tp.rows[1].date.maximumDate().toString("yyyy-MM-dd") == D(20),
        "B 줄 날짜는 탭 기간 안(날짜 칸 최소·최대)")

    print("\n=== C. 기록 ===")
    tp.ed_tags.setFocus()
    QTest.keyClicks(tp.ed_tags, "#report submit")
    chk(tp.btn_save.isEnabled(), "C 고치면 [저장] 켜짐")
    click(tp.btn_save)
    s2 = S.BizcardStore(db)
    notes = P.todo_notes(s2, gid)
    memo = P.todo_info(s2, gid)["memo"]
    raw = s2.con.execute("SELECT items FROM todo_notes WHERE id=?", (notes[0]["id"],)).fetchone()[0]
    s2.close()
    chk(len(notes) == 2 and [(i["done"], i["text"]) for i in notes[0]["items"]] == [(True, "첫 내용"), (False, "테스트 실행")]
        and [i["text"] for i in notes[1]["items"]] == ["첫 내용"] and notes[0]["tags"] == ["report", "submit"]
        and notes[0]["made"] == TODAY.isoformat(), "C [저장] = 오늘 새 기록(줄·체크·태그), 옛 기록 그대로", repr(notes))
    chk(isinstance(json.loads(raw), list) and "☐" not in json.dumps(json.loads(raw), ensure_ascii=False),
        "C 저장은 줄 데이터(글에 기호를 섞지 않음)")
    chk(memo == "☑ %s 첫 내용\n☐ %s 테스트 실행" % (D(-3) if False else notes[0]["items"][0]["due"], TODAY.isoformat()),
        "C 탭 '내용' = 줄 글(☑/☐ 날짜 글)", repr(memo))
    chk(tp.lbl_pos.text() == "1/2" and tp.btn_prev.isEnabled() and not tp.btn_next.isEnabled(), "C 최신에서 ◀ 만 켜짐")
    click(tp.btn_prev)
    chk([r.text.text() for r in tp.rows] == ["첫 내용"] and tp.lbl_pos.text() == "2/2", "C ◀ = 이전 기록")
    click(tp.btn_del)
    s2 = S.BizcardStore(db)
    notes = P.todo_notes(s2, gid)
    s2.close()
    chk(len(notes) == 1 and notes[0]["items"][1]["text"] == "테스트 실행", "C [삭제] = 보던 기록 하나만")

    print("\n=== A2. 할 일 탭이 아니면 ===")
    i_fav = next(i for i in range(dlg.fav_tabs.count()) if dlg.fav_tabs.tabData(i) not in (gid, g_old, FD.RECENT))
    QTest.mouseClick(dlg.fav_tabs, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, dlg.fav_tabs.tabRect(i_fav).center())
    pump(None)
    chk(not tp.isVisible() and dlg.fav.width() > fav_w_todo + 100, "A2 즐겨찾기 탭이면 할 일 칸 숨김·사람 칸이 끝까지")

    print("\n=== D. 할 일 고치기·엑셀 ===")
    dlg.todo_edit(gid, {"title": "가짜 보고서", "memo": "창에서 고친 내용", "start": D(-3), "end": D(20)})
    s2 = S.BizcardStore(db)
    notes = P.todo_notes(s2, gid)
    s2.close()
    chk(notes and [i["text"] for i in notes[0]["items"]] == ["창에서 고친 내용"] and notes[0]["tags"] == ["report", "submit"],
        "D 할 일 고치기 창에서 내용을 바꾸면 새 기록(글 → 줄, 태그 이어받음)", repr(notes[:1]))
    out = TMP / "할일.xlsx"
    dlg.last_tab_export = None
    dlg.export_tab(g_old, "xlsx", str(out))              # 탭 하나 내보내기(261120-42)
    pump(lambda: getattr(dlg, "last_tab_export", None) is not None, timeout=20)
    from openpyxl import load_workbook
    ws = load_workbook(str(out))["할 일"]
    rows = [[(c.value or "") for c in r] for r in ws.iter_rows()]
    r_old = next((r for r in rows if "가짜 끝낸 일" in r), None)
    chk(r_old is not None and r_old[1:4] == ["☑", D(3), "가짜 끝낸 일"],
        "D 내보낸 할 일 표 = 옛 기록도 줄(완료 ☑·기한 = 옛 끝 날짜·글)", repr(r_old))
    dlg.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "예외 없이 끝남")
finish()
