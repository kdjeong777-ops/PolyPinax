# -*- coding: utf-8 -*-
"""할 일 엑셀로 내보내기 (명함 SOT §5.24.2 '할 일 엑셀', 261120-21) — 가짜 명함·가짜 할 일만(명함 SOT §2.1).

오프스크린, 실제 설정·데이터 폴더를 쓰지 않는다(검사 작성 SOT §14.7.2). 파일은 임시 폴더에만.
A. 탭 메뉴에 '할 일 엑셀로 내보내기'(할 일이 있을 때만) — 실제 메뉴 항목을 눌러(저장 자리 묻기는 임시 경로로) 배경에서 씀
B. 모든 할 일(마감·기간 밖 포함)이 기간 차례, 상태 칸, 머리말
C. 명단 한 사람이 한 줄, 할 일 칸은 명단 줄에 걸쳐 합침, 휴대폰은 적을 꼴, 명단 없는 할 일도 한 줄, 종료일 없으면 '계속'
"""
import os, sys, tempfile, time, datetime
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMenu, QFileDialog, QMessageBox
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_todoxlsx_%d" % os.getpid())
fails = []
TMP = Path(tempfile.mkdtemp(prefix="bizcard_todoxlsx_"))
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
    P.apply_import(st, [{"name": "홍길동", "company": "가나다", "title": "부장", "phones": [("cell", "01000000001")],
                         "emails": ["hong@example.com"], "urls": []},
                        {"name": "김철수", "company": "라마바", "phones": [("cell", "010-0000-0002")], "emails": [], "urls": []}],
                   "주소록", "google")
    ids = [r[0] for r in st.con.execute("SELECT id FROM cards ORDER BY id").fetchall()]
    P.fav_init(st, "즐겨찾기")
    today = datetime.date.today()
    d = lambda n: (today + datetime.timedelta(days=n)).isoformat()
    g_live = P.todo_add(st, {"title": "가짜 진행", "memo": "첫 줄\n둘째 줄", "start": d(-3), "end": ""}, ids, "…")
    g_soon = P.todo_add(st, {"title": "가짜 예정", "memo": "", "start": d(10), "end": d(20)}, [ids[0]], "…")
    g_past = P.todo_add(st, {"title": "가짜 지남", "memo": "", "start": d(-30), "end": d(-20)}, [], "…")
    g_closed = P.todo_add(st, {"title": "가짜 마감", "memo": "", "start": d(-5), "end": d(5)}, [ids[1]], "…")
    P.fav_close(st, g_closed)
    st.close()
    out = TMP / "out" / "할일.xlsx"
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(out), ""))
    QMessageBox.exec = lambda self: 0
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    menus = []
    QMenu.exec = lambda self, *a, **k: menus.append(self) or None

    from viewer.widgets import bizcard_find_dialog as FD
    dlg = FD.BizcardFindDialog(None, db=db)
    dlg.show()
    pump(lambda: dlg.table.rowCount() >= 2)
    tb = dlg.fav_tabs
    pos = tb.tabRect(0).center()
    dlg._fav_tab_menu(pos)
    m = menus[-1] if menus else None
    act = next((a for a in (m.actions() if m else []) if a.text() == "할 일 엑셀로 내보내기"), None)
    chk(act is not None, "A 탭 메뉴에 '할 일 엑셀로 내보내기'", repr([a.text() for a in (m.actions() if m else [])]))
    if act is not None:
        act.trigger()
    chk(pump(lambda: getattr(dlg, "last_todo_export", None) is not None, timeout=20), "A 배경에서 다 씀")
    chk(out.exists() and not Path(str(out) + ".part").exists(), "A 고른 자리에 .xlsx (임시 파일 안 남음)")

    from openpyxl import load_workbook
    wb = load_workbook(str(out)) if out.exists() else None
    ws = wb.active if wb else None
    if ws is not None:
        rows = [[(c.value if c.value is not None else "") for c in r] for r in ws.iter_rows()]
        print("=== B. 차례·상태 ===")
        chk(rows[0] == ["시작일", "종료일", "상태", "제목", "내용", "해시태그", "이름", "회사", "직함", "휴대폰", "메일"], "B 머리말", repr(rows[0]))
        titles = [r[3] for r in rows[1:] if r[3]]
        chk(titles == ["가짜 지남", "가짜 마감", "가짜 진행", "가짜 예정"],"B 모든 할 일이 기간(시작일) 차례 — 마감·기간 밖 포함", repr(titles))
        state = {r[3]: r[2] for r in rows[1:] if r[3]}
        chk(state == {"가짜 지남": "기간 지남", "가짜 진행": "진행", "가짜 마감": "마감", "가짜 예정": "예정"}, "B 상태 칸", repr(state))
        chk(ws.freeze_panes == "A2" and ws.cell(1, 1).font.bold, "B 머리말 굵게·고정")
        print("\n=== C. 명단 줄·합친 칸 ===")
        i_live = next(i for i, r in enumerate(rows) if r[3] == "가짜 진행")
        live_people = [rows[i_live][6], rows[i_live + 1][6]]
        chk(live_people == ["홍길동", "김철수"] and rows[i_live + 1][3] == "", "C 명단 한 사람이 한 줄(할 일 칸은 첫 줄에만)",
            repr(live_people))
        merged = [str(r) for r in ws.merged_cells.ranges]
        chk("D%d:D%d" % (i_live + 1, i_live + 2) in merged, "C 할 일 칸은 명단 줄에 걸쳐 합침", repr(merged[:6]))
        chk(rows[i_live][1] == "계속" and rows[i_live][4] == "첫 줄\n둘째 줄", "C 종료일 없으면 '계속', 내용 줄바꿈 그대로")
        chk(rows[i_live][9] == "010-0000-0001" and rows[i_live][10] == "hong@example.com" and rows[i_live][8] == "부장",
            "C 휴대폰은 적을 꼴, 메일·직함", repr(rows[i_live][8:]))
        i_past = next(i for i, r in enumerate(rows) if r[3] == "가짜 지남")
        chk(rows[i_past][6] == "" and (i_past + 1 >= len(rows) or rows[i_past + 1][3] != ""), "C 명단 없는 할 일도 한 줄")
    dlg.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "예외 없이 끝남")
finish()
