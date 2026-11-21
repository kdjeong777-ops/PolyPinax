# -*- coding: utf-8 -*-
"""'해시태그 수정' — 일부에만 붙은 태그를 모두에 (태그 SOT §8.7 '일부에만 붙은 태그를 모두에', 261120-63). 가짜 파일 이름·임시 설정만.

1안 찾기 칸에 이미 있는 태그를 치면 '모두에 붙이기'(실제 글자·Enter) → 대상 모두에, 되돌리기 한 걸음, 이미 모두면 꺼짐·풍선 도움말
2안 일부에만 붙은 태그도 왼쪽 '기존 태그' 에 ◐ n/m, 모두에 붙은 태그는 오른쪽에만
명함 꼴(card_mode)도 같다
"""
import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_tag_partial_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="tag_partial_"))
from viewer import settings_store
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
from PyQt6.QtWidgets import QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)
fails = []
KEEP = []                                            # 창의 배경 일꾼(짝 낱말·날짜·썸네일)이 도는 동안 붙잡아 둔다


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


def pump(sec=0.2):
    t = time.monotonic()
    while time.monotonic() - t < sec:
        app.processEvents()
        time.sleep(0.01)


def left(dlg):
    lw = dlg.lst_avail
    return {lw.item(i).data(Qt.ItemDataRole.UserRole): lw.item(i).text() for i in range(lw.count()) if lw.item(i).data(Qt.ItemDataRole.UserRole)}


def right(dlg):
    lw = dlg.lst_tags
    return {lw.item(i).data(Qt.ItemDataRole.UserRole): lw.item(i).text() for i in range(lw.count()) if lw.item(i).data(Qt.ItemDataRole.UserRole)}


try:
    from viewer.tag_store import TagStore
    from viewer.widgets.tag_apply_dialog import TagApplyDialog
    files = []
    for n in ("a", "b", "c"):
        f = TMP / ("가짜_%s.txt" % n)
        f.write_text("x", encoding="utf-8")
        files.append(str(f))
    other = TMP / "가짜_다른.txt"
    other.write_text("x", encoding="utf-8")
    for card_mode in (False, True):
        tag = "가짜교통부" if not card_mode else "가짜명함태그"
        st = TagStore()
        st.set(files[0], [tag])
        st.set(files[1], ["가짜모두"])
        st.set(files[2], ["가짜모두"])
        st.set(files[0], [tag, "가짜모두"])
        st.set(str(other), [tag + "익산"])
        kw = {"card_mode": True, "known": [tag + "익산"]} if card_mode else {}
        dlg = TagApplyDialog(st, files, files, None, keep=KEEP, **kw)
        dlg.show()
        pump()
        mode = "명함 꼴" if card_mode else "파일 꼴"
        print("=== %s ===" % mode)
        L, R = left(dlg), right(dlg)
        chk(tag in L and "◐ 1/3" in L[tag] and tag in R, "2안 일부에만 붙은 태그는 왼쪽에도 ◐ 1/3 (%s)" % mode, str((L, R)))
        chk("가짜모두" not in L and "가짜모두" in R, "2안 모두에 붙은 태그는 오른쪽에만 (%s)" % mode, str(L))
        ed = dlg.ed_find
        ed.setFocus()
        ed.setText(" " + tag.upper() + " ")
        pump()
        b = dlg.btn_find_add
        chk(b.isEnabled() and b.text() == "모두에 붙이기", "1안 이미 있는 태그를 치면 '모두에 붙이기' (%s)" % mode, str((b.isEnabled(), b.text())))
        QTest.keyClick(ed, Qt.Key.Key_Return)
        pump()
        got = [tag in st.get_manual(f) for f in files]
        chk(all(got), "1안 Enter 로 대상 모두에 붙임 (%s)" % mode, str(got))
        ed.setText(tag)                              # 한글은 QTest.keyClicks 가 오프스크린에서 죽는다 — 글은 칸에, 키는 실제로
        pump()
        chk(not b.isEnabled() and "이미 모두에 붙어 있음" in b.toolTip(), "1안 이미 모두면 꺼지고 풍선 도움말 (%s)" % mode, str((b.isEnabled(), b.toolTip())))
        ed.clear()
        dlg.undo()
        pump()
        chk([tag in st.get_manual(f) for f in files] == [True, False, False], "1안 되돌리기 한 걸음 (%s)" % mode)
        dlg.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외")
print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
