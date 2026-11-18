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
    chk(dlg.thumbs.count() == 2, "B 작은 그림 줄 — 앞면·뒷면", str(dlg.thumbs.count()))
    dlg.ed_find.clear()
    pump(lambda: dlg.table.rowCount() == 3, timeout=3)
    dlg.cb_period.setCurrentIndex(dlg.cb_period.findData("1y"))
    chk(pump(lambda: dlg.table.rowCount() == 2, timeout=3), "B 기간 '최근 1년'", str(dlg.table.rowCount()))
    dlg.cb_period.setCurrentIndex(dlg.cb_period.findData("all"))
    pump(lambda: dlg.table.rowCount() == 3, timeout=3)

    print("\n=== C. 인물 사진 ===")
    r_h = next(i for i, c in enumerate(dlg._rows) if c["name"] == "홍길동")
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
    chk((pdir / "홍길동_가나도로공사 (2).jpg").exists() and dlg.thumbs.count() == 4, "C 둘째는 ' (2)'·작은 그림 줄에 보임",
        str(dlg.thumbs.count()))

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
    other = next(i for i, c in enumerate(dlg._rows) if c["name"] == "김철수")
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
except Exception:
    import traceback
    traceback.print_exc()
    fails.append("예외")
finish()
