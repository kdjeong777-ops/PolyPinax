# -*- coding: utf-8 -*-
"""명함 점검(261120-77) 코드 판단 고침 ②⑤⑥⑦⑧⑨ (261120-78) — 가짜 명함·임시 폴더만.

② 사진 올리기가 도는 중 불러오기 → 그 일꾼이 끝난 뒤 시작, 도중에 멈추면 '일부만 바뀌었을 수 있음 + 백업'
⑤ 얼굴 찾기 일시 오류는 그 그림만 — 연달아 ERR_MAX 번일 때만 끔
⑥ 창을 닫으면 목록 얼굴 대기열 비움
⑦ zip 합치기는 칸 출처·카톡 표시도 새 id 로
⑧ 얼굴 캐시 — 지금 명함이 안 쓰는 것 지움, 바꾸기 전 백업 zip 은 최근 3개만
⑨ [적용] 공통 규칙 — 변경 기록 창은 체크 0개면 꺼짐·되돌리는 길 글이 창 안, 중복 검토는 되돌리기 왼쪽·[적용][닫기] 오른쪽 끝
"""
import os, sys, tempfile, time, zipfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QPoint
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox
from pathlib import Path
from PIL import Image

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_fix78_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_fix78_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
WARN, INFO = [], []
QMessageBox.warning = staticmethod(lambda *a, **k: WARN.append(a[2] if len(a) > 2 else "") or QMessageBox.StandardButton.Ok)
QMessageBox.information = staticmethod(lambda *a, **k: INFO.append(a[2] if len(a) > 2 else "") or QMessageBox.StandardButton.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
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


try:
    from viewer.bizcard import people as P, store as S, gsync as G, archive as AR, face_thumb as FT
    FOLD = TMP / "cards"
    (FOLD / "정리").mkdir(parents=True)
    db = TMP / "local" / "bizcard.db"
    st = S.BizcardStore(db)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    P.src_init(st)
    f = FOLD / "정리" / "가짜일_가짜사.jpg"
    Image.new("RGB", (300, 200), "white").save(f)
    a = st.upsert({"front": str(f), "name": "가짜일", "company": "가짜사", "phones": [("cell", "010-0000-0001")]})
    P._set_srcs(st, a, ["name"], G.SRC)
    G.kakao_set(st, [a], True)                              # 직접 정한 표시
    st.con.commit()
    st.close()
    settings_store.set_picture_prefs({"bizcard_folder": str(FOLD)})
    out = TMP / "옮김.zip"
    AR.export_zip(db, str(FOLD), out)

    # ── ⑦ ──
    print("=== ⑦ 합치기 — 출처·카톡 표시 ===")
    db2 = TMP / "다른" / "bizcard.db"
    F2 = TMP / "다른" / "명함"
    F2.mkdir(parents=True)
    st2 = S.BizcardStore(db2)
    st2.meta_set(P.KINDS_FIXED_KEY, 1.0)
    st2.close()
    r = AR.import_zip(out, db2, str(F2), mode="merge")
    st2 = S.BizcardStore(db2)
    nid = r["new_ids"][0]
    chk(nid in G._google_src_ids(st2) and G.kakao_rows(st2).get(nid, (None, 0))[0] is True and G.kakao_rows(st2)[nid][1] > 0,
        "⑦ 더한 명함의 칸 출처·직접 정한 카톡 표시도 새 id 로", str((G._google_src_ids(st2), G.kakao_rows(st2))))
    st2.close()

    # ── ⑧ 백업 3개 ──
    print("\n=== ⑧ 백업·캐시 ===")
    bdir = TMP / "bak"
    bdir.mkdir()
    for i in range(5):
        p = bdir / ("명함 백업_26112%d-000000.zip" % i)
        p.write_bytes(b"x")
        os.utime(p, (time.time() - 100 + i, time.time() - 100 + i))
    AR.prune_backups(bdir)
    left = sorted(x.name for x in bdir.glob("명함 백업_*.zip"))
    chk(len(left) == 3 and left[-1].startswith("명함 백업_261124"), "⑧ 바꾸기 전 백업 zip 은 최근 3개만", str(left))
    # 캐시
    st = S.BizcardStore(db)
    used = FT.thumb(str(f), True)
    stray = FT.cache_dir() / "지운명함얼굴.jpg"
    stray.write_bytes(b"x")
    n = FT.prune(st, str(FOLD))
    st.close()
    chk(n >= 1 and not stray.exists() and Path(used).exists(), "⑧ 얼굴 캐시 — 지금 명함이 안 쓰는 것만 지움", str((n, stray.exists())))

    # ── ⑤ ──
    print("\n=== ⑤ 얼굴 찾기 일시 오류 ===")
    FT._no_detector, FT._errors = False, 0

    class Bad:
        def convert(self, *_a):
            raise OSError("가짜 일시 오류")
    FT.faces(Bad())
    chk(FT._no_detector is False, "⑤ 한 번의 오류로 끄지 않음")
    for _ in range(FT.ERR_MAX):
        FT.faces(Bad())
    chk(FT._no_detector is True, "⑤ 연달아 ERR_MAX 번이면 끔")
    FT._no_detector, FT._errors = False, 0

    # ── ② ⑥ ⑨ ──
    print("\n=== ② ⑥ ⑨ 창 ===")
    from viewer.widgets import bizcard_find_dialog as FD
    fd = FD.BizcardFindDialog(None, db=db)
    fd._bz_folder = str(FOLD)
    fd.show()
    pump(lambda: fd.table.rowCount() == 1)

    class FakeMW:
        stopped = False

        def stop(self):
            FakeMW.stopped = True
    fd.media_busy, fd._media_worker = True, FakeMW()
    fd.import_archive(path=str(out), mode="replace", folder=str(FOLD))
    chk(FakeMW.stopped and not getattr(fd, "archive_busy", False) and getattr(fd, "_pending_import", None) is not None,
        "② 사진 올리기가 도는 중이면 멈추게만 하고 불러오기는 기다림")
    fd._media_done({"done": 0, "failed": 0, "reasons": {}, "left": 1, "stopped": "stop"})
    pump(lambda: getattr(fd, "archive_result", None) is not None and not getattr(fd, "archive_busy", False), timeout=15)
    chk((fd.archive_result or {}).get("cards") == 1 and not any("올리" in w for w in WARN), "② 일꾼이 끝난 뒤 이어서 불러옴(사진 알림 없이)",
        str((fd.archive_result, WARN)))
    # 도중에 멈춤 — 실제 상태대로
    WARN.clear()
    _cp = AR._copy_db
    calls = [0]

    def boom(a_, b_):
        calls[0] += 1
        if calls[0] >= 2:                                  # 첫째는 백업 내보내기, 둘째(교체)에서 멈춤
            raise OSError("가짜 디스크 오류")
        return _cp(a_, b_)
    AR._copy_db = boom
    fd.archive_result = None
    fd.import_archive(path=str(out), mode="replace", folder=str(FOLD))
    pump(lambda: not getattr(fd, "archive_busy", False) and WARN, timeout=15)
    AR._copy_db = _cp
    chk(WARN and "일부만" in WARN[-1] and "명함 백업_" in WARN[-1] and "그대로입니다" not in WARN[-1], "② 도중에 멈추면 '일부만 + 백업 zip' 으로 알림", str(WARN))
    # ⑥
    fd._face_queue.extend([1, 2, 3])
    fd._face_asked.update({1, 2, 3})
    fd.close()
    chk(not fd._face_queue and not fd._face_asked, "⑥ 창을 닫으면 얼굴 대기열 비움")
    # ⑨ 변경 기록 창
    fd2 = FD.BizcardFindDialog(None, db=db)
    fd2.show()
    pump(lambda: fd2.table.rowCount() >= 1)
    st3 = fd2._store()
    P.update_card(st3, P.card_by_id(st3, list(fd2._by_id)[0])["id"], {"title": "가짜부장"})
    hd = fd2.open_history(exec_=False)
    pump(lambda: hd.tree.topLevelItemCount() > 0, timeout=5)
    for i in range(hd.tree.topLevelItemCount()):
        hd.tree.topLevelItem(i).setCheckState(0, Qt.CheckState.Unchecked)
    chk(not hd.btn_restore.isEnabled() and "되돌릴 수" in hd.lbl.text(), "⑨ 변경 기록 — 체크 0개면 [적용] 꺼짐·되돌리는 길 글이 창 안", hd.lbl.text())
    hd.tree.topLevelItem(0).setCheckState(0, Qt.CheckState.Checked)
    chk(hd.btn_restore.isEnabled(), "⑨ 체크하면 [적용] 켜짐")
    hd.close()
    dd = fd2.open_dupes(exec_=False)
    pump(lambda: hasattr(dd, "btn_apply"))
    xs = {n_: w.mapTo(dd, QPoint(0, 0)).x() for n_, w in (("undo", dd.btn_undo), ("lbl", dd.lbl), ("apply", dd.btn_apply))}
    close_btn = next(b for b in dd.findChildren(type(dd.btn_apply)) if b.text() == "닫기")
    xs["close"] = close_btn.mapTo(dd, QPoint(0, 0)).x()
    chk(xs["undo"] < xs["lbl"] < xs["apply"] < xs["close"], "⑨ 중복 검토 — 되돌리기 왼쪽, [적용][닫기] 오른쪽 끝", str(xs))
    dd.close()
    fd2.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외")
print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
