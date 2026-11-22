# -*- coding: utf-8 -*-
"""중복 검토 '명함 사진 삭제' — 고른 사진만 (명함 SOT §5.24.8 '명함 사진 삭제', 261120-65). 가짜 명함·가짜 그림만.

A 메뉴 '명함 사진 삭제' → 창에 앞면·뒷면·인물 사진 썸네일, 체크한 것만(실제 클릭) 휴지통
B 앞면만 지우면 뒷면이 앞면으로 올라감(인물 사진은 그대로), 원본 스캔은 남음
C 인물 사진 하나만 지우면 그것만, 남은 사진 이름 차례대로
D 앞·뒷면을 모두 지우면 그림 없는 명함·원본 스캔도 휴지통
E 구글 짝 명함의 인물 사진을 모두 지우면 다음 싱크에 '구글 연락처 사진 — 지울까요'(처음 꺼짐), 구글 사진을 다시 받지 않음
"""
import os, sys, tempfile, time, copy
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PyQt6.QtCore import QStandardPaths, QCoreApplication, Qt, QPoint
QStandardPaths.setTestModeEnabled(True)             # 검사 작성 SOT §14.7.2
from PyQt6.QtWidgets import QApplication, QMessageBox, QMenu, QDialog
from PyQt6.QtTest import QTest
from pathlib import Path
from PIL import Image

app = QApplication.instance() or QApplication(sys.argv[:1])
QCoreApplication.setApplicationName("polypdf_bizcard_pics_%d" % os.getpid())
TMP = Path(tempfile.mkdtemp(prefix="bizcard_pics_"))
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


def pump(cond=None, timeout=5.0):
    t = time.monotonic()
    while time.monotonic() - t < timeout:
        app.processEvents()
        if cond is not None and cond():
            return True
        if cond is None and time.monotonic() - t > 0.2:
            return True
        time.sleep(0.01)
    return False


def jpg(p, col):
    Image.new("RGB", (340, 200), col).save(p)


