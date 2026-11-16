# -*- coding: utf-8 -*-
"""261116-13(사진 보기 SOT §4.47, 사용자 지시·결정): 2단 칸 고르기 — 보기 탭 `2단` ▾ `PDF`·`PIX`·`스크린샷`.

▾ 항목은 **오른쪽(2단) 칸에 무엇을** 띄울지다. 왼쪽 칸과 창의 모드(사진 SOT D1)는 그대로.
- 같은 종류(PDF 모드의 `PDF`·사진 모드의 `PIX`) = 종전 2단(본체 `_vm_split`·`Ctrl+Shift+2` 와 같다).
- 다른 종류 = **섞은 2단**: 아래 책갈피창만 그 종류의 목록, 오른쪽 칸은 **보기 중심**(리본·검색·색인은 창 모드 그대로),
  처음은 그 모드의 마지막 자리, 썸네일 칸은 활성 창 따라. 섞은 칸 우클릭 = 그 모드로 보기(창 모드를 바꿔 1단에).
- `스크린샷` = 스크린샷 띠의 지금 컷을 누른 것과 같은 길(스크린샷 SOT §5).
상태는 이 실행 동안만(`_mix_on`) — 설정 파일에 남기지 않는다.
261116-17 되돌아오기: 2단을 닫을 때 오른쪽 칸(종류·파일·쪽)을 기억(`_split_last`), 1단에서 2단으로 돌아오면 되살린다.
"""
from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtWidgets import QMenu

from viewer.history import HistoryItem
from viewer.i18n import tr

KINDS = ("pdf", "pix", "shot")


