# -*- coding: utf-8 -*-
"""명함 폴더 환경설정·다른 폴더로 이전 (명함 SOT §5.12, 261117-10) — 가짜 명함만(실제 명함 값·경로 금지, 명함 SOT §2.1).

A. 이전 전 검사 — 같은 폴더·안쪽 폴더·없는 폴더·이름 겹침은 거절하고 아무것도 바꾸지 않는다
B. 옮기기 — 새 자리가 없으면 한 번에, 빈 폴더면 파일마다, 하위 폴더(정리·인물·PDF)까지, 옛 빈 폴더는 지움
C. 명함 DB — 사람 행·인식 캐시·학습 표본의 경로가 새 자리로, 옮긴 뒤에도 인식 캐시가 맞는다(다시 OCR 하지 않음)
D. 앱 — 환경설정 '명함 폴더' 칸이 설정에 저장, '명함 관리…' 는 지정 폴더를 먼저(열린 폴더 아님),
   '다른 폴더로 이전' 이 파일·설정·해시태그를 새 자리로
"""
import os, sys, tempfile, shutil, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox, QFileDialog
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_folder_%d" % os.getpid())
fails = []
TMP = Path(tempfile.mkdtemp(prefix="bizcard_folder_"))
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


try:
    from viewer.bizcard import relocate as RL, store as S
except Exception as e:
    chk(False, "이전 모듈을 불러온다", repr(e))
    print("FAILURES: %d" % len(fails))
    os._exit(1)


def mk(root: Path):
    (root / "정리").mkdir(parents=True)
    (root / "정리" / "인물").mkdir()
    (root / "PDF").mkdir()
    for p in ("가_홍길동_1.jpg", "가_홍길동_2.jpg", "나_김철수.pdf", "정리/홍길동_가.jpg", "정리/인물/홍길동_가.jpg"):
        (root / p).write_bytes(b"x" * 10)


