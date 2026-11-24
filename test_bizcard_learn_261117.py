# -*- coding: utf-8 -*-
"""명함 인식 개선·배우기 (명함 SOT §5.11, 261117-9) — 가짜 명함만(실제 명함 값·경로 금지, 명함 SOT §2.1).

A. 점·가운뎃점·쉼표로 나눈 번호('010.0000.0001'·'010·0000·0002'·'010. 0000. 0003')
B. 이름 앞 직위 — '시험실장 홍  길  동' → 이름 홍길동·직위 시험실장, '품질팀장 김철수'
C. 누리집·메일 도메인 → 직장 — www.seoul.go.kr 이고 회사 줄이 없으면 '서울시청', 아래 도메인도, 배운 표가 먼저, 개인 메일은 안 봄
D. 다시 매기기 — 양식 상자 안의 후보가 1위로(OCR 없이), 배운 가중치를 쓰면 순위가 바뀜
E. 가중치 배우기 — 표본이 모자라면 None, 충분하면 1위 정확도가 기본 이상, 표본에는 이름 글자가 없다
F. 앱 — 명함 읽기 창: 미리 보기 위치 지정이 그 자리만 읽어 이름 칸을 채우고 같은 회사 양식으로 기억(다른 줄 다시 매김),
   [적용] 뒤 도메인 → 직장을 배움, 글자 '명함 읽기'(명함찾기 단추 — 261117-56 에 도구 탭 메뉴는 없앰)
G. 세로로 누운 명함 — 0도에서 연락처를 못 찾으면 돌려 읽는다(OCR, 없으면 SKIP)
"""
import os, sys, tempfile, shutil, time, json
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtTest import QTest
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_learn_%d" % os.getpid())
fails = []
TMP = Path(tempfile.mkdtemp(prefix="bizcard_learn_"))
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
    from viewer.bizcard import recognize as R, learn as LN, store as S
except Exception as e:
    chk(False, "배우기 모듈을 불러온다", repr(e))
    print("FAILURES: %d" % len(fails))
    os._exit(1)
