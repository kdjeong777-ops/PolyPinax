# -*- coding: utf-8 -*-
"""명함 들이기·확인 표·적용 (명함 SOT §5.10, P2) — 가짜 명함만(실제 명함 값·경로 금지, 명함 SOT §2.1).

실제 MainWindow 로(오프스크린, 실제 설정·데이터 폴더를 쓰지 않는다 — 검사 작성 SOT §14.7.2).
A. 폴더 훑기 — 앞뒤 짝, 하위 pdf\\ 원본이 원천(PNG 짝은 원천 아님), 뒷면만 있는 묶음은 뺌, 정리 폴더는 안 봄
B. DB — 인식 캐시는 원천이 바뀌면 버림, 고침 보관, 사람 행 찾기(FTS)·스캔일 범위, 이름 1위 비율
C. 적용 — PDF 는 300 dpi JPG 앞·뒤, JPG 는 바이트 그대로, '넣지 않음' 뒷면은 안 만듦, 같은 이름은 ' (2)',
   같은 원천을 다시 적용하면 새 파일 없이 DB 만(메모 지킴), 원본은 그대로
D. 앱 — 도구 탭 `명함 ▾`(tools.bizcard) 자리, 폴더 줄 우클릭 연결, 창을 열어 배경 인식(가짜 인식기)이 표를 채움,
   이름 풀다운 고침이 새 파일 이름·캐시에 들어감, [적용] 단추를 눌러 정리본·해시태그(#명함·#회사·#한글), 메인 정지 < 1초
"""
import os, sys, tempfile, shutil, time, io
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
QCoreApplication.setApplicationName("polypdf_bizcard_import_%d" % os.getpid())
fails = []
TMP = Path(tempfile.mkdtemp(prefix="bizcard_p2_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")     # bizcard.db 를 시험 폴더에


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


try:
    from viewer.bizcard import importer as I, store as S, apply as AP, recognize as R
except Exception as e:                       # 이 판 전 코드엔 모듈이 없다
    chk(False, "명함 들이기 모듈을 불러온다", repr(e))
    print("FAILURES: %d" % len(fails))
    os._exit(1)

from PIL import Image
import fitz


def jpg(p, color="white", size=(339, 186)):
    Image.new("RGB", size, color).save(p, quality=90)


def png(p, size=(535, 292)):
    Image.new("RGB", size, "white").save(p)


def pdf2(p):
    doc = fitz.open()
    for c in ((1, 1, 1), (0.9, 0.9, 1)):
        pg = doc.new_page(width=258, height=142)
        pg.draw_rect(pg.rect, color=c, fill=c)
        pg.insert_text((20, 40), "CARD", fontsize=14)
    doc.save(p)
    doc.close()


def mkfolder(root: Path):
    root.mkdir(parents=True)
    (root / "pdf").mkdir()
    png(root / "가나다_홍길동_p0001.png"); png(root / "가나다_홍길동_p0002.png")
    pdf2(str(root / "pdf" / "가나다_홍길동.pdf"))
    jpg(root / "라마바_김철수_1.jpg", "ivory")
    jpg(root / "사아자_이영희_1.jpg"); jpg(root / "사아자_이영희_2.jpg", "lightblue")
    jpg(root / "뒷면만_2.jpg")
    jpg(root / "20250101_120000.jpg")
    (root / "정리").mkdir()
    jpg(root / "정리" / "이미있음_회사.jpg")


try:
    # ── A ──
    print("=== A. 폴더 훑기 ===")
    F = TMP / "cards"
    mkfolder(F)
    items = I.scan_folder(F)
    by = {it.base: it for it in items}
    chk(sorted(by) == sorted(["가나다_홍길동", "라마바_김철수", "사아자_이영희", "20250101_120000"]),
        "A 묶음 넷(뒷면만·정리 폴더 제외)", str(sorted(by)))
    g = by.get("가나다_홍길동")
    chk(g is not None and g.pdf.endswith("가나다_홍길동.pdf") and g.key == g.pdf, "A 하위 pdf 원본이 원천 열쇠")
    chk(by["사아자_이영희"].back.endswith("_2.jpg") and by["라마바_김철수"].back == "", "A 앞뒤 짝")
    chk(all(len(it.scanned) == 10 for it in items), "A 스캔일(파일 날짜) YYYY-MM-DD")
    F3 = TMP / "cards_flat"                  # 261117-9: 원본 PDF 를 그림 옆(같은 폴더)으로 옮긴 꼴
    F3.mkdir()
    png(F3 / "가나다_홍길동_p0001.png"); pdf2(str(F3 / "가나다_홍길동.pdf")); pdf2(str(F3 / "PDF만_있음.pdf"))
    (F3 / "PDF").mkdir()
    it3 = {it.base: it for it in I.scan_folder(F3)}
    chk(sorted(it3) == ["PDF만_있음", "가나다_홍길동"] and it3["가나다_홍길동"].pdf.endswith("가나다_홍길동.pdf")
        and it3["가나다_홍길동"].key == it3["가나다_홍길동"].pdf, "A 같은 폴더의 원본 PDF 도 짝·원천(PDF 만 있는 명함 포함)", str(sorted(it3)))
    chk(str(R.card_sources(F3 / "가나다_홍길동_p0001.png")["pdf"]).endswith("가나다_홍길동.pdf"), "A 인식 원천도 같은 폴더 PDF")

    # ── B ──
    print("\n=== B. DB ===")
    db = TMP / "t.db"
    st = S.BizcardStore(db)
    k = by["라마바_김철수"].key
    sig = S.source_sig([k])
    st.recog_put(k, sig, {"name": "김철수"})
    st.edit_put(k, {"name": "김철수2"})
    hit = st.recog_get(k, sig)
    chk(hit and hit["result"]["name"] == "김철수" and hit["edit"]["name"] == "김철수2", "B 캐시·고침 보관")
    chk(st.recog_get(k, sig + "x") is None, "B 원천이 바뀌면(지문 다름) 캐시를 쓰지 않는다")
    st.recog_put(k, sig + "x", {"name": "새"})
    chk(st.recog_get(k, sig + "x")["edit"] == {}, "B 원천이 바뀌면 옛 고침도 버린다")
    st.upsert({"front": str(TMP / "a.jpg"), "name": "홍길동", "company": "가나다기술", "memo": "골프 모임",
               "phones": [("cell", "010-0000-0001")], "scanned": "2026-10-01", "top1": True})
    st.upsert({"front": str(TMP / "b.jpg"), "name": "김철수", "company": "라마바", "scanned": "2025-01-01", "top1": False})
    chk([d["name"] for d in st.search("가나다")] == ["홍길동"], "B 회사로 찾기")
    chk([d["name"] for d in st.search("골프")] == ["홍길동"], "B 메모로 찾기")
    chk([d["name"] for d in st.search("", since="2026-01-01")] == ["홍길동"], "B 스캔일 범위")
    chk(st.top1_ratio() == (1, 2), "B 이름 1위 비율(참·거짓만)", str(st.top1_ratio()))
    st.close()
    # 261117-11: 부서 열이 없던 옛 DB — 열은 한 번만 더하고, 옛 행은 그대로, 옛 판의 넣기(열 이름을 적은 INSERT)도 된다
    import sqlite3
    olddb = TMP / "old.db"
    con = sqlite3.connect(olddb)
    con.executescript("""CREATE TABLE cards(id INTEGER PRIMARY KEY, front TEXT UNIQUE NOT NULL, back TEXT, src_key TEXT, src_pdf TEXT,
        name TEXT, company TEXT, title TEXT, phones TEXT, emails TEXT, urls TEXT, address TEXT, en TEXT, memo TEXT, tags TEXT,
        scanned TEXT, top1 INTEGER, created REAL, updated REAL);
        INSERT INTO cards(front, name, company) VALUES('a.jpg', '홍길동', '가나다');""")
    con.commit(); con.close()
    for _ in range(2):
        so = S.BizcardStore(olddb)
        so.close()
    con = sqlite3.connect(olddb)
    cols = [r[1] for r in con.execute("PRAGMA table_info(cards)")]
    con.execute("INSERT INTO cards(front, name, company) VALUES('b.jpg', '김철수', '라마바')")   # 옛 판의 꼴
    con.commit()
    rows = con.execute("SELECT name, dept FROM cards ORDER BY id").fetchall()
    con.close()
    con = sqlite3.connect(olddb)
    tbls = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    chk({"corrections", "layouts", "domain_org", "samples"} <= tbls, "B 옛 DB 에 배우기·교정 표가 더해진다(261117-13)", str(sorted(tbls)))
    chk(cols.count("dept") == 1 and rows == [("홍길동", None), ("김철수", None)],
        "B 옛 DB — 부서 열은 한 번만, 옛 행 그대로, 옛 판 넣기도 된다", "%s %s" % (cols.count("dept"), rows))

    # ── C ──
    print("\n=== C. 적용 ===")
    out = TMP / "out"
    rows = [
        {"key": g.key, "front": g.front, "back": g.back, "pdf": g.pdf, "keep_back": True, "name": "홍 길동",
         "company": "(주)가나다기술", "langs": ["한글", "영어"], "phones": [("cell", "010-0000-0001")]},
        {"key": by["라마바_김철수"].key, "front": by["라마바_김철수"].front, "back": "", "pdf": "", "keep_back": False,
         "name": "김철수", "company": "라마바", "langs": ["한글"]},
        {"key": by["사아자_이영희"].key, "front": by["사아자_이영희"].front, "back": by["사아자_이영희"].back, "pdf": "",
         "keep_back": False, "name": "김철수", "company": "라마바", "langs": ["한글"]},
    ]
    before = sorted(os.listdir(F))
    done = AP.apply_cards(rows, out, db)
    names = sorted(os.listdir(out))
    chk(names == sorted(["홍길동_가나다기술.jpg", "홍길동_가나다기술_뒷면.jpg", "김철수_라마바.jpg", "김철수_라마바 (2).jpg"]),
        "C 정리본 이름·뒷면·겹친 이름 (2)·'넣지 않음' 뒷면 없음", str(names))
    with Image.open(out / "홍길동_가나다기술.jpg") as im:
        chk(im.format == "JPEG" and abs(im.width - round(258 / 72 * 300)) <= 2, "C PDF 앞면은 300 dpi JPG", str(im.size))
    chk((out / "김철수_라마바.jpg").read_bytes() == Path(by["라마바_김철수"].front).read_bytes(), "C JPG 원천은 바이트 그대로")
    chk(sorted(os.listdir(F)) == before, "C 원본 폴더는 그대로(D10)")
    chk(done[0][2] == ["명함", "가나다기술", "한글", "영어"], "C 해시태그 #명함·#회사·#한글·#영어", str(done[0][2]))
    st = S.BizcardStore(db)
    cid = st.card_by_src(g.key)["id"]
    st.con.execute("UPDATE cards SET memo='메모' WHERE id=?", (cid,)); st.con.commit()
    st.close()
    AP.apply_cards(rows[:1], out, db)
    st = S.BizcardStore(db)
    chk(sorted(os.listdir(out)) == names and st.card_by_src(g.key)["memo"] == "메모",
        "C 같은 원천을 다시 적용 — 새 파일 없음·메모 지킴")
    chk(st.card_by_src(g.key)["company"] == "가나다기술", "C DB 회사는 법인 꼴 없이")
    st.close()

    # ── D ──
    print("\n=== D. 앱 ===")
    def fake_recognize(path, ui_lang="ko"):
        time.sleep(0.05)
        stem = Path(path).stem
        hn, hc = R.parse_hint(path)
        c = R.CardResult(name=hn or "", company=hc, phones=[("cell", "010-0000-0009")], emails=["user@example.com"],
                         name_cands=[R.Cand(hn or "가짜", 4.0), R.Cand("후보둘", 2.0)], company_cands=[R.Cand(hc, 2.0)],
                         langs=("한글",), back_promo=None, need_check=("name",) if "김철수" in stem else ())
        return c
    R.recognize = fake_recognize
    F2 = TMP / "cards2"
    mkfolder(F2)
    from viewer.app import MainWindow
    import modal_guard
    modal_guard.install(label=lambda: "명함 들이기", echo=False)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    mw = MainWindow(); mw._skip_save_on_close = True
    mw.show()
    pump(timeout=1.0)
    import ui_layout
    w = ui_layout.where(mw, "tools.bizcard")
    tw = ui_layout.where(mw, "tools.reindex")
    chk(w is not None and tw is not None and w[0] == tw[0] and w[1] == tw[1] and w[2] == tw[2] + 1,
        "D 도구 탭 생성 묶음에서 `인덱스` 바로 뒤가 `명함 ▾`", "%s / %s" % (w, tw))
    chk(callable(getattr(mw.bookmark_tree, "bizcard_import", None)), "D 책갈피창 폴더 줄 우클릭이 앱에 이어진다")
    mw._action_bizcard_import(str(F2))
    dlg = getattr(mw, "_bizcard_dlg", None)
    chk(dlg is not None and dlg.table.rowCount() == 4, "D 창이 열리고 명함 넷 줄", str(dlg and dlg.table.rowCount()))
    gaps = []
    last = [time.monotonic()]

    def beat():
        now = time.monotonic(); gaps.append(now - last[0]); last[0] = now
    from PyQt6.QtCore import QTimer
    hb = QTimer(); hb.timeout.connect(beat); hb.start(20)
    chk(pump(lambda: dlg.bar.value() == 4, timeout=30), "D 배경 인식이 끝까지", str(dlg.bar.value()))
    hb.stop()
    chk(max(gaps or [0]) < 1.0, "D 읽는 동안 메인 정지 < 1초", "%.2f" % max(gaps or [0]))
    rk = next(i for i, it in enumerate(dlg._items) if it.base == "라마바_김철수")
    from viewer.widgets import bizcard_import_dialog as BD
    pump(lambda: not dlg._pending, timeout=10)
    chk(len(dlg.choices(rk, BD.C_NAME)) >= 2, "D 이름 칸은 후보 고르기", str(len(dlg.choices(rk, BD.C_NAME))))
    from PyQt6.QtWidgets import QComboBox, QStyleOptionViewItem
    idx = dlg.table.model().index(rk, BD.C_NAME)
    ed = dlg.table.itemDelegate().createEditor(dlg.table.viewport(), QStyleOptionViewItem(), idx)
    chk(isinstance(ed, QComboBox) and ed.isEditable() and ed.count() >= 2, "D 고칠 때 풀다운이 뜬다(후보 + 직접 입력)")
    ed.deleteLater()
    chk(not any(dlg.table.cellWidget(r, c) for r in range(dlg.table.rowCount()) for c in range(dlg.table.columnCount())),
        "D 표에 칸 위젯이 없다 — 줄마다 풀다운 위젯을 만들지 않는다(261117-12 '응답 없음')")
    dlg.set_cell(rk, BD.C_NAME, "박영수")
    pump(timeout=0.2)
    chk(dlg.table.item(rk, BD.C_FILE).text() == "박영수_라마바.jpg", "D 이름을 고치면 새 파일 이름이 바로", dlg.table.item(rk, BD.C_FILE).text())
    chk(dlg.table.horizontalHeaderItem(BD.C_DEPT).text() == "부서", "D 확인 표에 '부서' 열(261117-11)")
    dlg.table.item(rk, BD.C_DEPT).setText("품질팀")
    st = S.BizcardStore()
    hit = st.recog_get(dlg._items[rk].key, S.source_sig([dlg._items[rk].pdf, dlg._items[rk].front, dlg._items[rk].back]))
    chk(hit and hit["edit"].get("name") == "박영수", "D 고친 값은 캐시에(다시 열면 이어서)")
    st.close()
    dlg.chk_need.setChecked(True)
    pump(timeout=0.2)
    vis = [r for r in range(dlg.table.rowCount()) if not dlg.table.isRowHidden(r)]
    chk(vis == [rk], "D '확인 필요만' 거르기", str(vis))
    dlg.chk_need.setChecked(False)
    # 스캔일 일괄(D7) — 고른 줄만 바뀐다(표를 칸 위젯 없이 바꾼 뒤에도, 261117-12)
    dlg.table.clearSelection()
    dlg.table.selectRow(rk)
    dlg.ed_date.setText("2024-05-06")
    QTest.mouseClick(dlg.btn_date, Qt.MouseButton.LeftButton)
    others = [dlg.cell(r, BD.C_DATE) for r in range(dlg.table.rowCount()) if r != rk]
    chk(dlg.cell(rk, BD.C_DATE) == "2024-05-06" and "2024-05-06" not in others, "D 스캔일 일괄 — 고른 줄만")
    r0 = next(i for i, it in enumerate(dlg._items) if it.base == "20250101_120000")
    dlg.table.item(r0, 0).setCheckState(Qt.CheckState.Unchecked)       # 이 줄은 적용하지 않는다
    out2 = TMP / "cards2" / "정리"
    QTest.mouseClick(dlg.btn_apply, Qt.MouseButton.LeftButton)
    pump(lambda: hasattr(dlg, "applied"), timeout=30)
    made = sorted(os.listdir(out2))
    chk("박영수_라마바.jpg" in made and "홍길동_가나다.jpg" in made and not any(n.startswith("20250101") for n in made),
        "D [적용] — 체크한 줄만 정리본", str(made))
    st2 = S.BizcardStore()
    row2 = st2.card_by_front(out2 / "박영수_라마바.jpg")
    chk(row2 is not None and row2.get("dept") == "품질팀" and [d["name"] for d in st2.search("품질팀")] == ["박영수"],
        "D 부서가 명함 DB 에 들어가고 찾기로 나온다", str(row2 and row2.get("dept")))
    st2.close()
    tags = mw.bookmark_tree._tags.get(str(out2 / "박영수_라마바.jpg"))
    chk(tags[:3] == ["명함", "라마바", "한글"], "D 해시태그는 앱의 태그 저장소에", str(tags))
    from PyQt6.QtGui import QPixmap
    for w0, h0, what in ((420, 1200, "세로 명함"), (4000, 2200, "큰 그림")):      # 261117-10 사용자 보고: 크거나 세로면 넘쳤다
        dlg._fit(dlg.pv_front, QPixmap(w0, h0))
        pm = dlg.pv_front.pixmap()
        chk(pm.height() <= dlg.pv_front.height() and pm.width() <= dlg.pv_front.width()
            and abs(pm.width() / pm.height() - w0 / h0) < 0.02, "D 미리 보기는 칸 안에 비율대로 — " + what,
            "%dx%d in %dx%d" % (pm.width(), pm.height(), dlg.pv_front.width(), dlg.pv_front.height()))
    dlg.close()
    pump(timeout=0.5)

    # ── E. 많은 명함 — 표를 채우는 동안 메인 정지(261117-12 사용자 보고 '응답 없음') ──
    print()
    print("=== E. 명함 600장 ===")
    F5 = TMP / "many"
    F5.mkdir()
    for i in range(600):
        jpg(F5 / ("회사%03d_홍길동_1.jpg" % i))
    mw._action_bizcard_import(str(F5))
    dm = mw._bizcard_dlg
    gaps.clear(); last[0] = time.monotonic()
    hb.start(20)
    chk(pump(lambda: dm.bar.value() == 600 and not dm._pending, timeout=120), "E 600장 끝까지", str(dm.bar.value()))
    hb.stop()
    chk(max(gaps or [0]) < 0.5, "E 표를 채우는 동안 메인 정지 < 0.5초(종전 1000장 1.9초)", "%.2f" % max(gaps or [0]))
    dm.close()
    pump(timeout=0.5)

    # ── F. 다시 읽기(261117-15) — 지금의 인식으로 다시, 손으로 고친 칸은 그대로 ──
    print()
    print("=== F. 다시 읽기 ===")
    mw._action_bizcard_import(str(F2))
    dr = mw._bizcard_dlg
    chk(pump(lambda: dr.bar.value() == 4 and not dr._pending, timeout=30), "F 다시 연 창 — 캐시에서 채움")
    rk2 = next(i for i, it in enumerate(dr._items) if it.base == "라마바_김철수")
    ro2 = next(i for i, it in enumerate(dr._items) if it.base == "가나다_홍길동")
    chk(dr.cell(rk2, BD.C_NAME) == "박영수", "F 손으로 고친 이름이 캐시에서 되살아난다")
    calls = []

    def fake_v2(path, ui_lang="ko"):                    # 고친 인식 — 회사·부서가 새로 나온다
        calls.append(1)
        c = fake_recognize(path, ui_lang)
        c.company, c.dept = "새회사", "품질팀"
        c.company_cands = [R.Cand("새회사", 3.0)]
        return c
    R.recognize = fake_v2
    st4 = S.BizcardStore()
    st4.correction_put("dept", "품질팀", "품질관리팀")               # 교정 사전(-13) — 다시 읽기에도 쓰인다
    st4.close()
    dr._load_learned()
    gaps.clear(); last[0] = time.monotonic(); hb.start(20)
    chk(dr.reread([rk2, ro2], ask=False), "F [다시 읽기] 시작")
    chk(dr.reread([rk2], ask=False) is False, "F 읽는 중에 다시 누르면 받지 않는다")
    chk(pump(lambda: dr._worker.done_event.is_set() and not dr._pending, timeout=30) and len(calls) == 2,
        "F 캐시를 건너뛰고 두 장만 다시 읽음", str(len(calls)))
    hb.stop()
    chk(max(gaps or [0]) < 0.5, "F 다시 읽는 동안 메인 정지 < 0.5초", "%.2f" % max(gaps or [0]))
    pump(timeout=0.3)
    chk(dr.cell(rk2, BD.C_NAME) == "박영수" and dr.cell(rk2, BD.C_COMP) == "새회사" and dr.cell(rk2, BD.C_DEPT) == "품질팀",
        "F 손으로 고친 이름·부서(D 에서 고침)는 그대로, 손대지 않은 회사는 새 인식", "%s/%s/%s" % (dr.cell(rk2, BD.C_NAME), dr.cell(rk2, BD.C_COMP), dr.cell(rk2, BD.C_DEPT)))
    chk(dr.cell(ro2, BD.C_COMP) == "새회사" and dr.cell(ro2, BD.C_DEPT) == "품질관리팀",
        "F 손대지 않은 줄은 새 인식 + 교정 사전 적용(부서 품질팀 → 품질관리팀)", dr.cell(ro2, BD.C_DEPT))
    en_r = R.rescore({"company": "Korea Expressway Co", "dept": "Road Team", "title": "Senior Manager",
                      "name_cands": [], "company_cands": [{"text": "Korea Expressway Co", "score": 2.0, "feat": {}}]})
    chk(en_r["company"] == "Korea Expressway Co" and en_r["dept"] == "Road Team" and en_r["title"] == "Senior Manager",
        "F 영문 회사·부서·직함의 띄어쓰기는 그대로(한글 사이만 없앰)", str((en_r["company"], en_r["dept"], en_r["title"])))
    st3 = S.BizcardStore()
    hit3 = st3.recog_get(dr._items[rk2].key, S.source_sig([dr._items[rk2].pdf, dr._items[rk2].front, dr._items[rk2].back]))
    st3.close()
    chk(hit3 and hit3["edit"].get("name") == "박영수" and "company" not in hit3["edit"], "F 기록에는 손으로 고친 칸만 남는다", str(hit3 and hit3["edit"]))
    # 261117-16: [다시 읽기 ▾] — 고른 줄 / 모두(표에는 늘 한 줄이 골라져 있어 종전엔 늘 그 한 줄만 다시 읽혔다)
    dr.table.clearSelection()
    dr.table.selectRow(0)
    dr._fill_reread_menu()
    acts = dr._reread_menu.actions()
    chk(len(acts) == 2 and acts[0].text().endswith("(1장)") and acts[1].text().endswith("(4장)") and dr.btn_reread.menu() is dr._reread_menu,
        "F 다시 읽기 ▾ — '고른 줄 (1장)'·'모두 (4장)'", str([a.text() for a in acts]))
    dr.table.clearSelection()
    dr._fill_reread_menu()
    chk(not dr._reread_menu.actions()[0].isEnabled() and dr._reread_menu.actions()[0].text().endswith("(0장)")
        and dr._reread_menu.actions()[1].isEnabled(), "F 고른 줄이 없으면 '고른 줄' 은 꺼짐(보이되), '모두' 는 켜짐")
    dr.table.selectRow(0)
    dr._fill_reread_menu()                              # 메뉴는 펼칠 때마다 새로 — 앞의 항목은 지워진다
    calls.clear()
    dr._reread_menu.actions()[1].trigger()
    dr._fill_reread_menu()
    chk(not any(a.isEnabled() for a in dr._reread_menu.actions()), "F 읽는 중에는 두 항목 모두 꺼짐")
    chk(pump(lambda: dr._worker.done_event.is_set() and not dr._pending, timeout=30) and len(calls) == 4,
        "F '모두 다시 읽기' 는 한 줄이 골라져 있어도 모두", str(len(calls)))
    calls.clear()
    dr._fill_reread_menu()
    dr._reread_menu.actions()[0].trigger()
    chk(pump(lambda: dr._worker.done_event.is_set() and not dr._pending, timeout=30) and len(calls) == 1,
        "F '고른 줄 다시 읽기' 는 그 줄만", str(len(calls)))
    dr.close()
    pump(timeout=0.5)
    mw.close()
except Exception:
    import traceback
    traceback.print_exc()
    fails.append("예외")
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print()
print("ALL PASS" if not fails else "FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)          # Qt 소멸 단계 충돌을 피한다(MainWindow 검사 관례)
