# -*- coding: utf-8 -*-
"""명단 관리 (명함 SOT §5.32, 261122-1·-2) — 가짜 명함·가짜 vcf(010-0000-…)·임시 폴더만.

A. 010 둘 이상 보기
B. vcf 비교 — 이름이 있는 사람은 안 냄·'잘못 합쳐짐?'·'이름 바뀜?'·새 사람은 체크 때만·vcf 는 읽기만
C. 창 — ≡ 메뉴 '명단 관리'(명함찾기, 호스트 없어도)·보기 갈래·배경 읽기(메인 정지 < 1초)
D. 나누기 — vcf 이름·번호 미리 채움, 번호·메일 떼기, 주소록 출처 가져감·구글 짝 남음·다른 사람 기억·변경 기록 split
E. vcf 이름으로 · F. 추가 · G. 명함 그림 나누기(정리본 새 이름·남는 쪽 그림 없는 명함·인물 사진 그대로 그 사람)
"""
import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, QTimer
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox
from pathlib import Path
from PIL import Image

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_roster_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_roster_"))
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


def num(n):
    return "010-0000-%04d" % (n * 1111)


VCF = "\r\n".join([
    "BEGIN:VCARD", "VERSION:3.0", "FN:가짜갑", "TEL;TYPE=CELL:" + num(1), "END:VCARD",
    "BEGIN:VCARD", "VERSION:3.0", "FN:가짜을", "ORG:가짜회사", "TEL;TYPE=WORK:+82 10-0000-2222", "END:VCARD",   # 일반 전화 칸·+82 꼴도 010
    "BEGIN:VCARD", "VERSION:3.0", "FN:가짜새이름", "TEL:" + num(3), "END:VCARD",                                  # 종류 없는 번호
    "BEGIN:VCARD", "VERSION:3.0", "FN:가짜경", "TEL;TYPE=HOME:" + num(7), "END:VCARD",
    "BEGIN:VCARD", "VERSION:3.0", "FN:가짜묶음", "X-ADDRESSBOOKSERVER-KIND:group", "TEL:010-0000-5555", "END:VCARD",  # 그룹 카드는 사람 아님
    "BEGIN:VCARD", "VERSION:3.0", "FN:가짜무", "TEL;TYPE=CELL:" + num(9), "END:VCARD",
    "BEGIN:VCARD", "VERSION:3.0", "FN:가짜병", "TEL;TYPE=CELL:" + num(4), "END:VCARD", ""])

