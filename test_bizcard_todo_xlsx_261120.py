# -*- coding: utf-8 -*-
"""할 일 내보내기 — 고른 탭 하나를 엑셀·Word 로 (명함 SOT §5.24.2 '할 일 내보내기', 261120-42 — 종전 261120-21 '모든 할 일 엑셀'을 바꿈).
가짜 명함·가짜 할 일만(명함 SOT §2.1). 오프스크린, 실제 설정·데이터 폴더를 쓰지 않는다(검사 작성 SOT §14.7.2). 파일은 임시 폴더에만.

A. 탭 줄 `+` 바로 오른쪽에 엑셀·워드 아이콘 단추(아이콘 있음)
B. 탭 메뉴 — 할 일 탭은 '할 일 내보내기 ▸ 엑셀·Word', 보통 탭은 '명단 내보내기 ▸', 종전 '할 일 엑셀로 내보내기'(모든 할 일)는 없음
C. 할 일 탭을 엑셀 단추로(실제 클릭) — 그 탭만, 시트 '할 일'(제목·기간·상태·해시태그·할 일 표 최신 기록 먼저·수정일 칸 합침)·'명단'(휴대폰 꼴)
D. 같은 탭을 메뉴 'Word' 로 — 제목·머리 줄·할 일 표·명단 표, 한글 글꼴 eastAsia
E. 보통 탭은 명단만(엑셀 시트 하나·Word 표 하나), 다른 탭 할 일은 안 들어감
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
from PyQt6.QtTest import QTest
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


def wait_export(dlg):
    dlg.last_tab_export = None
    return pump(lambda: getattr(dlg, "last_tab_export", None) is not None, timeout=20)


def menu_texts(m):
    return [a.text() for a in m.actions()] if m else []


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
    g_todo = P.todo_add(st, {"title": "가짜 진행", "memo": "", "start": d(-3), "end": ""}, ids, "…")
    P.note_add(st, g_todo, {"items": [{"done": True, "due": d(-2), "text": "옛 줄"}], "tags": []}, d(-2))
    time.sleep(0.01)
    P.note_add(st, g_todo, {"items": [{"done": True, "due": d(-1), "text": "첫 줄"},
                                      {"done": False, "due": d(2), "text": "둘째 줄"}], "tags": ["가짜태그"]}, d(0))
    g_other = P.todo_add(st, {"title": "가짜 다른 일", "memo": "다른 내용", "start": d(1), "end": d(5)}, [ids[1]], "…")
    g_fav = P.fav_add_group(st, "가짜 모임")
    P.fav_add(st, g_fav, [ids[1]], ongoing="…")
    st.close()
    out = {}
    QFileDialog.getSaveFileName = staticmethod(lambda _p, _t, start, filt="", *a, **k: (str(out["next"]), ""))
    QMessageBox.exec = lambda self: 0
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    menus = []
    QMenu.exec = lambda self, *a, **k: menus.append(self) or None

    from viewer.widgets import bizcard_find_dialog as FD
    dlg = FD.BizcardFindDialog(None, db=db)
    dlg.show()
    pump(lambda: dlg.table.rowCount() >= 2)
    tb = dlg.fav_tabs

    def tab_of(gid):
        return next(i for i in range(tb.count()) if tb.tabData(i) == gid)

    print("=== A. 탭 줄 아이콘 단추 ===")
    bx, bw = getattr(dlg, "btn_export", {}).get("xlsx"), getattr(dlg, "btn_export", {}).get("docx")
    chk(bx is not None and bw is not None and not bx.icon().isNull() and not bw.icon().isNull(), "A 엑셀·워드 아이콘 단추")
    if bx is not None:
        pump(None)
        gx = lambda w: w.mapTo(dlg, w.rect().topLeft()).x()
        plus_r = gx(dlg.btn_fav_tab) + dlg.btn_fav_tab.width()
        fav_r = lambda: gx(dlg.fav) + dlg.fav.width()           # 탭 내용 창(명단 칸) 오른쪽 끝
        w_r = lambda: gx(bw) + bw.width()
        chk(plus_r < gx(bx) < gx(bw) and abs(w_r() - fav_r()) <= 6 and gx(bx) - plus_r > 12 and bx.isVisible(),
            "A 엑셀·워드는 탭 내용 창 폭 오른쪽 끝(261120-47)", "+끝 %d 엑셀 %d 워드끝 %d 명단끝 %d" % (plus_r, gx(bx), w_r(), fav_r()))
        dlg.resize(dlg.width() + 240, dlg.height())
        pump(None)
        chk(abs(w_r() - fav_r()) <= 6, "A 창 크기를 바꿔도 오른쪽 끝을 따라감", "워드끝 %d 명단끝 %d" % (w_r(), fav_r()))

    print("\n=== B. 탭 메뉴 ===")
    dlg._fav_tab_menu(tb.tabRect(tab_of(g_todo)).center())
    m = menus[-1] if menus else None
    texts = menu_texts(m)
    sub = next((a.menu() for a in (m.actions() if m else []) if a.text() == "할 일 내보내기"), None)
    chk(sub is not None and menu_texts(sub) == ["엑셀", "Word"], "B 할 일 탭 메뉴 '할 일 내보내기 ▸ 엑셀·Word'", repr(texts))
    chk("할 일 엑셀로 내보내기" not in texts, "B 종전 '할 일 엑셀로 내보내기'(모든 할 일)는 없음")
    dlg._fav_tab_menu(tb.tabRect(tab_of(g_fav)).center())
    m2 = menus[-1]
    chk(any(a.text() == "명단 내보내기" and a.menu() is not None for a in m2.actions()), "B 보통 탭은 '명단 내보내기 ▸'",
        repr(menu_texts(m2)))

    print("\n=== C. 할 일 탭 → 엑셀(아이콘 단추 클릭) ===")
    tb.setCurrentIndex(tab_of(g_todo))
    pump(None)
    out["next"] = TMP / "out" / "할일.xlsx"
    if bx is not None:
        QTest.mouseClick(bx, Qt.MouseButton.LeftButton)
    chk(wait_export(dlg) and dlg.last_tab_export[0], "C 배경에서 다 씀")
    x1 = out["next"]
    chk(x1.exists() and not Path(str(x1) + ".part").exists(), "C 고른 자리에 .xlsx (임시 파일 안 남음)")
    from openpyxl import load_workbook
    wb = load_workbook(str(x1)) if x1.exists() else None
    if wb is not None:
        chk(wb.sheetnames == ["할 일", "명단"], "C 시트 '할 일'·'명단'", repr(wb.sheetnames))
        ws = wb["할 일"]
        rows = [[(c.value if c.value is not None else "") for c in r] for r in ws.iter_rows()]
        flat = "\n".join("|".join(str(v) for v in r) for r in rows)
        chk(rows[0][0] == "가짜 진행" and ws.cell(1, 1).font.bold, "C 첫 줄 제목(굵게)", repr(rows[0]))
        chk(["기간", "%s ~ 계속" % d(-3)] == rows[1][:2] and rows[2][:2] == ["상태", "진행"] and rows[3][:2] == ["해시태그", "#가짜태그"],
            "C 기간(끝 없으면 '계속')·상태·해시태그(최신 기록)", repr(rows[1:4]))
        hi = next(i for i, r in enumerate(rows) if r[:4] == ["수정일", "완료", "기한", "내용"])
        body = [r[:4] for r in rows[hi + 1:]]
        chk(body == [[d(0), "☑", d(-1), "첫 줄"], ["", "☐", d(2), "둘째 줄"], [d(-2), "☑", d(-2), "옛 줄"]],
            "C 할 일 표 — 최신 기록 먼저, 지난 기록 아래(수정일·완료·기한·내용)", repr(body))
        merged = [str(r) for r in ws.merged_cells.ranges]
        chk("A%d:A%d" % (hi + 2, hi + 3) in merged, "C 한 기록의 수정일 칸은 그 줄들에 걸쳐 합침", repr(merged))
        chk(ws.freeze_panes == "A%d" % (hi + 2) and ws.cell(hi + 1, 1).font.bold, "C 할 일 표 머리말 굵게·고정")
        chk("다른 내용" not in flat and "가짜 다른 일" not in flat, "C 그 탭만 — 다른 할 일은 안 들어감")
        wp = wb["명단"]
        prow = [[(c.value if c.value is not None else "") for c in r] for r in wp.iter_rows()]
        chk(prow[0] == ["이름", "회사", "직함", "휴대폰", "메일"], "C 명단 머리말", repr(prow[0]))
        chk(prow[1:] == [["홍길동", "가나다", "부장", "010-0000-0001", "hong@example.com"],
                         ["김철수", "라마바", "", "010-0000-0002", ""]], "C 명단 줄(휴대폰은 적을 꼴, 명단 차례)", repr(prow[1:]))

    print("\n=== D. 같은 탭 → 메뉴 'Word' ===")
    out["next"] = TMP / "out" / "할일.docx"
    dlg._fav_tab_menu(tb.tabRect(tab_of(g_todo)).center())
    sub = next((a.menu() for a in menus[-1].actions() if a.text() == "할 일 내보내기"), None)
    act = next((a for a in (sub.actions() if sub else []) if a.text() == "Word"), None)
    dlg.last_tab_export = None
    if act is not None:
        act.trigger()
    chk(pump(lambda: getattr(dlg, "last_tab_export", None) is not None, timeout=20) and dlg.last_tab_export[0],
        "D 메뉴 'Word' 로 배경에서 다 씀")
    w1 = out["next"]
    if w1.exists():
        from docx import Document
        doc = Document(str(w1))
        paras = [p.text for p in doc.paragraphs if p.text.strip()]
        chk(paras[:4] == ["가짜 진행", "기간: %s ~ 계속" % d(-3), "상태: 진행", "해시태그: #가짜태그"],
            "D 제목·기간·상태·해시태그 줄", repr(paras[:4]))
        tabs = [[[c.text for c in r.cells] for r in t.rows] for t in doc.tables]
        chk(len(tabs) == 2 and tabs[0] == [["수정일", "완료", "기한", "내용"], [d(0), "☑", d(-1), "첫 줄"],
                                            ["", "☐", d(2), "둘째 줄"], [d(-2), "☑", d(-2), "옛 줄"]],
            "D 할 일 표(최신 기록 먼저)", repr(tabs[:1]))
        chk(len(tabs) == 2 and tabs[1][1] == ["홍길동", "가나다", "부장", "010-0000-0001", "hong@example.com"], "D 명단 표",
            repr(tabs[1:]))
        from docx.oxml.ns import qn
        rf = doc.paragraphs[0].runs[0]._element.rPr.find(qn("w:rFonts"))
        chk(rf is not None and rf.get(qn("w:eastAsia")) == "맑은 고딕", "D 한글 글꼴 eastAsia 도 맑은 고딕")
    else:
        chk(False, "D .docx 가 생김")

    print("\n=== E. 보통 탭은 명단만 ===")
    tb.setCurrentIndex(tab_of(g_fav))
    pump(None)
    out["next"] = TMP / "out" / "모임.xlsx"
    if bx is not None:
        QTest.mouseClick(bx, Qt.MouseButton.LeftButton)
    wait_export(dlg)
    wb2 = load_workbook(str(out["next"])) if out["next"].exists() else None
    chk(wb2 is not None and wb2.sheetnames == ["명단"] and wb2["명단"].max_row == 2
        and wb2["명단"].cell(2, 1).value == "김철수", "E 엑셀은 '명단' 시트 하나(그 탭 사람만)")
    out["next"] = TMP / "out" / "모임.docx"
    if bw is not None:
        QTest.mouseClick(bw, Qt.MouseButton.LeftButton)
    wait_export(dlg)
    if out["next"].exists():
        from docx import Document
        doc2 = Document(str(out["next"]))
        chk(len(doc2.tables) == 1 and doc2.paragraphs[0].text == "가짜 모임", "E Word 는 탭 이름 + 명단 표 하나")
    else:
        chk(False, "E .docx 가 생김")
    dlg.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "예외 없이 끝남")
finish()