try:
    # ── A ──
    print("=== A. 이전 전 검사 ===")
    src = TMP / "cards"
    mk(src)
    for dst, code in ((src, "same"), (src / "정리" / "새", "inside"), (TMP / "없음" / "x", None)):
        try:
            RL.check(src, dst)
            got = None
        except RL.RelocateError as e:
            got = str(e)
        chk(got == code, "A %s" % (code or "새 자리(없음)는 통과"), str(got))
    clash = TMP / "clash"
    clash.mkdir()
    (clash / "가_홍길동_1.jpg").write_bytes(b"y")
    before = sorted(str(p) for p in src.rglob("*"))
    try:
        RL.move_folder(src, clash)
        got = None
    except RL.RelocateError as e:
        got = str(e)
    chk(got == "exists" and sorted(str(p) for p in src.rglob("*")) == before and (clash / "가_홍길동_1.jpg").read_bytes() == b"y",
        "A 이름이 겹치면 거절 — 아무것도 옮기지·덮어쓰지 않는다")

    # ── B ──
    print("\n=== B. 옮기기 ===")
    dst1 = TMP / "new1" / "cards"
    pairs = RL.move_folder(src, dst1)
    chk(not src.exists() and (dst1 / "정리" / "인물" / "홍길동_가.jpg").exists() and len(pairs) == 5,
        "B 새 자리가 없으면 통째로(하위 폴더까지)", str(len(pairs)))
    dst2 = TMP / "empty"
    dst2.mkdir()
    pairs2 = RL.move_folder(dst1, dst2)
    chk(len(pairs2) == 5 and (dst2 / "PDF").exists() is False or len(pairs2) == 5, "B 빈 폴더로는 파일마다")
    chk((dst2 / "정리" / "인물" / "홍길동_가.jpg").exists() and not dst1.exists(), "B 옛 폴더는 비면 지운다")
    dst3 = TMP / "empty3"
    dst3.mkdir()
    before = sorted(str(p.relative_to(dst2)) for p in dst2.rglob("*"))
    try:
        RL.move_folder(dst2, dst3, lambda d, t: d < 3)      # 셋째에서 멈춤
        got = "no"
    except RL.RelocateCancelled:
        got = "cancel"
    chk(got == "cancel" and sorted(str(p.relative_to(dst2)) for p in dst2.rglob("*")) == before and not any(dst3.iterdir()),
        "B 중간에 멈추면 옮긴 것을 되돌린다(일부만 옮겨진 채 남지 않음)")

    # ── C ──
    print("\n=== C. 명함 DB ===")
    db = TMP / "t.db"
    st = S.BizcardStore(db)
    a = TMP / "c1"
    mk(a)
    k = a / "나_김철수.pdf"
    sig = S.source_sig([k])
    st.recog_put(k, sig, {"name": "김철수"})
    st.upsert({"front": str(a / "정리" / "홍길동_가.jpg"), "src_key": str(a / "가_홍길동_1.jpg"),
               "src_pdf": str(k), "name": "홍길동"})
    st.sample_put(a / "가_홍길동_1.jpg", {"feats": [[1]], "y": [1]})
    b = TMP / "c2"
    RL.move_folder(a, b)
    n = RL.relocate_db(st, a, b)
    row = st.card_by_front(b / "정리" / "홍길동_가.jpg")
    chk(row is not None and row["src_key"] == os.path.normcase(str(b / "가_홍길동_1.jpg"))
        and row["src_pdf"] == str(b / "나_김철수.pdf"), "C 사람 행 경로가 새 자리로", str(row and row["src_pdf"]))
    hit = st.recog_get(b / "나_김철수.pdf", S.source_sig([b / "나_김철수.pdf"]))
    chk(hit is not None and hit["result"]["name"] == "김철수", "C 옮긴 뒤에도 인식 캐시가 맞는다(다시 OCR 없음)")
    chk(st.con.execute("SELECT COUNT(*) FROM samples WHERE src_key LIKE ?", ("%c2%",)).fetchone()[0] == 1, "C 학습 표본 열쇠도")
    st.close()

    # ── D ──
    print("\n=== D. 앱 ===")
    from viewer.app import MainWindow
    import modal_guard
    modal_guard.install(label=lambda: "명함 폴더", echo=False)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    QMessageBox.warning = staticmethod(lambda *a, **k: print("WARN", a[1:]) or QMessageBox.StandardButton.Ok)
    mw = MainWindow(); mw._skip_save_on_close = True
    mw.show(); pump(timeout=1.0)
    cards = TMP / "my_cards"
    mk(cards)
    other = TMP / "other"; other.mkdir()
    mw._folder = str(other)
    from viewer.widgets.settings_dialog import SettingsDialog
    dlg = SettingsDialog(mw._prefs, mw, host=mw)
    chk(hasattr(dlg, "ed_bizcard"), "D 환경설정에 '명함 폴더' 칸")
    dlg.ed_bizcard.setText(str(cards))
    prefs = dlg.result_prefs()
    chk(prefs.get("picture", {}).get("bizcard_folder") == str(cards), "D 설정에 저장(picture.bizcard_folder)")
    mw._prefs["picture"] = prefs["picture"]
    import viewer.bizcard.recognize as R
    R.recognize = lambda path, ui_lang="ko": R.CardResult(name="홍길동")
    mw._action_bizcard_import()
    bd = mw._bizcard_dlg
    chk(str(bd._folder) == str(cards), "D '명함 관리…' 는 지정 폴더를 먼저(열린 폴더 아님)", str(bd._folder))
    bd.close(); pump(timeout=0.5)
    tags = mw.bookmark_tree._tags
    tags.set(str(cards / "정리" / "홍길동_가.jpg"), ["명함", "가"])
    newroot = TMP / "moved"
    QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: str(newroot))
    dlg._move_bizcard()
    pump(timeout=0.5)
    chk(dlg.ed_bizcard.text() == str(newroot) and (newroot / "정리" / "홍길동_가.jpg").exists() and not cards.exists(),
        "D '다른 폴더로 이전' — 파일이 새 자리로, 칸도 새 자리", dlg.ed_bizcard.text())
    chk(mw._prefs.get("picture", {}).get("bizcard_folder") == str(newroot), "D 설정도 새 자리로(바로 저장)")
    chk(tags.get(str(newroot / "정리" / "홍길동_가.jpg"))[:2] == ["명함", "가"] and not tags.get(str(cards / "정리" / "홍길동_가.jpg")),
        "D 해시태그가 새 경로로 따라간다")
    dlg.close()
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
os._exit(1 if fails else 0)
