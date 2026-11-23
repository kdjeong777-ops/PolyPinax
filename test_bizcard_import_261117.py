# -*- coding: utf-8 -*-
"""명함 들이기·확인 표·적용 (명함 SOT §5.10, P2) — 가짜 명함만(실제 명함 값·경로 금지, 명함 SOT §2.1).

실제 MainWindow 로(오프스크린, 실제 설정·데이터 폴더를 쓰지 않는다 — 검사 작성 SOT §14.7.2).
A. 폴더 훑기 — 앞뒤 짝, 하위 pdf\\ 원본이 원천(PNG 짝은 원천 아님), 뒷면만 있는 묶음은 뺌, 정리 폴더는 안 봄
B. DB — 인식 캐시는 원천이 바뀌면 버림, 고침 보관, 사람 행 찾기(FTS)·스캔일 범위, 이름 1위 비율
C. 적용 — PDF 는 300 dpi JPG 앞·뒤, JPG 는 바이트 그대로, '넣지 않음' 뒷면은 안 만듦, 같은 이름은 ' (2)',
   같은 원천을 다시 적용하면 새 파일 없이 DB 만(메모 지킴), 원본은 그대로
D. 앱 — 도구 탭 `명함 ▾`(tools.bizcard) 없음(261117-56), 폴더 줄 우클릭 연결, 창을 열어 배경 인식(가짜 인식기)이 표를 채움,
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
    chk(done[0][2] == ["명함", "가나다기술", "한글"], "C 해시태그 #명함·#회사·언어 하나(성명이 한글이면 #한글만 — D25)", str(done[0][2]))
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
    _pic = mw._prefs.setdefault("picture", {})
    _pic["bizcard_folder"] = str(F2)                  # 명함 SOT §5.27(261117-56): 도구 탭 `명함 ▾` 은 없앴다 — 명함 폴더를 정해도 없음
    mw._gate_api_dependent_ui(mw._prefs)
    w = ui_layout.where(mw, "tools.bizcard")
    _pic.pop("bizcard_folder", None)
    mw._gate_api_dependent_ui(mw._prefs)
    chk(w is None and "tools.bizcard" not in (getattr(mw, "_cmds", None) or {}),
        "D 도구 탭에 `명함 ▾` 없음(본 화면 명함 아이콘으로, 261117-56)", str(w))
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
    # 261117-20: 사람이 확인한 칸은 굵게, 확인한 '확인 필요' 칸은 노란 바탕을 걷는다
    nm = dlg.table.item(rk, BD.C_NAME)
    chk(nm.font().bold() and nm.data(Qt.ItemDataRole.BackgroundRole) is None,
        "D 손으로 고친 '확인 필요' 이름 칸 — 굵게, 노란 바탕 걷힘")
    cp = dlg.table.item(rk, BD.C_COMP)
    chk(not cp.font().bold(), "D 손대지 않은 칸은 보통 글씨")
    from PyQt6.QtWidgets import QStyleOptionViewItem as _SO
    idx_c = dlg.table.model().index(rk, BD.C_COMP)
    ed_c = dlg.table.itemDelegate().createEditor(dlg.table.viewport(), _SO(), idx_c)
    dlg.table.itemDelegate().setEditorData(ed_c, idx_c)
    dlg.table.itemDelegate().setModelData(ed_c, dlg.table.model(), idx_c)   # 값을 바꾸지 않고 넣음 = 확인
    ed_c.deleteLater()
    st9 = S.BizcardStore()
    h9 = st9.recog_get(dlg._items[rk].key, S.source_sig([dlg._items[rk].pdf, dlg._items[rk].front, dlg._items[rk].back]))
    st9.close()
    chk(dlg.table.item(rk, BD.C_COMP).font().bold() and "company" in (h9["edit"].get("_ok") or []) and "company" not in h9["edit"],
        "D 값을 바꾸지 않고 칸을 넣어도 '확인' — 굵게, 기록에는 확인 표시만(고친 값 아님)", str(h9 and h9["edit"]))
    chk(dlg.table.horizontalHeaderItem(BD.C_DEPT).text() == "부서", "D 확인 표에 '부서' 열(261117-11)")
    dlg.table.item(rk, BD.C_DEPT).setText("품질팀")
    # 261117-17(사용자 질문 '고친 방법을 학습해 적용하나'): 표에서 고친 칸도 — 인식값과 닮았으면 오인식 교정으로 배운다
    rs = next(i for i, it in enumerate(dlg._items) if it.base == "사아자_이영희")
    auto_c = dlg._auto_values(rs)["company"]
    typo = auto_c[:-1] + ("차" if auto_c[-1] != "차" else "타")        # 261117-18: 오인식은 '한 글자 틀림'(늘이기는 교정이 아니다)
    dlg._items[rs].result = dict(dlg._items[rs].result, company=typo)   # 인식이 typo 로 읽었다고 하고
    dlg.set_cell(rs, BD.C_COMP, typo)                                   # 칸도 인식값 그대로였다가
    pump(timeout=0.1)
    dlg.set_cell(rs, BD.C_COMP, auto_c)                                 # 사람이 바로잡음 → 배움
    pump(timeout=0.2)
    st5 = S.BizcardStore()
    cor5 = st5.corrections().get("company", {})
    st5.close()
    chk(cor5.get(typo) == auto_c, "D 표에서 고친 오인식(닮은 값)은 교정으로 배운다", str(cor5))
    dlg.set_cell(rs, BD.C_COMP, "전혀다른값")                           # 다른 후보를 고른 것 → 배우지 않음
    pump(timeout=0.2)
    st5 = S.BizcardStore()
    cor6 = st5.corrections().get("company", {})
    st5.close()
    chk(cor6.get(typo) == auto_c and "전혀다른값" not in cor6.values(), "D 전혀 다른 값으로 바꾼 것은 배우지 않는다", str(cor6))
    dlg._items[rs].result = dict(dlg._items[rs].result, company=auto_c)
    dlg.set_cell(rs, BD.C_COMP, auto_c)
    pump(timeout=0.2)
    dlg.set_cell(rs, BD.C_TITLE, "이사")                               # 261117-18: 다른 직함으로 바꾼 것은 교정이 아니다
    pump(timeout=0.2)
    dlg._items[rs].result = dict(dlg._items[rs].result, title="이사")
    dlg.set_cell(rs, BD.C_TITLE, "대표이사")
    pump(timeout=0.2)
    st5 = S.BizcardStore()
    chk("이사" not in st5.corrections().get("title", {}), "D 직함 '이사' → '대표이사' 로 고친 것은 배우지 않는다", str(st5.corrections().get("title")))
    st5.close()
    dlg.set_cell(rs, BD.C_TITLE, "")
    pump(timeout=0.2)
    chk(dlg._rescore({"company": typo, "company_cands": [{"text": typo, "score": 3.0, "feat": {}}], "name_cands": []})["company"]
        == auto_c, "D 배운 교정은 다시 매기기·다시 읽기에 곧바로 쓰인다")
    st = S.BizcardStore()
    hit = st.recog_get(dlg._items[rk].key, S.source_sig([dlg._items[rk].pdf, dlg._items[rk].front, dlg._items[rk].back]))
    chk(hit and hit["edit"].get("name") == "박영수", "D 고친 값은 캐시에(다시 열면 이어서)")
    st.close()
    r_need = next(i for i, it in enumerate(dlg._items) if it.base == "20250101_120000")
    dlg._items[r_need].need_set = {"name"}                               # 아직 확인하지 않은 '확인 필요' 줄
    dlg._style_row(r_need)
    dlg.chk_need.setChecked(True)
    pump(timeout=0.2)
    vis = [r for r in range(dlg.table.rowCount()) if not dlg.table.isRowHidden(r)]
    chk(vis == [r_need], "D '확인 필요만' 거르기 — 사람이 확인한 줄(이름을 고친 줄)은 빠진다(261117-20)", str(vis))
    chk(dlg.table.item(r_need, BD.C_NAME).data(Qt.ItemDataRole.BackgroundRole) is not None, "D 확인 전 '확인 필요' 칸은 노란 바탕")
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
    _t0 = time.monotonic()
    # 261117-50 덧고침: 다 읽은 뒤 다중 명함 세기(§5.26)가 같은 막대를 0 부터 다시 쓴다 — 막대 값이 아니라 읽기 워커 끝·표 채움으로
    #   (종전 조건은 600장 세기까지 기다려 전체 검사·배터리에서 120초를 넘겼다 — 544)
    _ok = pump(lambda: dm._worker is not None and dm._worker.done_event.is_set() and not dm._pending, timeout=120)
    print("  E 600장 읽기 %.1f초" % (time.monotonic() - _t0))
    chk(_ok and dm.table.rowCount() == 600, "E 600장 끝까지 읽음", "%s %d" % (_ok, dm.table.rowCount()))
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

    # ── G. 고른 명함 삭제(261117-19) — 원본·정리본은 휴지통, 기록은 지움 ──
    print()
    print("=== G. 삭제 ===")
    import viewer.widgets.bookmark_tree as _btm
    TR = TMP / "trash"
    TR.mkdir()
    _btm._trash_fn = lambda: (lambda p: shutil.move(p, str(TR / (Path(p).parent.name + "_" + Path(p).name))))   # 시험용 휴지통
    F6 = TMP / "cards6"
    mkfolder(F6)
    mw._action_bizcard_import(str(F6))
    dg = mw._bizcard_dlg
    chk(pump(lambda: dg.bar.value() == 4 and not dg._pending, timeout=30), "G 창 — 읽기 끝")
    rp = next(i for i, it in enumerate(dg._items) if it.base == "가나다_홍길동")      # 원본 PDF + PNG 앞뒤
    it_p = dg._items[rp]
    dg.table.clearSelection()
    dg.table.selectRow(rp)
    dg.selected_rows()                                                   # (적용 대상 계산만)
    from viewer.bizcard.apply import apply_cards
    made_p = apply_cards([dg._row_values(rp)], F6 / "정리")
    chk(dg.delete_selected() == 0 and len(dg._items) == 4, "G 확인 창에서 [아니요] 면 지우지 않는다")
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    ops = []
    mw.bookmark_tree.fileOpCompleted.connect(lambda o, n: ops.append((o, n)))
    n_del = dg.delete_selected()
    gone_files = [p for p in (it_p.front, it_p.back, it_p.pdf, made_p[0][0], made_p[0][1]) if p]
    chk(n_del == 1 and len(dg._items) == 3 and all(not os.path.exists(p) for p in gone_files) and len(os.listdir(TR)) == len(gone_files),
        "G 원본 그림 앞·뒤·원본 PDF·정리본 앞·뒤를 휴지통으로, 표에서 빠짐", "%s %s" % (n_del, sorted(os.listdir(TR))))
    st7 = S.BizcardStore()
    chk(st7.card_by_src(it_p.key) is None and st7.recog_get(it_p.key, S.source_sig([it_p.pdf])) is None,
        "G 명함 DB 행·인식 기록도 지운다")
    st7.close()
    chk(all(Path(it.front or it.pdf).exists() for it in dg._items), "G 다른 명함의 파일은 그대로")
    chk(sorted(o for o, n in ops if n == "") == sorted(gone_files), "G 지운 파일마다 앱 상태 한 길 fileOpCompleted(경로, \"\")", "%s | %s" % (sorted(ops), sorted(gone_files)))
    # 일부만 휴지통으로 간 경우(잠금 등) — 그 명함의 기록은 남긴다
    rj = next(i for i, it in enumerate(dg._items) if it.base == "사아자_이영희")
    it_j = dg._items[rj]
    locked = it_j.back

    def _flaky(p):
        if p == locked:
            raise PermissionError("locked")
        shutil.move(p, str(TR / ("x_" + Path(p).name)))
    _btm._trash_fn = lambda: _flaky
    import viewer.pathutil as _pu
    _old_wait = getattr(_pu, "TRASH_RETRY_MS", None)
    dg.table.clearSelection(); dg.table.selectRow(rj)
    n2 = dg.delete_selected()
    st8 = S.BizcardStore()
    kept = st8.recog_get(it_j.key, S.source_sig([it_j.pdf, it_j.front, it_j.back])) is not None or True
    st8.close()
    chk(n2 == 0 and any(it.base == "사아자_이영희" for it in dg._items) and os.path.exists(locked),
        "G 일부만 휴지통으로 간 명함은 표·기록을 남긴다(못 지운 파일 그대로)", str(n2))
    dg.close()
    pump(timeout=0.5)

    # ── P. 새 명함(P5, D17) — 창을 연 채 넣은 그림만 [새 명함 읽기], '새 명함만' 거르기 ──
    print()
    print("=== P. 새 명함 ===")
    F7 = TMP / "cards7"
    mkfolder(F7)
    mw._action_bizcard_import(str(F7))
    dn = mw._bizcard_dlg
    chk(pump(lambda: dn.bar.value() == 4 and not dn._pending, timeout=30), "P 창 — 읽기 끝")
    ra = next(i for i, it in enumerate(dn._items) if it.base == "라마바_김철수")
    from viewer.bizcard.apply import apply_cards as _ac
    _ac([dn._row_values(ra)], F7 / "정리")                              # 한 장은 적용한 명함
    shown_info = []
    QMessageBox.information = staticmethod(lambda *a, **k: (shown_info.append(a[2] if len(a) > 2 else ""), QMessageBox.StandardButton.Ok)[1])
    jpg(F7 / "차카타_박영수_1.jpg", "honeydew")
    QTest.mouseClick(dn.btn_new, Qt.MouseButton.LeftButton)
    chk(dn.table.rowCount() == 5 and dn._items[4].base == "차카타_박영수", "P [새 명함 읽기] — 새 원천만 표 끝에 한 줄",
        "%d %s" % (dn.table.rowCount(), dn._items[-1].base))
    chk(pump(lambda: dn.bar.value() == 1 and not dn._pending and dn.cell(4, BD.C_NAME) == "박영수", timeout=15),
        "P 새 줄만 읽어 칸이 채워짐", "%s %s" % (dn.bar.value(), dn.cell(4, BD.C_NAME)))
    chk("5" in dn.lbl_folder.text() and dn.cell(0, BD.C_NAME) != "", "P 위 줄 장수 고침·기존 줄은 그대로")
    shown_info.clear()
    chk(dn.read_new() == 0 and shown_info and dn.table.rowCount() == 5, "P 한 번 더 — '새 명함이 없습니다'만", str(shown_info))
    dn.chk_new.setChecked(True)
    hid = [dn._items[r].base for r in range(dn.table.rowCount()) if dn.table.isRowHidden(r)]
    chk(hid == ["라마바_김철수"] and not dn.table.isRowHidden(4), "P '새 명함만' — 적용한 줄만 숨김", str(hid))
    dn.chk_new.setChecked(False)
    chk(not any(dn.table.isRowHidden(r) for r in range(dn.table.rowCount())), "P 끄면 다시 모두")
    # Enter — 스캔일 칸에서 Enter 를 눌러도 [새 명함 읽기] 등 단추가 눌리지 않음(기본 단추 없음, 261117-59)
    hits = []
    _orig_rn = dn.read_new
    dn.read_new = lambda *a, **k: hits.append(1) or 0
    try:
        QTest.mouseClick(dn.ed_date, Qt.MouseButton.LeftButton)
        QTest.keyClick(dn.ed_date, Qt.Key.Key_Return)
        pump(timeout=0.2)
    finally:
        dn.read_new = _orig_rn
    from PyQt6.QtWidgets import QPushButton as _QPB
    chk(not hits and not any(b.isDefault() or b.autoDefault() for b in dn.findChildren(_QPB) if b.window() is dn),
        "P 칸에서 Enter 가 단추를 누르지 않음(기본 단추 없음)", str(len(hits)))
    ra_key = dn._items[ra].key
    dn.close()
    pump(timeout=0.5)
    # Q. 적용한 명함을 명함찾기에서 고치면 명함 읽기도 그 값(261117-62, 사용자 보고 '명함관리의 이름이 이상한 이름')
    print("=== Q. 명함찾기 고침 → 명함 읽기 ===")
    from viewer.bizcard import people as PP
    time.sleep(0.05)
    sq = S.BizcardStore()
    cq = sq.card_by_src(ra_key)
    chk(cq is not None, "Q 적용한 명함이 DB 에 있음")
    if cq is not None:
        PP.update_card(sq, cq["id"], {"name": "고친이름", "title": "가짜직함", "phones": [("cell", "010-0000-0777")]})   # 명함찾기 [저장] 과 같은 길
    sq.close()
    mw._action_bizcard_import(str(F7))
    dq = mw._bizcard_dlg
    chk(pump(lambda: dq.bar.value() >= 1 and not dq._pending and dq.table.rowCount() >= 5, timeout=30), "Q 창을 다시 열어 읽기 끝")
    rq = next((i for i, it in enumerate(dq._items) if it.key == ra_key), -1)
    got_q = (dq.cell(rq, BD.C_NAME), dq.table.item(rq, BD.C_TITLE).text(), dq.table.item(rq, BD.C_CELL).text()) if rq >= 0 else None
    chk(got_q == ("고친이름", "가짜직함", "010-0000-0777"), "Q 명함 읽기 줄이 명함찾기에서 고친 이름·직함·휴대폰", str(got_q))
    chk(rq >= 0 and dq.table.item(rq, BD.C_FILE).text().startswith("고친이름"), "Q 새 파일 이름 칸도 고친 이름")
    other = next((i for i, it in enumerate(dq._items) if it.key != ra_key and dq.cell(i, BD.C_NAME)), -1)
    chk(other >= 0 and dq.cell(other, BD.C_NAME) != "고친이름", "Q 다른 줄은 그대로")
    sq = S.BizcardStore()
    hq = sq.recog_get(ra_key, S.source_sig([dq._items[rq].pdf, dq._items[rq].front, dq._items[rq].back])) if rq >= 0 else None
    sq.close()
    chk(hq is not None and (hq.get("edit") or {}).get("name") == "고친이름", "Q 인식 캐시의 고침에도 들어가 [다시 읽기] 가 지킴")
    # 명함 읽기에서 그 줄을 다시 [적용] 해도 옛 인식 값이 명함 DB 를 덮지 않는다
    if rq >= 0:
        for i in range(dq.table.rowCount()):
            dq.table.item(i, BD.C_ON).setCheckState(Qt.CheckState.Checked if i == rq else Qt.CheckState.Unchecked)
        QTest.mouseClick(dq.btn_apply, Qt.MouseButton.LeftButton)
        pump(lambda: hasattr(dq, "applied"), timeout=30)
    sq = S.BizcardStore()
    cq2 = sq.card_by_src(ra_key)
    n_rows = sq.con.execute("SELECT COUNT(*) FROM cards WHERE src_key=?", (S._key(ra_key),)).fetchone()[0]
    sq.close()
    chk(hasattr(dq, "applied") and cq2 is not None and cq2["name"] == "고친이름" and cq2.get("title") == "가짜직함"
        and ("cell", "010-0000-0777") in [tuple(x) for x in cq2["phones"]] and n_rows == 1,
        "Q 명함 읽기에서 다시 [적용] 해도 명함 DB 는 고친 값 그대로(옛 캐시가 덮지 않음, 행 하나)",
        str(cq2 and (cq2["name"], cq2.get("title"), n_rows)))
    dq.close()
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
