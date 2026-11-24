# -*- coding: utf-8 -*-
"""명함 vCard 내보내기·합치기 (구글 싱크 SOT §5.8, P3 · R9·R10) — 가짜 명함만(010-0000-xxxx, 명함 SOT §2.1).

A. 한 장 만들기 — N(성·이름, 두 글자 성, 로마자)·FN 붙여 씀·ORG 회사;부서·TEL 종류·EMAIL·ADR·URL·NOTE(메모·드라이브 폴더/파일·
   검색 주소·영문 한 줄), 이스케이프, 75 바이트 접기(UTF-8 글자 안 자름), CRLF, 영문판은 영문 칸이 주
B. 읽기·합치기 — 되읽기, 접힌 줄·QUOTED-PRINTABLE, 같은 사람(이름 + 전화 숫자, +82 = 0)은 없는 줄만 더함·NOTE 덧붙임·
   다른 줄(PHOTO) 그대로, 이름만 같고 전화 다르면 새 사람, 새 파일 `_합침`(있으면 (2)), 기존 파일 그대로
C. 명함 읽기 창 — `vCard ▾` 메뉴 네 줄(고른 줄 없으면 끔), 메뉴를 눌러(묻는 창은 바꿔 끼움) 파일이 생기고 적용한 명함만·
   빠진 수, 드라이브 폴더 이름이 bizcard.db 에 남음, 합치기 메뉴로 `_합침.vcf`
"""
import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox
from pathlib import Path

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_vcard_%d" % os.getpid())
fails = []
TMP = Path(tempfile.mkdtemp(prefix="bizcard_p3_"))
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
    from viewer.bizcard import vcard as V
except Exception as e:                       # 이 판 전 코드엔 모듈이 없다
    chk(False, "vCard 모듈을 불러온다", repr(e))
    print("FAILURES: %d" % len(fails))
    sys.stdout.flush()
    os._exit(1)
from viewer.bizcard import importer as I, store as S, apply as AP, recognize as R
from viewer import bg_write

CARD = {"name": "홍길동", "company": "가나;다,기술", "dept": "기술연구소", "title": "책임",
        "phones": [["cell", "010-0000-0001"], ["work", "02-0000-0002"], ["fax", "02-0000-0003"]],
        "emails": ["hong@example.com"], "urls": ["www.example.com"],
        "address": "서울특별시 가나구 다라로 123 가나다빌딩 4층 401호 (마바동, 사아자타워) 우편 00000",
        "en": {"name": "Gildong Hong", "title": "Principal", "company": "Ganada Tech"},
        "memo": "첫 메모\n둘째 줄", "front": str(TMP / "정리" / "홍길동_가나다기술.jpg")}

