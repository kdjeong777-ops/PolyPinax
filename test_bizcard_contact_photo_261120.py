# -*- coding: utf-8 -*-
"""그림 없는 주소록 명함의 인물 사진 (명함 SOT §5.24.3 '그림 없는 명함') — 가짜 값만(명함 SOT §2.1).

오프스크린, 실제 설정·데이터 폴더를 쓰지 않는다(검사 작성 SOT §14.7.2).
A. 주소록 명함을 고르면 [사진 추가] 켜짐·[명함 보기] 꺼짐, [사진 추가] 를 누르면 `<명함 폴더>\\인물\\성명_회사명.jpg`
B. 같은 이름의 그림 명함(정리본)이 있으면 `_주소록` — 그림 명함의 사진과 섞이지 않음
C. 성명을 고쳐 [저장] 하면 사진 이름도 따라 바뀜
D. 명함을 지우면 인물 사진도 휴지통으로, 명함 폴더가 없으면 사진 단추 꺼짐
"""
import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox, QFileDialog
from PyQt6.QtTest import QTest
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_cphoto_%d" % os.getpid())
fails = []
TMP = Path(tempfile.mkdtemp(prefix="bizcard_cphoto_"))
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
    """한글 입력 — IME 처럼(검사 작성 SOT §14.7.2 의 24)."""
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
    from PIL import Image
    from viewer.bizcard import people as P, importer as I, apply as AP, store as S, vcard as V
    F = TMP / "cards"
    F.mkdir()
    Image.new("RGB", (339, 186), "white").save(F / "a_1.jpg", quality=90)
    items = {it.base: it for it in I.scan_folder(F)}
    db = TMP / "local" / "bizcard.db"
    AP.apply_cards([{"key": items["a"].key, "front": items["a"].front, "back": "", "pdf": "", "keep_back": False,
                     "name": "홍길동", "company": "가나다", "langs": ["한글"], "phones": [("cell", "010-0000-0001")]}],
                   F / "정리", db)
    st = S.BizcardStore(db)
    P.apply_import(st, [{"name": "이영희", "company": "사아자", "phones": [("cell", "010-0000-0002")]},
                        {"name": "홍길동", "company": "가나다", "phones": [("cell", "010-0000-0003")]}], "주소록", "google")
    cards = {(c["name"], V.is_contact(c)): c for c in P.find(st, "")}
    st.close()
    lee, hong_c, hong_p = cards[("이영희", True)], cards[("홍길동", True)], cards[("홍길동", False)]
    PIC = TMP / "사진.png"
    Image.new("RGB", (60, 80), "pink").save(PIC)
    QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([str(PIC)], ""))
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)

    from viewer.widgets import bizcard_find_dialog as FD
    dlg = FD.BizcardFindDialog(None, db=db)
    dlg._bz_folder = str(F)                            # 환경설정 명함 폴더(검사는 설정 파일 대신)
    dlg.show()
    pump(lambda: dlg.table.rowCount() >= 3)

    def pick(c):
        dlg.table.setCurrentCell(dlg.row_of_id(c["id"]), 0)
        pump(lambda: dlg._card is not None and dlg._card["id"] == c["id"], timeout=3)

    def add_photo():
        QTest.mouseClick(dlg.btn_photo, Qt.MouseButton.LeftButton)
        pump(lambda: not dlg.photo_busy and dlg.photos.count() > 0, timeout=15)

    print("=== A. 주소록 명함에 사진 추가 ===")
    pick(lee)
    chk(dlg.btn_photo.isEnabled() and not dlg.btn_open.isEnabled(), "A 주소록 명함 — [사진 추가] 켜짐, [명함 보기] 꺼짐",
        "%s %s" % (dlg.btn_photo.isEnabled(), dlg.btn_open.isEnabled()))
    add_photo()
    want = F / "인물" / "이영희_사아자.jpg"
    chk(want.exists() and dlg.photos.count() == 1, "A [사진 추가] → 명함 폴더 인물\\성명_회사명.jpg, 썸네일 한 장",
        str(list((F / "인물").glob("*")) if (F / "인물").exists() else "인물 폴더 없음"))
    chk(dlg.btn_photo_del.isEnabled(), "A 사진이 있으면 [사진 삭제] 켜짐")

    print("\n=== B. 같은 이름의 그림 명함 ===")
    pick(hong_c)
    add_photo()
    chk((F / "인물" / "홍길동_가나다_주소록.jpg").exists() and not (F / "인물" / "홍길동_가나다.jpg").exists(),
        "B 같은 이름 그림 명함이 있으면 _주소록", str(sorted(p.name for p in (F / "인물").glob("*"))))
    pick(hong_p)
    chk(dlg.photos.count() == 0, "B 그림 명함 쪽에는 주소록 명함 사진이 섞이지 않음", str(dlg.photo_paths()))

    print("\n=== C. 성명 고쳐 저장 → 사진 이름 따라감 ===")
    pick(lee)
    ed = dlg.eds["name"]
    ed.setFocus()
    ed.selectAll()
    QTest.keyClick(ed, Qt.Key.Key_Delete)
    type_ko(ed, "이수진")
    QTest.mouseClick(dlg.btn_save, Qt.MouseButton.LeftButton)
    pump(lambda: (F / "인물" / "이수진_사아자.jpg").exists(), timeout=5)
    chk((F / "인물" / "이수진_사아자.jpg").exists() and not want.exists(), "C 저장하면 사진도 이수진_사아자.jpg",
        str(sorted(p.name for p in (F / "인물").glob("*"))))
    chk(dlg.photos.count() == 1 and V.is_contact(dlg._card), "C 저장 뒤에도 그림 없는 명함 그대로·사진이 보임",
        "%s %r" % (dlg.photo_paths(), (dlg._card or {}).get("front")))
    st = S.BizcardStore(db)
    chk(V.is_contact(P.card_by_id(st, lee["id"])), "C 명함 DB 열쇠도 contact: 그대로(저장이 경로 열쇠로 바꾸지 않음)")
    st.close()

    print("\n=== D. 지우기·명함 폴더 없음 ===")
    gone = dlg.delete_cards([dlg._card], ask=False)
    chk(gone == 1 and not (F / "인물" / "이수진_사아자.jpg").exists(), "D 명함을 지우면 인물 사진도 휴지통으로",
        str(sorted(p.name for p in (F / "인물").glob("*"))))
    dlg._bz_folder = ""
    pick(hong_p)                                       # 지운 뒤 커서가 이미 그 줄일 수 있어 다른 명함을 거쳐 다시 고른다
    pick(hong_c)
    chk(not dlg.btn_photo.isEnabled(), "D 명함 폴더가 없으면 주소록 명함의 [사진 추가] 꺼짐")
    dlg.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "예외 없이 끝남")
finish()
