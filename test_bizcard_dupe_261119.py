# -*- coding: utf-8 -*-
"""명함 중복 검토 (명함 SOT §5.24.8, D30) — 가짜 명함만(010-0000-xxxx, 명함 SOT §2.1).

실제 MainWindow 로(오프스크린, 실제 설정·데이터 폴더를 쓰지 않는다 — 검사 작성 SOT §14.7.2).
A. 묶기 — 같은 번호·같은 메일(확실), 이름 같고 번호 한 자리 다름·이름+회사 같음(체크 꺼짐), 출처·차례(명함 > 리멤버 > 구글)
B. 합친 값 — 1순위 값 그대로·빈 칸은 다음 순위, 전화 모두(오타 번호 뺌), 메모 붙임
C. 명함찾기 아래 [중복 검토] 단추(실제 누름) → 창 두 나무(적용 전 대표+유사, 적용 후 합친 값)
D. 적용 — 남길 행·그림 옮김(대표가 주소록이면 그림 명함 행)·인물 사진 옮김·즐겨찾기 옮김·'병합 보관'·주소록 출처
E. 되돌리기 — 파일 제자리·DB 합치기 전으로, 우선순위 바꾸면 대표가 바뀜
"""
import os, sys, tempfile, time, datetime
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QPoint, QTimer
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtTest import QTest
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_dupe_%d" % os.getpid())
fails = []
TMP = Path(tempfile.mkdtemp(prefix="bizcard_dupe_"))
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


def finish():
    print("FAILURES: %d" % len(fails))
    for f in fails:
        print("  -", f)
    sys.stdout.flush()
    os._exit(1 if fails else 0)


from viewer.bizcard import people as P, importer as I, store as S, apply as AP
from PIL import Image

