# -*- coding: utf-8 -*-
"""명함 SOT 점검(beta.19 이후) 코드 고침 (명함 SOT §5.32·§5.29·§5.24.1, 261122-11) — 가짜 명함(010-0000-…)·임시 폴더만.

A '나누기'가 다른 명함 행의 경로(파일 잃은 묵은 행)를 피함 — [저장] 과 같은 길
B '나누기' DB 가 실패하면 반쯤 된 쓰기를 남기지 않고(rollback) 바꾼 파일 이름을 되돌림
C 명단 관리 '다른 전화' — 010 판단은 `mobiles_010` 한 곳(종류가 팩스여도 010 이면 010 칸)
D 명단 관리 '명함' 칸·≡ '명함 보기'·중복 검토 출처 — 그림 파일이 실제로 있어야 '명함'
E [연결 끊기] 가 '구글에만 둠' 도 지움
F 명단 관리 찾기 칸 — 글자마다 다시 읽지 않고 멈춘 뒤 한 번
"""
import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox
from pathlib import Path
from PIL import Image

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_audit_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_audit_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
WARN = []
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: (WARN.append(1), QMessageBox.StandardButton.Ok)[1])
ERRS = []
sys.excepthook = lambda t, v, tb: ERRS.append(repr(v))
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


def pump(cond, timeout=10.0):
    t = time.monotonic()
    while time.monotonic() - t < timeout:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


def num(n):
    return "010-0000-%04d" % (n * 1111)


