# -*- coding: utf-8 -*-
"""저장하지 않은 회전은 기억하지 않는다 · 파일을 옮길 때는 연 뒤 생긴 변경만 묻는다 (책갈피창·저장 SOT §4.7.16 '회전', 261115-3).

결함(설치본 beta.15): 편집하지 않았는데 다른 파일로 옮길 때 '저장하지 않은 편집 변경사항' 창 — 그 파일의 `page_meta.json` 에
예전에 돌려 두고 저장하지 않은 회전(39~42쪽)이 '저장 전 회전'(앱을 다시 켜도 남음, 261011-2)으로 남아 있었다.
사용자 결정: 추천대로(옮길 때는 연 뒤 생긴 변경만) + "수정하였던 것을 저장하지 않고 종료했을 경우 이를 기억할 필요 없음".
실제 MainWindow·책갈피창 파일 누르기(`_on_bookmark_activated`)·`PageMetaStore` 로(오프스크린, 시험 모드 설정 — 검사 작성 SOT §14.7.2).
A. 옛 판이 남긴 회전이 든 page_meta.json — 편집 모드에서 그 파일을 열고 다른 파일로 옮겨도 묻지 않는다(수정 전: 물음), 그 회전은 쓰지 않는다
B. 이번 실행에서 실제로 돌리면 옮길 때 여전히 묻는다
C. 회전은 page_meta.json 에 쓰지 않는다(수정 전: 씀) — 같은 실행에서 폴더를 다시 열면 남고, 다시 켜면(실행 메모리 없음) 없다
D. 발표 크롭(crop_global)·숨김 등 다른 기록은 그대로 저장된다
"""
import os, sys, time, json, shutil, tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pathlib import Path
from PyQt6.QtCore import QStandardPaths, QCoreApplication
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_rot_forget_%d" % os.getpid())
import modal_guard
guard = modal_guard.install(label=lambda: "회전 기억", echo=False)
import test_fixtures as TF
TF.autotag_off()            # 이 검사는 편집 확인만 본다(검사 작성 SOT §14.7.2 의 23)
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


def spin(sec):
    t = time.monotonic()
    while time.monotonic() - t < sec:
        app.processEvents()
        time.sleep(0.01)


def asked():
    return [s for s in guard.seen if "저장하지 않은 편집" in s[2]]


root = Path(tempfile.mkdtemp(prefix="polypdf_rotforget_"))
try:
    folder = root / "docs"
    folder.mkdir()
    a, b = folder / "a.pdf", folder / "b.pdf"
    shutil.copyfile(TF.text_pdf(), a)
    shutil.copyfile(TF.text_pdf(), b)
    (folder / "page_meta.json").write_text(json.dumps({"version": 2, "files": {
        "a.pdf": {"crop_global": [5.0, 5.0, 0.0, 0.0], "crop_pages": {}, "hidden": [], "rotation": {"1": 270, "2": 270}, "drawings": {}}}},
        ensure_ascii=False), encoding="utf-8")
    from viewer.app import MainWindow
    from viewer import page_meta as PM, bg_write
    mw = MainWindow(); mw._skip_save_on_close = True
    mw.resize(1200, 850); mw.show(); spin(0.3)
    mw.open_folder(str(folder)); spin(0.8)
    bt = mw.bookmark_tree
    if not bt.is_edit_mode():
        bt.btn_edit.setChecked(True); spin(0.3)
    chk(mw._in_edit(), "준비 — 편집 모드")

    def go(p):
        mw._on_bookmark_activated(str(p), 0); spin(0.3)
        TF.wait_main_open(mw); spin(0.3)

    # A
    go(a)
    chk(mw._rotations_for(str(a)) == {}, "A 옛 판이 남긴 저장 전 회전은 쓰지 않는다", str(mw._rotations_for(str(a))))
    guard.seen.clear()
    go(b)
    chk(not asked() and Path(mw.main_view.current_file()).name == "b.pdf", "A 편집 없이 옮기면 묻지 않는다",
        "%s %s" % (guard.report(), mw.main_view.current_file()))

    # B
    go(a)
    mw._rotate_pages([0], 90); spin(0.3)
    chk(mw._rotations_for(str(a)) == {0: 90}, "B 이번 실행에서 돌린 회전", str(mw._rotations_for(str(a))))
    guard.seen.clear()
    mw._on_bookmark_activated(str(b), 0); spin(0.5)
    chk(len(asked()) == 1 and Path(mw.main_view.current_file()).name == "a.pdf", "B 실제로 돌렸으면 옮길 때 묻는다(취소 → 그대로)",
        "%s %s" % (guard.report(), mw.main_view.current_file()))

    # C — 편집 모드를 끄고(묻는 창은 '저장 안 함' 쪽이 아닌 그대로 두기) 편집 밖에서 돌려 곧바로 저장되는 길
    mw._confirm_edit_save = lambda *a_, **k: "discard"
    bt.btn_edit.setChecked(False); spin(0.3)
    chk(not mw._in_edit(), "C 편집 모드 끔")
    mw._rotate_pages([0], 90); spin(0.3)
    st = mw._ensure_page_meta_store()
    st.set_hidden(str(a), [3], True); st.save()
    bg_write.flush() if hasattr(bg_write, "flush") else None
    spin(0.5)
    disk = json.loads((folder / "page_meta.json").read_text(encoding="utf-8"))
    fa = disk["files"].get("a.pdf") or {}
    chk(not fa.get("rotation"), "C 회전은 page_meta.json 에 쓰지 않는다", str(fa.get("rotation")))
    chk(mw._rotations_for(str(a)) == {0: 90}, "C 이번 실행 동안은 남는다", str(mw._rotations_for(str(a))))
    # D
    chk(list(fa.get("crop_global") or [])[:2] == [5.0, 5.0] and fa.get("hidden") == [3], "D 발표 크롭·숨김은 그대로 저장", str(fa))
    st2 = PM.PageMetaStore(folder)
    chk(st2.rotations(str(a)) == {0: 90}, "C 같은 실행에서 폴더를 다시 읽어도 남는다", str(st2.rotations(str(a))))
    PM._ROT_MEM.clear()                                  # 앱을 다시 켠 것과 같다(실행 메모리 없음)
    st3 = PM.PageMetaStore(folder)
    chk(st3.rotations(str(a)) == {}, "C 다시 켜면 저장하지 않은 회전은 없다", str(st3.rotations(str(a))))
    mw._confirm_close_edit = lambda: True
    mw.close(); spin(0.2)
except Exception:
    import traceback
    traceback.print_exc()
    fails.append("예외")
finally:
    shutil.rmtree(str(root), ignore_errors=True)

print()
print("ALL PASS" if not fails else "FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