try:
    chk(hasattr(P, "dupe_groups") and hasattr(P, "merge_plan"), "중복 검토 모듈이 있다")
    if not hasattr(P, "dupe_groups"):
        finish()

    def jpg(p, color="white"):
        Image.new("RGB", (339, 186), color).save(p, quality=90)
    F = TMP / "cards"
    F.mkdir()
    for n, col in (("a", "white"), ("b", "ivory"), ("c", "lavender"), ("d", "lightblue"), ("e", "pink")):
        jpg(F / ("%s_1.jpg" % n), col)
    items = {it.base: it for it in I.scan_folder(F)}
    OUT = F / "정리"
    one = lambda k, name, comp, phones, **kw: dict({"key": items[k].key, "front": items[k].front, "back": "", "pdf": "",
                                                    "keep_back": False, "name": name, "company": comp, "langs": ["한글"],
                                                    "phones": phones}, **kw)
    AP.apply_cards([
        one("a", "홍길동", "가나도로공사", [("cell", "010-0000-0001")], emails=["hong@example.com"]),
        one("b", "김철수", "라마바", [("cell", "010-0000-0003")]),
        one("c", "김철수", "라마바상사", [("cell", "010-0000-0008")]),      # 번호 한 자리 다름 — 오타?
        one("d", "이영희", "사아자", [("cell", "010-0000-0004")]),
        one("e", "박가짜", "가짜다른사", [("cell", "010-0000-0005")]),
    ], OUT)
    st = S.BizcardStore()
    P.fav_init(st, "즐겨찾기")
    ids = {r["name"] + "|" + r["company"]: r["id"] for r in st.con.execute("SELECT id, name, company FROM cards")}
    st.con.execute("UPDATE cards SET memo='골프 모임' WHERE id=?", (ids["홍길동|가나도로공사"],))
    st.con.execute("UPDATE cards SET scanned='2026-11-01' WHERE id=?", (ids["김철수|라마바"],))
    st.con.execute("UPDATE cards SET scanned='2026-01-01' WHERE id=?", (ids["김철수|라마바상사"],))
    st.con.commit()

    def contact(src, **p):
        P.apply_import(st, [dict({"phones": [], "emails": [], "urls": []}, **p)], "주소록", src)
        return st.con.execute("SELECT MAX(id) FROM cards").fetchone()[0]
    x_id = contact("remember", name="홍길동", company="가나도로공사(주)", title="상무", address="서울 가짜로 1",
                   phones=[("cell", "010-0000-0001"), ("work", "02-0000-0009")], emails=["hong@example.com"], memo="리멤버 메모")
    y_id = contact("google", name="이영희", company="사아자", dept="기획팀", phones=[("cell", "010-0000-0004")])
    z_id = contact("google", name="최가짜", company="가짜구글사", phones=[("cell", "010-0000-0006")])
    w_id = contact("remember", name="최가짜", company="가짜리멤버사", phones=[("cell", "010-0000-0006")])
    v_id = contact("google", name="박가짜", company="가짜다른사", phones=[("work", "02-0000-0077")])   # 휴대폰 없음 — 이름+회사(휴대폰이 다르면 다른 사람, 261120-48)
    gid = P.fav_add_group(st, "가짜 탭") if hasattr(P, "fav_add_group") else None
    if gid is None:
        st.con.execute("INSERT INTO fav_groups(name, pos) VALUES('가짜 탭', 9)")
        gid = st.con.execute("SELECT MAX(id) FROM fav_groups").fetchone()[0]
    st.con.execute("INSERT INTO fav_members(group_id, card_id, pos) VALUES(?,?,0)", (gid, x_id))
    st.con.commit()
    a_id, b_id, c_id, d_id, e_id = (ids[k] for k in ("홍길동|가나도로공사", "김철수|라마바", "김철수|라마바상사", "이영희|사아자", "박가짜|가짜다른사"))
    c_front = os.path.realpath(P.card_by_id(st, c_id)["front"])
    pdir = Path(c_front).parent.parent / P.PEOPLE_DIR
    pdir.mkdir(exist_ok=True)
    c_photo = pdir / (Path(c_front).stem + ".jpg")
    jpg(c_photo, "red")

    print("=== A. 묶기 ===")
    # A0 회사 대표 번호·팩스·공용 메일은 여럿이 같이 쓴다 — 이름이 다르면 같은 휴대폰일 때만 묶음 (사용자 보고 261119)
    t2 = S.BizcardStore(TMP / "share.db")
    P.apply_import(t2, [
        {"name": "정가짜", "company": "가짜공사", "phones": [("cell", "010-0000-7100"), ("work", "02-0000-7000"), ("fax", "02-0000-7001")],
         "emails": ["office@example.com"], "urls": []},
        {"name": "한가짜", "company": "가짜공사", "phones": [("cell", "010-0000-7200"), ("work", "02-0000-7000"), ("fax", "02-0000-7001")],
         "emails": ["office@example.com"], "urls": []},
        {"name": "윤가짜", "company": "가짜공사", "phones": [("work", "02-0000-7000")], "emails": [], "urls": []},
        {"name": "Fake Program", "company": "가짜공사", "phones": [("cell", "010-0000-7200")], "emails": [], "urls": []},
        {"name": "윤가짜", "company": "", "phones": [("work", "02-0000-7000")], "emails": [], "urls": []},
        {"name": "갑가짜", "company": "사슬사", "phones": [("work", "02-0000-7300")], "emails": [], "urls": []},     # 사슬: 갑-을 회사 번호
        {"name": "을가짜", "company": "사슬사", "phones": [("work", "02-0000-7300"), ("fax", "02-0000-7301")], "emails": [], "urls": []},
        {"name": "병가짜", "company": "사슬사", "phones": [("fax", "02-0000-7301"), ("work", "02-0000-7302")], "emails": [], "urls": []},   # 을-병 팩스, 직통은 한 자리 다름
    ], "주소록", "google")
    sg = [sorted(c["name"] for c in g["cards"]) for g in P.dupe_groups(t2)]
    chk(sorted(sg) == [["Fake Program", "한가짜"]],
        "A0 이름이 다르면 회사 번호·팩스·메일이 같아도 묶지 않음(이름 다른 세 사람·사슬 갑-을 회사 번호·을-병 팩스·한 자리 다른 직통도), 같은 휴대폰이면 이름이 달라도(잘못 읽음) 묶음, 일반 전화는 같은 이름이어도 평가에서 뺌(261120-48)", str(sg))
    t2.close()
    gs = P.dupe_groups(st)
    by = {frozenset(c["id"] for c in g["cards"]): g for g in gs}
    g1, g2, g3, g4, g5 = (by.get(frozenset(s)) for s in ((a_id, x_id), (b_id, c_id), (d_id, y_id), (z_id, w_id), (e_id, v_id)))
    chk(len(gs) == 5 and all((g1, g2, g3, g4, g5)), "A 묶음 다섯(같은 번호·메일 / 번호 오타 / 이름+회사)",
        str(sorted(sorted(c["name"] for c in g["cards"]) for g in gs)))
    sure = lambda g, cid: g["sure_root"][cid] == g["sure_root"][g["cards"][0]["id"]]
    if all((g1, g2, g3, g4, g5)):
        chk(g1["why"][x_id] == "phone" and sure(g1, x_id) and g2["why"][c_id] == "typo" and not sure(g2, c_id)
            and g5["why"][v_id] == "namecomp" and not sure(g5, v_id), "A 이유 — 같은 번호(확실)·번호 오타?·이름·회사 같음(확실 아님)")
        chk([c["id"] for c in g1["cards"]] == [a_id, x_id] and g1["src"] == {a_id: "card", x_id: "remember"}
            and [c["id"] for c in g4["cards"]] == [w_id, z_id] and [c["id"] for c in g2["cards"]] == [b_id, c_id],
            "A 차례 — 명함 > 리멤버 > 구글, 같은 출처는 최근 스캔 먼저")

        print("\n=== B. 합친 값 ===")
        p1 = P.merge_plan(g1["cards"])
        f1 = p1["fields"]
        chk(f1["company"] == "가나도로공사" and f1["title"] == "상무" and f1["address"] == "서울 가짜로 1"
            and p1["frm"]["title"] == x_id and p1["keeper"] == a_id and p1["drop"] == [x_id],
            "B 1순위 값은 그대로, 빈 칸은 다음 순위(직함·주소)", str((f1["company"], f1["title"])))
        chk([n for _k, n in f1["phones"]] == ["010-0000-0001", "02-0000-0009"] and f1["emails"] == ["hong@example.com"]
            and f1["memo"] == "골프 모임\n\n리멤버 메모", "B 전화·메일 모두(같은 것 한 번), 메모는 대표 위 + 다른 글 아래", str(f1["phones"]))
        p2 = P.merge_plan(g2["cards"])
        chk([n for _k, n in p2["fields"]["phones"]] == ["010-0000-0003"] and p2["photo_from"] == c_id,
            "B 한 자리만 다른 번호(오타)는 뺌, 대표에 인물 사진이 없으면 사진 있는 명함에서", str(p2["fields"]["phones"]))
        p4 = P.merge_plan(list(reversed(g4["cards"])))
        chk(p4["keeper"] == z_id and p4["fields"]["company"] == "가짜구글사", "B 대표를 바꾸면 그 명함 값이 1순위")
        p3 = P.merge_plan([P.card_by_id(st, y_id), P.card_by_id(st, d_id)])
        chk(p3["keeper"] == d_id and p3["fields"]["company"] == "사아자" and p3["fields"]["dept"] == "기획팀",
            "B 대표가 주소록이면 그림 명함 행에 합침(= 그림을 대표로 옮김)")
        fake = lambda i, ph, **kw: dict({"id": i, "front": "contact:%d" % i, "phones": ph, "emails": [], "urls": [], "tags": []}, **kw)
        pm = P.merge_plan([fake(901, [("cell", "010-0000-1111")], company="가"),
                           fake(902, [("cell", "010-0000-2222"), ("cell", "017-000-3333"), ("work", "02-0000-4444")], company="나")])
        chk([n for _k, n in pm["fields"]["phones"]] == ["010-0000-1111", "010-0000-2222", "02-0000-4444"],
            "B 우선순위가 있어도 다른 휴대폰 번호는 더함(바꿨을 수 있음), 010 이 있으면 017 등 예전 번호는 뺌", str(pm["fields"]["phones"]))
        po = P.merge_plan([fake(903, [("cell", "016-000-5555")]), fake(904, [])])
        chk([n for _k, n in po["fields"]["phones"]] == ["016-000-5555"], "B 010 번호가 없으면 예전 번호는 남김")
        ph = P.merge_plan([fake(905, [], company="리멤버값"), fake(906, [], company="손값")], manual={(906, "company")})
        chk(ph["fields"]["company"] == "손값", "B 손으로 고친 칸은 출처 순서보다 먼저(D24 그대로)")
    st.close()

    print("\n=== C. 단추·창 ===")
    from viewer.app import MainWindow
    import modal_guard
    modal_guard.install(label=lambda: "중복 검토", echo=False)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    mw = MainWindow(); mw._skip_save_on_close = True
    mw.show()
    pump(timeout=1.0)
    mw._action_bizcard_find()
    fd = mw._bizcard_find_dlg
    pump(lambda: fd.table.rowCount() >= 10, timeout=5)
    bd = getattr(fd, "act_dupe", None)
    fd.main_menu.aboutToShow.emit()
    mn = [a.text() for a in fd.main_menu.actions() if not a.isSeparator()]
    chk(bd is not None and bd.text() == "중복 검토" and mn[1:4] == ["명함 관리", "중복 검토", "주소록"],
        "C ≡ 메뉴 '중복 검토' 는 '명함 관리'·'주소록' 사이(아래 단추 줄은 261120-66 에 없앰)", str(mn))
    from viewer.widgets import bizcard_dupe_dialog as DD
    DD.BizcardDupeDialog.exec = lambda self: self.show()           # 모달 대신 보이기만(검사)
    bd.trigger()
    dd = getattr(fd, "dupe_dlg", None)
    chk(dd is not None and dd.isVisible() and dd.before.topLevelItemCount() == 5 and dd.after.topLevelItemCount() == 5,
        "C 누르면 창 — 왼쪽 적용 전·오른쪽 적용 후 묶음 다섯")
    tops = {dd.before.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole)[1]: dd.before.topLevelItem(i)
            for i in range(dd.before.topLevelItemCount())}
    t2 = tops.get(b_id)
    chk(t2 is not None and t2.childCount() == 1 and t2.child(0).checkState(0) == Qt.CheckState.Unchecked
        and t2.checkState(0) == Qt.CheckState.Unchecked and tops.get(a_id) is not None
        and tops[a_id].child(0).checkState(0) == Qt.CheckState.Checked,
        "C 확실한 묶음은 체크, 번호 오타·이름+회사만은 체크 꺼짐")
    gi2 = t2.data(0, Qt.ItemDataRole.UserRole)[0]
    chk(dd.after.topLevelItem(gi2).text(1) == "(합치지 않음)", "C 체크 꺼진 묶음은 적용 후에 '(합치지 않음)'")
    t2.child(0).setCheckState(0, Qt.CheckState.Checked)
    t2.setCheckState(0, Qt.CheckState.Checked)
    pump(timeout=0.1)
    a2 = dd.after.topLevelItem(gi2)
    chk(a2.text(0) == "김철수" and a2.text(1) == "라마바" and a2.childCount() >= 3, "C 체크하면 오른쪽에 합친 결과", a2.text(1))
    gi1 = tops[a_id].data(0, Qt.ItemDataRole.UserRole)[0]
    a1 = dd.after.topLevelItem(gi1)
    bold = [a1.child(i).text(0) for i in range(a1.childCount()) if a1.child(i).font(1).bold()]
    chk("직함" in bold and "이름" not in bold, "C 대표에서 바뀐 칸만 굵게", str(bold))
    dd.before.setCurrentItem(tops[a_id].child(0))
    chk(dd.after.currentItem() is a1, "C 왼쪽에서 고르면 오른쪽도 같은 묶음")
    # C2 고른 묶음의 명함 그림 — 썸네일 줄 + 큰 그림, 여럿이면 골라 크게 (사용자 지시 261119)
    nk = lambda x: os.path.normcase(os.path.realpath(x)) if x else ""
    b_front = nk(P.card_by_id(S.BizcardStore(), b_id)["front"])
    dd.before.setCurrentItem(t2)
    pump(lambda: getattr(dd, "imgs_pending", 1) == 0 and not dd.big.pixmap().isNull(), timeout=5)   # 그림은 배경에서 읽음
    th = getattr(dd, "thumbs", None)
    chk(th is not None and th.count() == 2 and nk(dd.big_path) == b_front and not dd.big.pixmap().isNull(),
        "C2 그림 명함 묶음을 고르면 아래에 명함 그림 썸네일(둘)·고른 명함 큰 그림", str(th and th.count()))
    chk(th is not None and th.count() == 2 and all(not th.item(i).icon().isNull() for i in range(2)),
        "C2 썸네일 그림은 배경에서 읽어 채움")
    if th is not None and th.count() == 2:
        th.setCurrentRow(1)
        pump(lambda: dd.imgs_pending == 0, timeout=5)
        chk(nk(dd.big_path) == nk(c_front), "C2 썸네일을 고르면 그 그림을 크게")
    t4 = tops.get(w_id) or tops.get(z_id)
    dd.before.setCurrentItem(t4)
    pump(timeout=0.1)
    chk(th is not None and th.count() == 0 and dd.big_path == "" and dd.big.text() == "(명함 그림 없음)",
        "C2 주소록 명함만 있는 묶음은 그림 없음")
    # C3 '적용 후' 값을 두 번 눌러 고치면 그 값으로 합침 — 잘못 들어간 정보 고치기 (사용자 지시 261119)
    a1 = dd.after.topLevelItem(gi1)
    ci = next((a1.child(i) for i in range(a1.childCount()) if a1.child(i).text(0) == "회사"), None)
    di = next((a1.child(i) for i in range(a1.childCount()) if a1.child(i).text(0) == "부서"), None)
    chk(ci is not None and di is not None and di.text(1) == "", "C3 적용 후에 빈 칸(부서)도 보여 채울 수 있음")
    if ci is not None:
        dd.after.scrollToItem(ci)
        rect = dd.after.visualItemRect(ci)
        pos = QPoint(dd.after.header().sectionPosition(1) + 10, rect.center().y())
        QTest.mouseClick(dd.after.viewport(), Qt.MouseButton.LeftButton, pos=pos)   # 줄을 고른 뒤
        QTest.mouseDClick(dd.after.viewport(), Qt.MouseButton.LeftButton, pos=pos)  # 두 번 눌러 고치기
        pump(timeout=0.1)
        ed = QApplication.focusWidget()
        if ed is not None and hasattr(ed, "selectAll"):
            ed.selectAll()
            QTest.keyClicks(ed, "Fake Edit Co")
            QTest.keyClick(ed, Qt.Key.Key_Return)
        pump(timeout=0.1)
    p1e = dd.plan(gi1)
    a1 = dd.after.topLevelItem(gi1)
    ce = next((a1.child(i) for i in range(a1.childCount()) if a1.child(i).text(0) == "회사"), None)
    chk(p1e["fields"]["company"] == "Fake Edit Co" and "company" not in p1e["frm"] and ce is not None and ce.text(2) == "직접",
        "C3 두 번 눌러 고친 값이 합칠 값(출처 '직접')", str(p1e["fields"]["company"]))
    gi3 = next(i for i in range(len(dd.groups)) if dd.rep[i] == d_id)
    dd.set_edit(gi3, "phones", "010-0000-0004, 02-0000-5555")
    chk([n for _k, n in dd.plan(gi3)["fields"]["phones"]] == ["010-0000-0004", "02-0000-5555"]
        and dd.plan(gi3)["fields"]["phones"][1][0] == "work", "C3 전화는 쉼표로 나눠 고침(새 번호 종류는 번호 꼴로)")

    print("\n=== D. 적용 ===")
    db_before = S.BizcardStore()
    n_before = db_before.count()
    db_before.close()
    order = []                                 # D0 기다리는 지역 루프 없음 — 타이머는 apply 가 돌아온 뒤에 돈다(§5.24.8 '응답성', 261120-45)
    QTimer.singleShot(0, lambda: order.append("timer"))
    ticks = [time.perf_counter()]              # 메인 정지 — 20ms 박자 사이 가장 긴 틈(응답성 SOT §2 기준 1초)
    beat = QTimer()
    beat.setInterval(20)
    beat.timeout.connect(lambda: ticks.append(time.perf_counter()))
    beat.start()
    t_call = time.perf_counter()
    got = dd.apply(ask=False)
    t_call = time.perf_counter() - t_call
    order.append("returned")
    busy_now = bool(getattr(dd, "working", False)) and not dd.isEnabled()
    pump(lambda: not getattr(dd, "working", False) and "timer" in order, timeout=15)
    beat.stop()
    gap = max(b2 - b1 for b1, b2 in zip(ticks, ticks[1:])) if len(ticks) > 1 else 99
    print("D0 apply 호출 %.3fs · 메인 최장 틈 %.3fs · 박자 %d" % (t_call, gap, len(ticks)))
    chk(order == ["returned", "timer"] and busy_now and dd.isEnabled(),
        "D0 합치기 적용은 배경 DB 일을 신호로 잇는다 — 안에서 이벤트를 돌리지 않음·그동안 창 꺼짐·끝나면 켜짐", str((order, busy_now)))
    chk(gap < 1.0, "D0 합치기 적용 동안 메인 최장 정지 < 1초", "%.3f" % gap)
    st = S.BizcardStore()
    a = P.card_by_id(st, a_id)
    chk(got == 4 and st.count() == n_before - 4 and P.card_by_id(st, x_id) is None and P.card_by_id(st, c_id) is None,
        "D 묶음 넷 합침(체크 꺼진 이름+회사 묶음은 그대로), 나머지 명함 지움", "%s %s" % (got, st.count()))
    chk(a and a["title"] == "상무" and a["address"] == "서울 가짜로 1" and a["memo"] == "골프 모임\n\n리멤버 메모"
        and len(a["phones"]) == 2 and a["company"] == "Fake Edit Co", "D 대표 행에 합친 값(고친 회사 포함)", str(a and (a["phones"], a["company"])))
    chk(st.con.execute("SELECT COUNT(*) FROM fav_members WHERE group_id=? AND card_id=?", (gid, a_id)).fetchone()[0] == 1,
        "D 지운 명함의 즐겨찾기 칸은 남길 행으로")
    chk(P.field_srcs(st, a_id).get("title") == "remember" and "company" not in P.field_srcs(st, a_id),
        "D 주소록 출처는 칸마다 값을 준 명함의 것")
    d = P.card_by_id(st, d_id)
    chk(d and d["dept"] == "기획팀" and P.card_by_id(st, y_id) is None, "D 주소록 명함은 DB 행만 지움, 그림 명함에 값")
    b = P.card_by_id(st, b_id)
    hold = OUT.parent / P.HOLD_DIR
    b_ph = P.person_photos(os.path.realpath(b["front"])) if b else []
    chk(len(b_ph) == 1 and not c_photo.exists() and hold.is_dir() and (hold / os.path.basename(c_front)).exists(),
        "D 대표에 없던 인물 사진은 옮기고, 지운 그림 명함 파일은 '병합 보관' 으로",
        str((b_ph, sorted(os.listdir(hold)) if hold.is_dir() else "-")))
    w = P.card_by_id(st, w_id)
    chk(w and w["company"] == "가짜리멤버사" and P.card_by_id(st, z_id) is None, "D 주소록끼리는 1순위(리멤버) 행에")
    chk(dd.btn_undo.isEnabled() and dd.before.topLevelItemCount() == 1, "D 적용 뒤 남은 묶음만·되돌리기 켜짐")
    st.close()

    print("\n=== E. 되돌리기·우선순위 ===")
    ok = dd.undo(ask=False)
    QTest.keyClick(dd, Qt.Key.Key_Escape)      # 배경 DB 일 중 Esc·닫기 — 창은 남고, 끝난 뒤 신호가 그 창에서 처리된다(261120-45)
    dd.close()
    still = dd.isVisible() and bool(getattr(dd, "working", False))
    pump(lambda: not getattr(dd, "working", False), timeout=15)
    pump(timeout=0.2)
    chk(still and dd.isVisible() and dd.isEnabled(), "E0 되돌리기 배경 일 중 Esc·닫기는 무시, 끝나면 창이 켜짐", str(still))
    st = S.BizcardStore()
    chk(ok and st.count() == n_before and P.card_by_id(st, x_id) is not None and P.card_by_id(st, c_id) is not None
        and (P.card_by_id(st, a_id) or {}).get("title") in ("", None), "E 되돌리기 — DB 를 합치기 전으로", str(st.count()))
    chk(c_photo.exists() and os.path.exists(c_front) and not any(hold.iterdir()) if hold.is_dir() else c_photo.exists(),
        "E 옮긴 파일 제자리로")
    st.close()
    dd.set_order(["card", "google", "remember", "contact"])
    g4b = next((dd.groups[i] for i in range(len(dd.groups)) if dd.rep[i] in (z_id, w_id)), None)
    chk(g4b is not None and g4b["cards"][0]["id"] == z_id and S.BizcardStore().meta_get(P.DUPE_ORDER_KEY)[:2] == ["card", "google"],
        "E 우선순위를 바꾸면 기억하고 대표가 바뀜(구글 먼저)")
    gi4 = next(i for i in range(len(dd.groups)) if dd.rep[i] == z_id)
    dd.set_rep(gi4, w_id)
    chk(dd.rep[gi4] == w_id and dd.plan(gi4)["keeper"] == w_id, "E 묶음마다 '대표로' 바꾸기")
    dd.close()

    print("\n=== F. 주소록 가져오기 뒤에는 늘 병합 창 ===")
    vf = TMP / "new.vcf"
    vf.write_text("BEGIN:VCARD\r\nVERSION:3.0\r\nFN:이영희\r\nTEL;TYPE=CELL:010-0000-0004\r\nORG:가짜새회사\r\nEND:VCARD\r\n", encoding="utf-8")
    st = S.BizcardStore()
    n0 = st.count()
    st.close()
    res = fd.import_contacts(str(vf), ask=False, source="google")
    d2 = getattr(fd, "dupe_dlg", None)
    st = S.BizcardStore()
    chk(res == 1 and st.count() == n0 + 1, "F 같은 번호여도 자동으로 합치지 않고 모두 넣음", str(res))
    st.close()
    g_lee = next((g for g in (d2.groups if d2 is not dd and d2 else []) if any(c["id"] == d_id for c in g["cards"])), None)
    chk(d2 is not None and d2 is not dd and d2.isVisible() and g_lee is not None and len(g_lee["cards"]) == 3,
        "F 가져오자마자 [중복 검토] 창 — 새 연락처가 기존 명함 묶음에", str(g_lee and len(g_lee["cards"])))
    if d2 is not None and d2 is not dd:
        d2.close()

    print("\n=== G. 이미 한 장으로 들어간 다중 명함 사진 찾기 (§5.26) ===")
    from PIL import ImageDraw as _ID
    FG = TMP / "multi_in"
    FG.mkdir()
    board = Image.new("RGB", (2000, 1500), (58, 60, 66))
    for cx, cy in ((500, 400), (1450, 400), (520, 1100)):
        c = Image.new("RGB", (700, 400), (246, 246, 242))
        _ID.Draw(c).rectangle([160, 80, 520, 100], fill=(20, 20, 20))
        board.paste(c, (cx - 350, cy - 200))
    board.save(FG / "g_1.jpg", quality=92)
    itg = {it.base: it for it in I.scan_folder(FG)}["g"]
    AP.apply_cards([{"key": itg.key, "front": itg.front, "back": "", "pdf": "", "keep_back": False,
                     "name": "다중가짜", "company": "가짜묶음사", "langs": ["한글"], "phones": [("cell", "010-0000-9900")]}],
                   FG / "정리")
    st = S.BizcardStore()
    g_old = P.find(st, "다중가짜")[0]
    g_out = os.path.realpath(g_old["front"])
    st.close()
    import viewer.widgets.bookmark_tree as _btm
    import shutil
    TRG = TMP / "trash_g"
    TRG.mkdir()
    _btm._trash_fn = lambda: (lambda p: shutil.move(p, str(TRG / Path(p).name)))      # 시험용 휴지통
    d3 = fd.open_dupes(exec_=False)
    chk(d3 is not None and hasattr(d3, "btn_multi"), "G 중복 검토 창에 [다중 명함 찾기]")
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)   # '명함 관리를 열어 읽을까요?' — 예
    QTest.mouseClick(d3.btn_multi, Qt.MouseButton.LeftButton)
    chk(pump(lambda: getattr(d3, "multi_dlg", None) is not None and d3.multi_dlg.isVisible(), timeout=20)
        and len(d3.multi_dlg.view.quads) == 3, "G 이미 들어간 명함의 원본을 세어 확인 창(테두리 셋)")
    if getattr(d3, "multi_dlg", None) is not None:
        QTest.mouseClick(d3.multi_dlg.btn_ok, Qt.MouseButton.LeftButton)
    chk(pump(lambda: getattr(d3, "multi_split", None) is not None and getattr(mw, "_bizcard_dlg", None) is not None, timeout=20),
        "G 나눈 뒤 명함 관리를 그 폴더로 엶")
    st = S.BizcardStore()
    names_g = sorted(os.listdir(FG))
    chk(P.card_by_id(st, g_old["id"]) is None and not os.path.exists(g_out) and "g_1 명함 03.jpg" in names_g
        and (FG / "다중 원본" / "g_1.jpg").exists(),
        "G 예전 한 장짜리 명함은 지우고(정리본 휴지통) 원본 옆에 셋, 원본은 '다중 원본'", str(names_g))
    st.close()
    imd = getattr(mw, "_bizcard_dlg", None)
    if imd is not None:
        pump(lambda: imd.bar.value() == 3 and not imd._pending, timeout=20)
        chk(imd.table.rowCount() == 3, "G 명함 관리가 잘라낸 셋을 읽음", str(imd.table.rowCount()))
        imd.close()
        pump(timeout=0.3)
    d4 = fd.open_dupes(exec_=False)
    chk(d4 is not None and d4.btn_undo.isEnabled(), "G 나눈 뒤 [마지막 합치기 되돌리기] 켜짐(합치기와 같은 길)")
    if d4 is not None:
        d4.undo(ask=False)
        pump(lambda: not getattr(d4, "working", False), timeout=15)
        pump(timeout=0.2)
        st = S.BizcardStore()
        chk(P.card_by_id(st, g_old["id"]) is not None and os.path.exists(g_out) and (FG / "g_1.jpg").exists()
            and not (FG / "g_1 명함 01.jpg").exists(), "G 되돌리기 — 예전 명함·정리본·원본 제자리, 잘라낸 것은 휴지통",
            str(sorted(os.listdir(FG))))
        st.close()
        # 크게 보기 — F11 전체 화면, Esc 로 돌아옴 (사용자 지시 261119)
        d4.activateWindow()
        QTest.keyClick(d4, Qt.Key.Key_F11)
        pump(timeout=0.2)
        full = d4.isFullScreen()
        QTest.keyClick(d4, Qt.Key.Key_Escape)
        pump(timeout=0.2)
        chk(bool(d4.windowFlags() & Qt.WindowType.WindowMaximizeButtonHint) and full and not d4.isFullScreen() and d4.isVisible(),
            "H 중복 검토 창 크게 보기 — 최대화 단추·F11 전체 화면·Esc 로 돌아옴(창은 그대로)")
        # 세는 중 다시 누르면 멈춤
        d4.find_multi(ask=False)
        d4.find_multi(ask=False)
        pump(lambda: d4._mw_multi.done_event.is_set(), timeout=20)
        pump(timeout=0.2)
        chk(d4.btn_multi.text() == "다중 명함 찾기", "G 세는 중 다시 누르면 멈춤 — 단추 글 되돌아옴", d4.btn_multi.text())
        d4.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "예외 없이 끝남")
finish()
