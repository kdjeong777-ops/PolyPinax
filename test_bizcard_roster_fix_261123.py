# -*- coding: utf-8 -*-
"""명단 관리 vcf 작업 목록 손보기 (명함 SOT §5.32 '작업 목록'·'되돌리기', 261122-4) — 가짜 명함·가짜 vcf(010-0000-…)·임시 폴더만.

A. 하위 줄에서 잘못 합쳐진 번호를 지워도 vcf 사람 줄이 남아 [추가] 할 수 있음, 하위 줄은 저절로 체크·회색
B. 대표를 추가해도 하위 줄이 남음(서로 따로 판정)
C. 사람이 정한 체크가 이김(다시 읽어도)
D. 하위 줄 두 번 누르면 '고치기'
E. 되돌리기·다시 실행 — 추가·고치기·사진 지우기(파일까지, 창을 닫으면 휴지통)
F. 창을 다시 열면 이어서(vcf 를 다시 읽지 않음)·[새로 비교]
"""
import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox, QDialog
from PyQt6.QtTest import QTest
from pathlib import Path
from PIL import Image

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_rosterfix_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_rosterfix_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
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
    "BEGIN:VCARD", "VERSION:3.0", "FN:가짜정", "TEL;TYPE=CELL:" + num(5), "END:VCARD", ""])