class SplitKindMixin:
    # ── 상태 ──────────────────────────────────────────────
    def _mix_on_now(self) -> bool:
        """섞은 2단(오른쪽 칸만 창 모드와 다른 종류)인가."""
        return bool(self.__dict__.get("_mix_on")) and bool(getattr(self, "_split_on", False))

    def _mix_pane(self, pane) -> bool:
        return pane == 1 and self._mix_on_now()

    def _pane_photo_kind(self, pane=None) -> bool:
        """그 창이 사진 종류인가 — 창 모드, 섞은 칸이면 그 반대."""
        if pane is None:
            pane = getattr(self, "_active_pane", 0)
        photo = bool(getattr(self, "_photo_mode", False))
        return (not photo) if self._mix_pane(pane) else photo

    def _split_kind_now(self):
        """지금 오른쪽 칸 종류 — 'pdf'·'pix'·'shot', 1단이면 None."""
        if not getattr(self, "_split_on", False):
            return None
        try:
            if self.bookmark_tree_right.in_shot_list():
                return "shot"
        except AttributeError:
            pass
        return "pix" if self._pane_photo_kind(1) else "pdf"

    # ── 보기 탭 `2단` ▾ ────────────────────────────────────
    def _split_menu_install(self, act) -> None:
        """`2단` 액션에 ▾ 메뉴 — 리본은 `ribbonSplit` 이면 분할 단추(본체 = 종전 2단, 디자인 SOT §2.9.5)."""
        m = QMenu(self)
        m.setObjectName("split_kind_menu")
        self._split_kind_acts = {}
        for kind, label in (("pdf", tr("PDF")), ("pix", tr("PIX")), ("shot", tr("스크린샷"))):
            a = m.addAction(label)
            a.setCheckable(True)
            a.setObjectName("split_kind_" + kind)
            a.triggered.connect(lambda _checked=False, k=kind: self._split_pick(k))
            self._split_kind_acts[kind] = a
        m.aboutToShow.connect(self._split_menu_sync)
        act.setMenu(m)
        act.setProperty("ribbonSplit", True)

    def _split_menu_sync(self) -> None:
        now = self._split_kind_now()
        acts = self.__dict__.get("_split_kind_acts") or {}
        for k, a in acts.items():
            a.setChecked(k == now)
        if "pix" in acts:
            acts["pix"].setEnabled(bool(getattr(self, "_photo_mode", False)) or self._photo_enabled())

    def _split_pick(self, kind: str) -> None:
        if kind != "shot" and self._split_restore(want=kind):   # 261116-17: 1단에서 같은 종류를 고르면 되살림
            return
        if kind == "shot":
            self._split_show_shot()
            return
        if (kind == "pix") == bool(getattr(self, "_photo_mode", False)):
            self._split_same()
        else:
            self._mix_enter()

    def _split_body(self) -> None:
        """본체·`Ctrl+Shift+2` — 종전 2단(사용자 결정 '본체는 늘 종전 2단'). 섞은 2단이면 같은 종류로 돌아온다.
        1단에서 누르면 닫기 전 오른쪽 칸을 되살린다(261116-17 '되돌아오기')."""
        if self._mix_on_now():
            self._split_same()
            return
        if not getattr(self, "_split_on", False):
            self._split_return()
            return
        self.act_split.setChecked(True)

    # ── 되돌아오기 — 2단 → 1단 → 2단 (261116-17, 사진 보기 SOT §4.47) ──
    def _split_remember(self) -> None:
        """2단을 닫기 직전(`_toggle_split(False)` 맨 앞) — 오른쪽 칸의 종류·파일·쪽·폴더. 이 실행 동안만."""
        try:
            kind = self._split_kind_now()
            mv = self._mv[1]
            if kind == "shot":
                f, pg = self.__dict__.get("_current_shot_path"), 0
            else:
                f = mv.current_file()
                pg = (mv.current_page() or 0) if (f and kind == "pdf") else 0
        except Exception:
            return
        if not kind or not f:
            return
        self._split_last = {"kind": kind, "file": str(f), "page": int(pg or 0),
                            "folder": self.__dict__.get("_folder_right")}

    def _split_return(self) -> None:
        """1단 → 2단(본체·`Ctrl+Shift+2`·우클릭 `2단 보기`·옆 패널 닫기) — 기억이 있으면 되살리고, 없으면 종전 2단."""
        if not self._split_restore():
            self.act_split.setChecked(True)

    def _split_restore(self, want=None) -> bool:
        """기억한 오른쪽 칸을 되살린다 — 되살렸으면 True. `want` 는 ▾ 로 고른 종류(다르면 되살리지 않는다)."""
        if getattr(self, "_split_on", False):
            return False
        rec = self.__dict__.get("_split_last") or {}
        kind, f = rec.get("kind"), rec.get("file")
        if kind not in KINDS or not f or (want is not None and want != kind):
            return False
        if kind == "shot":
            ss = getattr(self, "shot_strip", None)
            i = ss.index_of_path(f) if ss is not None else -1
            if i < 0:
                return False
            self._mix_leave()
            ss.activate_index(i)                         # 컷을 누른 것과 같은 길(스크린샷 SOT §5)
            return True
        photo = kind == "pix"
        if not os.path.isfile(f) or not self._mix_kind_ok(f, photo):
            return False
        page = int(rec.get("page") or 0)
        folder = rec.get("folder")
        if photo != bool(getattr(self, "_photo_mode", False)):
            if photo and not self._photo_enabled():
                return False
            fp = Path(f)
            root = Path(folder) if folder and Path(folder) in fp.parents else fp.parent
            self._mix_enter(target=(root, f, page))
            return True
        from viewer.pathutil import norm_key
        mv = self._mv[1]
        cur = mv.current_file()
        self.act_split.setChecked(True)                  # toggled → _toggle_split(True)
        if not (cur and norm_key(str(cur)) == norm_key(f)):
            fold = folder or getattr(self, "_folder", None)
            if fold:
                self._set_pane_folder(1, fold)
            self._set_active_pane(1)
            self._load_main(HistoryItem(f, page, "", "bookmark"))
        self._sync_split_menu_state()
        return True

    def _split_same(self) -> None:
        """같은 종류 2단 — 오른쪽 칸이 다른 종류·컷이면 닫고 왼쪽 것을 복사(`_view_as_split` 의 빈 칸 길)."""
        if not getattr(self, "_split_on", False):
            self._view_as_split(restore=False)           # ▾ 로 고른 것 — 되살리기는 `_split_pick` 이 먼저 보았다
            return
        if self._mix_on_now():
            self._mix_leave()
        else:
            rf = self._mv[1].current_file()
            try:
                shot = self.bookmark_tree_right.in_shot_list()
            except AttributeError:
                shot = False
            if shot or (rf and not self._mix_kind_ok(rf, bool(getattr(self, "_photo_mode", False)))):
                try:
                    self.bookmark_tree_right.leave_shot_list()
                except AttributeError:
                    pass
                self._mv[1].close_document()
        if self._mv[1].current_file() is None:
            left = self._mv[0]
            lf = left.current_file()
            lpg = left.current_page() if lf else 0
            if getattr(self, "_folder", None):
                self._set_pane_folder(1, self._folder)
            self._set_active_pane(1)
            if lf:
                self._load_main(HistoryItem(str(lf), lpg, "", "bookmark"))
        self._sync_split_menu_state()

    def _split_show_shot(self) -> None:
        """`스크린샷` — 띠에서 지금 고른 컷(없으면 맨 앞)을 누른 것과 같은 길."""
        ss = getattr(self, "shot_strip", None)
        n = ss.list.count() if ss is not None else 0
        if n == 0:
            self.status.showMessage(tr("스크린샷이 없습니다."), 4000)
            return
        self._mix_leave()
        i = ss.list.currentRow()
        ss.activate_index(i if 0 <= i < n else 0)

    # ── 섞은 2단 ───────────────────────────────────────────
    def _mix_kind_ok(self, path, photo: bool) -> bool:
        return self._is_photo_path(path) if photo else str(path).lower().endswith(".pdf")

    def _mix_target(self, photo: bool):
        """그 모드의 마지막 자리(사진 SOT §6.1 의 기억 — 읽기만) → (폴더, 파일, 쪽). 폴더가 없으면 왼쪽 폴더."""
        rec = (self.__dict__.get("_photo_mode_last") or {}).get("photo" if photo else "pdf") or {}
        lo = rec.get("last_open") if isinstance(rec.get("last_open"), dict) else {}
        target, kind = str(lo.get("path") or ""), lo.get("kind")
        if not target:
            target, kind = str(rec.get("last_folder") or ""), "folder"
        folder = None
        if target and os.path.exists(target):
            p = Path(target)
            folder = p.parent if (kind == "file" or p.is_file()) else p
        if folder is None and getattr(self, "_folder", None):
            folder = Path(self._folder)
        cands = []
        last_pdf = self.__dict__.get("_photo_pdf_last") if not photo else None
        if last_pdf:
            cands.append((str(last_pdf[0]), int(last_pdf[1] or 0)))
        lm = rec.get("last_main") if isinstance(rec.get("last_main"), dict) else {}
        if lm.get("file_path"):
            cands.append((str(lm["file_path"]), 0 if photo else int(lm.get("page_index") or 0)))
        for f, pg in cands:
            fp = Path(f)
            if folder is not None and (fp.parent == folder or folder in fp.parents) and fp.is_file() \
                    and self._mix_kind_ok(f, photo) and not self._photo_any_cached([f]):
                return folder, f, pg
        return folder, None, 0

    def _mix_enter(self, target=None) -> None:
        """다른 종류를 오른쪽 칸에 — PDF 모드의 `PIX`·사진 모드의 `PDF`. `target`=(폴더, 파일, 쪽)은 되돌아오기(261116-17)."""
        photo = not bool(getattr(self, "_photo_mode", False))
        if photo and not self._photo_enabled():
            return                                       # 보기 종류 'PDF 전용' — ▾ 의 PIX 는 꺼져 있다
        if self._mix_on_now():
            return
        folder, fpath, page = target or self._mix_target(photo)
        rt = self.bookmark_tree_right
        try:
            rt.leave_shot_list()
        except AttributeError:
            pass
        self._mv[1].close_document()
        self._mix_on = True
        if not self.__dict__.get("_mix_wired"):
            rt.filesListed.connect(self._mix_on_listed)
            rt.view_only = self._mix_on_now              # 261116-19: 섞은 동안 아래 창은 보기만(우클릭 = 그 모드로 보기, Del·이름 변경 없음)
            rt.view_only_menu = self._mix_tree_menu
            self._mix_wired = True
        rt._root_dir = None                              # 앞 목록을 새 종류로 한 번 더 훑지 않게(사진 SOT §4.2 와 같은 순서)
        rt.set_photo_mode(photo)
        self._folder_right = Path(folder) if folder else None
        if not getattr(self, "_split_on", False):
            self.act_split.setChecked(True)              # toggled → _toggle_split(True) — 오른쪽 폴더가 있어 왼쪽을 따라 읽지 않는다
        if folder:
            self._set_pane_folder(1, folder)
        self._mix_draw_gate()
        self._set_active_pane(1)
        if fpath:
            self._load_main(HistoryItem(str(fpath), page, "", "bookmark"))
        else:
            self._mv[1].set_empty_hint(tr("아래 목록에서 고르세요."))
        self._mix_sync_thumbs()
        self._sync_split_menu_state()

    def _mix_leave(self) -> None:
        """섞은 2단을 놓는다 — 섞은 칸을 닫고, 아래 책갈피창은 창 모드의 목록(왼쪽 폴더), 썸네일 칸은 창 모드대로."""
        if not self.__dict__.get("_mix_on"):
            return
        self._mix_on = False
        self._mix_strip_pane = None
        photo = bool(getattr(self, "_photo_mode", False))
        mv = self._mv[1]
        mv.close_document()
        mv.set_empty_hint(None)
        rt = self.bookmark_tree_right
        rt._root_dir = None
        rt.set_photo_mode(photo)
        self._folder_right = None
        if getattr(self, "_split_on", False) and getattr(self, "_folder", None):
            self._set_pane_folder(1, self._folder)
        self._mix_draw_gate()
        strip = self._photo_strip_widget(create=False)
        if strip is not None:
            self.page_thumbs.set_alt_view(strip, photo)
            if photo:
                cur = self._mv[0].current_file()
                strip.set_paths(self._photo_strip_source(), current=str(cur) if cur else None)
            else:
                strip.stop()
                strip.set_paths([])
        if getattr(self, "_split_on", False):
            self._set_active_pane(0)

    def _mix_mode_changed(self) -> None:
        """창 모드가 바뀌었다 — 섞은 칸의 종류가 곧 창 모드라 칸은 그대로, 표지만 놓는다."""
        if not self.__dict__.get("_mix_on"):
            return
        self._mix_on = False
        self._mix_strip_pane = None
        try:
            self._mv[1].set_empty_hint(None)
        except Exception:
            pass
        self._mix_draw_gate()

    def _mix_draw_gate(self) -> None:
        """섞은 칸에서는 꾸미기를 그리지 않는다(보기 중심) — 편집 모드여도."""
        try:
            edit = bool(self.bookmark_tree.is_edit_mode())
            mv = self._mv[1]
            if edit:
                self._init_draw_config(mv)
            mv.set_draw_mode(edit and not self._mix_pane(1))
        except Exception:
            pass

    def _mix_list(self, pane: int) -> list:
        """그 창 책갈피창에 보이는 차례 그대로의 그 종류 파일."""
        bt = self.bookmark_tree_right if pane == 1 else self.bookmark_tree
        photo = self._pane_photo_kind(pane)
        if not photo:
            return [str(p) for p in (bt.ordered_pdf_files() or [])]
        out = []
        for it in bt._iter_file_nodes():
            p = it.data(0, bt.DATA_FILE)
            if p and not it.isHidden() and self._is_photo_path(p):
                out.append(str(p))
        return out

    def _mix_sync_thumbs(self) -> None:
        """썸네일 칸은 활성 창 따라 — 사진 칸이면 사진 썸네일 줄(그 칸 목록), PDF 칸이면 쪽 썸네일."""
        if not self._mix_on_now():
            return
        pane = getattr(self, "_active_pane", 0)
        if self._pane_photo_kind(pane):
            strip = self._photo_strip_widget(create=True)
            cur = self._mv[pane].current_file()
            src = self._mix_list(1) if pane == 1 else self._photo_strip_source()
            self.page_thumbs.set_alt_view(strip, True)
            strip.set_paths(src, current=str(cur) if cur else None)
            self._mix_strip_pane = pane
        else:
            strip = self._photo_strip_widget(create=False)
            if strip is not None:
                self.page_thumbs.set_alt_view(strip, False)
            self._mix_strip_pane = None

    def _mix_on_listed(self) -> None:
        """아래 책갈피창 목록이 다 찼다 — 섞은 사진 칸이 활성이면 썸네일 줄을 그 목록으로."""
        if self._mix_on_now() and getattr(self, "_active_pane", 0) == 1:
            self._mix_sync_thumbs()
            cur = self._mv[1].current_file()
            if cur:
                self._mix_position(cur)

    def _mix_position(self, path) -> None:
        lst = [str(Path(p)) for p in self._mix_list(1)]
        k = str(Path(path))
        if k in lst and self._pane_photo_kind(1):
            self._mv[1].set_photo_position(lst.index(k), len(lst))

    def _mix_after_open(self, path) -> None:
        """섞은 사진 칸에 사진을 연 뒤(사진 모드의 `_photo_after_open` 대신) — 쪽 썸네일·사진 모드 기억은 건드리지 않는다."""
        self._mv[1].set_empty_hint(None)
        self._mix_sync_thumbs()
        self._mix_position(path)
        self._mix_select_row(path)

    def _mix_select_row(self, path) -> None:
        """아래 책갈피창의 그 줄을 신호 없이 고른다(다시 열지 않게)."""
        from viewer.pathutil import norm_key
        bt = self.bookmark_tree_right
        key = norm_key(str(path))
        node = next((it for it in bt._iter_file_nodes() if norm_key(str(it.data(0, bt.DATA_FILE))) == key), None)
        if node is None:
            return
        t = bt.tree
        t.blockSignals(True)
        try:
            t.setCurrentItem(node)
            t.scrollToItem(node)
        finally:
            t.blockSignals(False)

    def _mix_step(self, direction: int) -> None:
        """섞은 칸의 넘김 — 아래 책갈피창 차례. 사진은 묻지 않고(사진 SOT §4.12), PDF 는 종전 파일 경계 규칙(`cross_file_nav`·묻기)."""
        cur = self._mv[1].current_file()
        if not cur:
            return
        photo = self._pane_photo_kind(1)
        if not photo and not self._prefs.get("cross_file_nav", False):
            return
        lst = self._mix_list(1)
        norm = [str(Path(p)) for p in lst]
        try:
            i = norm.index(str(Path(cur)))
        except ValueError:
            return
        j = i + (1 if direction > 0 else -1)
        if not (0 <= j < len(lst)):
            if photo:
                self.status.showMessage(tr("마지막 사진입니다.") if direction > 0 else tr("첫 사진입니다."), 2000)
            return
        if photo:
            self._on_bookmark_activated_right(lst[j], 0)
            return
        if not self._ask_cross_file(lst[j], direction > 0):
            return
        self._on_bookmark_activated_right(lst[j], 0 if direction > 0 else 10 ** 9)

    # ── 사진 썸네일 줄 — 섞은 칸의 줄이면 그 칸에 ─────────────
    def _mix_strip_mixed(self) -> bool:
        return self.__dict__.get("_mix_strip_pane") == 1 and self._mix_on_now()

    def _photo_strip_pick(self, path) -> None:
        if self._mix_strip_mixed():
            self._on_bookmark_activated_right(str(path), 0)
        else:
            self._on_bookmark_activated(str(path), 0)

    def _photo_strip_menu_route(self, path, gpos) -> None:
        if self._mix_strip_mixed():
            self._mix_menu(gpos, path)
        else:
            self._photo_strip_menu(path, gpos)

    def _photo_strip_delete_route(self, paths) -> None:
        if not self._mix_strip_mixed():                  # 섞은 칸은 보기 중심 — 지우기는 사진 모드에서
            self._photo_delete(paths)

    # ── 섞은 칸 우클릭 — 그 모드로 보기 ───────────────────────
    def _mix_menu(self, gpos, path=None) -> None:
        from viewer.widgets.ctx_menu import CtxMenu
        menu = CtxMenu(self)
        label = tr("사진 모드로 보기") if self._pane_photo_kind(1) else tr("PDF 모드로 보기")
        a = menu.addAction(label)
        a.setObjectName("mix_view_in_mode")
        a.triggered.connect(lambda _checked=False, p=path: self._mix_view_in_mode(p))
        self._mix_last_menu = menu                       # 검사가 실제 항목을 누른다
        menu.exec(gpos)

    def _mix_tree_menu(self, path, gpos) -> None:
        """261116-19: 섞은 2단 아래 책갈피창 우클릭 — 그 칸 종류의 파일 줄이면 `그 모드로 보기` 한 줄, 그 밖(폴더·zip 줄)은 메뉴 없음."""
        if path and os.path.isfile(str(path)) and self._mix_kind_ok(path, self._pane_photo_kind(1)):
            self._mix_menu(gpos, path)

    def _mix_view_in_mode(self, path=None) -> None:
        """창 모드를 섞은 칸의 종류로 바꿔 그 파일을 1단에 연다(그 칸의 폴더)."""
        mv = self._mv[1]
        rf = str(path) if path else mv.current_file()
        if not rf:
            return
        rpg = 0 if path else (mv.current_page() or 0)
        target = self._pane_photo_kind(1)
        folder = self.__dict__.get("_folder_right")
        if not self._photo_leave_guard():
            return
        self.act_split.setChecked(False)                 # toggled → _toggle_split(False) → _mix_leave
        self._mix_leave()
        self._set_photo_mode(target, load_last=False)
        if bool(getattr(self, "_photo_mode", False)) != target:
            return
        p = Path(str(rf))
        root = Path(folder) if folder and Path(folder) in p.parents else p.parent
        if self._root_folder_differs(root):
            self.open_folder(root)
        self._set_active_pane(0)
        self._load_main(HistoryItem(str(p), int(rpg), "", "bookmark"))