try:
    from viewer.bizcard import people as P, store as S, gsync as G, roster as RS, history as H
    FOLD = TMP / "cards"
    (FOLD / "정리").mkdir(parents=True)
    db = TMP / "local" / "bizcard.db"
    st = S.BizcardStore(db)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    P.src_init(st)
    add = lambda name, nums, emails=(): P._insert_contact(st, {"name": name, "phones": [("cell", num(n)) for n in nums],
                                                                "emails": list(emails)}, ["명함"])
    m = add("가짜갑", [1, 2], ["gab@example.com", "eul@example.com"])   # 잘못 합쳐진 명단
    P._set_srcs(st, m, ["name", "phones"], G.SRC)
    G.init(st)
    G._link_put(st, m, "people/fake1", "e1")
    r = add("가짜옛이름", [3])
    k_ = add("가짜경", [7, 8])                                         # 같은 이름인데 vcf 와 번호가 다름
    n_ = add("가짜병", [4])
    f = FOLD / "정리" / "가짜정_가짜사.jpg"
    Image.new("RGB", (300, 180), "white").save(f)
    img = st.upsert({"front": str(f), "name": "가짜정", "company": "가짜사", "phones": [("cell", num(5)), ("cell", num(6))]})
    ph = P.next_photo_path(str(f))
    ph.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (60, 80), "gray").save(ph)
    st.con.commit()
    settings_store.set_picture_prefs({"bizcard_folder": str(FOLD)})
    vcf = TMP / "받은" / "주소록.vcf"
    vcf.parent.mkdir()
    vcf.write_text(VCF, encoding="utf-8")
    vcf_bytes = vcf.read_bytes()

    print("=== A·B 계산 ===")
    cards = RS.all_cards(st)
    chk(sorted(c["id"] for c in RS.multi_mobile(cards)) == sorted([m, img, k_]), "A 010 둘 이상 명단만", str([c["name"] for c in RS.multi_mobile(cards)]))
    persons = RS.read_vcf(str(vcf))
    gs = RS.vcf_compare(cards, persons)
    got = {g["person"]["name"]: [(s["card"]["id"], s["kind"]) for s in g["subs"]] for g in gs}
    chk(got == {"가짜갑": [(m, RS.SAME_NAME)], "가짜을": [(m, RS.MERGED)], "가짜새이름": [(r, RS.RENAMED)], "가짜경": [(k_, RS.SAME_NAME)]},
        "B vcf 비교 — 이름 없는 사람(잘못 합쳐짐?·이름 바뀜?)·이름 있어도 번호 다르면 같은 이름 명단, 번호까지 같은 병·번호 없는 무·그룹 카드는 안 냄, "
        "종류 없는·일반 전화·+82 꼴 010 도", str(got))
    gs2 = RS.vcf_compare(cards, persons, show_new=True)
    chk(any(g["person"]["name"] == "가짜무" and g["kind"] == RS.NEW for g in gs2), "B '새 사람' 은 체크를 켰을 때만")
    st.close()

    print("\n=== C 창 ===")
    from viewer.widgets import bizcard_find_dialog as FD
    fd = FD.BizcardFindDialog(None, db=db)
    fd._bz_folder = str(FOLD)
    fd.show()
    pump(lambda: fd.table.rowCount() == 5)
    fd.main_menu.aboutToShow.emit()
    names = [a.text() for a in fd.main_menu.actions() if not a.isSeparator()]
    chk("명단 관리" in names and "명함 관리" not in names, "C ≡ 메뉴 '명단 관리'(본 뷰어 없이도)·옛 이름 없음", str(names))
    gaps, last = [], [time.monotonic()]

    def tick():
        now = time.monotonic()
        gaps.append(now - last[0])
        last[0] = now
    tm = QTimer()
    tm.timeout.connect(tick)
    tm.start(10)
    act = next(a for a in fd.main_menu.actions() if a.text() == "명단 관리")
    from viewer.widgets import bizcard_roster_dialog as RD
    _orig_exec = RD.RosterDialog.exec
    RD.RosterDialog.exec = lambda self: self.show() or 0          # 메뉴 길 그대로, 모달 대신 보이기만
    act.trigger()
    RD.RosterDialog.exec = _orig_exec
    rd = getattr(fd, "roster_dlg", None)
    pump(lambda: rd is not None and not rd.loading and rd.tree.topLevelItemCount() == 5, timeout=10)
    chk(rd is not None and rd.tree.topLevelItemCount() == 5, "C '전체' — 명함 있든 없든 모든 명단", str(rd and rd.tree.topLevelItemCount()))
    rd.set_view("multi")
    pump(lambda: not rd.loading and rd.tree.topLevelItemCount() == 3, timeout=10)
    chk(rd.tree.topLevelItemCount() == 3, "C '010 둘 이상' 보기")
    rd.ed_find.setText("가짜정")
    pump(lambda: not rd.loading and rd.tree.topLevelItemCount() == 1, timeout=10)
    chk(rd.tree.topLevelItemCount() == 1, "C 찾기 칸으로 거름")
    rd.ed_find.setText("")
    rd.open_vcf(str(vcf))
    pump(lambda: not rd.loading and rd.view() == "vcf" and rd.tree.topLevelItemCount() == 4, timeout=10)
    chk(rd.tree.topLevelItemCount() == 4 and rd.btn_vcf.isVisible() and rd.chk_new.isVisible(), "C vcf 비교 — vcf 사람 4명, vcf 단추·체크 보임")
    tm.stop()
    chk(max(gaps or [0]) < 1.0, "C 읽기 동안 메인 최장 정지 < 1초", "%.2f" % max(gaps or [0]))
    chk(vcf.read_bytes() == vcf_bytes and not list(FOLD.rglob("*.vcf")), "B vcf 는 읽기만(바꾸지 않음·명함 폴더에 복사 안 함)")

    print("\n=== D 나누기 ===")
    gi = next(i for i, g in enumerate(rd.groups) if g["person"]["name"] == "가짜을")
    rd.select_card(m, gi=gi)
    d = rd.tree.currentItem().data(0, 0x0100)
    chk(d[0] == "card" and d[1] == m and rd.btn_split.isEnabled(), "D 잘못 합쳐짐? 줄을 고르면 [나누기] 켜짐")
    sd = rd.split_dialog()
    v0 = sd.values()
    chk(v0["fields"]["name"] == "가짜을" and v0["fields"]["company"] == "가짜회사" and [p[-1] for p in v0["phones"]] == [num(2)],
        "D vcf 이름·회사·그 010 번호를 미리 채움", str(v0))
    sd.check("email", "eul@example.com")
    nid = rd.split(dlg=sd)
    st2 = fd._store()
    mc, nc = P.card_by_id(st2, m), P.card_by_id(st2, nid) if nid else None
    chk(nid and [p[-1] for p in mc["phones"]] == [num(1)] and mc["emails"] == ["gab@example.com"],
        "D 남는 쪽에서 뗀 번호·메일이 빠짐", str(mc and (mc["phones"], mc["emails"])))
    chk(nc is not None and nc["name"] == "가짜을" and [p[-1] for p in nc["phones"]] == [num(2)] and nc["emails"] == ["eul@example.com"],
        "D 새 사람 — 이름·번호·메일", str(nc and (nc["name"], nc["phones"], nc["emails"])))
    chk(P.field_srcs(st2, nid).get("phones") == G.SRC and G.kakao_rows(st2).get(nid) is None and nid in G._google_src_ids(st2),
        "D 뗀 번호의 주소록 출처(구글)를 새 사람도 — 다음 싱크 '#' 없이", str(P.field_srcs(st2, nid)))
    lk = G.links(st2)
    chk(m in lk and nid not in lk, "D 구글 짝은 남는 쪽에")
    chk((min(m, nid), max(m, nid)) in P.not_same_pairs(st2), "D 두 사람은 '다른 사람' 으로 기억")
    gp = [{"resourceName": "people/fake1", "etag": "e1", "names": [{"unstructuredName": "가짜갑"}],
           "phoneNumbers": [{"value": num(1), "type": "mobile"}, {"value": num(2), "type": "mobile"}],
           "emailAddresses": [{"value": "gab@example.com"}, {"value": "eul@example.com"}],
           "metadata": {"sources": [{"updateTime": "2026-01-01T00:00:00Z"}]}}]          # 구글엔 아직 합쳐진 그대로
    rows = G.plan(st2, gp)
    up = [x for x in rows if x["kind"] == G.TO_GOOGLE and x["card_id"] == m]
    new = [x for x in rows if x["kind"] == G.NEW_GOOGLE and x["card_id"] == nid]
    chk(up and "phones" in up[0]["fields"] and new and new[0]["kakao"] is False,
        "D 다음 싱크 미리보기 — 남는 쪽 '구글 고침'(번호), 떼어 낸 쪽 '새 연락처'('#' 없이)", str([(x["kind"], x["card_id"]) for x in rows]))
    srcs = {row[0] for row in st2.con.execute("SELECT src FROM card_history WHERE card_id=?", (m,))}
    chk("split" in srcs, "D 변경 기록 출처 'split'", str(srcs))
    pump(lambda: not rd.loading, timeout=10)
    chk(not any(g["person"]["name"] == "가짜을" for g in rd.groups), "D 나눈 뒤 다시 읽음 — '을' 은 이제 명단에 있어 안 냄")

    print("\n=== E vcf 이름으로 ===")
    rd.select_card(r)
    chk(rd.btn_rename.isEnabled(), "E 이름 바뀜? 줄에서 [vcf 이름으로] 켜짐")
    ok = rd.vcf_name()
    chk(ok and P.card_by_id(st2, r)["name"] == "가짜새이름", "E 그 명단 이름이 vcf 이름으로", str(P.card_by_id(st2, r)["name"]))
    pump(lambda: not rd.loading, timeout=10)

    print("\n=== E2 vcf 번호로 ===")
    rd.select_card(k_)
    chk(rd.btn_nums.isEnabled() and not rd.btn_rename.isEnabled(), "E2 같은 이름·번호 다름 줄에서 [vcf 번호로] 켜짐")
    sd = rd.split_dialog()
    chk(sd.values()["fields"]["name"] == "" and [p[-1] for p in sd.values()["phones"]] == [num(8)],
        "E2 그 줄에서 나누기 — vcf 에 없는 번호를 미리 체크·이름은 비움", str(sd.values()))
    ok = rd.vcf_numbers()
    chk(ok and P.mobiles_010(P.card_by_id(st2, k_)) == ["01000007777"], "E2 010 번호를 vcf 의 것으로", str(P.card_by_id(st2, k_)["phones"]))
    pump(lambda: not rd.loading, timeout=10)

    print("\n=== F 추가 ===")
    rd.chk_new.setChecked(True)
    pump(lambda: not rd.loading and any(g["person"]["name"] == "가짜무" for g in rd.groups), timeout=10)
    gi_n = next(i for i, g in enumerate(rd.groups) if g["person"]["name"] == "가짜무")
    rd.select_person(gi_n)
    chk(rd.btn_add.isEnabled() and not rd.btn_split.isEnabled(), "F vcf 사람 줄 — [추가] 켜짐·[나누기] 꺼짐")
    rd.add()
    chk(any(c["name"] == "가짜무" for c in RS.all_cards(st2)), "F vcf 사람을 그림 없는 명함으로 더함")
    pump(lambda: not rd.loading, timeout=10)

    print("\n=== G 명함 그림 나누기 ===")
    rd.set_view("multi")
    pump(lambda: not rd.loading and rd.view() == "multi", timeout=10)
    rd.select_card(img)
    pump(lambda: rd.big.pixmap() is not None and not rd.big.pixmap().isNull(), timeout=5)
    bw = rd.big.pixmap().width() if rd.big.pixmap() is not None else 0
    chk(bw > 2 * 96 and rd.thumbs.count() == 2 and rd.big_path == P._real(P.card_by_id(fd._store(), img)["front"]),
        "H 오른쪽 — 앞면을 칸에 맞춰 크게(종전 썸네일 192px 보다 큼)·아래 썸네일 줄(앞면·인물 사진)", str((bw, rd.thumbs.count())))
    rd.thumbs.setCurrentRow(1)
    pump(lambda: rd.big_path.endswith(".jpg") and rd.big_path != P._real(P.card_by_id(fd._store(), img)["front"]), timeout=3)
    chk(rd.big_path != P._real(P.card_by_id(fd._store(), img)["front"]), "H 썸네일을 고르면 그 그림을 크게")
    sd = rd.split_dialog()
    sd.eds["name"].setText("가짜기")
    sd.eds["company"].setText("가짜사")
    sd.check("image")
    sd.check("phone", num(6))
    nid2 = rd.split(dlg=sd)
    a2, b2 = P.card_by_id(st2, img), P.card_by_id(st2, nid2) if nid2 else None
    from viewer.bizcard import vcard as V
    chk(b2 is not None and not V.is_contact(b2) and os.path.exists(P._real(b2["front"])) and Path(P._real(b2["front"])).name.startswith("가짜기_"),
        "G 새 사람이 명함 그림을 가짐(정리본 이름 새 사람으로)", str(b2 and b2["front"]))
    chk(V.is_contact(a2) and [p[-1] for p in a2["phones"]] == [num(5)], "G 남는 쪽은 그림 없는 명함·남은 번호", str(a2 and (a2["front"], a2["phones"])))
    pf = fd._photo_front(a2)
    chk(pf and len(P.person_photos(pf)) == 1, "G 남는 쪽 인물 사진은 그림 없는 명함 자리로 따라감", str(pf))
    rd.close()
    fd.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외")
print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
