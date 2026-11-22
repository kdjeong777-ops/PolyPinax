# -*- coding: utf-8 -*-
"""명함찾기 — 구분 여러 개·사진 쓸어 넘기기·사진창 비율·해시태그 창 명함 꼴·자동 태그 다시 맞춤·해시태그 메뉴
(명함 SOT §5.24.1 '구분'·§5.24.3 '명함'·'크기 비율'·§5.24.4·§5.5, 261120-49~-54). 가짜 명함만(§2.1), 오프스크린·임시 폴더.

A(-49) 구분 콤보 항목 체크로 여러 개(실제 클릭) — 같은 묶음 또는·묶음끼리 그리고, 펼친 채, 기억(목록)
B(-50) 명함 그림 좌우로 끌어 놓기 = 뒷면, 인물 사진 위 휠 = 다음 사진(썸네일 줄도)
C(-51) 사진창 — 둘 다 있으면 같은 높이, 창이 작고 명함 그림만 있으면 위를 크게, 손잡이를 끌면 비율 기억
D(-52) [해시태그] 창 — 기존 태그 = 지금 목록 명함 태그(찾기 단어 적용), 문서 종류·자동 속성 묶음·[문서 종류] 단추 없음
E(-53) 회사명이 바뀌는 길 — auto_retag·합치기·구글 싱크 '명함 고침' 이 옛 회사 태그를 걷고 새로
F(-54) 목록·탭·사람 칸 오른쪽 메뉴 '해시태그 수정'
"""
import os, sys, tempfile, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QPoint, QPointF
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtTest import QTest
from pathlib import Path
from PIL import Image

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_multi_%d" % os.getpid())
fails = []
TMP = Path(tempfile.mkdtemp(prefix="bizcard_multi_"))
from viewer import settings_store
settings_store._LOCAL_DIR_OVERRIDE = str(TMP / "local")
settings_store._DIR_OVERRIDE = str(TMP / "cfg")
(TMP / "cfg").mkdir()


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
    sys.stdout.flush()
    os._exit(1 if fails else 0)


QMessageBox.exec = lambda self: 0
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)

