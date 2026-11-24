# -*- coding: utf-8 -*-
"""명함 SOT 재점검(261124) 코드 고침 (명함 SOT §5.24.2·§5.29, 261122-18) — 가짜 값·가짜 구글만.

A 얼굴 찾기 공용 모듈 `viewer.win_face` — 못 쓰면(일시 오류) None, 얼굴이 없으면 [](쓸 수 없는 PC 면 None), 공용 오류 카운터 없음.
  명함 썸네일 `face_thumb.faces` 는 그 위의 감싸기 — 오류 횟수는 명함 쪽만 셈
B 미리보기에 '구글에만 있음 — 지울까요' 줄만 있어도 백업 권함(GOOGLE_WRITES), 명함 기준이면 '처음부터 체크·구글에서 지움' 문구
"""
import os, sys, tempfile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_audit2_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_audit2_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
fails = []


def chk(cond, msg, extra=""):
    print(("PASS" if cond else "FAIL"), "-", msg, extra if not cond else "", flush=True)
    if not cond:
        fails.append(msg)


class Bad:
    def convert(self, *_a):
        raise RuntimeError("일시 오류 흉내")


try:
    print("=== A 얼굴 찾기 공용 모듈 ===")
    from viewer import win_face as WF
    from PIL import Image
    chk(WF.detect(Bad()) is None, "A 일시 오류는 None(얼굴 없음과 다름)")
    blank = WF.detect(Image.new("RGB", (200, 150), "white"))
    chk((blank == [] and WF.available()) or (blank is None and not WF.available()),
        "A 얼굴 없는 그림 = [](쓸 수 없는 PC 면 None)", repr(blank))
    chk(not any(hasattr(WF, n) for n in ("_errors", "ERR_MAX", "_no_detector")), "A 공용 모듈엔 오류 카운터·끔 상태가 없음(부르는 쪽마다 셈)")
    from viewer.bizcard import face_thumb as FT
    FT._no_detector, FT._errors = False, 0
    FT.faces(Bad())
    chk(FT._errors == (1 if WF.available() else 0) and FT.faces(Bad()) == [], "A 명함 썸네일은 감싸기 — 일시 오류를 명함 쪽 횟수로 세고 [] 로 대신",
        str(FT._errors))
    FT._no_detector, FT._errors = False, 0

    print("\n=== B 구글에만 있음 — 백업 권함·문구 ===")
    from viewer.bizcard import gsync as G
    chk(G.GOOGLE_EXTRA in G.GOOGLE_WRITES, "B '구글에만 있음 — 지울까요' 는 구글을 바꾸는 갈래")
    from viewer.widgets.bizcard_gsync_dialog import GSyncDialog
    from viewer.bizcard import store as S
    st = S.BizcardStore(TMP / "local" / "bizcard.db")
    dlg = GSyncDialog(None, db=str(st.path), start=False)
    dlg._card_first = True
    dlg._planned([{"kind": G.GOOGLE_EXTRA, "card_id": 0, "rn": "people/x1", "name": ""}], [], "")
    t = dlg.lbl.text()
    chk("백업" in t, "B 그 줄만 있어도 [적용] 전 백업을 권함", t)
    chk("처음에 '남김'" not in t and "구글에서 지웁니다" in t, "B 명함 기준이면 '처음부터 체크·구글에서 지움' 문구", t)
    chk("구글에서 지울까요" in dlg.chk_card_first.toolTip(), "B '명함 기준으로 올리기' 풍선 도움말이 지울 수 있음을 알림")
    st.close()
except Exception as e:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외", repr(e))
print("FAILURES: %d" % len(fails))
for f in fails:
    print("  -", f)
sys.stdout.flush()
os._exit(1 if fails else 0)