try:
    from viewer.bizcard import people as P, store as S, vcard as V, gsync as G
    from viewer.widgets import bizcard_find_dialog as FD
    from viewer.widgets import bizcard_dupe_dialog as DD
    db = TMP / "local" / "bizcard.db"
    st = S.BizcardStore(db)
    st.meta_set(P.KINDS_FIXED_KEY, 1.0)
    fold = TMP / "cards" / "정리"
    fold.mkdir(parents=True)

    def card(name, cell, with_back=True, photos=1):
        orig = TMP / "cards" / ("%s_scan.jpg" % name)
        jpg(orig, "white")
        f, b = fold / ("%s_가짜사.jpg" % name), fold / ("%s_가짜사_뒷면.jpg" % name)
        jpg(f, "white")
        if with_back:
            jpg(b, "gray")
        cid = st.upsert({"front": str(f), "back": str(b) if with_back else "", "src_key": str(orig), "name": name, "company": "가짜사",
                         "phones": [("cell", cell)]})
        pf = P.photo_front(P.card_by_id(st, cid), "")
        for col in ("red", "blue")[:photos]:
            src = TMP / ("%s_%s.jpg" % (name, col))
            Image.new("RGB", (120, 160), col).save(src)
            P.save_person_photo(str(src), P.next_photo_path(pf))
        return cid, orig, f, b
    A = card("가짜가", "010-0000-0001", photos=2)
    B = card("가짜나", "010-0000-0001", photos=1)          # 같은 휴대폰 — 한 묶음
    st.close()

    fd = FD.BizcardFindDialog(None, db=db)
    fd._bz_folder = str(TMP / "cards")
    fd.show()
    pump(lambda: fd.table.rowCount() >= 2)
    dd = fd.open_dupes(exec_=False)
    pump(lambda: bool(dd.groups))
    picked = {}

    def fake_exec(self):                                  # 창 안 체크 칸을 실제로 눌러 고른다
        picked["labels"] = [self.lst.item(i).text() for i in range(self.lst.count())]
        for i in range(self.lst.count()):
            it = self.lst.item(i)
            if it.data(Qt.ItemDataRole.UserRole) in picked.get("want", ()):
                r = self.lst.visualItemRect(it)
                QTest.mouseClick(self.lst.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(r.left() + 10, r.center().y()))   # 체크 칸
        picked["checked"] = [self.lst.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.lst.count())
                             if self.lst.item(i).checkState() == Qt.CheckState.Checked]
        QTest.mouseClick(self.btn_ok, Qt.MouseButton.LeftButton)
        return self.result()
    PD = getattr(DD, "PicturePickDialog", None)
    if PD is not None:
        PD.exec = fake_exec
    menus = []
    QMenu.exec = lambda self, *a, **k: menus.append([x.text() for x in self.actions()])

    def menu_for(cid):
        for i in range(dd.before.topLevelItemCount()):
            top = dd.before.topLevelItem(i)
            for it in [top] + [top.child(j) for j in range(top.childCount())]:
                if it.data(0, Qt.ItemDataRole.UserRole)[1] == cid:
                    dd._menu(dd.before.visualItemRect(it).center())
                    return menus[-1] if menus else []
        return []

    # ── A·B ──
    print("=== A·B. 앞면만 ===")
    acts = menu_for(A[0])
    chk("명함 사진 삭제" in acts, "A 메뉴 '명함 사진 삭제'", str(acts))
    picked["want"] = {"front"}
    ok = dd.delete_pictures(A[0]) if hasattr(dd, "delete_pictures") else False
    pump()
    ca = P.card_by_id(fd._store(), A[0])
    chk(any("앞면" in x for x in picked.get("labels", [])) and any("뒷면" in x for x in picked.get("labels", []))
        and sum("인물" in x for x in picked.get("labels", [])) == 2, "A 창에 앞면·뒷면·인물 사진 둘", str(picked.get("labels")))
    chk(ok and ca and not V.is_contact(ca) and not ca.get("back") and A[2].exists() and not A[3].exists() and A[1].exists(),
        "B 앞면만 지우면 뒷면이 앞면으로(원본 스캔은 남음)", str((ok, ca and ca.get("front"), ca and ca.get("back"), A[3].exists())))
    pf = P.photo_front(ca, str(TMP / "cards")) if ca else ""
    chk(pf and len(P.person_photos(pf)) == 2, "B 인물 사진은 그대로 짝", str(pf))

    # ── C ──
    print("\n=== C. 인물 사진 하나 ===")
    ph = P.person_photos(pf)
    picked["want"] = {ph[0]}
    dd.delete_pictures(A[0])
    pump()
    left = P.person_photos(pf)
    chk(len(left) == 1 and A[2].exists(), "C 고른 인물 사진만 지움", str(left))

    # ── D ──
    print("\n=== D. 앞·뒷면 모두 ===")
    picked["want"] = {"front", "back"}
    dd.delete_pictures(B[0])
    pump(lambda: not B[2].exists())
    cb = P.card_by_id(fd._store(), B[0])
    chk(cb and V.is_contact(cb) and not B[2].exists() and not B[3].exists() and not B[1].exists() and not cb.get("src_key"),
        "D 모두 지우면 그림 없는 명함·원본 스캔도 휴지통", str((cb and cb.get("front"), B[1].exists())))

    # ── E ──
    print("\n=== E. 구글 사진 ===")
    stx = fd._store()
    G.init(stx)
    stx.con.execute("INSERT INTO google_link(card_id, resource_name, etag, synced, front) VALUES(?,?,?,?,?)",
                    (A[0], "people/a", "e", time.time() + 100, P.card_by_id(stx, A[0])["front"]))
    stx.con.commit()
    picked["want"] = set(P.person_photos(pf))
    dd.delete_pictures(A[0])
    pump()
    person = {"resourceName": "people/a", "etag": "e", "names": [{"unstructuredName": "가짜가"}],
              "phoneNumbers": [{"value": "010-0000-0001", "type": "mobile"}], "photos": [{"url": "https://example.com/p.jpg"}],
              "organizations": [{"name": "가짜사"}],
              "metadata": {"sources": [{"type": "CONTACT", "updateTime": "2020-01-01T00:00:00.000Z"}]}}
    rows = [r for r in G.plan(stx, [person], str(TMP / "cards"), photos=True) if r["card_id"] == A[0]]
    kinds = [r["kind"] for r in rows]
    chk(G.PHOTO_DOWN not in kinds and getattr(G, "PHOTO_GONE", "?") in kinds and not G.row_default(rows[kinds.index(G.PHOTO_GONE)]),
        "E 인물 사진을 모두 지운 짝은 '구글 사진 지울까요'(처음 꺼짐)·다시 받지 않음", str(kinds))
    dd.close()
    fd.close()
except Exception:
    import traceback
    traceback.print_exc()
    chk(False, "검사 중 예외")
print("FAILURES: %d" % len(fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
