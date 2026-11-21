# -*- coding: utf-8 -*-
"""명함찾기 창 (명함 SOT §5.9, P4) — 가짜 명함만(010-0000-xxxx, 명함 SOT §2.1).

실제 MainWindow 로(오프스크린, 실제 설정·데이터 폴더를 쓰지 않는다 — 검사 작성 SOT §14.7.2).
A. 찾기 모듈 — 낱말 일부('도로' → '가나도로공사'), 낱말 여럿은 모두, #태그, 기간, LIKE 특수 글자
B. 도구 탭에 `명함 ▾` 없음(261117-56 — 본 화면 명함 아이콘), 명함찾기 창(하나만), 글을 치면 250ms 뒤 결과, 기간 콤보
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
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QTimer, QDate
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox, QDialog, QPushButton
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

    print("\n=== L. 언어 해시태그는 하나(D25) ===")
    from viewer.bizcard import recognize as RZ
    chk(AP.tags_for({"name": "홍길동", "company": "Gana Co", "langs": RZ.order_langs(10, 80)}) == ["명함", "Gana Co", "한글"]
        and AP.tags_for({"name": "John Doe", "company": "가나", "langs": ("영어",)})[-1] == "한글",
        "L 성명이나 회사명이 한글이면 #한글만(영어 글자가 더 많아도)")
    chk(AP.tags_for({"name": "John Doe", "company": "Acme", "langs": RZ.order_langs(30, 20)})[-1] == "한글"
        and AP.tags_for({"name": "John Doe", "company": "Acme", "langs": RZ.order_langs(10, 80)})[-1] == "영어"
        and "한글" not in AP.tags_for({"name": "John Doe", "company": "Acme", "langs": RZ.order_langs(10, 80)}),
        "L 성명·회사명이 한글이 아니면 글자 수가 많은 말 하나")
    chk(AP.lang_tag("John Doe", "Acme", ["한글", "영어"], ordered=False) == "영어"
        and AP.lang_tag("홍길동", "", ["한글", "영어"], ordered=False) == "한글" and AP.lang_tag("홍길동", "", []) == "",
        "L 이미 둘 다 붙은 태그 — 성명·회사명 한글이면 #한글, 아니면 #영어")
    st = S.BizcardStore()
    hong0 = next(r for r in P.find(st, "") if r["name"] == "홍길동")
    P.update_card(st, hong0["id"], {"tags": ["명함", "가나도로공사", "한글", "영어"]})   # 종전 규칙으로 둘 다
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
        uv0 = ost.con.execute("PRAGMA user_version").fetchone()[0]
        P.fav_init(ost, "즐겨찾기")
        P.fav_init(ost, "즐겨찾기")                       # 할 일·마감·메모 글 열(D26·D28·D29)이 이미 있으면 ALTER 를 건너뜀
        cols = [r[1] for r in ost.con.execute("PRAGMA table_info(fav_groups)")]
        mcols = [r[1] for r in ost.con.execute("PRAGMA table_info(fav_members)")]
        ok_old = ok_old and len(P.fav_groups(ost)) == 1 and ost.count() == 0 and cols.count("todo") == 1 \
            and cols.count("closed") == 1 and mcols.count("memo_entry") == 1 \
            and ost.con.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='recent'").fetchone()[0] == 1 \
            and ost.con.execute("PRAGMA user_version").fetchone()[0] == uv0
        if not ok_old:
            print("A2", cols, uv0)
        ost.close()
        con = dbutil.connect(old_db, dbutil.BUSY_MS_BG)  # 옛 판(beta.17)의 즐겨찾기 쿼리 — 새 열이 있어도 그대로
        con.execute("INSERT INTO fav_groups(name, pos) VALUES('옛 판 탭', 1)")
        con.execute("INSERT OR IGNORE INTO fav_members(group_id, card_id, pos) VALUES(1, 99, 0)")   # 옛 판의 넣기
        ok_old = ok_old and [r[1] for r in con.execute("SELECT id, name FROM fav_groups ORDER BY pos, id")] == ["즐겨찾기", "옛 판 탭"] \
            and con.execute("SELECT memo_entry FROM fav_members WHERE card_id=99").fetchone()[0] == ""
        con.rollback(); con.close()
        ost = S.BizcardStore(old_db)
        ok_old = ok_old and len(P.fav_groups(ost, "2026-01-01")) == 1     # 옛 판이 넣은 행(todo 기본 0)은 보통 탭
        ost.close()
        con = dbutil.connect(old_db, dbutil.BUSY_MS_BG)  # 옛 판이 새 DB 를 읽는 꼴 — cards 는 그대로
        ok_old = ok_old and [r[1] for r in con.execute("PRAGMA table_info(cards)")][:3] == ["id", "front", "back"]
        con.close()
    except Exception as e:
        ok_old = False
        print(repr(e))
    chk(ok_old, "A2 옛 DB 를 열어도 깨지지 않음(새 표는 CREATE IF NOT EXISTS, cards 열은 그대로)")

    print("\n=== M. 명함 창 메뉴·단추 글자 — 글 끝 '…'·'...' 없음, 메뉴 단추 글자에 '▾' 없음(디자인 SOT §2.7) ===")
    import re as _re
    bad = []
    for _f in ("viewer/widgets/bizcard_find_dialog.py", "viewer/widgets/bizcard_import_dialog.py"):
        _src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), _f), encoding="utf-8").read()
        for _t in _re.findall(r'tr\("([^"]*)"\)', _src):
            if _re.search(r'[가-힣A-Za-z\]](\.\.\.|…)( \(\{n\}[^"]*\))?$', _t) and not _t.endswith("중…"):
                bad.append((_f.rsplit("/", 1)[-1], _t))
        bad += [(_f.rsplit("/", 1)[-1], _m) for _m in _re.findall(r'QPushButton\(([^)\n]*▾[^)\n]*)\)', _src)]
    chk(not bad, "M 명함 창 두 개의 메뉴·단추 글자에 끝 '…'·'▾' 없음", str(bad[:6]))

    print("\n=== B. 메뉴·창 ===")
    from viewer.app import MainWindow
    import modal_guard
    modal_guard.install(label=lambda: "명함찾기", echo=False)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    mw = MainWindow(); mw._skip_save_on_close = True
    mw.show()
    pump(timeout=1.0)
    from PyQt6.QtGui import QAction
    acts = [a for a in mw.findChildren(QAction) if a.text() == "명함찾기"]
    chk(not acts and "tools.bizcard" not in (getattr(mw, "_cmds", None) or {}),
        "B 도구 탭에 `명함 ▾`·`명함찾기` 없음 — 본 화면 명함 아이콘이 별도 프로그램으로(261117-56, 명함 SOT §5.27)")
    gaps, last = [], [time.monotonic()]

    def beat():
        now = time.monotonic(); gaps.append(now - last[0]); last[0] = now
    hb = QTimer(); hb.timeout.connect(beat); hb.start(20)
    hong_front = os.path.realpath(hong0["front"])
    mw.bookmark_tree._tags.set(hong_front, ["명함", "가나도로공사", "한글", "영어", "골프"])
    (acts[0].trigger() if acts else mw._action_bizcard_find())
    dlg = getattr(mw, "_bizcard_find_dlg", None)
    chk(dlg is not None and pump(lambda: dlg.table.rowCount() == 3, timeout=5), "B 창이 열리고 명함 셋", str(dlg and dlg.table.rowCount()))
    st = S.BizcardStore()
    h_tags = P.card_by_id(st, hong0["id"])["tags"]
    chk("한글" in h_tags and "영어" not in h_tags and st.meta_get(P.LANG_FIX_KEY) and P.fix_lang_tags(st) == 0,
        "L 명함찾기를 처음 열면 종전 '#한글·#영어' 를 하나로(한 번만)", str(h_tags))
    st.close()
    f_tags = mw.bookmark_tree._tags.get_manual(hong_front) or []
    chk("영어" not in f_tags and "한글" in f_tags and "골프" in f_tags, "L 정리본 파일 태그도 하나로, 사람이 붙인 태그는 그대로", str(f_tags))
    mw._action_bizcard_find()
    chk(mw._bizcard_find_dlg is dlg, "B 다시 눌러도 창은 하나")
    type_ko(dlg.ed_find, "도로")
    chk(pump(lambda: dlg.table.rowCount() == 1, timeout=3), "B 글을 치면 잠시 뒤 결과가 줄어듦", str(dlg.table.rowCount()))
    chk(dlg.eds["name"].text() == "홍길동" and dlg.eds["cell"].text() == "010-0000-0001" and dlg.ed_memo.toPlainText() == "골프 모임",
        "B 첫 결과의 칸·메모가 오른쪽에")
    chk(dlg.dots.isVisible() and dlg.dots.count == 2 and dlg.dots.current == 0
        and os.path.normcase(dlg.shown) == os.path.normcase(dlg._card["front"]),
        "B 사진창 — 명함 앞면, 뒷면이 있으면 쪽 점 둘(왼쪽 채움)")
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
    chk(row is not None and row["company"] == "새회사" and row["memo"].splitlines()[-1] == "골프 모임"
        and row["memo"].startswith("[") and "새회사" in row["tags"]
        and "가나도로공사" not in row["tags"] and st.count() == 3, "D DB 행 고침(새 행 없음·메모 지킴 — 맨 위 수정 기록 261120-26·#회사)", str(row and row["tags"]))
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
    # I1 명함 아이콘(본 화면 탭 줄, 명함 SOT §5.27) — 명함 폴더가 비면 숨김
    bz = getattr(mw, "_bizcard_btn", None)
    mw._prefs.setdefault("picture", {}).pop("bizcard_folder", None)
    mw._gate_api_dependent_ui(mw._prefs)
    chk(bz is not None and not bz.isVisible(), "I1 명함 폴더가 비면 명함 아이콘 숨김")
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
    heads = [dlg.table.horizontalHeaderItem(c).text() for c in range(dlg.table.columnCount())]
    chk(abs(dlg.mid.sizes()[0] - tw) <= 30 and heads[3:4] == ["전화"]
        and dlg.table.viewport().width() >= dlg.table.columnViewportPosition(3) + dlg.table.columnWidth(3)
        and ps >= 0.35 * (ls + ps) and ps > dlg.mid.sizes()[0],
        "I11·I17 처음 너비 — 목록은 전화까지 보이는 최소 폭, 사진창이 목록보다 넓음", "%s %s tw=%s" % (dlg.split.sizes(), dlg.mid.sizes(), tw))
    r_h = next(r for r in range(dlg.table.rowCount()) if dlg.table.item(r, 0).text() == "홍길동")
    chk(heads == ["이름", "회사", "직함", "전화", "메일", "수정일"] and dlg.table.item(r_h, 3).text() == "010-0000-0001"
        and dlg.table.item(r_h, 4).text() == "hong@example.com",
        "I17 목록 직함 오른쪽에 전화(휴대폰)·메일 열", "%s %s" % (heads, [dlg.table.item(r_h, c).text() for c in range(dlg.table.columnCount())]))
    # I2 머리말 정렬 — 실제 마우스로 머리말을 누름
    hh = dlg.table.horizontalHeader()
    col_names = lambda: [dlg.table.item(r, 0).text() for r in range(dlg.table.rowCount())]
    def click_head(col):
        QTest.mouseClick(hh.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(hh.sectionViewportPosition(col) + 5, hh.height() // 2))
        pump(timeout=0.1)
    a0 = col_names()                                    # I16 처음은 이름 차례
    chk(a0 == sorted(a0) and hh.sortIndicatorSection() == 0, "I16 목록 처음 정렬은 이름(성명) 차례", str(a0))
    click_head(1)
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
    # I3 쪽 점 표시 — 작은 원 둘, 지금 면 채움, 누르면 그 면 (사용자 지시 261119)
    dd_ = dlg.dots
    QTest.mouseClick(dd_, Qt.MouseButton.LeftButton, pos=dd_.dot_center(1).toPoint())
    b1, cur1 = dlg.shown, dd_.current
    QTest.mouseClick(dd_, Qt.MouseButton.LeftButton, pos=dd_.dot_center(0).toPoint())
    chk(os.path.normcase(b1) == os.path.normcase(hong["back"]) and cur1 == 1
        and os.path.normcase(dlg.shown) == os.path.normcase(hong["front"]) and dd_.current == 0 and dd_.D <= 8,
        "I3 쪽 점 — 오른쪽 원을 누르면 뒷면(그 원 채움), 왼쪽 원을 누르면 앞면, 원은 작게(지름 8 이하)")
    kim_ = next(c for c in dlg._rows if c["name"] == "김철수")
    dlg.table.setCurrentCell(dlg.row_of_id(kim_["id"]), 0)
    pump(timeout=0.1)
    chk(not dd_.isVisible(), "I3 뒷면이 없는 명함은 점 표시 숨김(한 면)")
    dlg.table.setCurrentCell(dlg.row_of_id(hong["id"]), 0)
    pump(timeout=0.1)
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
    dlg.fav_add_selected()                              # 표 오른쪽 메뉴 '즐겨찾기 탭에 넣기' 와 같은 함수(I15)
    chk(dlg.fav.count() == 2 and dlg.fav_tabs.count() == 2, "I5 고른 둘을 한 번에 즐겨찾기 탭에(맨 앞은 '최근')", str(dlg.fav.count()))
    dlg.fav_add_selected()
    chk(dlg.fav.count() == 2, "I5 이미 있으면 건너뜀")
    chk(pump(lambda: getattr(dlg, "fav_icons_pending", 0) == 0, timeout=5)
        and dlg.fav.item(dlg.fav_ids().index(rows["홍길동"]["id"])).data(Qt.ItemDataRole.UserRole + 1),
        "I5 인물 사진이 있으면 그 그림(배경에서 읽음)")
    from viewer.widgets.bizcard_find_dialog import _move_rows
    _move_rows(dlg.fav, [1], 0)
    dlg.fav.reordered.emit()
    order = dlg.fav_ids()
    gid = dlg.fav_tabs.tabData(1)
    dlg.fav_new_tab("가족")
    chk(dlg.fav_tabs.count() == 3 and dlg.fav.count() == 0, "I5 새 탭(빈 탭으로 바뀜)")
    dlg.fav_rename_tab(2, "친구")
    dlg.fav_tabs.setCurrentIndex(1)
    chk(dlg.fav_ids() == order and dlg.fav_tabs.tabText(2) == "친구", "I5 차례·탭 이름이 저장됨", str(dlg.fav_ids()))
    dlg.fav.item(0).setSelected(True)
    QTest.keyClick(dlg.fav, Qt.Key.Key_Delete)
    chk(dlg.fav.count() == 1, "I5 Delete 로 탭에서 빼기(명함은 그대로)", str(dlg.fav.count()))
    chk(dlg.fav_delete_tab(2, ask=False) and dlg.fav_tabs.count() == 2 and not dlg.fav_delete_tab(1, ask=False)
        and not dlg.fav_delete_tab(0, ask=False),
        "I5 탭 삭제 — 할 일이 아닌 마지막 탭·'최근' 은 지우지 않음")
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
    # I14 단추 자리 · 할 일(todo) · 즐겨찾기 사람 호버·메뉴 복사 (D26, 사용자 지시 261119)
    pb, pd = getattr(dlg, "btn_photo", None), getattr(dlg, "btn_photo_del", None)
    chk(pb is not None and pd is not None and dlg.photo_split.isAncestorOf(pb) and dlg.photo_split.isAncestorOf(pd)
        and pb.mapTo(dlg, pb.rect().topLeft()).y() > dlg.photos.mapTo(dlg, dlg.photos.rect().topLeft()).y(),
        "I14 [사진 추가…]·[사진 삭제] 는 인물 사진 칸 아래")
    bs, bc = dlg.btn_save, dlg.btn_copy
    chk(bs.parentWidget() is bc.parentWidget() and abs(bs.y() - bc.y()) <= 2 and bc.x() > bs.x(),
        "I14 [내용 복사] 는 [저장] 오른쪽")
    import viewer.widgets.bizcard_find_dialog as _fd
    td = getattr(_fd, "TodoDialog", None)
    today_s = datetime.date.today().isoformat()
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    gid = None
    old_memo = (P.card_by_id(dlg._store(), hong["id"])["memo"] or "").strip()
    if td is not None:
        def _fake_todo_exec(self):
            self.ed_title.setText("현장 점검")
            self.ed_memo.setPlainText("자료 준비")
            return QDialog.DialogCode.Accepted            # 시작일은 기본(오늘), 종료일 체크 없음 = 계속
        _orig_td = td.exec
        td.exec = _fake_todo_exec
        try:
            dlg.table.clearSelection()
            for c in (hong, kim):
                sm.select(dlg.table.model().index(dlg.row_of_id(c["id"]), 0),
                          QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
            dlg.todo_new()                              # '+'·표 오른쪽 메뉴의 '새 할 일…' 과 같은 함수(I15)
            pump(timeout=0.2)
        finally:
            td.exec = _orig_td
        tabs = [dlg.fav_tabs.tabText(i) for i in range(dlg.fav_tabs.count())]
        ti = tabs.index("현장 점검") if "현장 점검" in tabs else -1
        gid = dlg.fav_tabs.tabData(ti) if ti >= 0 else None
        tip = dlg.fav_tabs.tabToolTip(ti) if ti >= 0 else ""
        chk(ti >= 0 and "자료 준비" in tip and today_s in tip and sorted(c["name"] for c in P.fav_members(dlg._store(), gid)) == ["김철수", "홍길동"],
            "I14 새 할 일 → 작업 제목 탭에 고른 사람들, 탭 위 글에 내용·기간", "%s %r" % (tabs, tip))
        hm = P.card_by_id(dlg._store(), hong["id"])["memo"]
        chk(old_memo and hm == "[%s ~ 계속] 현장 점검\n자료 준비\n\n%s" % (today_s, old_memo),
            "I14 할 일에 든 사람 메모 맨 위에 기간·제목·내용, 종전 메모는 그 아래", repr(hm[:60]))
    else:
        chk(False, "I14 할 일 창")
    st = dlg._store()
    g_future = P.todo_add(st, {"title": "다음 주 일", "memo": "", "start": tomorrow, "end": ""}, [kim["id"]], "계속")
    g_past = P.todo_add(st, {"title": "지난 일", "memo": "", "start": yesterday, "end": yesterday}, [kim["id"]], "계속") \
        if hasattr(P, "todo_add") else None
    dlg._fav_fill_tabs(gid)
    tabs = [dlg.fav_tabs.tabText(i) for i in range(dlg.fav_tabs.count())]
    hidden = [t for _g, t in P.todo_hidden(st, today_s)]
    chk("다음 주 일" not in tabs and "지난 일" not in tabs and sorted(hidden) == ["다음 주 일", "지난 일"],
        "I14 기간 밖(시작 전·끝남) 할 일 탭은 숨기고 지우지 않음", "%s %s" % (tabs, hidden))
    dlg.todo_edit(g_future, {"title": "다음 주 일", "memo": "", "start": today_s, "end": tomorrow})
    tabs = [dlg.fav_tabs.tabText(i) for i in range(dlg.fav_tabs.count())]
    chk("다음 주 일" in tabs and P.todo_info(st, g_future)["end"] == tomorrow, "I14 할 일 고치기 — 기간을 오늘로 당기면 탭이 보임")
    km = P.card_by_id(st, kim["id"])["memo"]
    chk(km.startswith("[%s ~ %s] 지난 일" % (yesterday, yesterday)), "I14 최신 할 일이 메모 맨 위", repr(km[:40]))
    dlg.todo_delete(g_future, ask=False)
    dlg.todo_delete(g_past, ask=False)
    # 즐겨찾기 사람 — 호버에 휴대폰·메일, 메뉴 '내용 복사'
    dlg.fav_tabs.setCurrentIndex([dlg.fav_tabs.tabText(i) for i in range(dlg.fav_tabs.count())].index("현장 점검"))
    pump(timeout=0.1)
    hit = next((dlg.fav.item(i) for i in range(dlg.fav.count()) if dlg.fav.item(i).data(Qt.ItemDataRole.UserRole) == hong["id"]), None)
    chk(hit is not None and "010-0000-0001" in hit.toolTip() and "hong@example.com" in hit.toolTip(),
        "I14 즐겨찾기 사람 위 글에 휴대폰·메일", hit.toolTip() if hit else "")
    dlg.fav.clearSelection()
    if hit is not None:
        hit.setSelected(True)
    t = dlg.fav_copy_selected() if hasattr(dlg, "fav_copy_selected") else ""
    chk("홍길동" in t and "김철수" not in t and QApplication.clipboard().text() == t, "I14 즐겨찾기 사람 메뉴 '내용 복사' = 체크한 칸 글", repr(t[:40]))
    dlg.todo_delete(gid, ask=False)
    # I19 아래 단추 줄 [명함 관리] — [주소록] 왼쪽, 누르면 명함 관리 창 길 `_action_bizcard_import`(사용자 지시 261119 — 도구 탭 메뉴는 261117-56 에 없앰)
    bm_ = getattr(dlg, "btn_manage", None)
    calls = []
    _orig_imp = mw._action_bizcard_import
    mw._action_bizcard_import = lambda *a, **k: calls.append(a)
    try:
        if bm_ is not None and bm_.isVisible():
            QTest.mouseClick(bm_, Qt.MouseButton.LeftButton)
            pump(timeout=0.1)
    finally:
        mw._action_bizcard_import = _orig_imp
    chk(bm_ is not None and bm_.isVisible() and bm_.text() == "명함 관리"
        and abs(bm_.y() - dlg.btn_vcard.y()) <= 2 and bm_.x() < dlg.btn_vcard.x() and calls == [()],
        "I19 [명함 관리] 단추는 [주소록] 왼쪽, 누르면 명함 관리 창 길", str(calls))
    # I15 탭·메뉴 개편 — 아이콘·끌어 복사·'+'·표/탭/사람 메뉴·이메일 복사·마감·삭제(메모 글)·최근·탭 명단 보기 (사용자 지시 261119)
    from PyQt6.QtWidgets import QMenu, QInputDialog, QToolButton, QWidgetAction
    st = dlg._store()
    chk(not any(hasattr(dlg, b) for b in ("btn_todo", "btn_fav_add", "btn_del"))
        and abs(dlg.btn_tags.mapTo(dlg, dlg.btn_tags.rect().center()).y() - dlg.ed_find.mapTo(dlg, dlg.ed_find.rect().center()).y()) <= 4
        and dlg.btn_tags.x() > dlg.ed_find.x()
        and abs(dlg.btn_vcard.y() - dlg.btn_open.y()) <= 2 and dlg.btn_vcard.x() < dlg.btn_open.x(),
        "I15 [즐겨찾기에 넣기]·[할 일…]·[삭제] 없음, [해시태그…] 는 찾기 칸 오른쪽, [주소록 ▾] 은 [명함 보기] 왼쪽")
    shown = []
    _orig_exec = QMenu.exec
    QMenu.exec = lambda self, *a, **k: shown.append(self)
    _orig_get = QInputDialog.getText
    try:
        def sel(*cards):
            dlg.table.clearSelection()
            for c in cards:
                sm.select(dlg.table.model().index(dlg.row_of_id(c["id"]), 0),
                          QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)

        def act(menu, *path):
            for name in path[:-1]:
                menu = next(a.menu() for a in menu.actions() if a.menu() is not None and a.menu().title() == name)
            return next(a for a in menu.actions() if a.text() == path[-1] or a.text().startswith(path[-1]))
        # '+' — 새 즐겨찾기 탭(고른 명단 포함)
        sel(hong)
        QInputDialog.getText = staticmethod(lambda *a, **k: ("동료", True))
        QTest.mouseClick(dlg.btn_fav_tab, Qt.MouseButton.LeftButton)
        pump(timeout=0.1)
        texts = [a.text() for a in shown[-1].actions()] if shown else []
        act(shown[-1], "새 즐겨찾기 탭").trigger()
        tabs = [dlg.fav_tabs.tabText(i) for i in range(dlg.fav_tabs.count())]
        g_col = dlg.fav_tabs.tabData(tabs.index("동료")) if "동료" in tabs else None
        chk(any("(1" in t for t in texts) and g_col and [c["name"] for c in P.fav_members(st, g_col)] == ["홍길동"]
            and dlg.fav_tabs.tabText(0) == "최근",
            "I15 '+' → 새 즐겨찾기 탭에 표에서 고른 명단, 맨 앞은 '최근'", "%s %s" % (texts, tabs))
        # 할 일 탭 아이콘
        g_t = P.todo_add(st, {"title": "견적 보내기", "memo": "자료", "start": today_s, "end": ""}, [hong["id"]], "계속")
        dlg._fav_fill_tabs(g_t)
        ti = dlg.fav_tabs.currentIndex()
        chk(not dlg.fav_tabs.tabIcon(ti).isNull() and dlg.fav_tabs.tabIcon(tabs.index("동료")).isNull()
            and not dlg.fav_tabs.tabIcon(0).isNull(), "I15 할 일 탭(과 최근 탭)은 이름 앞에 아이콘, 즐겨찾기 탭은 없음")
        # 표 오른쪽 메뉴 — 즐겨찾기 탭에 넣기 ▸ 동료 · 이메일 복사
        sel(hong, kim)
        dlg._table_menu(dlg.table.visualRect(dlg.table.model().index(dlg.row_of_id(kim["id"]), 0)).center())
        m = shown[-1]
        top = [a.text() for a in m.actions() if a.text()]
        act(m, "즐겨찾기 탭에 넣기", "동료").trigger()
        act(m, "이메일 복사").trigger()
        chk(top[:2] == ["즐겨찾기 탭에 넣기", "할 일에 넣기"] and "삭제" in top
            and sorted(c["name"] for c in P.fav_members(st, g_col)) == ["김철수", "홍길동"]
            and QApplication.clipboard().text() == "hong@example.com",
            "I15 표 오른쪽 메뉴 — 즐겨찾기 탭에 넣기 ▸·할 일에 넣기 ▸·이메일 복사·삭제", "%s %r" % (top, QApplication.clipboard().text()))
        chk(P.emails_text([{"emails": ["a@x.com", "b@x.com"]}, {"emails": ["A@X.com"]}, {"emails": []}]) == "a@x.com, b@x.com",
            "I15 이메일 복사 = 쉼표로 이음, 같은 주소 한 번, 메일 없는 명함 건너뜀")
        # 사람 칸에서 골라 다른 탭에 끌어 놓으면 복사(지금 탭에서는 그대로)
        dlg.fav_tabs.setCurrentIndex(tabs.index("동료"))
        pump(timeout=0.1)
        dlg.fav.clearSelection()
        for i in range(dlg.fav.count()):
            if dlg.fav.item(i).data(Qt.ItemDataRole.UserRole) == kim["id"]:
                dlg.fav.item(i).setSelected(True)
        ti = [dlg.fav_tabs.tabData(i) for i in range(dlg.fav_tabs.count())].index(g_t)
        n = dlg._drop_on_tab(ti, dlg.fav)
        chk(n == 1 and sorted(c["name"] for c in P.fav_members(st, g_t)) == ["김철수", "홍길동"] and dlg.fav.count() == 2
            and P.card_by_id(st, kim["id"])["memo"].startswith("[%s ~ 계속] 견적 보내기" % today_s),
            "I15 사람 칸 → 다른 탭에 끌어 놓으면 복사(할 일이면 메모 맨 위 기록), 지금 탭은 그대로")
        chk(dlg._drop_on_tab(0, dlg.fav) == 0 and dlg._drop_on_tab(0, dlg.table) == 0, "I15 '최근' 에는 넣을 수 없음")
        dlg._fav_menu(dlg.fav.visualItemRect(dlg.fav.selectedItems()[0]).center())
        fm = [a.text() for a in shown[-1].actions() if a.text()]
        chk(fm[:2] == ["내용 복사", "이메일 복사"] and "다른 탭에 복사" in fm and "새 할 일로" in fm and fm[-1] == "탭에서 빼기",
            "I15 사람 메뉴 — 내용·이메일 복사·다른 탭에 복사·새 탭/할 일로·빼기", str(fm))
        # 탭 메뉴 — 이메일 복사·탭 마감 [?]·탭 삭제 [?]
        dlg.fav_tabs.setCurrentIndex(ti)
        dlg._fav_tab_menu(dlg.fav_tabs.tabRect(ti).center())
        m = shown[-1]
        wacts = {a.text(): a for a in m.actions() if isinstance(a, QWidgetAction)}
        info = []
        _orig_info = QMessageBox.information
        QMessageBox.information = staticmethod(lambda *a, **k: info.append(a[1:3]) or QMessageBox.StandardButton.Ok)
        try:
            q = [b for b in wacts["탭 삭제"].defaultWidget().findChildren(QToolButton) if b.text() == "?"] if "탭 삭제" in wacts else []
            if q:
                QTest.mouseClick(q[0], Qt.MouseButton.LeftButton)
        finally:
            QMessageBox.information = _orig_info
        chk(set(wacts) == {"탭 마감", "탭 삭제"} and q and info and "메모" in info[-1][1] and P.todo_info(st, g_t) is not None,
            "I15 탭 메뉴의 '탭 마감'·'탭 삭제' 오른쪽 [?] — 누르면 설명만(실행하지 않음)", str(info))
        act(m, "이메일 복사").trigger()
        chk(QApplication.clipboard().text() == "hong@example.com", "I15 탭 메뉴 '이메일 복사' = 그 탭 사람 모두")
        # 탭 마감 → 마감한 탭 ▸ 보기·다시 열기
        chk(dlg.tab_close(g_col, ask=False) and g_col not in [dlg.fav_tabs.tabData(i) for i in range(dlg.fav_tabs.count())]
            and g_col in [c for c, _n, _t in P.closed_tabs(st, today_s)] and P.fav_members(st, g_col),
            "I15 탭 마감 — 탭 줄에서 숨고 지우지 않음(마감한 탭)")
        dlg.tab_peek(g_col)
        peek_on = dlg._fav_gid() == g_col
        dlg.fav_tabs.setCurrentIndex(1)
        pump(timeout=0.2)
        chk(peek_on and g_col not in [dlg.fav_tabs.tabData(i) for i in range(dlg.fav_tabs.count())],
            "I15 마감한 탭 '보기' 는 잠시 — 다른 탭을 고르면 다시 숨음")
        dlg.tab_reopen(g_col)
        chk(g_col in [dlg.fav_tabs.tabData(i) for i in range(dlg.fav_tabs.count())], "I15 다시 열기")
        # 탭 삭제 — 할 일로 적은 메모 글도 지움(사람이 고친 다른 글은 그대로)
        hm0 = P.card_by_id(st, hong["id"])["memo"]
        P.update_card(st, hong["id"], {"memo": hm0 + "\n손으로 쓴 줄"})
        g_old = P.todo_add(st, {"title": "옛 할 일", "memo": "", "start": today_s, "end": ""}, [hong["id"]], "계속")
        st.con.execute("UPDATE fav_members SET memo_entry='' WHERE group_id=?", (g_old,))   # 글을 기억하지 않던 옛 할 일
        st.con.commit()
        chk(dlg.tab_delete(g_t, ask=False) and dlg.tab_delete(g_old, ask=False)
            and P.card_by_id(st, hong["id"]) and P.card_by_id(st, kim["id"]) and os.path.exists(hong["front"]),
            "I15 탭 삭제 — 명함 행·정리본 파일은 그대로")
        hm = P.card_by_id(st, hong["id"])["memo"]
        km = P.card_by_id(st, kim["id"])["memo"]
        chk("견적 보내기" not in hm and "옛 할 일" not in hm and hm.endswith("손으로 쓴 줄") and "견적 보내기" not in km
            and dlg.eds["name"].text() and P.todo_info(st, g_t) is None,
            "I15 탭 삭제 — 그 할 일로 메모에 적은 글을 지움(옛 할 일은 지금 제목·기간으로), 손으로 쓴 줄은 그대로", repr(hm[-40:]))
        P.update_card(st, hong["id"], {"memo": hm0})
        # 최근 탭 — 세부 칸에 RECENT_MS 넘게 본 명함, 빼기만, 기간
        dlg._recent_timer.setInterval(60)
        dlg.table.setCurrentCell(dlg.row_of_id(kim["id"]), 0)
        pump(lambda: kim["id"] in [c["id"] for c in P.recent_list(st)], timeout=2)
        P.recent_add(st, hong["id"], "2020-01-05 10:00:00")
        dlg.fav_tabs.setCurrentIndex(0)
        pump(timeout=0.1)
        ids_1w = dlg.fav_ids()
        dlg.cb_recent.setCurrentIndex(dlg.cb_recent.findData("custom"))
        dlg.d_recent_from.setDate(QDate(2020, 1, 1))
        dlg.d_recent_to.setDate(QDate(2020, 1, 31))
        pump(timeout=0.1)
        ids_2020 = dlg.fav_ids()
        chk(kim["id"] in ids_1w and hong["id"] not in ids_1w and ids_2020 == [hong["id"]] and dlg.cb_recent.isVisible(),
            "I15 최근 — 세부 칸에 오래 본 명함이 저절로, 기간(1주·지정)으로 거름", "%s %s" % (ids_1w, ids_2020))
        dlg.fav.item(0).setSelected(True)
        QTest.keyClick(dlg.fav, Qt.Key.Key_Delete)
        chk(hong["id"] not in [c["id"] for c in P.recent_list(st)] and dlg.fav.count() == 0, "I15 최근 — Delete 로 빼기")
        dlg.cb_recent.setCurrentIndex(0)
        # 탭을 누르면 목록 표에 그 탭 명단 — 찾기 칸을 고치면 찾기 결과로
        ci = [dlg.fav_tabs.tabData(i) for i in range(dlg.fav_tabs.count())].index(g_col)
        QTest.mouseClick(dlg.fav_tabs, Qt.MouseButton.LeftButton, pos=dlg.fav_tabs.tabRect(ci).center())
        pump(timeout=0.3)
        names_tab = sorted(dlg.table.item(r, 0).text() for r in range(dlg.table.rowCount()))
        lbl = dlg.lbl_count.text()
        dlg.ed_find.setText("")
        dlg.ed_find.setText(" ")
        pump(lambda: dlg.table.rowCount() >= 3, timeout=3)
        chk(names_tab == ["김철수", "홍길동"] and "동료" in lbl and dlg.table.rowCount() >= 3,
            "I15 탭을 누르면 목록 표에 그 탭 사람들, 찾기 칸을 고치면 찾기 결과로", "%s %r %d" % (names_tab, lbl, dlg.table.rowCount()))
        dlg.ed_find.setText("")
        pump(timeout=0.4)
        dlg.tab_delete(g_col, ask=False)
    finally:
        QMenu.exec = _orig_exec
        QInputDialog.getText = _orig_get
    # I16 찾기 칸을 고르면 전체 목록 · 사람 칸 키보드 이동 (사용자 지시 261119)
    g_fav = dlg.fav_tabs.tabData(1)
    dlg.fav_add_selected([hong, kim], gid=g_fav)
    QTest.mouseClick(dlg.fav_tabs, Qt.MouseButton.LeftButton, pos=dlg.fav_tabs.tabRect(1).center())
    pump(timeout=0.3)
    n_tab = dlg.table.rowCount()
    n_all = len(P.find(dlg._store(), ""))
    dlg.ed_find.clear()
    QTest.mouseClick(dlg.ed_find, Qt.MouseButton.LeftButton)
    pump(lambda: dlg.table.rowCount() == n_all, timeout=3)
    chk(n_tab == len(P.fav_members(dlg._store(), g_fav)) < n_all and dlg.table.rowCount() == n_all and dlg._table_tab is None,
        "I16 탭 명단을 보다가 빈 찾기 칸을 누르면 전체 목록", "%d %d %d" % (n_tab, dlg.table.rowCount(), n_all))
    dlg.fav_tabs.setCurrentIndex(1)
    pump(timeout=0.1)
    dlg.fav.setFocus()
    dlg.fav.setCurrentRow(0)
    pump(timeout=0.1)
    first = dlg.fav.item(0).data(Qt.ItemDataRole.UserRole)
    dlg._show_card_id(first)                            # 누르기 전에는 첫 사람을 보고 있다
    pump(timeout=0.1)
    shown_first = dlg._card and dlg._card["id"] == first
    QTest.keyClick(dlg.fav, Qt.Key.Key_Right)
    pump(timeout=0.2)
    second = dlg.fav.item(1).data(Qt.ItemDataRole.UserRole) if dlg.fav.count() > 1 else None
    chk(shown_first and dlg.fav.count() > 1 and dlg._card and dlg._card["id"] == second != first,
        "I16 사람 칸을 키보드(→)로 옮기면 그 명함을 보임", "%s %s %s" % (first, second, dlg._card and dlg._card["id"]))
    # I18 사람을 고르면 늘 목록에서 그 줄 — 목록에 없으면 탭 명단으로, 이미 보던 명함이어도 (사용자 보고 261119)
    dlg.ed_find.setText("홍길동")
    pump(lambda: dlg.table.rowCount() == 1, timeout=3)
    dlg.fav_tabs.setCurrentIndex(1)
    pump(timeout=0.1)
    k_it = next((dlg.fav.item(i) for i in range(dlg.fav.count()) if dlg.fav.item(i).data(Qt.ItemDataRole.UserRole) == kim["id"]), None)

    def sel_ids():
        return sorted({dlg.table.item(i.row(), 0).data(Qt.ItemDataRole.UserRole) for i in dlg.table.selectedIndexes()})
    if k_it is not None:
        QTest.mouseClick(dlg.fav.viewport(), Qt.MouseButton.LeftButton, pos=dlg.fav.visualItemRect(k_it).center())
        pump(timeout=0.3)
    ok_a = (k_it is not None and dlg.row_of_id(kim["id"]) >= 0 and dlg.table.currentRow() == dlg.row_of_id(kim["id"])
            and sel_ids() == [kim["id"]] and dlg._card and dlg._card["id"] == kim["id"])
    chk(ok_a, "I18 목록(찾기 결과)에 없는 사람을 고르면 목록을 탭 명단으로 바꾸고 그 줄을 고름",
        "%s %s" % (dlg.table.rowCount(), sel_ids()))
    dlg.table.clearSelection()
    if k_it is not None:
        k_it = next(dlg.fav.item(i) for i in range(dlg.fav.count()) if dlg.fav.item(i).data(Qt.ItemDataRole.UserRole) == kim["id"])
        QTest.mouseClick(dlg.fav.viewport(), Qt.MouseButton.LeftButton, pos=dlg.fav.visualItemRect(k_it).center())
        pump(timeout=0.3)
    chk(sel_ids() == [kim["id"]], "I18 이미 보던 명함을 다시 골라도 목록에서 그 줄을 고름", str(sel_ids()))
    dlg.ed_find.setText("")
    pump(lambda: dlg._table_tab is None and dlg.table.rowCount() >= 3, timeout=3)
    # I8 주소록 가져오기(리멤버 꼴 vCard) — 모두 넣고 곧바로 [중복 검토] 창(§5.24.8), 창에서 합치면 같은 사람은 빈 칸만
    from viewer.widgets import bizcard_dupe_dialog as _DD
    merged = []

    def merge_now():
        dd_ = getattr(dlg, "dupe_dlg", None)
        if dd_ is not None and dd_.isVisible():
            merged.append(dd_.apply(ask=False))
            dd_.close()
            dlg.after_dupes()
            dlg.raise_(); dlg.activateWindow()   # 모달 없이 띄운 창을 닫은 뒤 — 오프스크린은 활성 창이 돌아오지 않는다
            pump(timeout=0.1)
        else:
            merged.append(None)
    vf = TMP / "contacts.vcf"
    vf.write_text("BEGIN:VCARD\r\nVERSION:3.0\r\nN:;김철수;;;\r\nTEL;TYPE=work,cell:010-0000-0003\r\nEMAIL;TYPE=work:kim@example.com\r\n"
                  "ORG:다른회사;\r\nEND:VCARD\r\n"
                  "BEGIN:VCARD\r\nVERSION:3.0\r\nN:;박새사람;;;\r\nTEL;TYPE=work,cell:010-0000-0009\r\nORG:차카타;영업팀\r\n"
                  "TITLE:과장\r\nADR;TYPE=work:;가짜시 가짜로 1;;;;;\r\nEND:VCARD\r\n", encoding="utf-8")
    res = dlg.import_contacts(str(vf), ask=False)
    merge_now()
    st = S.BizcardStore()
    kim = P.find(st, "김철수")[0]
    new = P.find(st, "박새사람")
    chk(res == 2 and merged == [1], "I8 둘 다 넣고 병합 창에서 같은 번호 1묶음 합침", str((res, merged)))
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
    merge_now()
    chk(comp_of() == [("최가짜", "구글회사")], "I10 구글에서 새 사람", str(comp_of()))
    dlg.import_contacts(vcf("최가짜", "리멤버회사"), ask=False, source="remember")
    merge_now()
    chk(comp_of() == [("최가짜", "리멤버회사")], "I10 리멤버가 구글 값을 이김", str(comp_of()))
    dlg.import_contacts(vcf("최가짜", "구글새회사"), ask=False, source="google")
    merge_now()
    chk(comp_of() == [("최가짜", "리멤버회사")], "I10 구글은 리멤버 값을 덮지 않음", str(comp_of()))
    dlg.import_contacts(vcf("김철수", "리멤버회사", "010-0000-0003"), ask=False, source="remember")
    merge_now()
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
    merge_now()
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
    # I20 옛 상한(500장)보다 많은 명함 — 빈 찾기 칸을 실제로 누르면 전부(사용자 보고 261119 '전체 목록이 안보이고 일부 목록만')
    n_fake = 1200
    st = S.BizcardStore()
    st.con.executemany(
        "INSERT INTO cards(front, name, company, title, phones, emails, scanned, tags, en) VALUES(?,?,?,?,?,?,?,?,?)",
        [(str(TMP / "fake" / ("f%04d.jpg" % i)), "가짜%04d" % i, "가짜회사%d" % (i % 7), "",
          '[["cell","010-0000-%04d"]]' % (1000 + i), "[]", "2021-01-%02d" % (i % 28 + 1), "[]", "{}") for i in range(n_fake)])
    st.con.commit()
    n_db = st.con.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    st.close()
    QTest.mouseClick(dlg.fav_tabs, Qt.MouseButton.LeftButton, pos=dlg.fav_tabs.tabRect(1).center())   # 탭 명단을 보다가
    pump(timeout=0.3)
    dlg.ed_find.clear()
    t0 = time.monotonic()
    QTest.mouseClick(dlg.ed_find, Qt.MouseButton.LeftButton)                                        # 빈 찾기 칸을 누름
    pump(lambda: dlg.table.rowCount() == n_db, timeout=5)
    dt = time.monotonic() - t0
    chk(n_db > 500 and dlg.table.rowCount() == n_db and dlg.lbl_count.text() == "%d장" % n_db,
        "I20 옛 상한(500)보다 많은 명함 — 빈 찾기 칸을 누르면 전부·위 줄 n장",
        "%d/%d %r" % (dlg.table.rowCount(), n_db, dlg.lbl_count.text()))
    chk(dt < 1.5, "I20 전체 목록이 곧바로(1초 남짓 안)", "%.2fs" % dt)
    t0 = time.monotonic()
    dlg.refresh()
    dt_r = time.monotonic() - t0
    chk(dt_r < 1.0, "I20 전체 목록 다시 채우기 메인 정지 < 1초", "%.2fs" % dt_r)
    hh = dlg.table.horizontalHeader()                     # click_head 가 쓰는 머리말 — 지금 창의 것
    click_head(0)
    if hh.sortIndicatorOrder() != Qt.SortOrder.AscendingOrder:
        click_head(0)
    a_up = col_names()
    click_head(0)
    a_dn = col_names()
    chk(len(a_up) == n_db and a_up == sorted(a_up) and a_dn == sorted(a_up, reverse=True),
        "I20 많은 명함도 머리말 정렬·반대")
    r_last = dlg.row_of_id(max(c["id"] for c in dlg._rows))
    dlg.table.setCurrentCell(r_last, 0)
    pump(timeout=0.2)
    chk(dlg._card is not None and dlg._card["name"].startswith("가짜") and dlg.table.item(r_last, 0).text() == dlg._card["name"],
        "I20 아래쪽 줄을 골라도 그 명함이 세부 칸에")
    # I21 찾기 칸 앞 구분 · Enter 가 [해시태그] 를 누르지 않음 · [해시태그] 는 늘 '해시태그 수정' 창(사용자 지시 261119)
    st = S.BizcardStore()
    st.con.executemany("INSERT INTO cards(front, name, company, phones, emails, scanned, tags, en) VALUES(?,?,?,?,?,?,?,?)",
                       [("contact:zz1", "Jane Fakeperson", "Acme", "[]", "[]", "2021-02-01", "[]", "{}"),
                        (str(TMP / "fake" / "en1.jpg"), "Zed Nobody", "Acme", "[]", "[]", "2021-02-01", "[]", "{}")])
    st.con.commit()
    st.close()
    cbk = getattr(dlg, "cb_kind", None)
    chk(cbk is not None and dlg.layout().itemAt(0).layout().indexOf(cbk) == 0
        and [cbk.itemData(i) for i in range(cbk.count())] == ["all", "ko", "en", "card", "nocard"],
        "I21 찾기 칸 앞에 구분(전체·한글·영어·명함 있음·명함 없음)")
    got = {}
    if cbk is not None:
        dlg.ed_find.clear()
        dlg.refresh()
        for k in ("all", "ko", "en", "card", "nocard"):
            cbk.setCurrentIndex(cbk.findData(k))
            pump(timeout=0.1)
            got[k] = list(dlg._rows)
    import re as _re
    hz = lambda c: bool(_re.search("[가-힣]", c.get("name") or ""))
    nm = lambda rows: sorted(c["name"] for c in rows)
    chk(got and "Jane Fakeperson" in nm(got["en"]) and "Zed Nobody" in nm(got["en"]) and not any(hz(c) for c in got["en"])
        and got["ko"] and all(hz(c) for c in got["ko"]) and len(got["ko"]) + len(got["en"]) <= len(got["all"])
        and all(str(c["front"]).startswith("contact:") for c in got["nocard"]) and "Jane Fakeperson" in nm(got["nocard"])
        and not any(str(c["front"]).startswith("contact:") for c in got["card"])
        and len(got["card"]) + len(got["nocard"]) == len(got["all"]) and dlg.lbl_count.text() == "%d장" % len(got["nocard"]),
        "I21 한글·영어 = 이름 글자, 명함 있음·없음 = 그림(주소록 명함은 없음)", str({k: len(v) for k, v in got.items()}))
    # Enter — 세부 칸을 고치다 Enter 를 눌러도 [해시태그] 창이 뜨지 않음
    hits = []
    _orig_et = dlg.edit_tags
    dlg.edit_tags = lambda *a, **k: hits.append(1)
    try:
        ed = dlg.eds["dept"]
        QTest.mouseClick(ed, Qt.MouseButton.LeftButton)
        QTest.keyClicks(ed, "x")
        QTest.keyClick(ed, Qt.Key.Key_Return)
        QTest.keyClick(dlg.ed_find, Qt.Key.Key_Return)
        pump(timeout=0.2)
    finally:
        dlg.edit_tags = _orig_et
    chk(not hits and not any(b.isDefault() or b.autoDefault() for b in dlg.findChildren(QPushButton) if b.window() is dlg),
        "I21 Enter 가 [해시태그] 를 누르지 않음(기본 단추 없음)",
        "%d %s" % (len(hits), [b.text() for b in dlg.findChildren(QPushButton) if b.window() is dlg and (b.isDefault() or b.autoDefault())]))
    if dlg._dirty:
        dlg._load(dlg._card)                              # 고친 'x' 는 버림(아래 창 열기에서 묻지 않게)
        dlg._set_dirty(False)
    # 그림 없는 명함도 '해시태그 수정' 창 — 옛 '해시태그 편집' 창(TagEditDialog)은 뜨지 않음
    import viewer.widgets.tag_edit_dialog as _ted
    seen2, old_ed = {}, []
    def _fake_exec2(self):
        seen2["paths"] = list(self._paths)
        seen2["tips"] = [self.lst_files.item(i).toolTip() for i in range(self.lst_files.count())]
        self.apply_tags(True, tags=["주소록모임"])
        return 0
    _ted_exec = _ted.TagEditDialog.exec
    _ted.TagEditDialog.exec = lambda self: old_ed.append(1) or 0
    _tad.TagApplyDialog.exec = _fake_exec2
    try:
        cbk.setCurrentIndex(cbk.findData("nocard"))
        pump(timeout=0.1)
        jane = next(c for c in dlg._rows if c["name"] == "Jane Fakeperson")
        dlg.table.clearSelection()
        dlg.table.selectRow(dlg.row_of_id(jane["id"]))
        pump(timeout=0.1)
        QTest.mouseClick(dlg.btn_tags, Qt.MouseButton.LeftButton)
        pump(timeout=0.2)
    finally:
        _tad.TagApplyDialog.exec = _orig_exec
        _ted.TagEditDialog.exec = _ted_exec
    st = S.BizcardStore()
    j2 = P.card_by_id(st, jane["id"])
    st.close()
    vkeys = [k for k in mw.bookmark_tree._tags._data if "polypinax-bizcard-tags" in k]
    chk(not old_ed and len(seen2.get("paths", [])) == 1 and os.path.basename(seen2["paths"][0]) == "Jane Fakeperson_Acme"
        and "polypinax" not in (seen2.get("tips") or [""])[0],
        "I21 그림 없는 주소록 명함도 '해시태그 수정' 창(옛 편집 창 아님, 이름_회사로 보임)", "%s %s" % (old_ed, seen2))
    chk("주소록모임" in (j2["tags"] or []) and not vkeys, "I21 창에서 붙인 태그가 명함 DB 에, 실제 태그 저장소에는 가짜 경로가 남지 않음",
        "%s %d" % (j2["tags"], len(vkeys)))
    cbk.setCurrentIndex(0)
    # I22 이름은 굵게 — 목록 표 이름 칸·세부 이름 칸(사용자 지시 261119)
    pump(timeout=0.1)
    from PyQt6.QtWidgets import QStyleOptionViewItem as _SOV, QStyledItemDelegate as _SD
    mdl = dlg.table.model()
    def _opt_font(col):
        o = _SOV()
        o.font = dlg.table.font()
        d = _SD()
        d.initStyleOption(o, mdl.index(0, col))     # 표가 칸을 그릴 때와 같은 길로 글꼴을 합침
        return o.font
    fn, fc = _opt_font(0), _opt_font(1)
    chk(fn.bold() and not fc.bold() and fn.pointSizeF() == dlg.table.font().pointSizeF()
        and dlg.eds["name"].font().bold() and not dlg.eds["company"].font().bold(),
        "I22 목록 이름 칸·세부 이름 칸만 굵게(크기는 표 글꼴 그대로)",
        "%s %s %s %s" % (fn.bold(), fc.bold(), dlg.eds["name"].font().bold(), dlg.eds["company"].font().bold()))

    print("\n=== I24. 세부내용 묶음·테두리 없는 칸·이름과 휴대폰 굵게 (261120-4, 사용자 지시 261120) ===")
    from PyQt6.QtWidgets import QLabel as _QL
    import viewer.widgets.bizcard_find_dialog as BF
    box = getattr(dlg, "detail_box", None)

    def _edge_px(ed):
        """묶음을 그려 입력 칸 왼쪽 가장자리 바로 안쪽 점의 색 — 테두리가 있으면 테두리·입력 바탕 색."""
        img = box.grab().toImage()
        p = ed.mapTo(box, ed.rect().topLeft())
        return img.pixelColor(p.x() + 1, p.y() + ed.height() // 2).name()
    def _card_px():
        """그린 카드에서 — 제목 띠 왼쪽 안쪽 점·본문 칸 가장자리 점·메모 안쪽 점의 색."""
        img = box.grab().toImage()
        hd = getattr(dlg, "detail_head", None)
        hp = hd.mapTo(box, hd.rect().topLeft()) if hd is not None else None
        mp = dlg.ed_memo.mapTo(box, dlg.ed_memo.rect().topLeft())
        return ((img.pixelColor(hp.x() + 4, hp.y() + hd.height() // 2).name() if hp is not None else ""),
                _edge_px(dlg.eds["company"]),
                img.pixelColor(mp.x() + dlg.ed_memo.width() - 6, mp.y() + dlg.ed_memo.height() - 6).name(),
                _head_px())

    def _head_px():
        """목록 표 머리말(첫 칸 왼쪽 안쪽 점)의 색."""
        hh = dlg.table.horizontalHeader()
        img = hh.grab().toImage()
        return img.pixelColor(6, hh.height() // 2).name()

    def _want(theme):
        d = getattr(BF, "DETAIL_BG", {}).get(theme)
        return (d.get("head"), d.get("body"), d.get("memo"), d.get("head")) if isinstance(d, dict) else None
    pump(timeout=0.1)
    ok_box = box is not None and box.isAncestorOf(dlg.eds["name"])
    hd = getattr(dlg, "detail_head", None)
    px_l = _card_px() if box is not None else ()
    chk(ok_box and hd is not None and hd.text() == "세부내용" and bool(hd.alignment() & Qt.AlignmentFlag.AlignHCenter)
        and hd.font().bold() and box.isAncestorOf(dlg.ed_memo) and not box.isAncestorOf(dlg.btn_save)
        and px_l == _want("light") and len(set(px_l)) == 3,
        "I24 세부내용 카드 — 가운데 굵은 제목 띠·옅은 본문(칸 가장자리 = 본문 바탕, 테두리 없음)·더 옅은 메모, [저장]은 밖·목록 머리말 = 띠 색",
        "%s %s %s" % (ok_box, px_l, _want("light")))
    light_bg = (_want("light") or ("?",))[0]

    def _rows_px():
        """목록 표에서 고르지 않은 두 줄(짝·홀)의 빈 자리 색 — 직함 칸 오른쪽 끝 안쪽."""
        dlg.table.clearSelection()
        pump(timeout=0.1)
        img = dlg.table.viewport().grab().toImage()
        out = []
        for r in (2, 3):
            rc = dlg.table.visualRect(dlg.table.model().index(r, 2))
            out.append(img.pixelColor(rc.right() - 3, rc.center().y()).name())
        return tuple(out)
    d_l = getattr(BF, "DETAIL_BG", {}).get("light", {})
    rp = _rows_px()
    chk(isinstance(d_l, dict) and rp == (d_l.get("memo"), d_l.get("body")) and dlg.table.alternatingRowColors()
        and not dlg.table.showGrid(),
        "I24 목록 줄은 메모 바탕·본문 바탕을 번갈아(카드와 한 벌), 격자 선 없음", "%s %s" % (rp, d_l))
    bolds = {k: ed.font().bold() for k, ed in dlg.eds.items()}
    chk(bolds.get("name") and bolds.get("cell") and not any(v for k, v in bolds.items() if k not in ("name", "cell")),
        "I24 세부 칸은 이름·휴대폰만 굵게", str(bolds))
    mw.apply_theme("dark")
    pump(timeout=0.3)
    px_d = _card_px() if box is not None else ()
    mw.apply_theme("light")
    pump(timeout=0.3)
    px_l2 = _card_px() if box is not None else ()
    chk(px_d == _want("dark") and px_l2 == _want("light") and _want("dark") != _want("light"),
        "I24 다크로 바꾸면 카드 세 색도 다크 값, 돌아오면 라이트 값", "%s %s" % (px_d, px_l2))

    # I25 사진창 — '인물 사진' 제목 글 없음·위 명함과 아래 인물 사진 사이 가로 구분선(사용자 지시 261120)
    from PyQt6.QtWidgets import QLabel as _QL2
    # 구분선은 사진창 손잡이가 그린다(261120-22 — 끌어 크기 조절, 검사 test_bizcard_photo_handle_261120)
    sep = dlg.photo_split.handle(1) if dlg.photo_split.count() > 1 else None
    titles = [w.text() for w in dlg.findChildren(_QL2) if w.text() == "인물 사진"]
    sep_px = ""
    if sep is not None:
        y_sep = sep.mapTo(dlg, sep.rect().center()).y()
        y_pv = dlg.pv.mapTo(dlg, dlg.pv.rect().bottomLeft()).y()
        y_ph = dlg.photo_view.mapTo(dlg, dlg.photo_view.rect().topLeft()).y()
        sep_px = sep.grab().toImage().pixelColor(sep.width() // 2, sep.height() // 2).name()
    chk(not titles and sep is not None and sep.isVisible() and y_pv < y_sep < y_ph
        and sep_px == getattr(BF, "DETAIL_BG", {}).get("light", {}).get("border"),
        "I25 사진창 — '인물 사진' 글 없음, 명함과 인물 사진 사이 1px 구분선(카드 테 색 — 손잡이가 그림)", "%s %s %s" % (titles, sep, sep_px))

    # I26 목록 머리말 높이·위 끝 = 세부내용 제목 띠(사용자 지시 261120 '목록 머리글 높이를 오른쪽 세부내용과 맞춰')
    hh2, hd2 = dlg.table.horizontalHeader(), getattr(dlg, "detail_head", None)
    from PyQt6.QtWidgets import QStyleFactory as _QSF
    _w11 = _QSF.create("windows11") or _QSF.create("windowsvista")   # 명함 프로그램은 앱 스타일을 바꾸지 않는다 — 정렬 화살표를 글 위에 그림
    if _w11 is not None:
        hh2.setStyle(_w11)
        dlg._detail_css = ""
        dlg._style_detail()
        pump(timeout=0.2)
    y_h = hh2.mapTo(dlg, hh2.rect().topLeft()).y()
    y_d = hd2.mapTo(dlg, hd2.rect().topLeft()).y() if hd2 is not None else -99
    chk(hd2 is not None and hh2.height() == hd2.height() and abs(y_h - y_d) <= 1,
        "I26 목록 머리말 높이·위 끝이 세부내용 제목 띠와 같음",
        "%d/%s %d/%d" % (hh2.height(), hd2.height() if hd2 is not None else None, y_h, y_d))

    print("\n=== I27. 새 명함 입력 — 명함찾기·명함 관리 단추, 그림 없는/그림 명함, 인물 사진, 같은 사람 물음 (261120-15) ===")
    import viewer.widgets.bizcard_new_dialog as NDm
    bnew = getattr(dlg, "btn_new_card", None)
    order_ok = False
    if bnew is not None:
        lay = None
        for i in range(dlg.layout().count()):
            it = dlg.layout().itemAt(i)
            if it.layout() is not None and it.layout().indexOf(dlg.btn_manage) >= 0:
                lay = it.layout()
        order_ok = lay is not None and lay.indexOf(bnew) == 0 and lay.indexOf(dlg.btn_manage) == 1
    chk(order_ok, "I27 명함찾기 아래 줄 맨 앞에 [새 명함 입력]([명함 관리] 왼쪽)")
    jpg(TMP / "new_front.jpg", "mistyrose")
    jpg(TMP / "new_photo.jpg", "honeydew", size=(120, 160))
    plan = []

    def _fake_new_exec(self):
        """입력 창 — 실제 키·마우스로 칸을 채우고 [저장]을 누른 뒤 배경 저장이 끝날 때까지."""
        name, comp, cell, mail, front, photo = plan.pop(0)
        QTest.mouseClick(self.eds["name"], Qt.MouseButton.LeftButton)
        type_ko(self.eds["name"], name)
        QTest.mouseClick(self.eds["company"], Qt.MouseButton.LeftButton)
        type_ko(self.eds["company"], comp)
        QTest.keyClicks(self.eds["cell"], cell)
        QTest.keyClicks(self.eds["email"], mail)
        if front:
            self.set_side("front", front)
        if photo:
            self.add_photos([photo])
        QTest.mouseClick(self.btn_save, Qt.MouseButton.LeftButton)
        pump(lambda: self.new_id or not self.busy and self.result(), timeout=15)
        return self.result()
    asked3 = []
    _o_q3, _o_exec3 = QMessageBox.question, NDm.NewCardDialog.exec
    QMessageBox.question = staticmethod(lambda *a, **k: asked3.append(a[2] if len(a) > 2 else "") or QMessageBox.StandardButton.No)
    NDm.NewCardDialog.exec = _fake_new_exec
    dlg._bz_folder = str(F)
    try:
        # A — 그림 없이(같은 메일의 홍길동이 있음 → 중복 검토 물음)
        plan.append(("새가짜", "가짜상사", "01000000099", "hong@example.com", "", str(TMP / "new_photo.jpg")))
        if bnew is not None:
            QTest.mouseClick(bnew, Qt.MouseButton.LeftButton)
        nd = getattr(dlg, "new_dlg", None)
        st = S.BizcardStore()
        ca = P.card_by_id(st, nd.new_id) if nd is not None and nd.new_id else None
        ph_a = P.person_photos(P.photo_front(ca, str(F))) if ca else []
        chk(ca is not None and str(ca["front"]).startswith("contact:") and ca["name"] == "새가짜" and "직접입력" in (ca["tags"] or [])
            and ca["phones"] and ca["phones"][0][0] == "cell" and ca["phones"][0][1] == "010-0000-0099"
            and len(ph_a) == 1 and os.path.basename(ph_a[0]) == "새가짜_가짜상사.jpg"
            and dlg._card is not None and dlg._card["id"] == ca["id"] and asked3 and "1" in asked3[-1],
            "I27 그림 없이 넣으면 그림 없는 명함(#직접입력·번호 꼴)·인물 사진은 '인물\\성명_회사명'·목록에서 그 명함·같은 메일이면 중복 검토 물음",
            "%s %s %s %s" % (ca and (ca["front"], ca["tags"], ca["phones"]), ph_a, dlg._card and dlg._card.get("name"), asked3))
        # B — 앞면 그림을 붙이면 그림 명함(정리본 성명_회사명)
        plan.append(("그림가짜", "나다상사", "01000000098", "pic@example.com", str(TMP / "new_front.jpg"), str(TMP / "new_photo.jpg")))
        n_ask = len(asked3)
        QTest.mouseClick(bnew, Qt.MouseButton.LeftButton)
        nd = dlg.new_dlg
        cb_ = P.card_by_id(st, nd.new_id) if nd.new_id else None
        fr = str(cb_["front"]) if cb_ else ""
        ph_b = P.person_photos(fr) if cb_ else []
        chk(cb_ is not None and os.path.exists(fr) and os.path.basename(fr).lower() == "그림가짜_나다상사.jpg"
            and os.path.dirname(fr).lower() == str(OUT).lower() and "직접입력" in (cb_["tags"] or [])
            and os.path.exists(TMP / "new_front.jpg") and len(ph_b) == 1 and len(asked3) == n_ask,
            "I27 앞면 그림을 붙이면 그림 명함(정리\\성명_회사명.jpg, 원본 그대로)·인물 사진·같은 사람 없으면 묻지 않음",
            "%s %s %s" % (fr, ph_b, asked3[n_ask:]))
        st.close()
        # C — 명함 관리 창: [새 명함 읽기] 오른쪽에 [새 명함 입력], 누르면 같은 창
        G2 = TMP / "manual_empty"
        G2.mkdir(exist_ok=True)
        from viewer.widgets import bizcard_import_dialog as BD2
        idlg2 = BD2.BizcardImportDialog(str(G2), None, db=TMP / "local" / "bizcard_manual.db")
        idlg2.show()
        pump(timeout=0.3)
        bm = getattr(idlg2, "btn_manual", None)
        tl = idlg2.layout().itemAt(0).layout()
        plan.append(("관리가짜", "", "01000000097", "", "", ""))
        if bm is not None:
            QTest.mouseClick(bm, Qt.MouseButton.LeftButton)
        st2 = S.BizcardStore(TMP / "local" / "bizcard_manual.db")
        cm_ = [r[0] for r in st2.con.execute("SELECT name FROM cards")]
        st2.close()
        chk(bm is not None and tl.indexOf(bm) == tl.indexOf(idlg2.btn_new) + 1 and cm_ == ["관리가짜"],
            "I27 명함 관리 [새 명함 읽기] 오른쪽 [새 명함 입력] — 같은 창으로 넣음", str(cm_))
        idlg2.close()
    finally:
        QMessageBox.question, NDm.NewCardDialog.exec = _o_q3, _o_exec3
    pump(timeout=0.2)

    print("\n=== I23. 흐린 찾기 글 → 전체 목록 · 구분 기억 · 즐겨찾기 이름 굵게 · Gmail 보내기 (사용자 지시 261120) ===")
    import urllib.parse as _up
    import viewer.widgets.bizcard_find_dialog as BF
    dlg.activateWindow()
    dlg.ed_find.clear()
    dlg.refresh()
    pump(timeout=0.1)
    n_all = len(dlg._rows)
    QTest.mouseClick(dlg.ed_find, Qt.MouseButton.LeftButton)
    QTest.keyClicks(dlg.ed_find, "Acme")
    pump(lambda: len(dlg._rows) == 2, timeout=3)
    n_hit = len(dlg._rows)
    r0 = dlg.table.visualRect(dlg.table.model().index(0, 1)).center()
    QTest.mouseClick(dlg.table.viewport(), Qt.MouseButton.LeftButton, pos=r0)   # 칸을 떠남 — 흐려짐
    pump(timeout=0.4)
    dim1, n_leave = bool(dlg.ed_find.property("searchGhostDim")), len(dlg._rows)
    QTest.mouseClick(dlg.ed_find, Qt.MouseButton.LeftButton)                    # 흐린 글을 다시 누름 — 커서 맨 앞
    pump(lambda: len(dlg._rows) == n_all, timeout=2)
    n_home, cur_home, txt_home = len(dlg._rows), dlg.ed_find.cursorPosition(), dlg.ed_find.text()
    chk(n_hit == 2 and dim1 and n_leave == 2 and n_home == n_all and cur_home == 0 and txt_home == "Acme"
        and dlg.ed_find.property("searchGhostDim"),
        "I23 흐린 찾기 글을 다시 누르면(커서 맨 앞) 전체 목록 — 처음 떠날 때는 결과 그대로, 흐린 글은 칸에 남음",
        "%d %s %d %d/%d cur=%d %r" % (n_hit, dim1, n_leave, n_home, n_all, cur_home, txt_home))
    QTest.keyClick(dlg.ed_find, Qt.Key.Key_Right)                               # → 로 되살리기 — 그 글의 결과
    pump(lambda: len(dlg._rows) == 2, timeout=2)
    n_restore = len(dlg._rows)
    QTest.mouseClick(dlg.table.viewport(), Qt.MouseButton.LeftButton, pos=r0)
    pump(timeout=0.3)
    QTest.mouseClick(dlg.ed_find, Qt.MouseButton.LeftButton)
    pump(lambda: len(dlg._rows) == n_all, timeout=2)
    n_home2 = len(dlg._rows)
    QTest.keyClicks(dlg.ed_find, "Zed")                                          # 첫 입력 — 친 글의 결과
    pump(lambda: len(dlg._rows) == 1, timeout=3)
    chk(n_restore == 2 and n_home2 == n_all and dlg.ed_find.text() == "Zed" and [c["name"] for c in dlg._rows] == ["Zed Nobody"],
        "I23 → 로 되살리면 그 글의 결과, 다시 흐린 글을 누르면 전체, 첫 입력이면 친 글의 결과",
        "%d %d %r %s" % (n_restore, n_home2, dlg.ed_find.text(), [c["name"] for c in dlg._rows]))
    dlg.ed_find.clear()
    pump(timeout=0.4)

    # Gmail 보내기 — 브라우저 여는 길은 가짜로 받는다(실제 브라우저를 띄우지 않음)
    st = S.BizcardStore()
    st.con.executemany("INSERT INTO cards(front, name, company, phones, emails, scanned, tags, en) VALUES(?,?,?,?,?,?,?,?)",
                       [("contact:gm%d" % i, "메일가짜%02d" % i, "", "[]", '["fake%02d@example.com"]' % i, "2021-03-01", "[]", "{}")
                        for i in range(150)] + [("contact:gmnone", "메일없음가짜", "", "[]", "[]", "2021-03-01", "[]", "{}")])
    st.con.commit()
    gm_ids = [r[0] for r in st.con.execute("SELECT id FROM cards WHERE front LIKE 'contact:gm%' ORDER BY id")]
    hong_c = next(c for c in P.find(st, "홍길동"))
    g_mail = P.fav_add_group(st, "메일시험")
    P.fav_add(st, g_mail, [hong_c["id"]] + gm_ids)
    st.close()
    dlg._fav_fill_tabs(g_mail)
    pump(timeout=0.2)
    gi = [dlg.fav_tabs.tabData(i) for i in range(dlg.fav_tabs.count())].index(g_mail)
    dlg.fav_tabs.setCurrentIndex(gi)
    pump(timeout=0.2)
    chk(dlg.fav.count() == 152 and all(dlg.fav.item(i).font().bold() for i in range(dlg.fav.count())),
        "I23 즐겨찾기 사람 칸의 이름은 굵게", "%d" % dlg.fav.count())
    opened, asked, info2, ques = [], [], [], []
    shown = []
    _o_exec, _o_get, _o_info, _o_q = QMenu.exec, QInputDialog.getText, QMessageBox.information, QMessageBox.question
    _o_open = getattr(BF, "_open_url", None)
    QMenu.exec = lambda self, *a, **k: shown.append(self)
    QInputDialog.getText = staticmethod(lambda *a, **k: asked.append(k.get("text", "")) or ("me@example.com", True))
    QMessageBox.information = staticmethod(lambda *a, **k: info2.append(a[2] if len(a) > 2 else "") or QMessageBox.StandardButton.Ok)
    QMessageBox.question = staticmethod(lambda *a, **k: ques.append(a[2] if len(a) > 2 else "") or QMessageBox.StandardButton.Yes)
    BF._open_url = lambda u: opened.append(u) or True

    def _act(menu, *path):
        for name in path[:-1]:
            menu = next(a.menu() for a in menu.actions() if a.menu() is not None and a.menu().title() == name)
        return next(a for a in menu.actions() if a.text() == path[-1])

    def _q(u):
        return _up.parse_qs(_up.urlsplit(u).query)
    try:
        dlg._fav_tab_menu(dlg.fav_tabs.tabRect(gi).center())
        _act(shown[-1], "Gmail 보내기", "숨은 참조").trigger()
        pump(timeout=0.1)
        want = {"hong@example.com"} | {"fake%02d@example.com" % i for i in range(150)}
        got_bcc = [a for u in opened for a in ",".join(_q(u).get("bcc", [])).split(",") if a]
        chk(len(opened) >= 2 and all(len(u) <= BF.P.GMAIL_URL_MAX for u in opened) and set(got_bcc) == want
            and len(got_bcc) == len(want) and not any("to" in _q(u) for u in opened)
            and all(u.startswith("https://mail.google.com/mail/?") and _q(u).get("view") == ["cm"] for u in opened),
            "I23 탭 메뉴 'Gmail 보내기 ▸ 숨은 참조' — 그 탭 사람 모두의 메일을 숨은 참조로, 주소가 길면 여러 쓰기 창(각 2000자 이하)",
            "%d %s" % (len(opened), [len(u) for u in opened]))
        chk(asked == [""] and all(_q(u).get("authuser") == ["me@example.com"] for u in opened) and ques
            and any("1" in s for s in info2),
            "I23 보낼 계정을 처음 한 번 묻고 authuser 로 붙임·여러 창이면 먼저 확인·메일 없는 1명은 뺐다고 알림",
            "%s %s %s" % (asked, ques, info2))
        opened.clear(); info2.clear()
        dlg.fav.clearSelection()
        for i in range(dlg.fav.count()):
            if dlg.fav.item(i).data(Qt.ItemDataRole.UserRole) == hong_c["id"]:
                dlg.fav.item(i).setSelected(True)
        dlg._fav_menu(dlg.fav.visualItemRect(dlg.fav.selectedItems()[0]).center())
        fm2 = [a.text() for a in shown[-1].actions() if a.text()]
        _act(shown[-1], "Gmail 보내기", "받는 사람").trigger()
        pump(timeout=0.1)
        chk(fm2[:3] == ["내용 복사", "이메일 복사", "Gmail 보내기"] and len(opened) == 1
            and _q(opened[0]).get("to") == ["hong@example.com"] and "bcc" not in _q(opened[0]) and asked == [""] and not info2,
            "I23 사람 메뉴 'Gmail 보내기 ▸ 받는 사람' — 고른 사람만, 계정은 다시 묻지 않음", "%s %s %s" % (fm2, opened, asked))
        opened.clear()
        dlg._fav_menu(dlg.fav.visualItemRect(dlg.fav.selectedItems()[0]).center())
        _act(shown[-1], "Gmail 보내기", "보낼 계정 바꾸기").trigger()
        chk(asked == ["", "me@example.com"] and not opened, "I23 '보낼 계정 바꾸기' 는 지난 값을 채워 다시 묻고 창은 열지 않음", str(asked))
        st = S.BizcardStore()
        acct = st.meta_get("gmail_account", None)
        st.close()
        chk(acct == "me@example.com", "I23 보낼 계정은 명함 DB meta 에 기억", repr(acct))
        chk(P.gmail_urls(["a@example.com"], "to", "") == ["https://mail.google.com/mail/?view=cm&fs=1&to=a@example.com"]
            and P.gmail_urls([], "bcc", "") == [] and P.email_list([{"emails": ["a@x.com"]}, {"emails": []}, {"emails": ["A@X.com"]}]) == (["a@x.com"], 1),
            "I23 Gmail 주소 만들기(계정 비우면 authuser 없음)·주소 모으기(메일 없는 사람 수)")
    finally:
        QMenu.exec, QInputDialog.getText, QMessageBox.information, QMessageBox.question = _o_exec, _o_get, _o_info, _o_q
        if _o_open is not None:
            BF._open_url = _o_open

    # 구분 기억 — 다시 열면 그대로
    dlg.cb_kind.setCurrentIndex(dlg.cb_kind.findData("en"))
    pump(timeout=0.2)
    dlg.close()
    pump(timeout=0.2)
    mw._action_bizcard_find()
    dlg = mw._bizcard_find_dlg
    pump(lambda: dlg.table.rowCount() > 0, timeout=5)
    pump(timeout=0.3)
    kind2 = dlg.cb_kind.currentData()
    chk(kind2 == "en" and dlg._rows and all(not _re.search("[가-힣]", c.get("name") or "") for c in dlg._rows),
        "I23 찾기 칸 앞 구분은 창을 다시 열어도 그대로(명함 DB meta)", "%s %d" % (kind2, len(dlg._rows)))
    dlg.cb_kind.setCurrentIndex(0)
    dlg.close()
    pump(timeout=0.2)
except Exception:
    import traceback
    traceback.print_exc()
    fails.append("예외")
finish()