try:
    print("=== A. 한 장 만들기 ===")
    t = V.card_to_vcard(CARD, "명함폴더", "ko", "명함")
    raw = t.split("\r\n")
    chk(t.startswith("BEGIN:VCARD\r\nVERSION:3.0\r\n") and t.endswith("END:VCARD\r\n") and "\n" not in t.replace("\r\n", ""),
        "A 3.0 머리·꼬리, 줄 끝 CRLF")
    chk(all(len(x.encode("utf-8")) <= 75 for x in raw), "A 모든 물리 줄 ≤ 75 바이트(접기)",
        str(max(len(x.encode("utf-8")) for x in raw)))
    chk(any(x.startswith(" ") for x in raw), "A 긴 주소 줄은 접혔다")
    flat = V._unfold(t)
    chk("N:홍;길동;;;" in flat and "FN:홍길동" in flat, "A 한글 이름 N 성;이름·FN 붙여 씀")
    chk("ORG:가나\\;다\\,기술;기술연구소" in flat, "A ORG 회사;부서 + ; , 이스케이프", str([x for x in flat if x.startswith("ORG")]))
    chk("TEL;TYPE=CELL:010-0000-0001" in flat and "TEL;TYPE=WORK:02-0000-0002" in flat and "TEL;TYPE=FAX:02-0000-0003" in flat,
        "A 전화 종류 CELL·WORK·FAX")
    chk("EMAIL;TYPE=INTERNET:hong@example.com" in flat and "URL:www.example.com" in flat and "TITLE:책임" in flat,
        "A EMAIL·URL·TITLE")
    chk(any(x.startswith("ADR;TYPE=WORK:;;서울특별시") and x.endswith(";;;;") for x in flat), "A ADR 거리 칸(접힌 줄 펴서 그대로)")
    note = next(V.parse_line(x)[2] for x in flat if x.startswith("NOTE"))
    nl = note.split("\n")
    chk(nl[:2] == ["첫 메모", "둘째 줄"], "A NOTE 첫머리는 메모(줄바꿈 \\n 이스케이프 되읽기)", str(nl[:2]))
    chk("명함: 명함폴더/홍길동_가나다기술.jpg" in nl, "A NOTE 에 드라이브 폴더/파일 이름(D6)")
    chk(any(x.startswith(V.DRIVE_SEARCH) and "%ED%99%8D" in x for x in nl), "A NOTE 에 드라이브 검색 주소(URL 인코딩)")
    chk(any(x.startswith("English: Gildong Hong · Principal") for x in nl), "A 한국어판은 영문을 NOTE 한 줄로(D5)")
    t0 = V.card_to_vcard(CARD, "", "ko", "명함")
    chk(V.DRIVE_SEARCH not in t0, "A 드라이브 폴더를 비우면 링크 줄 없음")
    te = V._unfold(V.card_to_vcard(CARD, "명함폴더", "en", "Card"))
    chk("FN:Gildong Hong" in te and "N:Hong;Gildong;;;" in te and "TITLE:Principal" in te, "A 영문판은 영문 칸이 주·로마자 성은 끝 낱말")
    chk(any(x.startswith("NOTE") and "Korean: 홍길동" in V.parse_line(x)[2] for x in te), "A 영문판은 한글을 NOTE 한 줄로")
    chk(V.split_name("남궁민수") == ("남궁", "민수") and V.split_name("홍 길동") == ("홍", "길동"), "A 두 글자 성·띄운 이름")
    chk(V.export_text([CARD, dict(CARD, name="")]).count("BEGIN:VCARD") == 1, "A 이름 없는 행은 빼고 여러 장")

    print("\n=== B. 읽기·합치기 ===")
    pc = V.parse_vcf(t)
    chk(len(pc) == 1 and pc[0]["fn"] == "홍길동" and pc[0]["tels"] == {"01000000001", "0200000002", "0200000003"},
        "B 되읽기 — 이름·전화 숫자", str(pc and pc[0]["tels"]))
    qp = "BEGIN:VCARD\r\nVERSION:2.1\r\nFN;CHARSET=UTF-8;ENCODING=QUOTED-PRINTABLE:=ED=99=8D=EA=B8=B8=EB=8F=99\r\nEND:VCARD\r\n"
    chk(V.parse_vcf(qp)[0]["fn"] == "홍길동", "B QUOTED-PRINTABLE 이름 읽기")
    old = ("BEGIN:VCARD\r\nVERSION:3.0\r\nN:홍;길동;;;\r\nFN:홍길동\r\nTEL;TYPE=CELL:+82 10-0000-0001\r\n"
           "EMAIL:old@example.com\r\nPHOTO;ENCODING=b;TYPE=JPEG:AAAA\r\nNOTE:예전 메모\r\nEND:VCARD\r\n"
           "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:김철수\r\nTEL:010-0000-0007\r\nEND:VCARD\r\n")
    other = {"name": "이영희", "company": "라마바", "phones": [["cell", "010-0000-0005"]], "front": "이영희_라마바.jpg"}
    same_name = {"name": "김철수", "company": "사아자", "phones": [["cell", "010-0000-0008"]], "front": "김철수_사아자.jpg"}
    mt, ms = V.merge_text(old, [CARD, other, same_name], "명함폴더", "ko", "명함")
    mc = V.parse_vcf(mt)
    chk(ms["merged"] == 1 and ms["added"] == 2 and len(mc) == 4, "B 같은 사람 1(+82 = 0)·새 사람 2(이름만 같고 전화 다름 포함)",
        "%s / %d" % (ms, len(mc)))
    h = mc[0]
    chk(h["emails"] == {"old@example.com", "hong@example.com"} and "0200000003" in h["tels"], "B 같은 사람 — 없던 메일·팩스만 더함")
    chk(sum(1 for x in h["lines"] if x.startswith("TEL")) == 3, "B 같은 휴대폰은 두 번 넣지 않음(+82 10 = 010)",
        str([x for x in h["lines"] if x.startswith("TEL")]))
    chk(any(x.startswith("PHOTO") for x in h["lines"]), "B 기존 카드의 다른 줄(PHOTO)은 그대로")
    hn = h["note"].split("\n")
    chk(hn[0] == "예전 메모" and "첫 메모" in hn and sum(1 for x in h["lines"] if x.startswith("NOTE")) == 1,
        "B NOTE 는 기존 뒤에 새 줄만 덧붙여 하나로", str(hn[:3]))
    mt2, ms2 = V.merge_text(mt, [CARD], "명함폴더", "ko", "명함")
    chk(ms2["lines"] == 0 and V.parse_vcf(mt2)[0]["note"] == h["note"], "B 한 번 더 합쳐도 늘지 않음", str(ms2))
    ex = TMP / "연락처.vcf"
    ex.write_text(old, encoding="utf-8")
    p1 = V.merged_path(str(ex))
    chk(os.path.basename(p1) == "연락처_합침.vcf", "B 결과 이름 `<이름>_합침.vcf`", p1)
    Path(p1).write_text("x", encoding="utf-8")
    chk(os.path.basename(V.merged_path(str(ex))) == "연락처_합침 (2).vcf", "B 있으면 (2) — 덮어쓰지 않음")
    os.remove(p1)

    print("\n=== C. 명함 읽기 창 ===")
    from PIL import Image

    def jpg(p, color="white"):
        Image.new("RGB", (339, 186), color).save(p, quality=90)
    F = TMP / "cards"
    F.mkdir()
    jpg(F / "가나다_홍길동_1.jpg"); jpg(F / "라마바_김철수_1.jpg", "ivory"); jpg(F / "사아자_이영희_1.jpg", "lightblue")
    db = TMP / "local" / "bizcard.db"
    items = {it.base: it for it in I.scan_folder(F)}
    rows = [{"key": items[b].key, "front": items[b].front, "back": "", "pdf": "", "keep_back": False, "name": n, "company": c,
             "langs": ["한글"], "phones": [("cell", ph)], "emails": [m]}
            for b, n, c, ph, m in (("가나다_홍길동", "홍길동", "가나다", "010-0000-0001", "hong@example.com"),
                                   ("라마바_김철수", "김철수", "라마바", "010-0000-0002", "kim@example.com"))]
    AP.apply_cards(rows, F / "정리", db)          # 둘만 적용, 이영희는 아직

    def fake_recognize(path, ui_lang="ko"):
        hn, hc = R.parse_hint(path)
        return R.CardResult(name=hn or "", company=hc, phones=[("cell", "010-0000-0009")], emails=["user@example.com"],
                            name_cands=[R.Cand(hn or "가짜", 4.0)], company_cands=[R.Cand(hc, 2.0)], langs=("한글",),
                            back_promo=None, need_check=())
    R.recognize = fake_recognize
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    from viewer.widgets import bizcard_import_dialog as BD
    dlg = BD.BizcardImportDialog(str(F), None, db=db)
    dlg.show()
    chk(pump(lambda: dlg.bar.value() == 3, timeout=30), "C 창이 열리고 읽기 끝", str(dlg.bar.value()))
    chk(dlg.btn_vcard.menu() is not None, "C 위 줄에 `vCard ▾` 단추")
    dlg.table.clearSelection()
    dlg._vcard_menu.aboutToShow.emit()
    acts = [a for a in dlg._vcard_menu.actions() if not a.isSeparator()]
    chk(len(acts) == 4 and not acts[0].isEnabled() and acts[1].isEnabled() and "(3" in acts[1].text(),
        "C 메뉴 네 줄 — 고른 줄 없으면 '고른 명함' 끔, '모든 명함 (3장)'", str([a.text() for a in acts]))
    from PyQt6.QtWidgets import QFileDialog, QInputDialog
    outp = TMP / "내보냄.vcf"
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(outp), ""))
    asked = []
    QInputDialog.getText = staticmethod(lambda *a, **k: (asked.append(k.get("text")) or "명함폴더", True))
    acts[1].trigger()                              # '모든 명함 → vCard 파일…'
    bg_write.flush()
    chk(outp.exists(), "C 메뉴를 누르면 vCard 파일이 생김")
    vt = outp.read_bytes().decode("utf-8") if outp.exists() else ""
    chk(vt.count("BEGIN:VCARD") == 2 and "FN:홍길동" in vt and "FN:이영희" not in vt and "\r\n" in vt,
        "C 적용한 명함만(둘), CRLF", str(vt.count("BEGIN:VCARD")))
    chk((dlg.last_vcard or {}).get("skipped") == 1, "C 적용하지 않은 1장은 빠졌다고 셈", str(dlg.last_vcard))
    chk(asked == ["정리"], "C 드라이브 폴더 이름 처음 값 = 정리 폴더 이름", str(asked))
    st = S.BizcardStore(db)
    chk(st.meta_get("drive_folder") == "명함폴더", "C 드라이브 폴더 이름은 bizcard.db 에 남는다")
    st.close()
    chk("명함: 명함폴더/홍길동_가나다.jpg" in V.parse_vcf(vt)[0]["note"] if vt else False, "C NOTE 에 정리본 파일 이름")
    ex2 = TMP / "폰연락처.vcf"
    ex2.write_text("BEGIN:VCARD\r\nVERSION:3.0\r\nFN:홍길동\r\nTEL:010-0000-0001\r\nEND:VCARD\r\n", encoding="utf-8")
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(ex2), ""))
    dlg._vcard_menu.aboutToShow.emit()
    acts = [a for a in dlg._vcard_menu.actions() if not a.isSeparator()]
    acts[3].trigger()                              # '모든 명함을 기존 vCard 에 합치기…'
    bg_write.flush()
    mp = TMP / "폰연락처_합침.vcf"
    chk(mp.exists() and ex2.read_text(encoding="utf-8").count("BEGIN") == 1, "C 합치기 메뉴 — `_합침.vcf` 새 파일, 기존 그대로")
    lv = dlg.last_vcard or {}
    chk(lv.get("merged") == 1 and lv.get("added") == 1, "C 합치기 — 같은 사람 1·새 사람 1", str(lv))
    asked.clear()
    dlg._vcard_menu.aboutToShow.emit()
    [a for a in dlg._vcard_menu.actions() if not a.isSeparator()][1].trigger()
    bg_write.flush()
    chk(asked == ["명함폴더"], "C 다음에는 기억한 드라이브 폴더 이름이 처음 값", str(asked))
    dlg.close()
    pump(timeout=0.5)
except Exception:
    import traceback
    traceback.print_exc()
    fails.append("예외")

print("FAILURES: %d" % len(fails))
for f in fails:
    print("  -", f)
sys.stdout.flush()
os._exit(1 if fails else 0)