L = R.Line
try:
    # ── A ──
    print("=== A. 번호 구분자 ===")
    chk(R.find_phones("M. 010.0000.0001") == [("cell", "010-0000-0001")], "A 점")
    chk(R.find_phones("H.P 010·0000·0002") == [("cell", "010-0000-0002")], "A 가운뎃점", str(R.find_phones("H.P 010·0000·0002")))
    chk(R.find_phones("010. 0000. 0003") == [("cell", "010-0000-0003")], "A 점 + 빈칸")
    chk(R.find_phones("T 02·000·0004  F 02·000·0005") == [("work", "02-000-0004"), ("fax", "02-000-0005")], "A 가운뎃점 전화·팩스",
        str(R.find_phones("T 02·000·0004  F 02·000·0005")))

    # ── B ──
    print("\n=== B. 이름 앞 직위 ===")
    lines = [L("가나다시험연구원", 0.10, 90, 0.05), L("시험실장 홍  길  동", 0.14, 85, 0.40),
             L("M. 010-0000-0001", 0.05, 90, 0.9)]
    r = R.parse_lines(lines)
    chk(r.names_ko and r.names_ko[0].text == "홍길동", "B 이름 홍길동(띄운 글자 붙임·직위 뺌)", str([c.text for c in r.names_ko[:3]]))
    chk(r.titles_ko and r.titles_ko[0] == "시험실장", "B 직위 시험실장", str(r.titles_ko))
    r2 = R.parse_lines([L("라마바건설", 0.10, 90, 0.05), L("품질팀장 김철수", 0.12, 85, 0.4)])
    chk(r2.names_ko[0].text == "김철수" and "품질팀장" in r2.titles_ko, "B 품질팀장 김철수", str([c.text for c in r2.names_ko[:3]]) + str(r2.titles_ko))
    chk(all(c.feat.get("cx") is not None for c in r.names_ko), "B 후보마다 위치·특징이 남는다")

    # ── C ──
    print("\n=== C. 도메인 → 직장 ===")
    r3 = R.parse_lines([L("홍길동", 0.15, 90, 0.3), L("주무관", 0.06, 90, 0.4), L("www.seoul.go.kr", 0.04, 90, 0.9),
                        L("T. 02-000-0001", 0.04, 90, 0.95)])
    c3 = R.merge_sides(r3, None)
    chk(c3.company == "서울시청", "C www.seoul.go.kr · 회사 줄 없음 → 서울시청", c3.company)
    chk(R.org_from_domains(["user@dept.seoul.go.kr"], []) == "서울시청", "C 아래 도메인도 위로 올라가 찾는다")
    chk(R.org_from_domains(["user@gmail.com"], []) == "", "C 개인 메일은 직장이 아니다")
    chk(R.org_from_domains([], ["www.example.co.kr"], {"example.co.kr": "예시기술"}) == "예시기술", "C 배운 표")
    r4 = R.parse_lines([L("(주)가나다기술", 0.10, 90, 0.05), L("홍길동", 0.15, 90, 0.3), L("www.seoul.go.kr", 0.04, 90, 0.9)])
    chk(R.merge_sides(r4, None).company == "가나다기술", "C 회사 줄이 뚜렷하면 그대로")

    # ── D ──
    print("\n=== D. 다시 매기기 ===")
    lines5 = [L("홍길동", 0.14, 90, 0.10, 0.3, 0.15), L("김철수", 0.14, 90, 0.60, 0.7, 0.65),
              L("hong@example.co.kr", 0.04, 90, 0.9)]
    c5 = R.merge_sides(R.parse_lines(lines5), None)
    res5 = json.loads(json.dumps(__import__("dataclasses").asdict(c5), ensure_ascii=False))
    key = R.layout_key(res5["emails"], res5["urls"], res5["company"])
    chk(key == "d:example.co.kr", "D 양식 열쇠는 회사 도메인", key)
    top0 = R.rescore(res5)["name_cands"][0]["text"]
    other = "김철수" if top0 == "홍길동" else "홍길동"
    box = (0.6, 0.55, 0.8, 0.75) if other == "김철수" else (0.2, 0.05, 0.4, 0.25)
    rs = R.rescore(res5, None, {key: {"name": box}})
    chk(rs["name_cands"][0]["text"] == other and rs["name"] == other, "D 양식 상자 안 후보가 1위", "%s → %s" % (top0, rs["name"]))
    rc = R.rescore(res5, None, None, None, {"name": {top0: "고친이름"}, "dept": {"": "x"}})
    chk(rc["name_cands"][0]["text"] == "고친이름" or any(c["text"] == "고친이름" for c in rc["name_cands"]), "D 교정 표가 후보 글을 고친다")
    w = dict(R.NAME_W); w["h"] = 0.0; w["sur"] = 0.0
    chk(R.rescore(res5, w)["name_cands"][0]["score"] != R.rescore(res5)["name_cands"][0]["score"], "D 가중치를 바꾸면 점수가 바뀐다")

    # ── E ──
    print("\n=== E. 가중치 배우기 ===")
    import random
    random.seed(1)
    smps = []
    for i in range(60):                     # '직함 이웃' 이 정답을 가르는 가짜 표본 — 기본 가중치는 '크기' 를 더 믿는다
        good = {"bias": 1, "h": 0.3, "sur": 1, "title": 1, "len3": 1, "conf": 0.8}
        bad = {"bias": 1, "h": 1.0, "sur": 1, "title": 0, "len3": 1, "conf": 0.9}
        rows = [good, bad]
        random.shuffle(rows)
        smps.append({"feats": [[float(x.get(k, 0)) for k in R.NAME_FEATS] for x in rows], "y": [int(x is good) for x in rows]})
    chk(LN.train(smps[:10]) is None, "E 표본이 모자라면 배우지 않는다")
    wl = LN.train(smps)
    a0, a1 = LN.top1_accuracy(smps), LN.top1_accuracy(smps, wl)
    chk(wl is not None and a1 > a0 and a1 >= 0.95, "E 배운 가중치가 1위 정확도를 올린다", "%.2f → %.2f" % (a0, a1))
    smp = LN.sample_of({"name": "홍길동"}, res5)
    chk(smp is not None and "홍길동" not in json.dumps(smp, ensure_ascii=False) and sum(smp["y"]) == 1,
        "E 표본에는 이름 글자가 없고 정답 하나")

    # ── F ──
    print("\n=== F. 앱 — 명함 읽기 창 ===")
    from test_fixtures import KRFONT
    from viewer.study import ocr as O
    have_ocr = O.ensure_tesseract().get("ok") and KRFONT and "kor" in O.available_langs()
    from PIL import Image, ImageDraw, ImageFont
    F = TMP / "cards"
    F.mkdir()

    def card(path, name, extra_top="", rot=0):
        im = Image.new("RGB", (1060, 580), "white")
        d = ImageDraw.Draw(im)
        f = lambda s: ImageFont.truetype(KRFONT, s) if KRFONT else ImageFont.load_default()
        d.text((60, 40), extra_top or "가나다", font=f(40), fill="navy")          # 크고 이름 같은 낱말(미끼)
        d.text((620, 300), name, font=f(52), fill="black")
        d.text((60, 470), "M. 010-0000-0001   E. user@example.co.kr", font=f(28), fill="black")
        if rot:
            im = im.rotate(rot, expand=True)
        im.save(path, quality=92)
    card(F / "가_홍길동_1.jpg", "홍길동", "나무숲")
    card(F / "나_김철수_1.jpg", "김철수", "바다솔")
    mainmod = None

    def fake_recognize(path, ui_lang="ko"):              # 미끼(위 큰 글자)가 1위인 인식 결과 — 오른쪽 가운데 이름은 2위
        stem = Path(path).stem
        nm = "홍길동" if "홍길동" in stem else "김철수"
        bait = "나무숲" if nm == "홍길동" else "바다솔"
        f1 = {"bias": 1, "h": 1.0, "sur": 1, "len3": 1, "conf": 0.9, "cx": 0.2, "cy": 0.1}
        f2 = {"bias": 1, "h": 0.6, "sur": 1, "len3": 1, "conf": 0.9, "cx": 0.68, "cy": 0.56}
        return R.CardResult(name=bait, phones=[("cell", "010-0000-0001")], emails=["user@example.co.kr"],
                            name_cands=[R.Cand(bait, R.name_score(f1), (), f1), R.Cand(nm, R.name_score(f2), (), f2)],
                            company_cands=[], langs=("한글",), need_check=("name", "company"))
    R.recognize = fake_recognize
    from viewer.app import MainWindow
    import modal_guard
    modal_guard.install(label=lambda: "명함 읽기", echo=False)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    mw = MainWindow(); mw._skip_save_on_close = True
    mw.show(); pump(timeout=1.0)
    from PyQt6.QtGui import QAction
    acts = [a.text() for a in mw.findChildren(QAction) if "명함" in a.text()]
    # 261117-56: 본 뷰어 도구 탭의 `명함 ▾` 는 없앴다 — '명함 읽기' 는 명함찾기 아래 줄 단추(명함찾기 SOT §5.24.1 '단추')
    from viewer.widgets.bizcard_find_dialog import BizcardFindDialog as _BFD
    _fd = _BFD(mw)
    chk(_fd.act_manage.text() == "명함 읽기" and not any("들이기" in t for t in acts), "F 글자 '명함 읽기'(명함찾기 단추, 옛 '들이기' 없음)",
        "%r %s" % (_fd.act_manage.text(), acts))
    _fd.close()
    mw._action_bizcard_import(str(F))
    dlg = mw._bizcard_dlg
    chk(dlg.windowTitle() == "명함 읽기", "F 창 제목 '명함 읽기'", dlg.windowTitle())
    pump(lambda: dlg._worker is not None, timeout=5)
    reading = not dlg._worker.done_event.is_set()
    mw._action_bizcard_import(str(F))                                    # 261117-13: 두 번 눌러도 창은 하나(읽는 중이어도)
    from viewer.widgets.bizcard_import_dialog import BizcardImportDialog
    vis = [w for w in QApplication.topLevelWidgets() if isinstance(w, BizcardImportDialog) and w.isVisible()]
    chk(mw._bizcard_dlg is dlg and len(vis) == 1, "F 명함 읽기를 다시 눌러도 창은 하나(앞으로 가져옴)", str(len(vis)))
    chk(pump(lambda: dlg.bar.value() == 2, timeout=30), "F 읽는 중에 다시 눌러도 읽기는 이어진다(%s)" % ("읽는 중이었음" if reading else "이미 끝"))
    QTest.keyClick(dlg, Qt.Key.Key_F11)                                  # 명함 창의 F11 — 본 창(발표는 F5)과 겹치지 않는다
    pump(timeout=0.3)
    f11 = dlg.isFullScreen() and not mw.isFullScreen()
    QTest.keyClick(dlg, Qt.Key.Key_F11)
    pump(timeout=0.3)
    chk(f11 and not dlg.isFullScreen(), "F 명함 창 F11 — 그 창만 전체 화면 켬·끔")
    dlg.toggle_full()
    pump(timeout=0.3)
    full = dlg.isFullScreen()
    QTest.keyClick(dlg, Qt.Key.Key_Escape)
    pump(timeout=0.3)
    chk(full and not dlg.isFullScreen() and dlg.isVisible(), "F 전체 화면 ↔ Esc 로 돌아옴(창은 닫히지 않음)")
    chk(bool(dlg.windowFlags() & Qt.WindowType.WindowMaximizeButtonHint), "F 최대화 단추")
    chk(pump(lambda: dlg.bar.value() == 2 and not dlg._pending, timeout=30), "F 배경 인식 끝")
    r0 = next(i for i, it in enumerate(dlg._items) if "홍길동" in it.base)
    r1 = 1 - r0
    chk(dlg.cell(r0, 1) == "나무숲", "F 처음에는 미끼가 1위")
    dlg.table.setCurrentCell(r0, 1)
    pump(timeout=0.3)
    if have_ocr:
        shown = {}

        def fake_confirm(crop, text, fld):                                # 확인 창 — 고른 그림·읽은 글을 받는다
            shown.update(crop=crop, text=text, fld=fld)
            return text
        dlg._confirm_region = fake_confirm
        from PyQt6.QtCore import QTimer as _QT
        _gaps, _last = [], [time.monotonic()]

        def _beat():
            n = time.monotonic(); _gaps.append(n - _last[0]); _last[0] = n
        _hb = _QT(); _hb.timeout.connect(_beat); _hb.start(20)
        def region(rr, box, fld):                                    # 배경에서 읽고 신호로 잇는다(261117-14) — 끝날 때까지 돌린다
            dlg.set_region(rr, box, fld)
            pump(lambda: not dlg.region_busy, timeout=60)
            return dlg.last_region
        dlg.set_region(r0, (0.56, 0.48, 0.86, 0.66), "name")              # 오른쪽 가운데 이름 자리
        busy_now = dlg.region_busy and not dlg.table.isEnabled() and not dlg.btn_apply.isEnabled()
        dlg.set_region(r1, (0.1, 0.1, 0.2, 0.2), "name")                  # 읽는 중 다시 — 받지 않는다
        same_ctx = dlg._region_ctx[0] == r0
        pump(lambda: not dlg.region_busy, timeout=60)
        val = dlg.last_region
        _hb.stop()
        chk(max(_gaps or [0]) < 0.5, "F 자리를 읽는 동안 메인이 멈추지 않는다(배경 — '응답 없음' 결함, 261117-14)",
            "%.2f" % max(_gaps or [0]))
        chk(busy_now and same_ctx and dlg.table.isEnabled() and dlg.btn_apply.isEnabled(),
            "F 읽는 동안 표·[적용]·새 자리를 막고, 끝나면 다시 켠다(재진입 없음)")
        src = dlg._source_image(dlg._items[r0])
        cw, chh = shown["crop"].size
        chk(abs(cw - 0.30 * src.size[0]) <= 2 and abs(chh - 0.18 * src.size[1]) <= 2,
            "F 고른 그림은 그린 상자 그대로(넓히지 않음 — 옆 글자가 들어오던 결함)", "%s vs %s" % (shown["crop"].size, src.size))
        chk(shown.get("text") == "홍길동", "F 확인 창에 고른 그림과 읽은 글", repr(shown.get("text")))
        rd, red = dlg.region_dialog(shown["crop"], "홍길동")
        pm = rd._pic.pixmap()
        chk(pm is not None and not pm.isNull() and red.text() == "홍길동" and red.isEnabled() and not red.isReadOnly(),
            "F 확인 창 — 고른 그림과 고칠 수 있는 글 칸")
        rd.deleteLater()
        chk(val == "홍길동" and dlg.cell(r0, 1) == "홍길동", "F 위치 지정 — 그 자리만 읽어 이름 칸", repr(val))
        st = S.BizcardStore()
        lay = st.layouts()
        st.close()
        chk("d:example.co.kr" in lay and "name" in lay["d:example.co.kr"], "F 같은 회사 양식으로 기억(이 PC DB)", str(list(lay)))
        chk(dlg.cell(r1, 1) == "김철수", "F 같은 회사의 다른 명함은 다시 매겨 이름 자리 후보가 1위",
            dlg.cell(r1, 1))
    else:
        print("SKIP - F 위치 지정 OCR(Tesseract·한글 글꼴 없음)")
    if have_ocr:                                                         # 교정 배우기(§5.15)
        dlg._confirm_region = lambda crop, text, fld: "홍길순"           # 사람이 고침
        region(r0, (0.56, 0.48, 0.86, 0.66), "name")
        st = S.BizcardStore()
        cor = st.corrections()
        st.close()
        chk(cor.get("name", {}).get("홍길동") == "홍길순" and dlg.cell(r0, 1) == "홍길순", "F 고쳐 넣은 글은 교정으로 배운다(이 PC DB)", str(cor))
        dlg._load_learned()
        dlg._confirm_region = lambda crop, text, fld: shown.update(text2=text) or text
        region(r0, (0.56, 0.48, 0.86, 0.66), "name")
        chk(shown.get("text2") == "홍길순", "F 같은 오인식은 다음부터 고친 글을 먼저 보인다", repr(shown.get("text2")))
        dlg._confirm_region = lambda crop, text, fld: None
        chk(region(r0, (0.56, 0.48, 0.86, 0.66), "name") == "" and dlg.cell(r0, 1) == "홍길순", "F 확인 창 [취소] 면 칸을 바꾸지 않는다")
        dlg.set_region(r0, (0.56, 0.48, 0.86, 0.66), "name")              # 읽는 중에 창을 닫으면 결과를 버린다
        dlg._closing = True
        pump(lambda: not dlg.region_busy, timeout=60)
        chk(dlg.last_region is None and dlg.cell(r0, 1) == "홍길순", "F 읽는 중 창을 닫으면 결과를 버린다(칸 그대로)")
        dlg._closing = False
    dlg.set_cell(r0, 2, "예시기술")
    dlg.set_cell(r1, 2, "예시기술")
    pump(timeout=0.2)
    chk([dlg._row_values(i)["company"] for i in (r0, r1)] == ["예시기술", "예시기술"],
        "F 후보 없는 회사 칸에 쓴 값도 읽힌다(빈 풀다운은 거짓 — 261117-9 고침)")
    QTest.mouseClick(dlg.btn_apply, Qt.MouseButton.LeftButton)
    pump(lambda: hasattr(dlg, "applied"), timeout=30)
    st = S.BizcardStore()
    chk(st.domain_map().get("example.co.kr") == "예시기술", "F [적용] 뒤 도메인 → 직장을 배움",
        "%s %s %s" % (st.domain_map(), getattr(dlg, "_apply_box", {}).get("learn_err"), getattr(dlg, "applied", None)))
    chk(len(st.samples()) >= 1, "F 학습 표본이 남는다")
    st.close()
    dlg.close(); pump(timeout=0.5)
    mw.close()

    # ── H. 고른 자리 읽기(261117-14) ──
    print()
    print("=== H. 고른 자리 ===")
    from viewer.widgets.bizcard_import_dialog import pil_to_qimage
    odd = Image.new("RGB", (101, 37), (10, 200, 30))
    odd.putpixel((100, 36), (250, 5, 5))
    qi = pil_to_qimage(odd)
    c1, c2 = qi.pixelColor(0, 0), qi.pixelColor(100, 36)
    chk((c1.red(), c1.green(), c1.blue()) == (10, 200, 30) and (c2.red(), c2.green(), c2.blue()) == (250, 5, 5),
        "H 폭이 4의 배수가 아닌 그림도 어긋나지 않게(사선 무늬 결함)")
    if have_ocr:
        im = Image.new("RGB", (1075, 591), "white")
        dr = ImageDraw.Draw(im)
        dr.text((620, 60), "홍  길  동", font=ImageFont.truetype(KRFONT, 60), fill="black")   # 한 글자씩 띄운 큰 이름
        dr.text((60, 300), "(주)가나다기술", font=ImageFont.truetype(KRFONT, 44), fill="black")
        dr.text((60, 500), "user@example.com", font=ImageFont.truetype(KRFONT, 30), fill="black")
        v1, crop1 = R.read_box(im, (0.56, 0.08, 0.92, 0.24), "name")
        chk(v1 == "홍길동", "H 띄운 큰 이름 자리 → 붙여 읽음", repr(v1))
        v2, _ = R.read_box(im, (0.04, 0.48, 0.50, 0.62), "company")
        chk(v2 == "가나다기술", "H 회사 자리 → 법인 꼴 없이", repr(v2))
        v3, _ = R.read_box(im, (0.04, 0.82, 0.50, 0.92), "email")
        chk(v3 == "user@example.com", "H 메일 자리", repr(v3))
        chk(abs(crop1.size[0] - 0.36 * 1075) <= 2, "H 자른 그림은 그린 상자 그대로", str(crop1.size))
    else:
        print("SKIP - H OCR")

    # ── G ──
    print("\n=== G. 세로로 누운 명함 ===")
    if have_ocr:
        import importlib
        importlib.reload(R)                  # 가짜 인식기를 걷는다
        g = TMP / "rot"; g.mkdir()
        card(g / "다_박영수_1.jpg", "박영수", rot=90)
        res = R.recognize(g / "다_박영수_1.jpg")
        chk(("cell", "010-0000-0001") in res.phones and res.rotated in (90, 270), "G 돌려 읽어 연락처를 찾는다",
            "%s %s" % (res.phones, res.rotated))
    else:
        print("SKIP - G(Tesseract 없음)")
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
