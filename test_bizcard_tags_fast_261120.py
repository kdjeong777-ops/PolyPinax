# -*- coding: utf-8 -*-
"""[해시태그] 창 빠르게 (명함 SOT §5.24.4 '빠르게', 태그 SOT §8.7 '기존 태그 세기', 261120-20) — 가짜 태그 기록·가짜 명함만.

오프스크린, 실제 설정·데이터 폴더를 쓰지 않는다(검사 작성 SOT §14.7.2).
A. TagStore.known_tags — 고친 세대가 같으면 다시 세지 않고, 고치면(일괄 포함) 새 태그가 들어감, 결과는 종전 계산과 같음
B. 명함찾기(본 뷰어 없이 = PolyCardex) — 창이 뜬 뒤 쉬는 동안 배경에서 미리 셈, 그 뒤 [해시태그] 실제 클릭은 메인에서 다시 세지 않음
C. 태그 파일이 그대로면 저장소를 다시 열지 않고, 다른 곳이 고쳐 쓰면 다시 엶
D. 1만 개 기록에서 미리 센 뒤 [해시태그] 누름 → 창 보임 < 0.6초(이 PC 가짜 기록 실측 0.18초 — 넉넉히)
"""
import os, sys, tempfile, time, random
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_tagsfast_%d" % os.getpid())
fails = []
TMP = Path(tempfile.mkdtemp(prefix="bizcard_tagsfast_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "")
    if not cond:
        fails.append(msg)


def pump(cond=None, timeout=10.0):
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


try:
    import viewer.tag_store as TS
    from viewer import bg_write
    print("=== A. known_tags 세대 캐시 ===")
    random.seed(3)
    vocab = ["가짜태그%04d" % i for i in range(1500)]
    st = TS.TagStore()
    with st.bulk():
        for i in range(10000):
            st.set(str(TMP / "files" / ("문서%05d.pdf" % i)), random.sample(vocab, random.randint(2, 5)))
    st.set(str(TMP / "files" / "날짜.jpg"), ["2026-11-20", "가짜날짜옆"])
    bg_write.flush()
    has = hasattr(st, "known_tags") and hasattr(TS, "known_tags_of")
    chk(has, "A 저장소에 known_tags·known_tags_of 가 있다")
    if has:
        calls = {"n": 0}
        real_of = TS.known_tags_of

        def counted(store, keys):
            calls["n"] += 1
            return real_of(store, keys)
        TS.known_tags_of = counted
        k1 = st.known_tags()
        k2 = st.known_tags()
        chk(calls["n"] == 1 and k1 == k2, "A 고치지 않으면 다시 세지 않음", str(calls["n"]))
        chk("2026-11-20" not in k1 and "가짜날짜옆" in k1 and len(k1) >= 1500, "A 날짜 꼴은 빼고 나머지 태그는 모두", str(len(k1)))
        st.set(str(TMP / "files" / "새것.pdf"), ["가짜새태그"])
        chk("가짜새태그" in st.known_tags() and calls["n"] == 2, "A 고치면 다시 셈(새 태그 들어감)")
        with st.bulk():
            st.clear_auto_tag("없는태그") if hasattr(st, "clear_auto_tag") else None
            st.set(str(TMP / "files" / "새것2.pdf"), ["가짜일괄태그"])
        chk("가짜일괄태그" in st.known_tags(), "A 일괄로 고쳐도 새로 셈")
        TS.known_tags_of = real_of
    bg_write.flush()

    print("\n=== B·C·D. 명함찾기 [해시태그] ===")
    from PIL import Image
    from viewer.bizcard import importer as I, apply as AP
    F = TMP / "cards"
    F.mkdir()
    Image.new("RGB", (339, 186), "white").save(F / "a_1.jpg", quality=90)
    items = {it.base: it for it in I.scan_folder(F)}
    db = TMP / "local" / "bizcard.db"
    AP.apply_cards([{"key": items["a"].key, "front": items["a"].front, "back": "", "pdf": "", "keep_back": False,
                     "name": "홍길동", "company": "가나다", "langs": ["한글"]}], F / "정리", db)
    bg_write.flush()
    from viewer.widgets import bizcard_find_dialog as FD
    from viewer.widgets import tag_apply_dialog as TA
    seen = {}

    def fake_exec(self):
        seen["shown_at"] = time.perf_counter()
        seen["known"] = list(self._all_known())
        return 0
    TA.TagApplyDialog.exec = fake_exec
    dlg = FD.BizcardFindDialog(None, db=db)              # 본 뷰어 없이(PolyCardex 와 같이)
    dlg.show()
    pump(lambda: dlg.table.rowCount() >= 1)
    dlg.table.setCurrentCell(0, 0)
    chk(pump(lambda: getattr(dlg, "known_preloaded", False), timeout=10), "B 창이 뜬 뒤 쉬는 동안 배경에서 미리 셈")
    real = dlg._tagstore()
    chk(real is dlg._tagstore(), "C 태그 파일이 그대로면 같은 저장소를 다시 씀")
    if has:
        calls = {"n": 0}
        real_of = TS.known_tags_of

        def counted2(store, keys):
            calls["n"] += 1
            return real_of(store, keys)
        TS.known_tags_of = counted2
        t0 = time.perf_counter()
        next(a for a in (dlg.tag_menu.aboutToShow.emit() or dlg.tag_menu.actions()) if a.text() == "해시태그 수정").trigger()   # '#' 풀다운 맨 아래(261120-66)
        dt = seen.get("shown_at", t0) - t0
        kn = seen.get("known") or []
        chk(calls["n"] == 0 and "가나다" in kn and "가짜새태그" not in kn,   # 기존 태그 = 지금 목록 명함 태그만(261120-52)
            "B [해시태그] 는 메인에서 저장소 전체를 세지 않고, 기존 태그는 지금 목록 명함의 태그만(다른 파일 태그 빼고)",
            "calls=%d %s" % (calls["n"], kn[:6]))
        chk(0 <= dt < 0.6, "D 1만 개 기록 — 누름 → 창 %.2f초 (< 0.6)" % dt)
        TS.known_tags_of = real_of
    other = TS.TagStore()                               # 다른 곳(본 뷰어)이 고쳐 씀
    other.set(str(TMP / "files" / "밖.pdf"), ["가짜밖태그"])
    bg_write.flush()
    time.sleep(0.05)
    r2 = dlg._tagstore()
    chk(r2 is not real and "가짜밖태그" in r2.known_tags(), "C 다른 곳이 태그 파일을 고쳐 쓰면 다시 엶")
    dlg.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "예외 없이 끝남")
finish()
