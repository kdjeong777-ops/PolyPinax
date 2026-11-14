# -*- coding: utf-8 -*-
"""261115-4: 목록을 다시 만들어도 책갈피창 선택은 본문에 열린 파일 (책갈피창·저장 SOT §4.7.24).

사용자 지시: "책갈피 새로고침 후, 선택되어 있던 파일의 선택이 없어졌어. 새로고침하더라도 해당 파일의 선택이 유지하도록 수정해.
만일 그 파일이 없어졌으면, 그 다음 파일을 선택하도록 해." · "일부 작업을 진행한 후 썸네일과 본화면에 파일 내용을 보여주고 있는데도,
책갈피창의 파일 선택이 해제되는 경우가 있어."

A. ↻ 새로고침(단추 길 refresh)·정렬 바꾸기·보기(단일/트리) 바꾸기·편집 취소 다시 읽기 뒤 본문 파일 줄이 골라져 있다(수정 전: ↻·정렬·편집 취소에서 고른 줄 없음)
B. 되살리기는 본문을 다시 열지 않는다 — 보던 쪽 그대로
C. 본문 파일이 없어졌으면 ↻ 뒤 다음 파일을 고르고 연다, 마지막 파일이었으면 이전 파일
D. 작업 뒤 — 이름 바꾸기·태그 붙이기·저장(책갈피 [저장]) 뒤에도 본문 파일 줄이 골라져 있다
E. 파일 모드(여러 파일) ↻ 뒤에도
"""
import os, sys, tempfile, shutil, faulthandler
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
faulthandler.dump_traceback_later(240, exit=True)
from pathlib import Path

import fitz
from PyQt6.QtCore import QStandardPaths, Qt
QStandardPaths.setTestModeEnabled(True)
from PyQt6.QtWidgets import QApplication, QMessageBox, QDialog, QLineEdit
from PyQt6.QtTest import QTest

app = QApplication.instance() or QApplication(sys.argv[:1])
from PyQt6.QtCore import QCoreApplication
QCoreApplication.setApplicationName("polypdf_keepsel_%d" % os.getpid())   # 검사 작성 SOT §14.7.2 의 3
import modal_guard
modal_guard.install(label=lambda: "책갈피창 선택 유지", echo=False)        # §14.7.2 의 6
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def spin(n=10, ms=20):
    for _ in range(n):
        app.processEvents(); QTest.qWait(ms)


def make_pdf(p, tag, pages=4):
    d = fitz.open()
    for i in range(pages):
        d.new_page().insert_text((72, 72), f"{tag} body {i}")
    d.set_toc([[1, f"{tag}-ch1", 1], [1, f"{tag}-ch2", 3]])
    d.save(str(p)); d.close()


