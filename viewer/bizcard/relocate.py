"""명함 폴더를 다른 폴더로 이전 (명함 SOT §5.12, 사용자 지시·결정 '폴더 통째').

폴더 안의 모든 것(원본 그림·PDF·정리·인물 사진)을 새 자리로 옮기고, 명함 DB(`bizcard.db`)의 경로를 새 자리로 바꾼다.
해시태그·검색 색인 등 앱 상태는 돌려준 `(옛 경로, 새 경로)` 짝으로 메인이 한 길(`filesRelocated`)·`TagStore.rehome` 으로 고친다.
- 같은 이름이 새 자리에 있으면 **아무것도 옮기지 않고** 멈춘다(덮어쓰지 않는다).
- 새 자리가 원래 폴더 안이면 거절한다.
- 같은 드라이브이고 새 자리가 없으면 폴더 이름 바꾸기 한 번(빠르고 원자적), 아니면 파일마다 옮긴다(배경).
★ 명함 글·경로는 로그·예외 메시지에 싣지 않는다(§2.1) — 예외는 종류만.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path


class RelocateError(Exception):
    """사람에게 보일 까닭 코드 — 'same'·'inside'·'missing'·'exists'·'notempty'."""


class RelocateCancelled(Exception):
    pass


def _files(root: Path) -> list:
    out = []
    for dp, dns, fns in os.walk(root):
        for f in fns:
            p = Path(dp) / f
            out.append(p.relative_to(root))
    return sorted(out)


def check(src, dst) -> list:
    """옮기기 전 검사 — 문제가 없으면 옮길 상대 경로 목록, 있으면 RelocateError."""
    src, dst = Path(src).resolve(), Path(dst).resolve()
    if not src.is_dir():
        raise RelocateError("missing")
    if os.path.normcase(str(src)) == os.path.normcase(str(dst)):
        raise RelocateError("same")
    if os.path.normcase(str(dst)).startswith(os.path.normcase(str(src)) + os.sep):
        raise RelocateError("inside")
    rels = _files(src)
    if dst.exists():
        if not dst.is_dir():
            raise RelocateError("exists")
        clash = [r for r in rels if (dst / r).exists()]
        if clash:
            raise RelocateError("exists")
    return rels


def move_folder(src, dst, progress=None) -> list:
    """폴더 통째 옮기기 → [(옛 경로, 새 경로)] 파일 짝. `progress(했음, 전체)` 가 False 면 멈춤(옮긴 것은 남는다)."""
    src, dst = Path(src).resolve(), Path(dst).resolve()
    rels = check(src, dst)
    pairs = [(str(src / r), str(dst / r)) for r in rels]
    same_drive = os.path.splitdrive(str(src))[0].lower() == os.path.splitdrive(str(dst))[0].lower()
    if not dst.exists() and same_drive:
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.rename(str(src), str(dst))                  # 한 번에(원자적)
        if progress is not None:
            progress(len(rels), len(rels))
        return pairs
    made_dst = not dst.exists()
    dst.mkdir(parents=True, exist_ok=True)
    done = []
    try:
        for i, r in enumerate(rels):
            if progress is not None and progress(i, len(rels)) is False:
                raise RelocateCancelled()
            s, d = src / r, dst / r
            d.parent.mkdir(parents=True, exist_ok=True)
            if d.exists():                             # 그 사이 생겼으면 건너뛴다(덮어쓰지 않는다)
                continue
            shutil.move(str(s), str(d))
            done.append((str(s), str(d)))
    except BaseException:
        # ★ 중간에 멈추거나 실패하면 옮긴 것을 되돌린다 — 일부만 옮겨진 채(DB·태그는 옛 자리) 남지 않게(전부 아니면 무)
        for s, d in reversed(done):
            try:
                Path(s).parent.mkdir(parents=True, exist_ok=True)
                shutil.move(d, s)
            except Exception:
                pass
        for dp, dns, fns in sorted(os.walk(dst), key=lambda t: -len(t[0])):
            if made_dst or dp != str(dst):
                try:
                    os.rmdir(dp)
                except OSError:
                    pass
        raise
    for dp, dns, fns in sorted(os.walk(src), key=lambda t: -len(t[0])):     # 빈 폴더만 지운다(아래부터)
        try:
            os.rmdir(dp)
        except OSError:
            pass
    if progress is not None:
        progress(len(rels), len(rels))
    return done


def relocate_db(store, src, dst) -> int:
    """명함 DB 의 경로(사람 행·인식 캐시·학습 표본 열쇠)를 옛 폴더 → 새 폴더로. 반환 = 고친 행 수."""
    a = os.path.normcase(os.path.abspath(str(src)))
    b = os.path.normcase(os.path.abspath(str(dst)))
    raw_a, raw_b = os.path.abspath(str(src)), os.path.abspath(str(dst))

    def sub(v, norm=True):
        if not v:
            return v
        x, y = (a, b) if norm else (raw_a, raw_b)
        vv = os.path.normcase(v) if not norm else v
        if norm:
            return y + v[len(x):] if v == x or v.startswith(x + os.sep) else v
        return raw_b + v[len(raw_a):] if vv == os.path.normcase(raw_a) or vv.startswith(os.path.normcase(raw_a) + os.sep) else v

    n = 0
    con = store.con
    for r in con.execute("SELECT id, front, back, src_key, src_pdf FROM cards").fetchall():
        nv = (sub(r["front"]), sub(r["back"]), sub(r["src_key"]), sub(r["src_pdf"], norm=False))
        if nv != (r["front"], r["back"], r["src_key"], r["src_pdf"]):
            con.execute("UPDATE cards SET front=?, back=?, src_key=?, src_pdf=? WHERE id=?", nv + (r["id"],))
            n += 1
    for tbl in ("recog", "samples"):
        for r in con.execute("SELECT src_key FROM %s" % tbl).fetchall():
            nk = sub(r["src_key"])
            if nk != r["src_key"]:
                con.execute("DELETE FROM %s WHERE src_key=?" % tbl, (nk,))
                con.execute("UPDATE %s SET src_key=? WHERE src_key=?" % tbl, (nk, r["src_key"]))
                n += 1
    con.commit()
    return n
