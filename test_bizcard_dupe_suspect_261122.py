# -*- coding: utf-8 -*-
"""중복 검토 ① 나눔·잘못 합쳐짐 의심·다른 사람 기억·010 경고·합친 뒤 확인 (명함 SOT §5.24.8, 261122-1) — 가짜 명함·임시 DB 만.

A. 같은 휴대폰·이름 다름 — 010 하나씩이면 '같은 번호·이름 다름 — 확인'(처음 체크), 한쪽이 010 둘 이상이면 잇지 않고 의심 갈래
B. 잘못 합쳐짐 의심 — 010 하나인 사람이 기준, 010 둘 이상 명단이 아래, 체크 없음·[적용] 은 합치지 않음
C. '다른 사람' 으로 기억한 짝은 묶지도 의심으로 내지도 않음
D. 합치면 010 둘 이상 — '적용 후' 줄·확인 창 경고
E. 합친 뒤 확인 — 새로 010 둘 이상이 된 묶음만 목록, 고른 묶음만 되돌림(다른 묶음은 그대로)
"""
import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_suspect_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_suspect_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()
(TMP / "local").mkdir()
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
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


def cell(n):
    return ("cell", "010-0000-%04d" % (n * 1111))       # 서로 오타 거리가 아니게(한 자리 차이는 합칠 때 오타로 빠짐)


