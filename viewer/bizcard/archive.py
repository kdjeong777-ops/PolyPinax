# -*- coding: utf-8 -*-
"""명함 자료 옮기기 zip (명함찾기 SOT §5.31, 261120-73) — Qt 없음, 배경 일꾼이 부른다.

담는 것: 명함 DB 일관된 사본(SQLite 백업 API) · 정리본 앞·뒷면 · 인물 사진 · manifest.json.
원본 스캔·원본 PDF·로그인 토큰·클라이언트 보안 비밀·사진 대기열은 담지 않는다.
불러오기: 판 확인 → 바꾸기(지금 것을 먼저 같은 꼴 zip 으로 백업) 또는 합치기(없는 명함만), 경로는 이 PC 의 명함 폴더로 바꿔 적는다.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3

from viewer import dbutil
import tempfile
import time
import zipfile
from pathlib import Path

FORMAT = "polycardex-zip"
VERSION = 1
OUTSIDE = "가져온 명함"                             # 명함 폴더 밖에 있던 정리본·인물 사진을 모으는 자리(그 아래 정리·인물)
DROP_META = ("gsync_client_secret", "gsync_media_queue", "gsync_failed")   # 그 PC 의 비밀·일 — 담지 않는다
PATH_COLS = ("front", "back", "src_key")
BACKUP_KEEP = 3                                    # 바꾸기 전 백업 zip — 최근 이만큼만 남기고 예전 것은 휴지통(261120-78, 사용자 결정)
BACKUP_GLOB = "명함 백업_*.zip"


class ArchiveError(Exception):
    """zip 을 쓸 수 없음 — what = 'format'|'version'|'schema'|'empty'|'folder'|'partial'(도중에 멈춤 — backup = 바꾸기 전 백업)."""

    def __init__(self, what: str, backup: str = ""):
        super().__init__(what)
        self.what = what
        self.backup = backup


def _norm(p) -> str:
    return os.path.normcase(os.path.abspath(str(p)))


def _copy_db(src, dst) -> None:
    a = dbutil.connect(str(src), row_factory=False)
    b = dbutil.connect(str(dst), row_factory=False)
    try:
        a.backup(b)
    finally:
        b.close()
        a.close()


def _arc_for(path: str, folder: str, kind: str) -> str:
    """파일의 zip 안 이름 — 명함 폴더 안이면 상대 경로, 밖이면 '가져온 명함/정리|인물/이름'."""
    if folder:
        try:
            rel = os.path.relpath(_norm(path), _norm(folder))
            if not rel.startswith(".."):
                return "files/" + rel.replace("\\", "/")
        except ValueError:
            pass
    return "files/%s/%s/%s" % (OUTSIDE, kind, os.path.basename(path))


def _card_files(store, folder: str) -> list:
    """[(실제 경로, zip 이름)] — 정리본 앞·뒷면(그림 명함)·인물 사진(그림 없는 명함 포함)."""
    from viewer.bizcard import people as P
    from viewer.bizcard.vcard import is_contact
    from viewer.bizcard.importer import OUT_DIR
    out, seen = [], set()

    def add(p, kind):
        if p and os.path.isfile(p) and _norm(p) not in seen:
            seen.add(_norm(p))
            out.append((os.path.realpath(p), _arc_for(p, folder, kind)))
    for r in store.con.execute("SELECT * FROM cards").fetchall():
        c = store._row(r)
        if not is_contact(c):
            add(c.get("front") or "", OUT_DIR)
            add(c.get("back") or "", OUT_DIR)
        pf = P.photo_front(c, folder)
        for ph in (P.person_photos(pf) if pf else []):
            add(ph, P.PEOPLE_DIR)
    return out


def export_zip(db_path, folder: str, out_zip, progress=None) -> dict:
    """내보내기 — 반환 {'cards', 'files', 'path'}."""
    from viewer.bizcard.store import BizcardStore, SCHEMA_VER
    tmp = Path(tempfile.mkdtemp(prefix="pcx_out_"))
    try:
        dbc = tmp / "bizcard.db"
        _copy_db(db_path, dbc)
        con = dbutil.connect(str(dbc), row_factory=False)
        try:
            con.executemany("DELETE FROM meta WHERE k=?", [(k,) for k in DROP_META])
            con.commit()
        except sqlite3.OperationalError:
            pass
        finally:
            con.close()
        st = BizcardStore(dbc)
        try:
            files = _card_files(st, folder)
            n_cards = st.con.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        finally:
            st.close()
        mapping = {_norm(p): arc for p, arc in files}
        man = {"format": FORMAT, "version": VERSION, "schema": SCHEMA_VER, "created": time.strftime("%Y-%m-%d %H:%M:%S"),
               "folder": _norm(folder) if folder else "", "cards": n_cards, "map": mapping}
        out_zip = Path(out_zip)
        part = out_zip.with_name(out_zip.name + ".part")
        total = len(files) + 1
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps(man, ensure_ascii=False, indent=1))
            z.write(dbc, "bizcard.db")
            if progress:
                progress(1, total)
            for i, (p, arc) in enumerate(files):
                z.write(p, arc, compress_type=zipfile.ZIP_STORED)   # JPG 는 이미 눌려 있다
                if progress:
                    progress(i + 2, total)
        os.replace(part, out_zip)
        return {"cards": n_cards, "files": len(files), "path": str(out_zip)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _safe_rel(arc) -> str:
    """zip 안 이름 → 명함 폴더 기준 상대 경로. 'files/' 로 시작하지 않거나 '..'·절대 경로·드라이브가 있으면 ArchiveError('format')
    — 만든 zip 하나로 명함 폴더 밖에 쓰지 못하게(zip slip, 261120-78)."""
    a = str(arc or "")
    if not a.startswith("files/") or "\\" in a:
        raise ArchiveError("format")
    rel = a[len("files/"):]
    parts = rel.split("/")
    if not rel or rel.startswith("/") or ":" in rel or any(x in ("", ".", "..") for x in parts):
        raise ArchiveError("format")
    return rel.replace("/", os.sep)


def _inside(folder, rel) -> Path:
    """명함 폴더 안의 실제 경로 — resolve 뒤에도 폴더 안이 아니면 ArchiveError('format')."""
    base = Path(folder).resolve()
    dst = (base / rel).resolve()
    if dst != base and base not in dst.parents:
        raise ArchiveError("format")
    return dst


def read_manifest(zip_path) -> dict:
    """판 확인 — 꼴이 다르거나 판·스키마가 이 프로그램보다 크면 ArchiveError."""
    from viewer.bizcard.store import SCHEMA_VER
    try:
        with zipfile.ZipFile(zip_path) as z:
            man = json.loads(z.read("manifest.json").decode("utf-8"))
            names = set(z.namelist())
    except (KeyError, zipfile.BadZipFile, ValueError, OSError):
        raise ArchiveError("format")
    if man.get("format") != FORMAT or "bizcard.db" not in names:
        raise ArchiveError("format")
    if int(man.get("version") or 0) > VERSION:
        raise ArchiveError("version")
    if int(man.get("schema") or 0) > SCHEMA_VER:
        raise ArchiveError("schema")
    mp = man.get("map") or {}
    if not isinstance(mp, dict):
        raise ArchiveError("format")
    for arc in mp.values():                               # 이름을 모두 먼저 본다 — 하나라도 위험하면 아무것도 풀지 않음
        _safe_rel(arc)
        if arc not in names:
            raise ArchiveError("format")
    return man


def _rebase_db(dbp, man: dict, folder: str) -> dict:
    """사본 DB 의 경로 칸을 새 명함 폴더로 — {옛 경로(소문자): 새 경로(소문자)}."""
    new = {old: os.path.normcase(str(_inside(folder, _safe_rel(arc)))) for old, arc in man.get("map", {}).items()}
    oldf = man.get("folder") or ""
    con = dbutil.connect(str(dbp), row_factory=False)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(cards)")}
        use = [c for c in PATH_COLS if c in cols]
        for row in con.execute("SELECT id, %s FROM cards" % ", ".join(use)).fetchall():
            ch = {}
            for c, v in zip(use, row[1:]):
                if not v or str(v).startswith("contact:"):
                    continue
                k = os.path.normcase(str(v))
                if k in new:
                    ch[c] = new[k]
                elif oldf and k.startswith(oldf + os.sep):          # 담지 않은 원본(원본 열쇠 등) — 같은 상대 자리로
                    ch[c] = os.path.normcase(os.path.join(folder, k[len(oldf) + 1:]))
            if ch:
                con.execute("UPDATE cards SET %s WHERE id=?" % ", ".join('"%s"=?' % c for c in ch), list(ch.values()) + [row[0]])
        con.executemany("DELETE FROM meta WHERE k=?", [(k,) for k in DROP_META])
        con.commit()
    finally:
        con.close()
    return new


def _extract(z, man: dict, folder: str, only=None, overwrite=True, progress=None, base=0, total=0) -> int:
    n = 0
    arcs = [a for a in man.get("map", {}).values() if only is None or a in only]
    for i, arc in enumerate(arcs):
        dst = _inside(folder, _safe_rel(arc))
        if dst.exists() and not overwrite:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        with z.open(arc) as src, open(dst, "wb") as out:
            shutil.copyfileobj(src, out)
        n += 1
        if progress:
            progress(base + i + 1, total)
    return n


def import_zip(zip_path, db_path, folder: str, mode: str = "replace", backup_dir=None, progress=None) -> dict:
    """불러오기 — mode 'replace'(지금 것을 백업 zip 으로 둔 뒤 교체) | 'merge'(없는 명함만 더함).
    부르는 쪽은 그 DB 의 다른 연결을 먼저 닫는다. 반환 {'cards', 'files', 'backup', 'new_ids'}."""
    if not folder:
        raise ArchiveError("folder")
    man = read_manifest(zip_path)
    tmp = Path(tempfile.mkdtemp(prefix="pcx_in_"))
    try:
        with zipfile.ZipFile(zip_path) as z:
            dbp = tmp / "bizcard.db"
            with z.open("bizcard.db") as src, open(dbp, "wb") as out:
                shutil.copyfileobj(src, out)
            new = _rebase_db(dbp, man, folder)
            total = len(man.get("map", {})) + 2
            backup = ""
            if mode == "replace":
                if Path(db_path).exists():
                    bdir = Path(backup_dir or Path(db_path).parent)
                    bpath = bdir / ("명함 백업_%s.zip" % time.strftime("%y%m%d-%H%M%S"))
                    export_zip(db_path, folder, bpath)
                    backup = str(bpath)
                    prune_backups(bdir)
                if progress:
                    progress(1, total)
                try:
                    nf = _extract(z, man, folder, progress=progress, base=1, total=total)
                    _copy_db(dbp, db_path)                   # 열린 파일을 바꿔치지 않고 백업 API 로 내용을 덮는다
                except Exception:
                    raise ArchiveError("partial", backup)     # 도중에 멈춤 — 그림 일부가 바뀌었을 수 있다(백업은 있음)
                con = dbutil.connect(str(db_path), row_factory=False)
                n = con.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
                con.close()
                if progress:
                    progress(total, total)
                return {"cards": n, "files": nf, "backup": backup, "new_ids": []}
            try:
                return _merge(z, man, dbp, db_path, folder, new, progress, total)
            except ArchiveError:
                raise
            except Exception:
                raise ArchiveError("partial")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def prune_backups(bdir, keep: int = BACKUP_KEEP) -> int:
    """바꾸기 전 백업 zip — 최근 keep 개만 남기고 예전 것은 휴지통으로(없으면 그대로). 반환 = 보낸 수."""
    try:
        files = sorted(Path(bdir).glob(BACKUP_GLOB), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return 0
    n = 0
    for p in files[keep:]:
        try:
            from send2trash import send2trash
            send2trash(str(p))
            n += 1
        except Exception:
            pass
    return n


def _merge(z, man, dbp, db_path, folder, new, progress, total) -> dict:
    """합치기 — 지금 DB 에 같은 정리본(또는 같은 원본 열쇠)이 없는 명함만 새 id 로 더하고 그 명함의 파일만 푼다(있는 파일은 두고)."""
    from viewer.bizcard.store import BizcardStore
    inv = {v: k for k, v in new.items()}
    arc_of = man.get("map", {})
    src = dbutil.connect(str(dbp))
    st = BizcardStore(db_path)
    new_ids, need = [], set()
    try:
        from viewer.bizcard import people as _P, gsync as _G
        _P.src_init(st)
        _G.init(st)
        have = {os.path.normcase(str(r[0])) for r in st.con.execute("SELECT front FROM cards") if r[0]}
        have |= {os.path.normcase(str(r[0])) for r in st.con.execute("SELECT src_key FROM cards") if r[0]}
        cols = [r[1] for r in st.con.execute("PRAGMA main.table_info(cards)")]
        for r in src.execute("SELECT * FROM cards ORDER BY id").fetchall():
            d = {k: r[k] for k in r.keys()}
            f = os.path.normcase(str(d.get("front") or ""))
            if f and (f in have or (d.get("src_key") and os.path.normcase(str(d["src_key"])) in have)):
                continue
            vals = {c: d[c] for c in cols if c in d and c != "id"}
            cur = st.con.execute("INSERT INTO cards(%s) VALUES(%s)" % (", ".join('"%s"' % k for k in vals), ", ".join("?" * len(vals))),
                                 list(vals.values()))
            nid = cur.lastrowid
            fresh = st._row(st.con.execute("SELECT * FROM cards WHERE id=?", (nid,)).fetchone())
            st.con.execute("INSERT INTO cards_fts(rowid, body) VALUES(?,?)", (nid, st._body(fresh)))
            new_ids.append(nid)
            have.add(f)
            # 칸 출처·카톡 표시도 새 id 로(261120-78 — '#' 판정의 구글 흔적·'구글에 이미 있을 수 있음' 을 잃지 않게). 구글 짝은 옮기지 않음
            for tbl in ("contact_src", "kakao_block"):
                try:
                    rows_ = src.execute("SELECT * FROM %s WHERE card_id=?" % tbl, (d["id"],)).fetchall()
                except sqlite3.OperationalError:
                    continue
                dcols = [r[1] for r in st.con.execute("PRAGMA main.table_info(%s)" % tbl)]
                for rr in rows_:
                    vals = {k: rr[k] for k in rr.keys() if k in dcols}
                    vals["card_id"] = nid
                    st.con.execute("INSERT OR REPLACE INTO %s(%s) VALUES(%s)" % (tbl, ", ".join('"%s"' % k for k in vals), ", ".join("?" * len(vals))),
                                   list(vals.values()))
            for c in ("front", "back"):
                old = inv.get(os.path.normcase(str(d.get(c) or "")))
                if old in arc_of:
                    need.add(arc_of[old])
        st.con.commit()
        from viewer.bizcard import people as P
        for nid in new_ids:                                  # 그 명함의 인물 사진도(이름 규칙 — 같은 정리본 이름)
            c = P.card_by_id(st, nid)
            pf = P.photo_front(c, folder)
            if pf:
                stem = Path(pf).stem.lower()
                for old, arc in arc_of.items():
                    if "/%s/" % P.PEOPLE_DIR in "/" + arc and Path(arc).stem.lower().split(" (")[0] == stem:
                        need.add(arc)
    finally:
        st.close()
        src.close()
    nf = _extract(z, man, folder, only=need, overwrite=False, progress=progress, base=1, total=total)
    if progress:
        progress(total, total)
    return {"cards": len(new_ids), "files": nf, "backup": "", "new_ids": new_ids}
