# -*- coding: utf-8 -*-
"""전화번호 꼴 맞춤 (명함 SOT §5.11 '번호 꼴'·'`+82`·기본 국가'·'치는 대로 하이픈') — 가짜 번호만(010-0000-xxxx, 명함 SOT §2.1).

오프스크린, 실제 설정·데이터 폴더를 쓰지 않는다(검사 작성 SOT §14.7.2).
A. 꼴 한 곳(`phone.normalize`) — 01012345678·+821012345678 → 010-…, 지역·대표·050x, 숫자 아닌 글은 그대로, 기본 국가 지정 안 함이면 +82-…
B. 인식 — `+82` 로 읽힌 번호(한국이면 국내 꼴, 지정 안 함이면 국제 꼴), 띄어 읽힌 휴대폰
C. 명함찾기 세부 칸 — 실제 키 입력으로 하이픈 자동·`-` 를 쳐도 겹치지 않음·하이픈 Backspace·커서·+82 는 떠날 때·[저장] 하면 DB 에 그 꼴
D. 명함 관리 확인 표 휴대폰 칸 편집기 — 실제 키 입력·넣으면 그 꼴
E. vCard(주소록) 가져오기·내보내기도 같은 꼴, 환경설정 '전화번호 기본 국가' 칸이 설정에 남음
"""
import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox, QLineEdit
from PyQt6.QtTest import QTest
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_phone_%d" % os.getpid())
fails = []
TMP = Path(tempfile.mkdtemp(prefix="bizcard_phone_"))
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


def finish():
    print("FAILURES: %d" % len(fails))
    for f in fails:
        print("  -", f)
    sys.stdout.flush()
    os._exit(1 if fails else 0)


def retype(ed, keys):
    """칸을 비우고 실제 키로 친다."""
    ed.setFocus()
    ed.selectAll()
    QTest.keyClick(ed, Qt.Key.Key_Delete)
    QTest.keyClicks(ed, keys)


try:
    from viewer.bizcard import phone as PH
except Exception as e:                       # 이 판 전 코드엔 모듈이 없다
    chk(False, "번호 꼴 모듈(viewer/bizcard/phone.py)을 불러온다", repr(e))
    PH = None

