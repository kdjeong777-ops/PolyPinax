# -*- coding: utf-8 -*-
"""명단 관리 vcf 다시 읽기·[추가] 한 번만 (명함찾기 SOT §5.32 '작업 목록', 261122-7) — 가짜 명함·가짜 vcf(010-0000-…)·임시 폴더만.

A [추가] 하면 그 vcf 사람 줄이 저절로 체크
B 같은 줄을 다시 [추가] 하면 '이미 추가함' 알림·명단이 늘지 않음
C 되돌리기로 추가를 무르면 다시 [추가] 할 수 있음
D 창만 다시 열면 이어서(추가 표시 그대로)
E 같은 vcf 를 다시 읽으면 옛 작업 목록을 버리고 그 시점 DB 로 새로 비교 — 해결된 사람은 빠지고 남은 것만
"""
import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_reread_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_reread_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
INFO = []
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
QMessageBox.information = staticmethod(lambda *a, **k: (INFO.append(a[2] if len(a) > 2 else ""), QMessageBox.StandardButton.Ok)[1])
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
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


VCF = "\r\n".join([
    "BEGIN:VCARD", "VERSION:3.0", "FN:가짜갑", "TEL;TYPE=CELL:" + num(1), "END:VCARD",
    "BEGIN:VCARD", "VERSION:3.0", "FN:가짜을", "TEL;TYPE=CELL:" + num(2), "END:VCARD",
    "BEGIN:VCARD", "VERSION:3.0", "FN:가짜병", "TEL;TYPE=CELL:" + num(3), "END:VCARD", ""])

try:
    from viewer.bizcard import people as P, store as S, roster as RS
    FOLD = TMP / "cards"
    (FOLD / "정리").mkdir(parents=True)
    db = TMP / "local" / "bizcard.db"
    st = S.BizcardStore(db)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    P.src_init(st)
    gab = P._insert_contact(st, {"name": "가짜갑", "phones": [("cell", num(1)), ("cell", num(2))]}, ["명함"])   # 을의 번호가 섞임
    P._insert_contact(st, {"name": "가짜병", "phones": [("cell", num(4))]}, ["명함"])                          # 같은 이름·번호 다름
    st.con.commit()
    st.close()
    settings_store.set_picture_prefs({"bizcard_folder": str(FOLD)})
    vcf = TMP / "받은" / "주소록.vcf"
    vcf.parent.mkdir()
    vcf.write_text(VCF, encoding="utf-8")

    from viewer.widgets import bizcard_find_dialog as FD
    fd = FD.BizcardFindDialog(None, db=db)
    fd._bz_folder = str(FOLD)
    fd.show()
    pump(lambda: fd.table.rowCount() == 2)
    rd = fd.open_roster(exec_=False)
    rd.open_vcf(str(vcf))
    pump(lambda: not rd.loading and rd.view() == "vcf" and rd.tree.topLevelItemCount() >= 2, timeout=10)
    G = lambda name, r=None: next((g for g in (r or rd).groups if g["person"]["name"] == name), None)   # noqa: E731
    n_cards = lambda: len(RS.all_cards(fd._store()))                                                      # noqa: E731

    def top_of(r, gi):
        for i in range(r.tree.topLevelItemCount()):
            if r.tree.topLevelItem(i).data(0, 0x0100) == ("vcf", gi):
                return r.tree.topLevelItem(i)
        return None
    g_eul = G("가짜을")
    chk(g_eul is not None and not g_eul["auto"], "(전제) '을' 줄 — 명단에 없음")

    print("=== A [추가] 하면 체크 ===")
    rd.select_person(g_eul["gi"])
    n0 = n_cards()
    rd.add()
    pump(lambda: not rd.loading, timeout=10)
    chk(n_cards() == n0 + 1, "A 명단이 하나 늘어남")
    it = top_of(rd, g_eul["gi"])
    chk(it is not None and it.checkState(0) == Qt.CheckState.Checked, "A '을' 줄 앞이 저절로 체크")

    print("\n=== B 다시 [추가] ===")
    rd.select_person(g_eul["gi"])
    INFO.clear()
    got = rd.add()
    pump(lambda: not rd.loading, timeout=10)
    chk(got == 0 and n_cards() == n0 + 1 and any("이미 추가" in t for t in INFO), "B '이미 추가함' 알림·명단 그대로",
        "%s %d %s" % (got, n_cards(), INFO))

    print("\n=== C 되돌리면 다시 추가 가능 ===")
    rd.undo()
    pump(lambda: not rd.loading, timeout=10)
    chk(n_cards() == n0, "C (전제) 되돌리기로 추가가 빠짐")
    rd.select_person(g_eul["gi"])
    INFO.clear()
    got = rd.add()
    pump(lambda: not rd.loading, timeout=10)
    chk(got == 1 and n_cards() == n0 + 1 and not INFO, "C 되돌린 뒤엔 다시 [추가] 됨", "%s %s" % (got, INFO))

    print("\n=== D 창만 다시 열면 이어서 ===")
    rd.close()
    pump(lambda: False, timeout=0.3)
    rd2 = fd.open_roster(exec_=False)
    rd2.set_view("vcf")
    pump(lambda: not rd2.loading and rd2.tree.topLevelItemCount() >= 2, timeout=10)
    g2 = G("가짜을", rd2)
    it2 = top_of(rd2, g2["gi"]) if g2 else None
    chk(it2 is not None and it2.checkState(0) == Qt.CheckState.Checked, "D 옛 작업 목록 그대로·'을' 체크")
    rd2.select_person(g2["gi"])
    INFO.clear()
    chk(rd2.add() == 0 and INFO, "D 다시 열어도 다시 추가하지 않음")

    print("\n=== E 같은 vcf 를 다시 읽음 ===")
    P.update_card(fd._store(), gab, {"phones": [("cell", num(1))]})       # 잘못 섞인 번호를 고침
    rd2.open_vcf(str(vcf))
    pump(lambda: not rd2.loading, timeout=10)
    names = sorted(g["person"]["name"] for g in rd2.groups)
    chk(names == ["가짜병"], "E 지금 DB 로 새로 비교 — 고친 '갑'·추가한 '을' 은 빠지고 남은 '병' 만", str(names))
    chk(not rd2.added and not rd2.checks, "E 옛 추가 표시·체크는 버림")
except Exception as e:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외", repr(e))
print("FAILURES: %d" % len(fails))
for f in fails:
    print("  -", f)
sys.stdout.flush()
os._exit(1 if fails else 0)
