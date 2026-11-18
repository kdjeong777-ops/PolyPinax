# -*- coding: utf-8 -*-
"""명함찾기 창 (명함 SOT §5.9, P4) — 가짜 명함만(010-0000-xxxx, 명함 SOT §2.1).

실제 MainWindow 로(오프스크린, 실제 설정·데이터 폴더를 쓰지 않는다 — 검사 작성 SOT §14.7.2).
A. 찾기 모듈 — 낱말 일부('도로' → '가나도로공사'), 낱말 여럿은 모두, #태그, 기간, LIKE 특수 글자
B. 메뉴 `명함 ▾` → `명함찾기…` 로 창(하나만), 글을 치면 250ms 뒤 결과, 기간 콤보
C. 인물 사진 — 배경에서 `인물` 폴더의 `<정리본 이름>.jpg`, EXIF 뺌·방향 반영, 둘째는 ` (2)`
D. 고쳐 저장(실제 키 입력·단추) — 이름·회사가 바뀌면 정리본·뒷면·인물 사진 이름이 바뀌고 DB·#회사 태그가 따라감, 메모만 바꾸면 이름 그대로
E. 저장 안 한 고침 — 다른 줄을 고르면 묻는다(버리기면 안 남음)
F. 책갈피창 이름 바꾸기 한 길(`_rename_bg` → `_after_rename`)로 정리본 이름을 바꾸면 명함 DB 가 따라감(배경)
G. vCard 로 내보내기(고른 명함), 메인 정지 < 1초
H. 텍스트 창 명함 메모 칸
I. 명함찾기 개편(명함 SOT §5.24) — 명함 폴더가 비면 `명함` 단추 숨김, 머리말 정렬, 앞↔뒤 단추, 체크한 칸 복사(기억),
   즐겨찾기 탭(여러 명 넣기·빼기·차례·탭 더하기/이름/지우기·그림), 인물 사진 차례 = 파일 이름·지우기 = 휴지통,
   해시태그(DB·파일, #찾기, 저장해도 남음), 주소록 vCard 가져오기(합치기·그림 없는 명함)·리멤버용 내보내기,
   주소록 우선순위(리멤버 > 구글, 명함·손 고침은 덮지 않음), 목록에서 지우기, 처음 너비(I11), '해시태그 수정' 창(I12)
"""
import os, sys, tempfile, time, datetime
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QTimer
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtTest import QTest
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_find_%d" % os.getpid())
fails = []
TMP = Path(tempfile.mkdtemp(prefix="bizcard_p4_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def pump(cond=None, timeout=15.0):
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
    """한글 입력 — IME 처럼 QInputMethodEvent(검사 작성 SOT §14.7.2 의 24: keyClicks 한글은 프로세스가 죽는다)."""
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
    from viewer.bizcard import people as P
except Exception as e:                       # 이 판 전 코드엔 모듈이 없다
    chk(False, "명함찾기 모듈을 불러온다", repr(e))
    finish()
from viewer.bizcard import importer as I, store as S, apply as AP
from PIL import Image

try:
    def jpg(p, color="white", size=(339, 186)):
        Image.new("RGB", size, color).save(p, quality=90)
    F = TMP / "cards"
    F.mkdir()
    jpg(F / "a_1.jpg"); jpg(F / "a_2.jpg", "lightblue"); jpg(F / "b_1.jpg", "ivory"); jpg(F / "c_1.jpg", "lavender")
    items = {it.base: it for it in I.scan_folder(F)}
    OUT = F / "정리"
    rows = [
        {"key": items["a"].key, "front": items["a"].front, "back": items["a"].back, "pdf": "", "keep_back": True,
         "name": "홍길동", "company": "가나도로공사", "title": "부장", "langs": ["한글"],
         "phones": [("cell", "010-0000-0001"), ("work", "02-0000-0002")], "emails": ["hong@example.com"]},
        {"key": items["b"].key, "front": items["b"].front, "back": "", "pdf": "", "keep_back": False,
         "name": "김철수", "company": "라마바", "title": "대리", "langs": ["한글"], "phones": [("cell", "010-0000-0003")]},
        {"key": items["c"].key, "front": items["c"].front, "back": "", "pdf": "", "keep_back": False,
         "name": "이영희", "company": "사아자_100%", "langs": ["한글"], "phones": [("cell", "010-0000-0004")]},
    ]
    AP.apply_cards(rows, OUT)
    st = S.BizcardStore()
    today = datetime.date.today()
    st.con.execute("UPDATE cards SET scanned=?, memo=? WHERE name='홍길동'", (today.isoformat(), "골프 모임"))
    st.con.execute("UPDATE cards SET scanned=? WHERE name='김철수'", ((today - datetime.timedelta(days=60)).isoformat(),))
    st.con.execute("UPDATE cards SET scanned='2020-01-01' WHERE name='이영희'")
    st.con.commit()

    print("=== A. 찾기 모듈 ===")
    names = lambda rs: sorted(r["name"] for r in rs)
    chk(names(P.find(st, "도로")) == ["홍길동"], "A 낱말 일부 — '도로' 로 '가나도로공사'")
    chk(names(P.find(st, "골프")) == ["홍길동"] and names(P.find(st, "0000-0003")) == ["김철수"], "A 메모·전화 번호 일부")
    chk(names(P.find(st, "홍 라마바")) == [] and names(P.find(st, "홍 도로")) == ["홍길동"], "A 낱말 여럿은 모두 들어 있어야")
    chk(names(P.find(st, "#라마바")) == ["김철수"] and names(P.find(st, "#없는태그")) == [], "A #태그 거르기")
    chk(names(P.find(st, "100%")) == ["이영희"] and names(P.find(st, "%")) == ["이영희"], "A LIKE 특수 글자(%)는 글자 그대로")
    chk(names(P.find(st, "", P.since_for("1m"))) == ["홍길동"] and names(P.find(st, "", P.since_for("1y"))) == ["김철수", "홍길동"],
        "A 기간 — 최근 1개월·1년")
    chk(names(P.find(st, "", "2019-12-31", "2020-01-01")) == ["이영희"], "A 기간 직접(끝 날짜 포함)")
    chk([r["name"] for r in P.find(st, "")][:1] == ["홍길동"], "A 스캔일 최근 먼저")
    st.close()

    print("\n=== A2. 옛 명함 DB(즐겨찾기·주소록 출처 표 없음)로 열기 ===")
    import sqlite3 as _sq
    from viewer import dbutil
    old_db = TMP / "old_bizcard.db"
    con = dbutil.connect(old_db, dbutil.BUSY_MS_BG)
    con.executescript("CREATE TABLE cards(id INTEGER PRIMARY KEY, front TEXT UNIQUE NOT NULL, back TEXT, src_key TEXT, src_pdf TEXT, "
                      "name TEXT, company TEXT, title TEXT, phones TEXT, emails TEXT, urls TEXT, address TEXT, en TEXT, memo TEXT, "
                      "tags TEXT, scanned TEXT, top1 INTEGER, created REAL, updated REAL);"
                      "CREATE VIRTUAL TABLE cards_fts USING fts5(body, tokenize='unicode61');"
                      "INSERT INTO cards(front, name, phones, emails, urls, tags, en) VALUES('c:\\x\\a.jpg', '옛사람', '[]', '[]', '[]', '[]', '{}');")
    con.commit(); con.close()
    try:
        ost = S.BizcardStore(old_db)
        oid = ost.con.execute("SELECT id FROM cards").fetchone()[0]
        ok_old = P.field_srcs(ost, oid) == {}            # 출처 표가 아직 없어도
        ost.delete_card(oid)                              # 즐겨찾기·출처 표 없이 지우기
        P.fav_init(ost, "즐겨찾기")
        ok_old = ok_old and len(P.fav_groups(ost)) == 1 and ost.count() == 0
        ost.close()
        con = dbutil.connect(old_db, dbutil.BUSY_MS_BG)  # 옛 판이 새 DB 를 읽는 꼴 — cards 는 그대로
        ok_old = ok_old and [r[1] for r in con.execute("PRAGMA table_info(cards)")][:3] == ["id", "front", "back"]
        con.close()
    except Exception as e:
        ok_old = False
        print(repr(e))
    chk(ok_old, "A2 옛 DB 를 열어도 깨지지 않음(새 표는 CREATE IF NOT EXISTS, cards 열은 그대로)")

    print("\n=== B. 메뉴·창 ===")
    from viewer.app import MainWindow
    import modal_guard
    modal_guard.install(label=lambda: "명함찾기", echo=False)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    mw = MainWindow(); mw._skip_save_on_close = True
    mw.show()
    pump(timeout=1.0)
    from PyQt6.QtGui import QAction
    acts = [a for a in mw.findChildren(QAction) if a.text().replace("…", "...") == "명함찾기..."]
    chk(bool(acts), "B 도구 탭 `명함 ▾` 에 `명함찾기…`")
    gaps, last = [], [time.monotonic()]

    def beat():
        now = time.monotonic(); gaps.append(now - last[0]); last[0] = now
    hb = QTimer(); hb.timeout.connect(beat); hb.start(20)
    (acts[0].trigger() if acts else mw._action_bizcard_find())
    dlg = getattr(mw, "_bizcard_find_dlg", None)
    chk(dlg is not None and pump(lambda: dlg.table.rowCount() == 3, timeout=5), "B 창이 열리고 명함 셋", str(dlg and dlg.table.rowCount()))
    mw._action_bizcard_find()
    chk(mw._bizcard_find_dlg is dlg, "B 다시 눌러도 창은 하나")
    type_ko(dlg.ed_find, "도로")
    chk(pump(lambda: dlg.table.rowCount() == 1, timeout=3), "B 글을 치면 잠시 뒤 결과가 줄어듦", str(dlg.table.rowCount()))
    chk(dlg.eds["name"].text() == "홍길동" and dlg.eds["cell"].text() == "010-0000-0001" and dlg.ed_memo.toPlainText() == "골프 모임",
        "B 첫 결과의 칸·메모가 오른쪽에")
    chk(dlg.btn_flip.isEnabled() and os.path.normcase(dlg.shown) == os.path.normcase(dlg._card["front"]),
        "B 사진창 — 명함 앞면, 뒷면이 있으면 앞↔뒤 단추 켜짐")
    dlg.ed_find.clear()
    pump(lambda: dlg.table.rowCount() == 3, timeout=3)
    dlg.cb_period.setCurrentIndex(dlg.cb_period.findData("1y"))
    chk(pump(lambda: dlg.table.rowCount() == 2, timeout=3), "B 기간 '최근 1년'", str(dlg.table.rowCount()))
    dlg.cb_period.setCurrentIndex(dlg.cb_period.findData("all"))
    pump(lambda: dlg.table.rowCount() == 3, timeout=3)

    print("\n=== C. 인물 사진 ===")
    r_h = dlg.row_of_id(next(c["id"] for c in dlg._rows if c["name"] == "홍길동"))
    dlg.table.setCurrentCell(r_h, 0)
    pump(timeout=0.2)
    src = TMP / "photo.jpg"
    im = Image.new("RGB", (40, 20), "red")
    ex = Image.Exif()
    ex[0x010F] = "FakeCam"                     # Make
    ex[0x0112] = 6                             # 방향 — 90도 돌려 보임
    im.save(src, exif=ex.tobytes())
    dlg.add_photos([str(src)])
    chk(pump(lambda: not dlg.photo_busy, timeout=10), "C 사진 넣기 끝(배경)")
    pdir = OUT.parent / P.PEOPLE_DIR
    p1 = pdir / "홍길동_가나도로공사.jpg"
    chk(p1.exists(), "C `인물\\<정리본 이름>.jpg`", str(sorted(os.listdir(pdir)) if pdir.exists() else "-"))
    if p1.exists():
        with Image.open(p1) as q:
            chk(q.format == "JPEG" and len(q.getexif()) == 0 and q.size == (20, 40), "C JPG·EXIF 없음·방향 반영",
                "%s %s %s" % (q.format, dict(q.getexif()), q.size))
    dlg.add_photos([str(src)])
    pump(lambda: not dlg.photo_busy, timeout=10)
    chk((pdir / "홍길동_가나도로공사 (2).jpg").exists() and dlg.photos.count() == 2, "C 둘째는 ' (2)'·인물 사진 칸에 보임",
        str(dlg.photos.count()))

    print("\n=== D. 고쳐 저장 ===")
    front0 = OUT / "홍길동_가나도로공사.jpg"
    ed = dlg.eds["company"]
    ed.setFocus()
    ed.selectAll()
    type_ko(ed, "(주)새회사")
    chk(dlg.btn_save.isEnabled(), "D 칸을 고치면 [저장] 켜짐")
    QTest.mouseClick(dlg.btn_save, Qt.MouseButton.LeftButton)
    pump(timeout=0.5)
    nf = OUT / "홍길동_새회사.jpg"
    chk(nf.exists() and not front0.exists() and (OUT / "홍길동_새회사_뒷면.jpg").exists(), "D 정리본·뒷면 이름이 `성명_회사명`(법인 꼴 뗌)",
        str(sorted(os.listdir(OUT))))
    chk((pdir / "홍길동_새회사.jpg").exists() and (pdir / "홍길동_새회사 (2).jpg").exists(), "D 인물 사진 이름도 따라감",
        str(sorted(os.listdir(pdir))))
    st = S.BizcardStore()
    row = st.card_by_front(nf)
    chk(row is not None and row["company"] == "새회사" and row["memo"] == "골프 모임" and "새회사" in row["tags"]
        and "가나도로공사" not in row["tags"] and st.count() == 3, "D DB 행 고침(새 행 없음·메모 지킴·#회사)", str(row and row["tags"]))
    st.close()
    tags = mw.bookmark_tree._tags
    tg = tags.get_manual(str(nf)) or []
    chk("새회사" in tg and "가나도로공사" not in tg and "명함" in tg, "D 파일 해시태그 — #회사 바뀜, #명함 그대로", str(tg))
    chk(dlg.eds["company"].text() == "새회사" and not dlg.btn_save.isEnabled(), "D 저장 뒤 칸은 새 값·[저장] 꺼짐")
    dlg.ed_memo.setPlainText("새 메모")
    QTest.mouseClick(dlg.btn_save, Qt.MouseButton.LeftButton)
    pump(timeout=0.3)
    st = S.BizcardStore()
    chk(nf.exists() and st.card_by_front(nf)["memo"] == "새 메모", "D 메모만 바꾸면 파일 이름 그대로")
    st.close()

    print("\n=== E. 저장 안 한 고침 ===")
    asked = []
    QMessageBox.question = staticmethod(lambda *a, **k: (asked.append(1), QMessageBox.StandardButton.Discard)[1])
    dlg.eds["title"].setFocus()
    QTest.keyClicks(dlg.eds["title"], "X")
    other = dlg.row_of_id(next(c["id"] for c in dlg._rows if c["name"] == "김철수"))
    dlg.table.setCurrentCell(other, 0)
    pump(timeout=0.2)
    st = S.BizcardStore()
    chk(asked and dlg.eds["name"].text() == "김철수" and st.card_by_front(nf)["title"] == "부장", "E 다른 줄 — 묻고, 버리면 안 남음")
    st.close()

    print("\n=== F. 책갈피창 이름 바꾸기 → 명함 DB 따라감 ===")
    bt = mw.bookmark_tree
    old_k = OUT / "김철수_라마바.jpg"
    new_k = OUT / "김철수_라마바(새이름).jpg"
    before = getattr(mw, "_bizcard_follow_done", 0)
    err = bt._rename_bg(str(old_k), str(new_k), "test")
    if err is None:
        bt._after_rename(None, old_k, new_k)
    chk(err is None and pump(lambda: getattr(mw, "_bizcard_follow_done", 0) > before, timeout=5), "F 배경 따라가기 끝")
    st = S.BizcardStore()
    chk(st.card_by_front(new_k) is not None and st.card_by_front(old_k) is None, "F 명함 DB 앞면 경로가 새 이름으로")
    st.close()
    dlg.refresh()
    pump(timeout=0.2)

    print("\n=== G. vCard·응답성 ===")
    from viewer import bg_write
    dlg.table.selectAll()
    out = TMP / "find.vcf"
    n = dlg.export_vcard(path=str(out), drive="명함폴더")
    bg_write.flush()
    vt = out.read_text(encoding="utf-8") if out.exists() else ""
    chk(n == 3 and vt.count("BEGIN:VCARD") == 3 and "FN:홍길동" in vt, "G 고른 명함 셋을 vCard 로", str(n))
    hb.stop()
    chk(max(gaps or [0]) < 1.0, "G 메인 정지 < 1초", "%.2f" % max(gaps or [0]))
    dlg.close()
    pump(timeout=0.3)

    print("\n=== H. 텍스트 창 명함 메모 칸(텍스트 창 SOT §2.2) ===")
    tp = mw.text_panel
    ok_open = mw._photo_open_arg(str(nf))
    if hasattr(mw, "_vm_text"):
        mw._vm_text()
    chk(ok_open and pump(lambda: tp.card_box.isVisible(), timeout=10), "H 사진 모드에서 정리본을 열면 메모 칸이 보임")
    chk(tp.card_memo.toPlainText() == "새 메모" and "홍길동" in tp.card_title.text(), "H 그 명함의 메모·이름",
        tp.card_title.text())
    tp.card_memo.moveCursor(tp.card_memo.textCursor().MoveOperation.End)
    tp.card_memo.setFocus()
    type_ko(tp.card_memo, " 추가")
    def _memo():
        s = S.BizcardStore()
        try:
            return s.card_by_front(nf)["memo"]
        finally:
            s.close()
    chk(_memo() == "새 메모", "H 치자마자 쓰지 않음(600ms 모아 한 번)")
    chk(pump(lambda: _memo() == "새 메모 추가", timeout=3), "H 고친 메모가 명함 DB 에(명함찾기와 같은 칸)", _memo())
    type_ko(tp.card_memo, "!")
    other_photo = Path(items["b"].front)               # 원본 그림 — 정리본 아님
    mw._photo_open_arg(str(other_photo))
    chk(pump(lambda: not tp.card_box.isVisible(), timeout=10), "H 명함 정리본이 아닌 사진에서는 숨김")
    st = S.BizcardStore()
    chk(st.card_by_front(nf)["memo"] == "새 메모 추가!", "H 사진을 바꾸기 전에 남은 고침을 먼저 씀", st.card_by_front(nf)["memo"])
    st.close()

    print("\n=== I. 명함찾기 개편(§5.24) ===")
    import hashlib, shutil
    from PyQt6.QtCore import QPoint
    import viewer.widgets.bookmark_tree as _btm
    TR = TMP / "trash"
    TR.mkdir()
    _btm._trash_fn = lambda: (lambda p: shutil.move(p, str(TR / (Path(p).parent.name + "_" + Path(p).name))))   # 시험용 휴지통
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    # I1 명함 단추 — 명함 폴더가 비면 숨김
    bz = mw._cmds.get("tools.bizcard")
    mw._gate_api_dependent_ui(mw._prefs)
    chk(bz is not None and not bz.isVisible(), "I1 명함 폴더가 비면 도구 탭 `명함` 숨김")
    mw._prefs.setdefault("picture", {})["bizcard_folder"] = str(F)
    mw._gate_api_dependent_ui(mw._prefs)
    chk(bz is not None and bz.isVisible(), "I1 명함 폴더를 정하면 보임")
    mw._action_bizcard_find()
    dlg = mw._bizcard_find_dlg
    pump(lambda: dlg.table.rowCount() == 3, timeout=5)
    # I11 처음 너비 — 목록은 네 열이 다 보이는 최소 폭, 사진창은 넓게
    pump(timeout=0.2)
    tw = dlg.table_min_width()
    ls, ps = dlg.split.sizes()
    chk(abs(dlg.mid.sizes()[0] - tw) <= 30 and dlg.table.viewport().width() >= sum(dlg.table.columnWidth(c) for c in range(3))
        and ps >= 0.35 * (ls + ps) and ps > dlg.mid.sizes()[0],
        "I11 처음 너비 — 목록은 스캔일까지 보이는 최소 폭, 사진창이 목록보다 넓음", "%s %s tw=%s" % (dlg.split.sizes(), dlg.mid.sizes(), tw))
    # I2 머리말 정렬 — 실제 마우스로 머리말을 누름
    hh = dlg.table.horizontalHeader()
    col_names = lambda: [dlg.table.item(r, 0).text() for r in range(dlg.table.rowCount())]
    def click_head(col):
        QTest.mouseClick(hh.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(hh.sectionViewportPosition(col) + 5, hh.height() // 2))
        pump(timeout=0.1)
    click_head(0)
    a1 = col_names()
    click_head(0)
    a2 = col_names()
    chk(a1 == sorted(a1) and a2 == sorted(a1, reverse=True) and a1 != a2, "I2 머리말을 누르면 정렬, 다시 누르면 반대", "%s %s" % (a1, a2))
    hong = next(c for c in dlg._rows if c["name"] == "홍길동")
    dlg.table.setCurrentCell(dlg.row_of_id(hong["id"]), 0)
    pump(timeout=0.1)
    click_head(1)
    chk(dlg._card and dlg._card["id"] == hong["id"] and dlg.table.currentRow() == dlg.row_of_id(hong["id"]), "I2 정렬해도 고른 명함 그대로")
    # I3 앞↔뒤 단추
    QTest.mouseClick(dlg.btn_flip, Qt.MouseButton.LeftButton)
    b1 = dlg.shown
    QTest.mouseClick(dlg.btn_flip, Qt.MouseButton.LeftButton)
    chk(os.path.normcase(b1) == os.path.normcase(hong["back"]) and os.path.normcase(dlg.shown) == os.path.normcase(hong["front"]),
        "I3 동그란 단추 — 누르면 뒷면, 또 누르면 앞면")
    # I4 체크한 칸 복사 — 기억
    for k, cb in dlg.chk.items():
        if cb.isChecked() != (k in ("name", "cell")):
            QTest.mouseClick(cb, Qt.MouseButton.LeftButton)
    kim = next(c for c in dlg._rows if c["name"] == "김철수")
    dlg.table.clearSelection()
    from PyQt6.QtCore import QItemSelectionModel
    sm = dlg.table.selectionModel()
    for c in (hong, kim):
        sm.select(dlg.table.model().index(dlg.row_of_id(c["id"]), 0),
                  QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    QTest.mouseClick(dlg.btn_copy, Qt.MouseButton.LeftButton)
    cb_text = QApplication.clipboard().text()
    want = {"이름: 홍길동\n휴대폰: 010-0000-0001", "이름: 김철수\n휴대폰: 010-0000-0003"}
    chk(set(cb_text.split("\n\n")) == want, "I4 체크한 칸만 '항목: 값' 줄로, 명함 사이 빈 줄", repr(cb_text))
    dlg.close()
    pump(timeout=0.2)
    mw._action_bizcard_find()
    dlg = mw._bizcard_find_dlg
    pump(lambda: dlg.table.rowCount() == 3, timeout=5)
    chk({k for k, cb in dlg.chk.items() if cb.isChecked()} == {"name", "cell"}, "I4 체크는 창을 다시 열어도 그대로")
    # I5 즐겨찾기 — 여러 명 넣기·빼기·차례·탭
    rows = {c["name"]: c for c in dlg._rows}
    sm = dlg.table.selectionModel()
    dlg.table.clearSelection()
    for n in ("홍길동", "김철수"):
        sm.select(dlg.table.model().index(dlg.row_of_id(rows[n]["id"]), 0),
                  QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    QTest.mouseClick(dlg.btn_fav_add, Qt.MouseButton.LeftButton)
    chk(dlg.fav.count() == 2 and dlg.fav_tabs.count() == 1, "I5 고른 둘을 한 번에 즐겨찾기 탭에", str(dlg.fav.count()))
    QTest.mouseClick(dlg.btn_fav_add, Qt.MouseButton.LeftButton)
    chk(dlg.fav.count() == 2, "I5 이미 있으면 건너뜀")
    chk(pump(lambda: getattr(dlg, "fav_icons_pending", 0) == 0, timeout=5)
        and dlg.fav.item(dlg.fav_ids().index(rows["홍길동"]["id"])).data(Qt.ItemDataRole.UserRole + 1),
        "I5 인물 사진이 있으면 그 그림(배경에서 읽음)")
    from viewer.widgets.bizcard_find_dialog import _move_rows
    _move_rows(dlg.fav, [1], 0)
    dlg.fav.reordered.emit()
    order = dlg.fav_ids()
    gid = dlg.fav_tabs.tabData(0)
    dlg.fav_new_tab("가족")
    chk(dlg.fav_tabs.count() == 2 and dlg.fav.count() == 0, "I5 새 탭(빈 탭으로 바뀜)")
    dlg.fav_rename_tab(1, "친구")
    dlg.fav_tabs.setCurrentIndex(0)
    chk(dlg.fav_ids() == order and dlg.fav_tabs.tabText(1) == "친구", "I5 차례·탭 이름이 저장됨", str(dlg.fav_ids()))
    dlg.fav.item(0).setSelected(True)
    QTest.keyClick(dlg.fav, Qt.Key.Key_Delete)
    chk(dlg.fav.count() == 1, "I5 Delete 로 탭에서 빼기(명함은 그대로)", str(dlg.fav.count()))
    chk(dlg.fav_delete_tab(1, ask=False) and dlg.fav_tabs.count() == 1 and not dlg.fav_delete_tab(0, ask=False),
        "I5 탭 지우기 — 마지막 하나는 지우지 않음")
    it = dlg.fav.item(0)
    QTest.mouseClick(dlg.fav.viewport(), Qt.MouseButton.LeftButton, pos=dlg.fav.visualItemRect(it).center())
    pump(timeout=0.1)
    chk(dlg._card and dlg._card["id"] == it.data(Qt.ItemDataRole.UserRole), "I5 사람을 누르면 그 명함을 보임")
    # I6 인물 사진 차례 = 파일 이름, 지우기 = 휴지통
    hong = P.card_by_id(dlg._store(), rows["홍길동"]["id"])
    dlg.table.setCurrentCell(dlg.row_of_id(hong["id"]), 0)
    pump(timeout=0.1)
    ph = dlg.photo_paths()
    # I13 인물 사진 — 위 큰 화면, 아래 썸네일 한 줄, 썸네일을 누르면 큰 화면에
    pv = getattr(dlg, "photo_view", None)
    chk(pv is not None and len(ph) == 2 and os.path.normcase(getattr(dlg, "photo_shown", "")) == os.path.normcase(ph[0])
        and pv.pixmap() is not None and not pv.pixmap().isNull()
        and not dlg.photos.isWrapping() and pv.height() > dlg.photos.height() and pv.y() < dlg.photos.y(),
        "I13 명함을 고르면 첫 인물 사진이 위 큰 화면에, 그 아래 썸네일 한 줄",
        "%s %s" % (getattr(dlg, "photo_shown", None), pv and (pv.height(), dlg.photos.height())))
    it2 = dlg.photos.item(1)
    QTest.mouseClick(dlg.photos.viewport(), Qt.MouseButton.LeftButton, pos=dlg.photos.visualItemRect(it2).center())
    pump(timeout=0.1)
    chk(os.path.normcase(getattr(dlg, "photo_shown", "")) == os.path.normcase(ph[1]), "I13 썸네일을 누르면 그 사진이 큰 화면에")
    Image.new("RGB", (30, 30), "blue").save(ph[1])          # 둘째를 다른 그림으로 — 바뀐 것이 보이게
    md5 = lambda f: hashlib.md5(Path(f).read_bytes()).hexdigest()
    h0, h1 = md5(ph[0]), md5(ph[1])
    _move_rows(dlg.photos, [1], 0)
    dlg.photos.reordered.emit()
    ph2 = dlg.photo_paths()
    chk([os.path.basename(x) for x in ph2] == [os.path.basename(x) for x in ph] and md5(ph2[0]) == h1 and md5(ph2[1]) == h0,
        "I6 끌어 차례를 바꾸면 파일 이름이 그 차례대로", str([os.path.basename(x) for x in ph2]))
    n = dlg.delete_photos([ph2[0]], ask=False)
    ph3 = dlg.photo_paths()
    chk(n == 1 and len(ph3) == 1 and os.path.basename(ph3[0]) == os.path.basename(ph[0]) and md5(ph3[0]) == h0
        and any(x.endswith(os.path.basename(ph[0])) for x in os.listdir(TR)), "I6 사진 지우기 = 휴지통, 남은 사진은 첫 이름으로")
    # I7 해시태그 — DB·파일, #찾기, 저장해도 남음
    dlg.table.clearSelection()
    dlg.table.setCurrentCell(dlg.row_of_id(hong["id"]), 0)
    chk(dlg.edit_tags(text="명함 새회사 한글 골프동호회") == 1, "I7 해시태그 붙이기")
    st = S.BizcardStore()
    hong = P.card_by_id(st, hong["id"])
    chk("골프동호회" in hong["tags"] and [r["name"] for r in P.find(st, "#골프동호회")] == ["홍길동"], "I7 명함 DB 태그·#찾기")
    st.close()
    chk("골프동호회" in (mw.bookmark_tree._tags.get_manual(os.path.realpath(hong["front"])) or []), "I7 정리본 파일에도 같은 해시태그")
    dlg.ed_memo.setPlainText("태그 뒤 메모")
    QTest.mouseClick(dlg.btn_save, Qt.MouseButton.LeftButton)
    pump(timeout=0.3)
    st = S.BizcardStore()
    chk("골프동호회" in P.card_by_id(st, hong["id"])["tags"], "I7 칸을 고쳐 저장해도 사람이 붙인 해시태그는 남음")
    st.close()
    # I12 해시태그 — 책갈피창 '해시태그 수정' 창과 같은 길(창에 고른 명함의 정리본 앞면, 닫으면 DB·뒷면 맞춤)
    import viewer.widgets.tag_apply_dialog as _tad
    seen = {}
    def _fake_exec(self):
        seen["paths"] = list(self._paths)
        self.apply_tags(True, tags=["가족모임"])     # [적용] 을 누른 것처럼
        return 0
    _orig_exec = _tad.TagApplyDialog.exec
    _tad.TagApplyDialog.exec = _fake_exec
    try:
        hong = P.card_by_id(dlg._store(), hong["id"])
        kim = next(c for c in dlg._rows if c["name"] == "김철수")
        dlg.table.clearSelection()
        sm = dlg.table.selectionModel()
        for c in (hong, kim):
            sm.select(dlg.table.model().index(dlg.row_of_id(c["id"]), 0),
                      QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        QTest.mouseClick(dlg.btn_tags, Qt.MouseButton.LeftButton)
        pump(timeout=0.2)
    finally:
        _tad.TagApplyDialog.exec = _orig_exec
    want_paths = sorted(os.path.normcase(os.path.realpath(c["front"])) for c in (hong, kim))
    chk(sorted(os.path.normcase(x) for x in seen.get("paths", [])) == want_paths,
        "I12 [해시태그…] 는 '해시태그 수정' 창에 고른 명함들의 정리본 앞면을 넘김", str(len(seen.get("paths", []))))
    st = S.BizcardStore()
    h2, k2 = P.card_by_id(st, hong["id"]), P.card_by_id(st, kim["id"])
    chk("가족모임" in h2["tags"] and "가족모임" in k2["tags"] and sorted(r["name"] for r in P.find(st, "#가족모임")) == ["김철수", "홍길동"],
        "I12 창에서 붙인 태그가 명함 DB 태그 칸에(#찾기)")
    st.close()
    chk("가족모임" in (mw.bookmark_tree._tags.get_manual(os.path.realpath(h2["back"])) or []), "I12 뒷면 파일에도 같은 태그")
    # I8 주소록 가져오기(리멤버 꼴 vCard) — 같은 사람은 빈 칸만, 없는 사람은 그림 없는 명함
    vf = TMP / "contacts.vcf"
    vf.write_text("BEGIN:VCARD\r\nVERSION:3.0\r\nN:;김철수;;;\r\nTEL;TYPE=work,cell:010-0000-0003\r\nEMAIL;TYPE=work:kim@example.com\r\n"
                  "ORG:다른회사;\r\nEND:VCARD\r\n"
                  "BEGIN:VCARD\r\nVERSION:3.0\r\nN:;박새사람;;;\r\nTEL;TYPE=work,cell:010-0000-0009\r\nORG:차카타;영업팀\r\n"
                  "TITLE:과장\r\nADR;TYPE=work:;가짜시 가짜로 1;;;;;\r\nEND:VCARD\r\n", encoding="utf-8")
    res = dlg.import_contacts(str(vf), ask=False)
    st = S.BizcardStore()
    kim = P.find(st, "김철수")[0]
    new = P.find(st, "박새사람")
    chk(res == (1, 1), "I8 합침 1·더함 1", str(res))
    chk(kim["emails"] == ["kim@example.com"] and kim["company"] == "라마바", "I8 같은 사람은 빈 칸만 채움(회사는 그대로)", str(kim["company"]))
    chk(len(new) == 1 and new[0]["front"].startswith("contact:") and new[0]["dept"] == "영업팀" and new[0]["address"] == "가짜시 가짜로 1",
        "I8 없는 사람은 그림 없는 명함으로(부서·주소)")
    st.close()
    pump(lambda: dlg.table.rowCount() == 4, timeout=3)
    dlg.table.clearSelection()
    dlg.table.setCurrentCell(dlg.row_of_id(new[0]["id"]), 0)
    pump(timeout=0.1)
    chk(not dlg.btn_photo.isEnabled() and not dlg.btn_open.isEnabled() and dlg.btn_tags.isEnabled(), "I8 그림 없는 명함 — 사진·명함 보기 끔")
    from viewer import bg_write
    rf = TMP / "remember.vcf"
    dlg.export_vcard(path=str(rf), style="remember")
    bg_write.flush()
    rt = rf.read_text(encoding="utf-8") if rf.exists() else ""
    chk("N:;박새사람;;;" in rt and "TEL;TYPE=work,cell:010-0000-0009" in rt and "ORG:차카타;영업팀" in rt
        and "drive.google" not in rt, "I8 리멤버용 vCard 내보내기 꼴")
    # I10 주소록 우선순위(D24) — 같은 번호, 다른 회사: 리멤버 > 구글, 명함·손 고침은 덮어쓰지 않음
    def vcf(name, comp, num="010-0000-0077"):
        f = TMP / ("p_%s_%s.vcf" % (len(list(TMP.glob("p_*.vcf"))), comp))
        f.write_text("BEGIN:VCARD\r\nVERSION:3.0\r\nFN:%s\r\nTEL;TYPE=CELL:%s\r\nORG:%s\r\nEND:VCARD\r\n" % (name, num, comp), encoding="utf-8")
        return str(f)
    def comp_of(num_part="0000-0077"):
        st = S.BizcardStore()
        try:
            r = P.find(st, num_part)
            return [(x["name"], x["company"]) for x in r]
        finally:
            st.close()
    dlg.import_contacts(vcf("최가짜", "구글회사"), ask=False, source="google")
    chk(comp_of() == [("최가짜", "구글회사")], "I10 구글에서 새 사람", str(comp_of()))
    dlg.import_contacts(vcf("최가짜", "리멤버회사"), ask=False, source="remember")
    chk(comp_of() == [("최가짜", "리멤버회사")], "I10 리멤버가 구글 값을 이김", str(comp_of()))
    dlg.import_contacts(vcf("최가짜", "구글새회사"), ask=False, source="google")
    chk(comp_of() == [("최가짜", "리멤버회사")], "I10 구글은 리멤버 값을 덮지 않음", str(comp_of()))
    dlg.import_contacts(vcf("김철수", "리멤버회사", "010-0000-0003"), ask=False, source="remember")
    chk(comp_of("0000-0003") == [("김철수", "라마바")], "I10 명함을 읽은 값은 리멤버도 덮지 않음", str(comp_of("0000-0003")))
    pump(timeout=0.1)
    choi = next(c for c in dlg._rows if c["name"] == "최가짜")
    dlg.table.clearSelection()
    dlg.table.setCurrentCell(dlg.row_of_id(choi["id"]), 0)
    pump(timeout=0.1)
    ed = dlg.eds["company"]
    ed.setFocus(); ed.selectAll()
    type_ko(ed, "손회사")
    QTest.mouseClick(dlg.btn_save, Qt.MouseButton.LeftButton)
    pump(timeout=0.3)
    dlg.import_contacts(vcf("최가짜", "리멤버다른회사"), ask=False, source="remember")
    chk(comp_of() == [("최가짜", "손회사")], "I10 손으로 고친 칸은 리멤버도 덮지 않음", str(comp_of()))
    pump(lambda: dlg.table.rowCount() == 5, timeout=3)
    # I9 목록에서 지우기 — 명함 관리 [삭제]와 같은 길
    lee = next(c for c in dlg._rows if c["name"] == "이영희")
    st = S.BizcardStore()
    gid0 = dlg._fav_gid()
    P.fav_add(st, gid0, [lee["id"]])
    st.close()
    lee_front = os.path.realpath(lee["front"])
    src_lee = Path(items["c"].front)
    dlg.table.clearSelection()
    dlg.table.setCurrentCell(dlg.row_of_id(lee["id"]), 0)
    pump(timeout=0.1)
    dlg.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)   # 지울 명함이 맨 위가 아니게(고치기 전 코드는 맨 위로 갔다)
    pump(timeout=0.1)
    r_lee = dlg.row_of_id(lee["id"])
    below = dlg._card_at(r_lee + 1) if r_lee + 1 < dlg.table.rowCount() else dlg._card_at(r_lee - 1)
    dlg.activateWindow(); dlg.table.setFocus()
    QTest.keyClick(dlg.table, Qt.Key.Key_Delete)
    pump(timeout=0.3)
    chk(r_lee > 0 and dlg._card is not None and below is not None and dlg._card["id"] == below["id"]
        and dlg.table.currentRow() == dlg.row_of_id(below["id"]), "I9 지운 뒤 커서는 맨 위가 아니라 바로 아래 명함",
        "%s %s" % (dlg.table.currentRow(), r_lee))
    st = S.BizcardStore()
    chk(not os.path.exists(lee_front) and not src_lee.exists() and P.find(st, "이영희") == [], "I9 Delete — 원본·정리본 휴지통, DB 행 지움")
    chk(st.con.execute("SELECT COUNT(*) FROM fav_members WHERE card_id=?", (lee["id"],)).fetchone()[0] == 0, "I9 즐겨찾기 칸도 지움")
    st.close()
    chk(dlg.table.rowCount() == 4, "I9 표에서 빠짐", str(dlg.table.rowCount()))
    dlg.close()
    pump(timeout=0.2)
except Exception:
    import traceback
    traceback.print_exc()
    fails.append("예외")
finish()
