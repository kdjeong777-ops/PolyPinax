# -*- coding: utf-8 -*-
"""새 명함 입력의 [사진에서 읽기] (명함 SOT §5.24.1 '사진에서 읽기', 261120-31) — 가짜 명함만 쓴다(명함 SOT §2.1).

A. 명함 관리 [새 명함 입력] → [사진에서 읽기] 를 실제로 눌러 사진 둘을 고르면: 명함 폴더 맨 위에 복사(같은 이름은 ' (2)'), 원본 그대로,
   창이 닫히고 명함 관리에 '입력한 명함만' 이 보이며 켜진 채, 보이는 줄은 넣은 사진 둘뿐, 새 줄이 읽히고 명함 DB 에는 아직 넣지 않는다
   (확인 표 [적용] 전), 필터를 끄면 원래 줄도 보인다
B. 칸에 글을 적어 두었으면 '입력한 칸은 저장하지 않습니다' 를 묻고, [아니요]면 복사하지 않는다
C. 다중 명함을 나누면 잘라낸 사진도 '입력한 명함만' 안에 든다
D. 명함찾기 [새 명함 입력] → [사진에서 읽기] 는 호스트의 명함 관리(명함 폴더)를 열어 같은 필터로 읽는다
"""
import os, sys, time, tempfile, shutil
os.environ["QT_QPA_PLATFORM"] = "offscreen"          # 검사 작성 SOT §14.7
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox, QFileDialog
from PyQt6.QtTest import QTest
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_newread_%d" % os.getpid())
fails = []
TMP = Path(tempfile.mkdtemp(prefix="bizcard_newread_"))
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


from PIL import Image
from viewer.bizcard import recognize as R, store as S, importer as I
from viewer.widgets import bizcard_import_dialog as BD
from viewer.widgets import bizcard_new_dialog as ND


def jpg(p, color="white", size=(339, 186)):
    Image.new("RGB", size, color).save(p, quality=90)


def fake_recognize(path, ui_lang="ko"):
    hn, hc = R.parse_hint(path)
    return R.CardResult(name=hn or "가짜", company=hc, phones=[("cell", "010-0000-0031")], emails=["user@example.com"],
                        name_cands=[R.Cand(hn or "가짜", 4.0)], company_cands=[R.Cand(hc, 2.0)], langs=("한글",),
                        back_promo=None, need_check=())


R.recognize = fake_recognize
I.MultiWorker._run = lambda self: self.finishedAll.emit(True)     # 다중 명함 세기는 이 검사 밖(§5.26 검사가 본다)
asked = []
_o_q = QMessageBox.question
QMessageBox.question = staticmethod(lambda *a, **k: (asked.append(a[2] if len(a) > 2 else ""), QMessageBox.StandardButton.Yes)[1])
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)

G = TMP / "cards"                                    # 명함 폴더
G.mkdir()
for n in ("가나상사_홍길동_1.jpg", "다라기술_김철수_1.jpg"):
    jpg(G / n)
SRC = TMP / "phone_photos"                           # 사진을 고르는 바깥 폴더(원본)
SRC.mkdir()
jpg(SRC / "마바산업_박가짜_1.jpg", "lightyellow")
jpg(SRC / "가나상사_홍길동_1.jpg", "lightblue")      # 같은 이름 — ' (2)' 로 복사
DB = TMP / "local" / "bizcard_newread.db"
picked = [str(SRC / "마바산업_박가짜_1.jpg"), str(SRC / "가나상사_홍길동_1.jpg")]
_o_open = QFileDialog.getOpenFileNames
QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: (list(picked), ""))

