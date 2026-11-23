# -*- coding: utf-8 -*-
"""명함 DB 살리기 알아보기 — 읽기 전용(어떤 파일도 바꾸지 않는다). 명함 글은 찍지 않고 개수·시각·검사 결과만.

① 명함 DB 폴더의 백업 후보(bizcard.db.dupe_bak·kinds_bak·-wal, '명함 백업_*.zip' 안의 DB)마다 — 성한지·명함 수·마지막으로 고친 때
② 손상된 지금 DB 에서 명함을 id 하나씩 읽어 몇 장을 살릴 수 있는지(id 는 찾기 색인 cards_fts 에서)

사용:  .venv\\Scripts\\python.exe scripts\\bizcard_db_rescue.py      (명함찾기·PolyCardex 는 닫고)
"""
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


def ro(path):
    return sqlite3.connect("file:%s?mode=ro" % str(path).replace("\\", "/"), uri=True)


def when(t):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(t)) if t else "-"


def look(path, label):
    try:
        con = ro(path)
    except sqlite3.Error as e:
        print("  %s: 열기 실패 %s" % (label, e))
        return
    try:
        qc = [r[0] for r in con.execute("PRAGMA quick_check(1)")]
        ok = qc == ["ok"]
        try:
            n, last = con.execute("SELECT count(*), max(updated) FROM cards").fetchone()
        except sqlite3.Error as e:
            n, last = "?", 0
        try:
            full = sum(1 for _ in con.execute("SELECT id FROM cards"))
            scan = "전부 읽힘"
        except sqlite3.Error:
            full, scan = 0, "전부 읽기 실패"
        try:
            h = con.execute("SELECT count(*) FROM card_history").fetchone()[0]
        except sqlite3.Error:
            h = "-"
        print("  %s: %s · 명함 %s장(%s) · 마지막 고친 때 %s · 변경 기록 %s줄" % (
            label, "성함" if ok else "손상(" + qc[0][:60] + ")", n, scan, when(last or 0), h))
    finally:
        con.close()


def main():
    if len(sys.argv) > 1:
        db = Path(sys.argv[1])                          # 검사·다른 자리
    else:
        from viewer.bizcard.store import db_path
        db = Path(db_path())
    d = db.parent
    print("명함 DB 폴더:", d)
    print("\n① 백업 후보")
    for p in sorted(d.iterdir(), key=lambda x: x.stat().st_mtime):
        if p.name.startswith("bizcard.db") or p.name.startswith("bizcard.") or p.name.startswith("명함 백업_"):
            print("- %s · %d 바이트 · 파일 시각 %s" % (p.name, p.stat().st_size, when(p.stat().st_mtime)))
    for p in sorted(d.iterdir(), key=lambda x: x.stat().st_mtime):
        if p.suffix in (".dupe_bak", ".kinds_bak") or p.name.endswith("_bak"):
            look(p, p.name)
        elif p.name.startswith("명함 백업_") and p.suffix == ".zip":
            tmp = Path(tempfile.mkdtemp(prefix="pcx_chk_"))
            try:
                with zipfile.ZipFile(p) as z, z.open("bizcard.db") as src, open(tmp / "bizcard.db", "wb") as out:
                    shutil.copyfileobj(src, out)
                look(tmp / "bizcard.db", p.name + " 안의 DB")
            except Exception as e:                      # noqa: BLE001
                print("  %s: zip 읽기 실패 %s" % (p.name, type(e).__name__))
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
    print("\n③ 다른 자리의 명함 DB(설치판 앱 전용 사본·옛 설정 폴더)")
    la = Path(os.environ.get("LOCALAPPDATA", ""))
    others = []
    if la.is_dir():
        others += list(la.glob("Packages/*/LocalCache/Local/*/bizcard.db"))
        others += [la / n / "bizcard.db" for n in ("PolyPDF", "PolyPinax", "PolyCardex")]
    seen = {os.path.normcase(str(db))}
    for p in others:
        if p.is_file() and os.path.normcase(str(p)) not in seen:
            seen.add(os.path.normcase(str(p)))
            print("- %s · %d 바이트 · 파일 시각 %s" % (p, p.stat().st_size, when(p.stat().st_mtime)))
            look(p, "그 DB")
            try:
                c2 = ro(p)
                has = {r[0] for r in c2.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                print("    구글 짝 표 %s · 변경 기록 표 %s" % ("있음" if "google_link" in has else "없음",
                                                     "있음" if "card_history" in has else "없음"))
                c2.close()
            except sqlite3.Error as e:
                print("    표 목록 실패", type(e).__name__)
    if len(seen) == 1:
        print("  (다른 자리에 명함 DB 없음)")
    print("\n② 지금 DB 에서 한 장씩 살리기")
    con = ro(db)
    try:
        ids = [r[0] for r in con.execute("SELECT rowid FROM cards_fts")]
    except sqlite3.Error as e:
        print("  찾기 색인 id 읽기 실패:", e)
        ids = []
    ok = bad = none = 0
    for i in ids:
        try:
            r = con.execute("SELECT * FROM cards WHERE id=?", (i,)).fetchone()
            if r is None:
                none += 1
            else:
                ok += 1
        except sqlite3.Error:
            bad += 1
    print("  찾기 색인의 명함 %d장 — 읽힘 %d · 손상 %d · 없음 %d" % (len(ids), ok, bad, none))
    for t in ("contact_src", "google_link", "kakao_block", "fav_members", "todo_notes", "recent", "meta"):
        try:
            print("  %-12s %d줄 읽힘" % (t, sum(1 for _ in con.execute('SELECT * FROM "%s"' % t))))
        except sqlite3.Error as e:
            print("  %-12s 읽기 실패 %s" % (t, type(e).__name__))
    con.close()


if __name__ == "__main__":
    main()