try:
    from viewer.bizcard import people as P, store as S, roster as RS, gsync as G
    FOLD = TMP / "cards"
    OUT = FOLD / "정리"
    OUT.mkdir(parents=True)
    db = TMP / "local" / "bizcard.db"
    st = S.BizcardStore(db)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    P.src_init(st)
    f_a = OUT / "가짜갑_가짜사.jpg"
    Image.new("RGB", (300, 180), "white").save(f_a)
    a = st.upsert({"front": str(f_a), "name": "가짜갑", "company": "가짜사",
                   "phones": [("cell", num(1)), ("fax", num(2)), ("work", "02-0000-0003")]})
    lost = st.upsert({"front": str(OUT / "가짜을_가짜사.jpg"), "name": "가짜잃음", "company": "가짜사",   # 파일 잃은 묵은 행
                      "phones": [("cell", num(4))]})
    st.con.commit()
    st.close()
    settings_store.set_picture_prefs({"bizcard_folder": str(FOLD)})

    from viewer.widgets import bizcard_find_dialog as FD, bizcard_roster_dialog as RD
    fd = FD.BizcardFindDialog(None, db=db)
    fd._bz_folder = str(FOLD)
    fd.show()
    pump(lambda: fd.table.rowCount() == 2)
    rd = fd.open_roster(exec_=False)
    pump(lambda: not rd.loading, timeout=10)

    print("=== C 다른 전화 — 010 은 종류 무관 ===")
    c_a = P.card_by_id(fd._store(), a)
    chk(RD._other_phones(c_a) == "02-0000-0003", "C 팩스 종류의 010 도 '다른 전화' 에 다시 나오지 않음", repr(RD._other_phones(c_a)))

    print("\n=== D '명함' 칸·명함 보기·중복 검토 출처 ===")
    items = {rd.tree.topLevelItem(i).text(0): rd.tree.topLevelItem(i).text(5) for i in range(rd.tree.topLevelItemCount())}
    chk(items.get("가짜갑") == "명함" and items.get("가짜잃음") == "", "D 명단 관리 '명함' 칸 — 파일 잃은 명함은 빈칸", str(items))
    fd.table.setCurrentCell(fd.row_of_id(lost), 0)
    pump(lambda: fd._card and fd._card["id"] == lost, timeout=3)
    chk(not fd.act_open.isEnabled(), "D ≡ '명함 보기' — 파일 잃은 명함은 흐림")
    chk(P.card_source(fd._store(), P.card_by_id(fd._store(), lost)) != "card" and P.card_source(fd._store(), c_a) == "card",
        "D 중복 검토 출처 — 파일 잃은 명함은 '명함' 이 아님")

    print("\n=== A 나누기가 묵은 행 경로를 피함 ===")
    rd.select_card(a)
    dlg = rd.split_dialog()
    dlg.eds["name"].setText("가짜을")
    dlg.eds["company"].setText("가짜사")
    dlg.check("image")
    dlg.check("phone", num(2))
    ERRS.clear()
    nid = rd.split(dlg=dlg)
    pump(lambda: not rd.loading, timeout=10)
    new = P.card_by_id(fd._store(), nid) if nid else None
    chk(nid and not ERRS and new and os.path.exists(P._real(new["front"]))
        and os.path.normcase(P._real(new["front"])) != os.path.normcase(str(OUT / "가짜을_가짜사.jpg")),
        "A 새 사람 그림 이름이 묵은 행 경로와 겹치지 않음(` (2)`)", "%s %s" % (ERRS, new and new["front"]))

    print("\n=== B 나누기 DB 실패 — 되돌림 ===")
    st = fd._store()
    f_b = OUT / "가짜병_가짜사.jpg"
    Image.new("RGB", (300, 180), "white").save(f_b)
    b = st.upsert({"front": str(f_b), "name": "가짜병", "company": "가짜사", "phones": [("cell", num(5)), ("cell", num(6))]})
    st.con.commit()
    rd.reload()
    pump(lambda: not rd.loading, timeout=10)
    rd.select_card(b)
    dlg = rd.split_dialog()
    dlg.eds["name"].setText("가짜정")
    dlg.check("image")
    dlg.check("phone", num(6))
    n0 = len(RS.all_cards(st))
    _sp = P.split_card

    def bad_split(store, cid, *a_, **k_):
        store.con.execute("INSERT INTO cards(front, name, phones, emails, urls, tags, en) VALUES('contact:half', '반쯤', '[]', '[]', '[]', '[]', '{}')")
        raise RuntimeError("fake")
    P.split_card = bad_split
    WARN.clear()
    try:
        got = rd.split(dlg=dlg)
    finally:
        P.split_card = _sp
    pump(lambda: not rd.loading, timeout=10)
    st.con.commit()                                              # 다음 commit 이 반쯤 된 쓰기를 함께 저장하지 않아야
    chk(not got and WARN and f_b.exists() and not any(n.startswith("가짜정") for n in os.listdir(OUT)),
        "B 알리고 바꾼 파일 이름을 되돌림", str(sorted(os.listdir(OUT))))
    chk(len(RS.all_cards(st)) == n0, "B 반쯤 된 쓰기가 남지 않음(rollback)", "%d %d" % (n0, len(RS.all_cards(st))))

    print("\n=== E [연결 끊기] ===")
    st.meta_set(G.GOOGLE_ONLY_KEY, ["people/x1"])
    G.unlink(st)
    chk(not (st.meta_get(G.GOOGLE_ONLY_KEY, []) or []), "E 연결 끊기 — '구글에만 둠' 도 지움")

    print("\n=== F 찾기 칸 늦춤 ===")
    rd.set_view("all")
    pump(lambda: not rd.loading, timeout=10)
    g0 = rd._gen
    for t in ("가", "가짜", "가짜갑"):
        rd.ed_find.setText(t)
        app.processEvents()
    pump(lambda: rd._gen > g0 and not rd.loading, timeout=5)
    pump(lambda: False, timeout=0.5)
    chk(rd._gen - g0 == 1, "F 글자마다 읽지 않고 멈춘 뒤 한 번", str(rd._gen - g0))
except Exception as e:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외", repr(e))
print("FAILURES: %d" % len(fails))
for f in fails:
    print("  -", f)
sys.stdout.flush()
os._exit(1 if fails else 0)