try:
    from viewer.bizcard import people as P, store as S, roster as RS
    from viewer.widgets import bizcard_import_dialog as BI
    TRASHED = []

    def fake_trash(_parent, _mw, paths):
        for p in paths:
            TRASHED.append(p)
            os.remove(p)
        return []
    BI.trash_paths = fake_trash                         # 휴지통 대신 기록(검사가 사용자 휴지통을 건드리지 않게)
    FOLD = TMP / "cards"
    (FOLD / "정리").mkdir(parents=True)
    db = TMP / "local" / "bizcard.db"
    st = S.BizcardStore(db)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    P.src_init(st)
    m = P._insert_contact(st, {"name": "가짜갑", "phones": [("cell", num(1)), ("cell", num(2))]}, ["명함"])   # 을의 번호가 섞임
    f = FOLD / "정리" / "가짜정_가짜사.jpg"
    Image.new("RGB", (300, 180), "white").save(f)
    img = st.upsert({"front": str(f), "name": "가짜정", "company": "가짜사", "phones": [("cell", num(5)), ("cell", num(6))]})
    ph = P.next_photo_path(str(f))
    ph.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (60, 80), "gray").save(ph)
    st.con.commit()
    st.close()
    settings_store.set_picture_prefs({"bizcard_folder": str(FOLD)})
    vcf = TMP / "받은" / "주소록.vcf"
    vcf.parent.mkdir()
    vcf.write_text(VCF, encoding="utf-8")

    from viewer.widgets import bizcard_find_dialog as FD, bizcard_dupe_dialog as DD
    fd = FD.BizcardFindDialog(None, db=db)
    fd._bz_folder = str(FOLD)
    fd.show()
    pump(lambda: fd.table.rowCount() == 2)
    rd = fd.open_roster(exec_=False)
    rd.open_vcf(str(vcf))
    pump(lambda: not rd.loading and rd.view() == "vcf" and rd.tree.topLevelItemCount() >= 2, timeout=10)
    G = lambda name: next((g for g in rd.groups if g["person"]["name"] == name), None)      # noqa: E731

    def item_of(gi, cid=None):
        for i in range(rd.tree.topLevelItemCount()):
            top = rd.tree.topLevelItem(i)
            if top.data(0, 0x0100) == ("vcf", gi):
                if cid is None:
                    return top
                return next((top.child(j) for j in range(top.childCount()) if top.child(j).data(0, 0x0100)[1] == cid), None)
        return None
    g_eul = G("가짜을")
    chk(g_eul is not None and [s["card"]["id"] for s in g_eul["subs"]] == [m] and not g_eul["auto"], "(전제) '을' 아래 잘못 합쳐진 '갑' 명단")

    print("=== A 하위 번호를 지워도 줄이 남음 ===")
    rd.select_card(m, gi=g_eul["gi"])
    c = P.card_by_id(fd._store(), m)
    ed = DD.CardEditDialog(c, rd)
    for g_, k_, e_ in ed.extra_eds:
        if g_ == "phone":
            e_.setText("")                                  # 둘째 휴대폰(을의 번호)을 지움
    rd.edit(dlg=ed)
    pump(lambda: not rd.loading, timeout=10)
    g_eul = G("가짜을")
    sub_it = item_of(g_eul["gi"], m) if g_eul else None
    chk(g_eul is not None and sub_it is not None, "A '을' vcf 줄과 하위 줄이 남음(작업 목록 고정)")
    chk(sub_it is not None and sub_it.checkState(0) == Qt.CheckState.Checked
        and sub_it.foreground(0).color() == rd.palette().placeholderText().color(), "A 하위 줄은 저절로 체크·회색")
    chk(g_eul is not None and not g_eul["auto"] and item_of(g_eul["gi"]).checkState(0) == Qt.CheckState.Unchecked,
        "A 대표 줄은 아직 해결 아님(따로 판정)")
    rd.select_person(g_eul["gi"])
    chk(rd.btn_add.isEnabled(), "A 대표 줄에서 [추가] 켜짐")

    print("\n=== B 대표 추가해도 하위가 남음 ===")
    rd.add()
    pump(lambda: not rd.loading, timeout=10)
    g_eul = G("가짜을")
    chk(g_eul is not None and g_eul["auto"] and item_of(g_eul["gi"], m) is not None, "B 대표는 해결·하위 줄은 그대로", str(g_eul and g_eul["auto"]))
    g_gab = G("가짜갑")
    chk(g_gab is not None and all(s["auto"] for s in g_gab["subs"]), "B '갑' 의 같은 이름 줄도 번호가 vcf 와 같아져 해결")

    print("\n=== C 사람이 정한 체크가 이김 ===")
    it = item_of(g_eul["gi"], m)
    it.setCheckState(0, Qt.CheckState.Unchecked)
    rd.reload()
    pump(lambda: not rd.loading, timeout=10)
    it = item_of(g_eul["gi"], m)
    chk(it.checkState(0) == Qt.CheckState.Unchecked and it.foreground(0).color() == rd.palette().text().color(),
        "C 저절로 체크된 줄을 사람이 풀면 다시 읽어도 풀린 채·회색 아님")

    print("\n=== D 두 번 누르면 고치기 ===")
    hits = []
    _ex = DD.CardEditDialog.exec
    DD.CardEditDialog.exec = lambda self_: hits.append(self_.card["id"]) or QDialog.DialogCode.Rejected
    try:
        rd.tree.scrollToItem(it)
        rect = rd.tree.visualItemRect(it)
        # 실제 두 번 누름 = 누름·뗌 다음 두 번 누름(Qt6 은 앞 누름이 없으면 itemDoubleClicked 를 내지 않는다)
        QTest.mouseClick(rd.tree.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, rect.center())
        QTest.mouseDClick(rd.tree.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, rect.center())
        app.processEvents()
    finally:
        DD.CardEditDialog.exec = _ex
    chk(hits == [m], "D 하위 줄을 두 번 누르면 그 명단 '고치기' 창", str(hits))

    print("\n=== E 되돌리기·다시 실행 ===")
    n_before = len(RS.all_cards(fd._store()))
    rd.undo()                                            # 추가 되돌림
    pump(lambda: not rd.loading, timeout=10)
    chk(len(RS.all_cards(fd._store())) == n_before - 1 and not G("가짜을")["auto"], "E 되돌리기 — 추가한 '을' 이 빠지고 대표 줄은 미해결로")
    rd.undo()                                            # 번호 지우기 되돌림
    pump(lambda: not rd.loading, timeout=10)
    chk(P.mobiles_010(P.card_by_id(fd._store(), m)) == ["01000001111", "01000002222"], "E 되돌리기 — 지운 번호가 돌아옴")
    rd.redo()
    pump(lambda: not rd.loading, timeout=10)
    chk(P.mobiles_010(P.card_by_id(fd._store(), m)) == ["01000001111"] and rd.btn_redo.isEnabled(), "E 다시 실행 — 번호를 다시 지움")
    # 사진 지우기(파일) → 되돌리기 → 다시 실행 → 창을 닫으면 휴지통
    rd.set_view("multi")
    pump(lambda: not rd.loading and rd.view() == "multi", timeout=10)
    rd.select_card(img)
    rd.delete_picks(P.card_by_id(fd._store(), img), [str(ph)], ask=False)
    pump(lambda: not rd.loading, timeout=10)
    held = rd.held_files()
    chk(not ph.exists() and len(held) == 1 and not TRASHED, "E 사진 지우기는 휴지통 대신 '병합 보관' 으로(되돌릴 수 있게)", str(held))
    rd.undo()
    pump(lambda: not rd.loading, timeout=10)
    chk(ph.exists() and not rd.held_files(), "E 되돌리기 — 사진이 제자리로")
    rd.redo()
    pump(lambda: not rd.loading, timeout=10)
    chk(not ph.exists() and len(rd.held_files()) == 1, "E 다시 실행 — 다시 보관으로")
    rd.close()
    chk(len(TRASHED) == 1 and Path(TRASHED[0]).parent.name == P.HOLD_DIR, "E 창을 닫으면 보관한 파일을 휴지통으로", str(TRASHED))

    print("\n=== F 다시 열면 이어서·새로 비교 ===")
    os.replace(vcf, str(vcf) + ".bak")                  # vcf 가 없어도 이어서 보인다(다시 읽지 않음)
    rd2 = fd.open_roster(exec_=False)
    rd2.set_view("vcf")
    pump(lambda: not rd2.loading and rd2.tree.topLevelItemCount() >= 2, timeout=10)
    g2 = next((g for g in rd2.groups if g["person"]["name"] == "가짜을"), None)
    it2 = None
    if g2 is not None:
        top = next(rd2.tree.topLevelItem(i) for i in range(rd2.tree.topLevelItemCount()) if rd2.tree.topLevelItem(i).data(0, 0x0100) == ("vcf", g2["gi"]))
        it2 = next((top.child(j) for j in range(top.childCount()) if top.child(j).data(0, 0x0100)[1] == m), None)
    chk(g2 is not None and it2 is not None and it2.checkState(0) == Qt.CheckState.Unchecked and not rd2.undo_stack,
        "F 다시 열면 같은 작업 목록·사람이 정한 체크 그대로(되돌리기 목록은 비움)")
    os.replace(str(vcf) + ".bak", vcf)
    rd2.recompare()
    pump(lambda: not rd2.loading, timeout=10)
    chk(not rd2.checks and rd2.frozen is not None and not any(g["person"]["name"] == "가짜을" and g["subs"] for g in rd2.groups),
        "F [새로 비교] — 체크를 지우고 지금 명단으로 다시 견줌('을' 은 이제 같은 번호를 가진 다른 이름 명단이 없음)")
    rd2.close()
    fd.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외")
print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