try:
    from viewer.bizcard import recognize as R, vcard as V, importer as I, apply as AP, store as S, people as P

    if PH is not None:
        print("=== A. 꼴 한 곳 ===")
        PH.set_country(PH.KR)
        cases = {"01000001234": "010-0000-1234", "+821000001234": "010-0000-1234", "+82 10-0000-1234": "010-0000-1234",
                 "+82-010-0000-1234": "010-0000-1234", "010 0000 1234": "010-0000-1234", "010.0000.1234": "010-0000-1234",
                 "0110001234": "011-000-1234", "020001234": "02-000-1234", "0200001234": "02-0000-1234",
                 "0310001234": "031-000-1234", "03100001234": "031-0000-1234", "07000001234": "070-0000-1234",
                 "05050001234": "0505-000-1234", "15880000": "1588-0000", "+1 555 000 1234": "+1-555-000-1234",
                 "010-0000-1234 내선 5": "010-0000-1234 내선 5", "12345": "12345", "": ""}
        bad = {k: PH.normalize(k) for k, v in cases.items() if PH.normalize(k) != v}
        chk(not bad, "A 기본 국가 한국 — 휴대폰·+82·지역·대표·050x·해외·숫자 아닌 글", repr(bad))
        PH.set_country("")
        chk(PH.normalize("+821000001234") == "+82-10-0000-1234" and PH.normalize("01000001234") == "010-0000-1234",
            "A 기본 국가 지정 안 함 — +82 는 국제 꼴, 국내 번호는 국내 꼴", PH.normalize("+821000001234"))
        PH.set_country(PH.KR)

    print("\n=== B. 인식 ===")
    if PH is not None:
        PH.set_country(PH.KR)
    got = R.pick_phones(["M. +82 10 0000 1234", "T. 02 0000 1235"])
    chk(("cell", "010-0000-1234") in got and ("work", "02-0000-1235") in got, "B +82 로 읽힌 휴대폰 → 010-…(한국)", repr(got))
    got = R.pick_phones(["HP 010 0000 1236"])
    chk(got == [("cell", "010-0000-1236")], "B 띄어 읽힌 휴대폰 → 하이픈 꼴", repr(got))
    if PH is not None:
        PH.set_country("")
        got = R.pick_phones(["M. +82 10 0000 1234"])
        chk(got == [("cell", "+82-10-0000-1234")], "B 기본 국가 지정 안 함 — +82 휴대폰은 국제 꼴, 종류는 휴대폰", repr(got))
        PH.set_country(PH.KR)

    print("\n=== C. 명함찾기 세부 칸 (실제 키 입력) ===")
    from PIL import Image
    F = TMP / "cards"
    F.mkdir()
    Image.new("RGB", (339, 186), "white").save(F / "a_1.jpg", quality=90)
    items = {it.base: it for it in I.scan_folder(F)}
    db = TMP / "local" / "bizcard.db"
    AP.apply_cards([{"key": items["a"].key, "front": items["a"].front, "back": "", "pdf": "", "keep_back": False,
                     "name": "홍길동", "company": "가나다", "langs": ["한글"],
                     "phones": [("cell", "01000000001"), ("work", "02-0000-0002")], "emails": ["hong@example.com"]}], F / "정리", db)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Discard)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    from viewer.widgets import bizcard_find_dialog as FD
    dlg = FD.BizcardFindDialog(None, db=db)
    dlg.show()
    pump(lambda: dlg.table.rowCount() >= 1)
    dlg.table.setCurrentCell(0, 0)
    pump(lambda: dlg._card is not None)
    ed = dlg.eds["cell"]
    chk(ed.text() == "010-0000-0001", "C 옛 값(01000000001)도 보일 때 꼴을 맞춤", repr(ed.text()))
    chk(dlg.table.item(0, FD.C_PHONE).text() == "010-0000-0001", "C 목록 전화 열도 같은 꼴",
        repr(dlg.table.item(0, FD.C_PHONE).text()))
    retype(ed, "01000001234")
    chk(ed.text() == "010-0000-1234" and ed.cursorPosition() == len(ed.text()), "C 숫자만 쳐도 하이픈 자동, 커서는 끝",
        "%r %d" % (ed.text(), ed.cursorPosition()))
    retype(ed, "0100")
    chk(ed.text() == "010-0", "C 치는 중에도 하이픈(010-0)", repr(ed.text()))
    retype(ed, "010-0000-1234")
    chk(ed.text() == "010-0000-1234", "C '-' 를 직접 쳐도 겹치지 않음", repr(ed.text()))
    ed.setCursorPosition(9)                            # 둘째 하이픈 뒤
    QTest.keyClick(ed, Qt.Key.Key_Backspace)
    chk(ed.text() == "010-0001-234" and ed.cursorPosition() == 7, "C 하이픈 앞 Backspace — 그 앞 숫자를 지우고 커서는 그 자리",
        "%r %d" % (ed.text(), ed.cursorPosition()))
    ed.setCursorPosition(4)                            # '010-' 뒤에 숫자 하나 끼우기
    QTest.keyClicks(ed, "9")
    chk(ed.text() == "010-9000-1234" and ed.cursorPosition() == 5, "C 가운데 끼워 쳐도 커서는 친 숫자 뒤",
        "%r %d" % (ed.text(), ed.cursorPosition()))
    retype(ed, "+821000001234")
    chk(ed.text() == "+821000001234", "C '+' 국제 번호는 치는 동안 그대로", repr(ed.text()))
    QTest.keyClick(ed, Qt.Key.Key_Return)
    chk(ed.text() == "010-0000-1234", "C 칸을 떠나면(Enter) +82 → 010-…", repr(ed.text()))
    retype(dlg.eds["work"], "0200001235")
    chk(dlg.eds["work"].text() == "02-0000-1235", "C 전화 칸 — 서울 02 꼴", repr(dlg.eds["work"].text()))
    retype(dlg.eds["fax"], "0310001236")
    chk(dlg.eds["fax"].text() == "031-000-1236", "C 팩스 칸 — 지역번호 꼴", repr(dlg.eds["fax"].text()))
    chk(dlg.btn_save.isEnabled(), "C 고치면 [저장] 켜짐")
    QTest.mouseClick(dlg.btn_save, Qt.MouseButton.LeftButton)
    st = S.BizcardStore(db)
    ph = [tuple(x) for x in next(r for r in P.find(st, "") if r["name"] == "홍길동")["phones"]]
    st.close()
    chk(("cell", "010-0000-1234") in ph and ("work", "02-0000-1235") in ph and ("fax", "031-000-1236") in ph,
        "C [저장] 하면 명함 DB 에 그 꼴", repr(ph))
    dlg.close()

    print("\n=== D. 명함 관리 확인 표 휴대폰 칸 ===")

    def fake_recognize(path, ui_lang="ko"):
        return R.CardResult(name="홍길동", company="가나다", phones=[("cell", "010-0000-0009")], emails=["user@example.com"],
                            name_cands=[R.Cand("홍길동", 4.0)], company_cands=[R.Cand("가나다", 2.0)], langs=("한글",),
                            back_promo=None, need_check=())
    R.recognize = fake_recognize
    G = TMP / "cards2"
    G.mkdir()
    Image.new("RGB", (339, 186), "ivory").save(G / "b_1.jpg", quality=90)
    from viewer.widgets import bizcard_import_dialog as BD
    idlg = BD.BizcardImportDialog(str(G), None, db=TMP / "local" / "bizcard2.db")
    idlg.show()
    pump(lambda: idlg.bar.value() == 1, timeout=30)
    tbl = idlg.table
    # 진행 막대는 신호 때 오르고 줄은 나눠 채운다(_drain_pending) — 부하 때 편집 중 값을 덮지 않게 줄이 채워질 때까지
    pump(lambda: not idlg._pending and tbl.item(0, BD.C_CELL).text() == "010-0000-0009", timeout=30)
    tbl.setFocus()
    tbl.setCurrentCell(0, BD.C_CELL)
    QTest.keyClick(tbl.viewport(), Qt.Key.Key_F2)
    tbl.editItem(tbl.item(0, BD.C_CELL)) if not tbl.findChild(QLineEdit) else None
    pump(lambda: tbl.findChild(QLineEdit) is not None, timeout=3)
    ted = tbl.findChild(QLineEdit)
    if ted is None:
        chk(False, "D 휴대폰 칸 편집기가 열림")
    else:
        retype(ted, "01000005678")
        chk(ted.text() == "010-0000-5678", "D 편집기에서 치는 대로 하이픈", repr(ted.text()))
        retype(ted, "+82 10 0000 5679")
        QTest.keyClick(ted, Qt.Key.Key_Return)
        pump(lambda: tbl.item(0, BD.C_CELL).text() == "010-0000-5679", timeout=2)
        chk(tbl.item(0, BD.C_CELL).text() == "010-0000-5679", "D 넣으면 +82 → 010-…", repr(tbl.item(0, BD.C_CELL).text()))
        chk(("cell", "010-0000-5679") in idlg._row_values(0)["phones"], "D 적용할 값도 그 꼴")
    idlg.close()

    print("\n=== E. vCard·환경설정 ===")
    vcf = "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:홍길동\r\nTEL;TYPE=CELL:+82 10 0000 1237\r\nTEL;TYPE=WORK:0200001238\r\nEND:VCARD\r\n"
    ppl = V.people_from_vcf(vcf)
    phs = ppl[0]["phones"] if ppl else []
    chk(("cell", "010-0000-1237") in phs and ("work", "02-0000-1238") in phs, "E 주소록 가져오기 — 같은 꼴", repr(phs))
    out = V.card_to_vcard({"name": "홍길동", "phones": [("cell", "01000001239")]})
    out2 = V.card_to_vcard({"name": "홍길동", "phones": [("cell", "01000001239")]}, style="remember")
    chk("TEL;TYPE=CELL:010-0000-1239" in out and "TEL;TYPE=work,cell:010-0000-1239" in out2,
        "E vCard 내보내기(구글·리멤버) — 옛 값도 그 꼴", repr(out2))
    from viewer.widgets import settings_dialog as SD
    sdlg = SD.SettingsDialog({}, None) if hasattr(SD, "SettingsDialog") else None
    cmb = getattr(sdlg, "cmb_phone_country", None)
    chk(cmb is not None and cmb.currentData() == "KR", "E 환경설정 '전화번호 기본 국가' 칸 — 처음 값 한국")
    if cmb is not None:
        cmb.setCurrentIndex(cmb.findData(""))
        chk(sdlg.result_prefs().get("picture", {}).get("phone_country") == "", "E 고른 값이 picture.phone_country 로",
            repr(sdlg.result_prefs().get("picture")))
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "예외 없이 끝남")
finish()