try:
    from viewer.bizcard import people as P, store as S, gsync as G
    db = TMP / "local" / "bizcard.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    st = S.BizcardStore(db)
    P.apply_import(st, [{"name": "홍가짜", "company": "가나다", "phones": [("cell", "010-0000-0001")], "emails": [], "urls": []},
                        {"name": "Fake Kim", "company": "라마바", "phones": [("cell", "010-0000-0002")], "emails": [], "urls": []}],
                   "주소록", "google")
    ids = [r[0] for r in st.con.execute("SELECT id FROM cards ORDER BY id").fetchall()]
    P.update_card(st, ids[0], {"tags": ["명함", "주소록", "골프"]})
    P.update_card(st, ids[1], {"tags": ["명함", "주소록", "등산"]})
    fold = TMP / "cards" / "정리"
    fold.mkdir(parents=True)
    front, back = fold / "박가짜_가짜상사.jpg", fold / "박가짜_가짜상사_뒷면.jpg"
    Image.new("RGB", (340, 200), "white").save(front)
    Image.new("RGB", (340, 200), "gray").save(back)
    pid = st.upsert({"front": str(front), "back": str(back), "name": "박가짜", "company": "가짜상사", "tags": ["명함", "가짜상사", "한글"]})
    card = P.card_by_id(st, pid)
    pf = P.photo_front(card, "")
    for col in ("red", "blue"):
        src = TMP / (col + ".jpg")
        Image.new("RGB", (120, 160), col).save(src)
        P.save_person_photo(str(src), P.next_photo_path(pf))
    P.fav_init(st, "즐겨찾기")
    g_fav = P.fav_add_group(st, "가짜 모임")
    P.fav_add(st, g_fav, [ids[0], pid], ongoing="…")
    st.close()

    from viewer.widgets import bizcard_find_dialog as FD
    dlg = FD.BizcardFindDialog(None, db=db)
    dlg.show()
    pump(lambda: dlg.table.rowCount() >= 3)
    names = lambda: sorted(c["name"] for c in dlg._rows)

    # ── A ──
    print("=== A. 구분 여러 개 ===")
    cb = dlg.cb_kind
    model = cb.model()

    def click_kind(key):
        cb.showPopup()
        pump(None)
        view = cb.view()
        row = cb.findData(key)
        r = view.visualRect(model.index(row, 0))
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=r.center())
        pump(None)

    click_kind("ko")
    still_open = cb.view().isVisible()
    click_kind("en")
    chk(still_open and sorted(getattr(dlg, "kinds", lambda: [])()) == ["en", "ko"] and names() == ["Fake Kim", "박가짜", "홍가짜"],
        "A 한글+영어(같은 묶음) = 또는, 체크해도 목록은 펼친 채", str((still_open, names())))
    click_kind("en")
    click_kind("photo")
    chk(names() == ["박가짜"], "A 한글+사진 있음(묶음끼리) = 그리고", str(names()))
    cb.hidePopup()
    stv = S.BizcardStore(db)
    chk(sorted(stv.meta_get("find_kind", []) or []) == ["ko", "photo"], "A 고른 구분 기억(목록)", str(stv.meta_get("find_kind")))
    stv.close()
    click_kind("all")
    cb.hidePopup()
    chk(len(dlg._rows) == 3 and getattr(dlg, "kinds", lambda: None)() == ["all"], "A '전체' 를 고르면 나머지를 끔", str(names()))

    # ── B ──
    print("\n=== B. 쓸어 넘기기 ===")
    dlg.resize(1360, 900)
    pump(None)
    dlg._show_card_id(pid) if hasattr(dlg, "_show_card_id") else None
    pump(lambda: dlg._card and dlg._card["id"] == pid)
    pv = dlg.pv
    c0 = pv.rect().center()
    QTest.mousePress(pv, Qt.MouseButton.LeftButton, pos=QPoint(c0.x() + 80, c0.y()))
    QTest.mouseRelease(pv, Qt.MouseButton.LeftButton, pos=QPoint(c0.x() - 80, c0.y()))
    pump(None)
    chk(dlg._side == "back" and os.path.normcase(dlg.shown) == os.path.normcase(str(back)), "B 명함 그림을 왼쪽으로 쓸면 뒷면", str((dlg._side, dlg.shown)))
    first = dlg.photo_shown
    pvw = dlg.photo_view
    ev = QWheelEvent(QPointF(pvw.rect().center()), QPointF(pvw.mapToGlobal(pvw.rect().center())), QPoint(0, 0), QPoint(0, -120),
                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(pvw, ev)
    pump(None)
    chk(first and dlg.photo_shown and dlg.photo_shown != first and dlg.photos.currentRow() == 1,
        "B 인물 사진 위 휠 = 다음 사진(썸네일 줄도)", str((first, dlg.photo_shown, dlg.photos.currentRow())))

    # ── C ──
    print("\n=== C. 사진창 비율 ===")
    sz = dlg.photo_split.sizes()
    chk(abs(sz[0] - sz[1]) <= 4, "C 명함 그림·인물 사진 둘 다 있으면 같은 높이", str(sz))
    for f in P.person_photos(pf):
        os.remove(f)
    dlg._fill_photos()
    dlg.resize(1100, 680)
    pump(None)
    sz = dlg.photo_split.sizes()
    chk(sz[0] > sz[1] * 1.3, "C 창이 작고 명함 그림만 있으면 그림 칸(위)을 크게", str(sz))
    tot = sum(sz)
    dlg.photo_split.moveSplitter(int(tot * 0.3), 1)
    pump(None)
    stv = S.BizcardStore(db)
    saved = stv.meta_get("photo_split", None)
    stv.close()
    dlg.resize(1360, 900)
    pump(None)
    sz2 = dlg.photo_split.sizes()
    chk(saved and saved < 0.5 and abs(sz2[0] / max(1, sum(sz2)) - saved) < 0.03, "C 손잡이를 끌면 비율을 기억하고 자동 비율을 쓰지 않음", str((saved, sz2)))

    # ── D ──
    print("\n=== D. 해시태그 창 — 명함 꼴 ===")
    from viewer.widgets import tag_apply_dialog as TAD
    seen = {}

    def fake_exec(self):
        seen["avail"] = [self.lst_avail.item(i).text().strip() for i in range(self.lst_avail.count())]
        seen["fmt_btn"] = self.btn_format.isVisible()
        return 0
    TAD.TagApplyDialog.exec = fake_exec
    dlg.ed_find.setText("홍가짜")
    pump(lambda: names() == ["홍가짜"])
    dlg.table.selectRow(0)
    pump(None)
    dlg.edit_tags()
    av = seen.get("avail", [])
    chk("문서 종류" not in av and "자동 해시태그 속성" not in av and not seen.get("fmt_btn"),
        "D 문서 종류·자동 속성 묶음·[문서 종류] 단추 없음", str(av[:8]))
    chk("#등산" not in av and "#가짜상사" not in av, "D 기존 태그 = 지금 목록(찾기 단어 적용) 명함의 태그만", str(av))
    dlg.ed_find.clear()
    pump(lambda: len(dlg._rows) == 3)
    dlg.table.selectRow(0)
    dlg.edit_tags()
    av = seen.get("avail", [])
    chk(any(t in av for t in ("#등산", "#가짜상사")), "D 찾기·구분이 없으면 명함 전체의 태그", str(av))

    # ── E ──
    print("\n=== E. 자동 태그 다시 맞춤 ===")
    ar = getattr(P, "auto_retag", None)
    if ar:
        tags, _old = ar(["명함", "(주)가나상사", "한글", "골프"], [{"name": "홍가짜", "company": "(주)가나상사"}], "홍가짜", "다라마")
        chk(tags[:2] == ["명함", "다라마"] and "골프" in tags and "(주)가나상사" not in tags,
            "E auto_retag — 법인 꼴 그대로 붙은 옛 회사 태그도 걷고 새 회사, 사람 태그는 그대로", str(tags))
    else:
        chk(False, "E auto_retag 가 있다")
    mp = P.merge_plan([{"id": 1, "name": "홍가짜", "company": "새회사", "tags": ["명함", "새회사", "한글"], "front": "contact:1", "phones": []},
                       {"id": 2, "name": "홍가짜", "company": "옛회사", "tags": ["명함", "옛회사", "골프"], "front": "contact:2", "phones": []}])
    chk("옛회사" not in mp["fields"]["tags"] and "새회사" in mp["fields"]["tags"] and "골프" in mp["fields"]["tags"],
        "E 합치기 — 남지 않는 회사의 옛 태그는 걷음", str(mp["fields"]["tags"]))
    stx = S.BizcardStore(db)
    cid = ids[1]
    P.update_card(stx, cid, {"tags": ["명함", "라마바", "영어", "등산"]})
    G.init(stx)
    stx.con.execute("INSERT INTO google_link(card_id, resource_name, etag, synced, front) VALUES(?,?,?,?,?)",
                    (cid, "people/x", "e", 0.0, P.card_by_id(stx, cid)["front"]))
    stx.con.commit()

    class _Api:
        def list_people(self):
            return [{"resourceName": "people/x", "etag": "e2", "names": [{"unstructuredName": "Fake Kim"}],
                     "organizations": [{"name": "새가짜사"}], "phoneNumbers": [{"value": "010-0000-0002", "type": "mobile"}]}]
    G.apply(stx, _Api(), [{"kind": G.TO_CARD, "card_id": cid, "rn": "people/x", "fields": ["company"]}])
    t2 = P.card_by_id(stx, cid)["tags"]
    stx.close()
    chk("라마바" not in t2 and "새가짜사" in t2 and "등산" in t2, "E 구글 싱크 '명함을 구글 값으로 고침' 도 회사 태그를 바꿈", str(t2))

    # ── F ──
    print("\n=== F. 해시태그 수정 메뉴 ===")
    menus = []
    QMenu.exec = lambda self, *a, **k: menus.append(self) or None
    texts = lambda m: [a.text() for a in m.actions()] if m else []
    dlg.refresh()
    pump(lambda: len(dlg._rows) == 3)
    dlg.table.selectRow(0)
    dlg._table_menu(dlg.table.visualRect(dlg.table.model().index(0, 0)).center())
    chk("해시태그 수정" in texts(menus[-1] if menus else None), "F 목록 오른쪽 메뉴 '해시태그 수정'", str(texts(menus[-1] if menus else None)))
    tb = dlg.fav_tabs
    ti = next(i for i in range(tb.count()) if tb.tabData(i) == g_fav)
    dlg._fav_tab_menu(tb.tabRect(ti).center())
    chk("해시태그 수정" in texts(menus[-1]), "F 탭 메뉴 '해시태그 수정'", str(texts(menus[-1])))
    tb.setCurrentIndex(ti)
    pump(lambda: dlg.fav.count() >= 2)
    dlg.fav.item(0).setSelected(True)
    dlg._fav_menu(dlg.fav.visualItemRect(dlg.fav.item(0)).center())
    chk("해시태그 수정" in texts(menus[-1]), "F 사람 칸 오른쪽 메뉴 '해시태그 수정'", str(texts(menus[-1])))
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외")
finish()