try:
    from viewer.bizcard import people as P, store as S
    db = TMP / "local" / "bizcard.db"
    st = S.BizcardStore(db)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    P.src_init(st)
    add = lambda name, phones, emails=(): P._insert_contact(st, {"name": name, "phones": list(phones), "emails": list(emails)}, ["명함"])
    a1 = add("가짜갑", [cell(1)])
    m = add("가짜갑", [cell(1), cell(2)])                      # 예전에 잘못 합쳐진 명단(을의 번호가 섞임)
    b = add("가짜을", [cell(2)])
    c1 = add("가짜병", [cell(3)])
    c2 = add("가짜정", [cell(3)])                              # 같은 번호·이름 다름·010 하나씩
    x1 = add("가짜무", [cell(5)])
    x2 = add("가짜무", [cell(5)])                              # 다른 사람으로 기억
    y1 = add("가짜기", [cell(6)])
    y2 = add("가짜경", [cell(6), cell(7)])                     # 다른 사람으로 기억 — 의심으로도 안 냄
    z1 = add("가짜신", [cell(8)], ["sin@example.com"])
    z2 = add("가짜신", [cell(9)], ["sin@example.com"])         # 성명+메일 확정 → 합치면 010 둘
    st.con.commit()
    P.mark_not_same(st, x1, x2)
    P.mark_not_same(st, y1, y2)

    print("=== A·B·C 계산 ===")
    gs = P.dupe_groups(st)
    gid = lambda cid: next((i for i, g in enumerate(gs) if cid in {c["id"] for c in g["cards"]}), None)
    g_c = gs[gid(c1)] if gid(c1) is not None else None
    chk(g_c is not None and gid(c2) == gid(c1) and g_c["why"][c2 if g_c["cards"][0]["id"] == c1 else c1] == "phone_name"
        and g_c["sure_root"][c1] == g_c["sure_root"][c2], "A 같은 번호·이름 다름·010 하나씩 — '확인' 이유·확실(처음 체크)", str(g_c and g_c["why"]))
    chk(gid(b) is None or gid(b) != gid(m), "A 010 둘 이상 명단과 이름 다른 사람은 잇지 않음", str((gid(b), gid(m))))
    chk(gid(a1) is not None and gid(a1) == gid(m), "A 이름이 같으면 종전대로 같은 번호로 묶음")
    sus = P.merge_suspects(st)
    chk(len(sus) == 1 and sus[0]["base"]["id"] == b and [s["id"] for s in sus[0]["subs"]] == [m],
        "B 잘못 합쳐짐 의심 — 010 하나인 '을' 이 기준, 010 둘 이상 명단이 아래", str([(e["base"]["name"], [s["name"] for s in e["subs"]]) for e in sus]))
    chk(gid(x1) is None and gid(x2) is None, "C 다른 사람으로 기억한 짝은 묶지 않음(같은 이름·같은 번호여도)")
    chk(all(e["base"]["id"] not in (y1, y2) for e in sus), "C 다른 사람으로 기억한 짝은 의심으로도 내지 않음")

    print("\n=== B·D 창 ===")
    from viewer.widgets import bizcard_find_dialog as FD
    st.close()
    fd = FD.BizcardFindDialog(None, db=db)
    fd.show()
    pump(lambda: fd.table.rowCount() >= 10)
    dd = fd.open_dupes(exec_=False)
    pump(lambda: hasattr(dd, "btn_apply"))
    items = dd.suspect_items()
    flags_ok = all(x.data(0, Qt.ItemDataRole.CheckStateRole) is None for it in items for x in [it] + [it.child(j) for j in range(it.childCount())])
    chk(len(items) == 1 and items[0].childCount() == 1 and flags_ok and "의심" in items[0].text(5),
        "B 창 맨 아래 '잘못 합쳐짐 의심' 갈래 — 체크 없음", str([(it.text(0), it.text(5)) for it in items]))
    chk(dd.after.topLevelItemCount() == len(dd.groups), "B '적용 후' 에는 합치기 묶음만(의심 갈래 없음)")
    gi_c = next(i for i, g in enumerate(dd.groups) if c1 in {c["id"] for c in g["cards"]})
    chk(dd.gchk.get(gi_c) is True, "A 창 — '같은 번호·이름 다름' 묶음은 처음 체크")
    gi_a = next(i for i, g in enumerate(dd.groups) if a1 in {c["id"] for c in g["cards"]})
    top_a = dd.after.topLevelItem(gi_a)
    chk("010 2개" in top_a.text(0), "D '적용 후' 묶음 줄에 '010 n개' 경고", top_a.text(0))
    # 실제 클릭으로 의심 줄을 고르면 그 사람들의 그림 칸(오류 없이)
    dd.before.setCurrentItem(items[0].child(0))
    app.processEvents()

    print("\n=== D·E 적용 → 합친 뒤 확인 → 고른 묶음만 되돌리기 ===")
    for gi, g in enumerate(dd.groups):                      # 을·병정 묶음은 이 검사에서 합치지 않음 — 갑·신 묶음만
        if not ({a1, z1} & {c["id"] for c in g["cards"]}):
            dd.gchk[gi] = False
    dd.fill_after()
    n = dd.apply(ask=False)
    pump(lambda: not dd.working, timeout=15)
    chk(n == 2 and "010 번호가 둘 이상" in (getattr(dd, "last_confirm", "") or ""), "D [적용] 확인 글에 010 경고", str((n, getattr(dd, "last_confirm", None))))
    cd = getattr(dd, "check_dlg", None)
    pump(lambda: cd is not None and cd.isVisible(), timeout=3)
    rows = [cd.tree.topLevelItem(i).text(0) for i in range(cd.tree.topLevelItemCount())] if cd else []
    chk(cd is not None and len(rows) == 1 and "가짜신" in rows[0], "E 합친 뒤 확인 — 새로 010 둘 이상이 된 묶음만(이미 둘이던 갑은 아님)", str(rows))
    chk(cd is not None and not cd.btn_undo.isEnabled(), "E 체크 0개면 [선택한 합치기 되돌리기] 꺼짐")
    st2 = fd._store()
    alive = lambda cid: P.card_by_id(st2, cid) is not None
    chk(not (alive(z1) and alive(z2)) and not (alive(a1) and alive(m)), "E 적용으로 두 묶음 모두 합쳐짐")
    if cd is not None:
        cd.tree.topLevelItem(0).setCheckState(0, Qt.CheckState.Checked)
        chk(cd.btn_undo.isEnabled(), "E 체크하면 켜짐")
        cd.btn_undo.click()
    pump(lambda: not dd.working, timeout=15)
    pump(lambda: alive(z1) and alive(z2), timeout=5)
    z1c, z2c = P.card_by_id(st2, z1), P.card_by_id(st2, z2)
    chk(z1c is not None and z2c is not None and P.mobiles_010(z1c) == ["01000008888"] and P.mobiles_010(z2c) == ["01000009999"],
        "E 고른 묶음(신)만 합치기 전 두 명단으로", str((z1c and z1c["phones"], z2c and z2c["phones"])))
    chk(not (alive(a1) and alive(m)), "E 고르지 않은 묶음(갑)은 합친 그대로")
    dd.close()
    fd.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외")
print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