try:
    # ── A ──
    print("=== A. 명함 관리 → 사진에서 읽기 ===")
    imp = BD.BizcardImportDialog(str(G), None, db=DB)
    imp.show()
    chk(pump(lambda: imp._worker is not None and imp._worker.done_event.is_set(), timeout=30), "A 명함 관리가 처음 두 장을 읽음")
    n0 = imp.table.rowCount()
    dlg = imp.new_manual(exec_=False)
    pump(timeout=0.3)
    btn = getattr(dlg, "btn_read", None)
    chk(btn is not None and btn.isEnabled(), "A 새 명함 입력 창에 [사진에서 읽기](명함 폴더가 있으면 켜짐)")
    if btn is not None:
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
    chk(pump(lambda: not dlg.isVisible(), timeout=15), "A 복사가 끝나면 창이 닫힘")
    copied = sorted(p.name for p in G.iterdir() if p.is_file())
    chk("마바산업_박가짜_1.jpg" in copied and "가나상사_홍길동_1 (2).jpg" in copied
        and all(os.path.exists(p) for p in picked), "A 명함 폴더 맨 위에 복사(같은 이름은 ' (2)'), 원본 그대로", str(copied))
    chk(pump(lambda: imp.table.rowCount() == n0 + 2 and imp._worker.done_event.is_set(), timeout=30),
        "A 명함 관리에 새 줄 둘이 더해져 읽힘", str(imp.table.rowCount()))
    vis = [os.path.basename(imp._items[r].front) for r in range(imp.table.rowCount()) if not imp.table.isRowHidden(r)]
    chk(imp.chk_sent.isVisible() and imp.chk_sent.isChecked() and sorted(vis) == ["가나상사_홍길동_1 (2).jpg", "마바산업_박가짜_1.jpg"],
        "A '입력한 명함만' 이 켜진 채 넣은 사진 둘만 보임", str(vis))
    st = S.BizcardStore(DB)
    ncards = st.con.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    st.close()
    chk(ncards == 0, "A 명함 DB 에는 아직 넣지 않음(확인 표 [적용] 전)", str(ncards))
    imp.chk_sent.setChecked(False)
    chk(not any(imp.table.isRowHidden(r) for r in range(imp.table.rowCount())), "A 필터를 끄면 원래 줄도 보임")
    imp.chk_sent.setChecked(True)

    # ── B ──
    print("=== B. 적어 둔 칸 ===")
    dlg2 = imp.new_manual(exec_=False)
    pump(timeout=0.3)
    dlg2.eds["name"].setText("적어둔가짜")
    QMessageBox.question = staticmethod(lambda *a, **k: (asked.append(a[2] if len(a) > 2 else ""), QMessageBox.StandardButton.No)[1])
    picked[:] = [str(SRC / "마바산업_박가짜_1.jpg")]
    before = sorted(p.name for p in G.iterdir() if p.is_file())
    QTest.mouseClick(dlg2.btn_read, Qt.MouseButton.LeftButton)
    pump(timeout=0.5)
    chk(asked and "저장하지 않습니다" in asked[-1] and sorted(p.name for p in G.iterdir() if p.is_file()) == before
        and dlg2.isVisible(), "B 적어 둔 칸이 있으면 묻고, [아니요]면 복사하지 않음", str(asked[-1:]))
    dlg2.reject()
    QMessageBox.question = staticmethod(lambda *a, **k: (asked.append(a[2] if len(a) > 2 else ""), QMessageBox.StandardButton.Yes)[1])

    # ── C ──
    print("=== C. 나눈 사진 ===")
    sent = str(G / "마바산업_박가짜_1.jpg")
    (G / "다중 원본").mkdir(exist_ok=True)
    shutil.move(sent, str(G / "다중 원본" / "마바산업_박가짜_1.jpg"))
    crops = [str(G / "마바산업_박가짜_1 명함 01.jpg"), str(G / "마바산업_박가짜_1 명함 02.jpg")]
    for c in crops:
        jpg(Path(c), "pink")
    imp._split_done({sent: crops})
    chk(pump(lambda: imp._worker is not None and imp._worker.done_event.is_set(), timeout=30), "C 나눈 뒤 다시 읽음")
    vis = sorted(os.path.basename(imp._items[r].front) for r in range(imp.table.rowCount()) if not imp.table.isRowHidden(r))
    chk(vis == sorted(["가나상사_홍길동_1 (2).jpg"] + [os.path.basename(c) for c in crops]),
        "C 잘라낸 사진도 '입력한 명함만' 안에(원래 두 장은 숨김)", str(vis))
    imp._closing = True
    imp.close()

    # ── D ──
    print("=== D. 명함찾기 → 사진에서 읽기 ===")
    from viewer.bizcard import standalone
    from viewer.widgets.bizcard_find_dialog import BizcardFindDialog
    G3 = TMP / "cards3"
    G3.mkdir()
    jpg(G3 / "사아상사_이가짜_1.jpg")
    host = standalone.Host()
    fd = BizcardFindDialog(None, host=host)
    host.find_dlg = fd
    fd._bz_folder = str(G3)
    picked[:] = [str(SRC / "마바산업_박가짜_1.jpg")]
    nd = fd.new_card(exec_=False)
    pump(timeout=0.3)
    QTest.mouseClick(nd.btn_read, Qt.MouseButton.LeftButton)
    chk(pump(lambda: getattr(host, "_bizcard_dlg", None) is not None, timeout=15), "D 명함 관리(명함 폴더)가 열림")
    imp3 = host._bizcard_dlg
    ok3 = imp3 is not None and pump(lambda: imp3.table.rowCount() == 2 and imp3._worker is not None
                                    and imp3._worker.done_event.is_set(), timeout=30)
    vis3 = [os.path.basename(imp3._items[r].front) for r in range(imp3.table.rowCount()) if not imp3.table.isRowHidden(r)] if imp3 else []
    chk(ok3 and imp3.chk_sent.isChecked() and vis3 == ["마바산업_박가짜_1.jpg"],
        "D 같은 필터로 넣은 사진만 보이고 읽힘", str(vis3))
    if imp3 is not None:
        imp3._closing = True
        imp3.close()
    fd.close()
finally:
    QFileDialog.getOpenFileNames = _o_open
    QMessageBox.question = _o_q
    pump(timeout=0.5)
    shutil.rmtree(TMP, ignore_errors=True)

print()
print("ALL PASS" if not fails else "FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