errs = []
sys.excepthook = lambda t, v, tb: errs.append(f"{t.__name__}: {v}")
root = Path(tempfile.mkdtemp(prefix="polypdf_keepsel_"))
try:
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    import test_fixtures as _TFX; _TFX.autotag_off()   # 자동 태그가 배경에서 목록 글을 바꾸지 않게
    from viewer.app import MainWindow
    mw = MainWindow(); mw.resize(1300, 850); mw.show(); app.processEvents()
    bt = mw.bookmark_tree

    fo = root / "fo"; fo.mkdir()
    for nm in ("A", "B", "C", "D", "E"):
        make_pdf(fo / f"{nm}.pdf", nm)
    mw.open_folder(fo); spin(20)

    def row(name):
        for it in bt._iter_file_nodes():
            if Path(it.data(0, bt.DATA_FILE)).stem == name:
                return it
        return None

    def click(name):
        it = row(name)
        bt.tree.scrollToItem(it)
        QTest.mouseClick(bt.tree.viewport(), Qt.MouseButton.LeftButton, pos=bt.tree.visualItemRect(it).center())
        spin(20)

    def shown():
        f = mw._mv[0].current_file()
        return Path(f).stem if f else None

    def picked():
        it = bt.tree.currentItem()
        node = bt._file_node_of(it) if it is not None else None
        return Path(node.data(0, bt.DATA_FILE)).stem if node is not None else None

    def same(lbl):
        chk(shown() is not None and picked() == shown() and bool(bt.tree.selectedItems()),
            lbl, f"본문={shown()} 고른 줄={picked()} 선택={[i.text(0) for i in bt.tree.selectedItems()]}")

    click("C")
    chk(shown() == "C" and picked() == "C", "준비 — C 를 눌러 본문에 C", f"{shown()} {picked()}")

    # ── A. 목록을 다시 만드는 길 ──
    bt.btn_refresh.click() if hasattr(bt, "btn_refresh") else bt.refresh(); spin(20)
    same("A ↻ 새로고침 뒤 C 줄이 골라져 있다")
    mw._mv[0].go_to_page(2) if hasattr(mw._mv[0], "go_to_page") else None; spin(10)
    page_before = mw._mv[0].current_page() if hasattr(mw._mv[0], "current_page") else None
    i = bt._sort_combo.findData(bt.SORT_MTIME)
    bt._sort_combo.setCurrentIndex(i if i >= 0 else (bt._sort_combo.currentIndex() + 1) % bt._sort_combo.count()); spin(20)
    same("A 정렬 바꾸기 뒤")
    bt._sort_combo.setCurrentIndex(bt._sort_combo.findData(bt.SORT_NAME)); spin(20)
    same("A 정렬 되돌리기 뒤")
    bt.set_tree_view(not bt.is_tree_view()); spin(20)
    same("A 보기 바꾸기 뒤")
    bt.set_tree_view(not bt.is_tree_view()); spin(20)
    same("A 보기 되돌리기 뒤")
    bt.set_edit_mode(True); bt._dirty = True
    bt._op_cancel(); spin(20)
    same("A 편집 취소(원본으로 다시 읽기) 뒤")
    bt.set_edit_mode(False); spin(5)

    # ── B. 본문을 다시 열지 않는다 ──
    if page_before is not None:
        chk(mw._mv[0].current_page() == page_before, "B 되살리기 뒤 보던 쪽 그대로",
            f"{page_before} → {mw._mv[0].current_page()}")
    chk(shown() == "C", "B 본문은 C 그대로", str(shown()))

    # ── C. 본문 파일이 없어졌으면 다음 / 마지막이면 이전 ──
    #   열린 파일은 Windows 가 잡고 있어 밖에서 옮겨지지 않는다 — 없어지는 것은 앱이 핸들을 푼 뒤(옮기기·다른 창의 요청)다.
    click("C")
    out = root / "out"; out.mkdir()
    bt._transfer_files([str(fo / "C.pdf")], out, move=True); spin(30)
    chk((out / "C.pdf").exists() and row("C") is None, "C 준비 — 우클릭 '폴더로 이동' 으로 C 를 밖으로", str(sorted(p.name for p in fo.iterdir())))
    chk(picked() == "D", "C 옮긴 뒤 — 없어진 C 대신 다음 파일 D 를 고른다", str(picked()))
    chk(shown() == "D", "C 다음 파일 D 를 본문에 연다(본문 = 고른 줄)", str(shown()))
    click("E")
    mw._on_release_file(str(fo / "E.pdf")); spin(5)   # 다른 PolyPinax 창이 옮기려고 핸들을 풀게 했다(§4.7.8)
    (fo / "E.pdf").replace(root / "E_밖.pdf")
    bt.refresh(); spin(30)
    chk(picked() == "D" and shown() == "D", "C 마지막 파일 E 가 없어진 뒤 ↻ — 이전 파일 D 를 고르고 연다", f"{picked()} {shown()}")

    # ── D. 작업 뒤 ──
    click("B")

    def fake_exec(dlg):
        ed = dlg.findChild(QLineEdit)
        if ed is not None:
            ed.setText("B2")
        return QDialog.DialogCode.Accepted
    _old_exec = QDialog.exec
    QDialog.exec = fake_exec
    try:
        bt._edit_file_node(row("B")); spin(30)
    finally:
        QDialog.exec = _old_exec
    chk((fo / "B2.pdf").exists(), "D 준비 — 이름 바꾸기 B → B2", str(sorted(p.name for p in fo.iterdir())))
    same("D 이름 바꾸기 뒤 B2 줄이 골라져 있다")
    bt.refresh(); spin(20)
    same("D 이름 바꾸기 → ↻ 뒤에도")

    store = bt._tags
    if store is not None:
        try:
            store.add(str(fo / "B2.pdf"), ["시험태그"])
        except Exception:
            try:
                store.set(str(fo / "B2.pdf"), ["시험태그"])
            except Exception as e:
                print("태그 넣기 실패", e)
        bt.refresh_tag_labels(); spin(10)
        same("D 태그 붙이기 뒤")
        bt.search_edit.setText("#시험태그"); spin(10)
        bt.search_edit.setText(""); spin(10)
        same("D 태그 거르기·풀기 뒤")

    bt.set_edit_mode(True)
    bt._dirty = True
    bt._op_save(); spin(40)
    bt.set_edit_mode(False); spin(10)
    same("D 책갈피 [저장] 뒤")

    # ── E. 파일 모드 ──
    fm = root / "fm"; fm.mkdir()
    fs = []
    for nm in ("P", "Q", "R"):
        p = fm / f"{nm}.pdf"; make_pdf(p, nm); fs.append(p)
    mw.open_pdfs(fs); spin(20)
    click("Q")
    bt.refresh(); spin(20)
    same("E 파일 모드 ↻ 뒤 Q 줄")

    chk(not errs, "예외 없음", str(errs[:3]))
except Exception as e:
    import traceback; traceback.print_exc()
    chk(False, "검사 중 예외", repr(e))
finally:
    try:
        mw.close()
    except Exception:
        pass
    shutil.rmtree(root, ignore_errors=True)

print("FAILS:", len(fails))
for f in fails:
    print("  -", f)
sys.stdout.flush()
os._exit(1 if fails else 0)
