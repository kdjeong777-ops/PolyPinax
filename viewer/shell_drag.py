# -*- coding: utf-8 -*-
"""책갈피창 → 파일 탐색기 끌기 — Windows 셸 끌기 (261117-3, 책갈피창·저장 SOT §4.7.30, 사용자 결정 A·가).

왜 Qt 끌기(`QDrag.exec`)가 아닌가: Qt 의 끌기 자료는 '비동기 복사'(IDataObjectAsyncCapability)를 내주지 않아,
탐색기가 놓기(Drop) 안에서 복사를 끝까지 하고 그동안 앱의 끌기가 돌아오지 못한다 — 끄는 모양('+'·썸네일)이 남고
메인이 묶였다(사용자 보고). 셸이 만든 끌기 자료(`SHCreateDataObject`)는 비동기를 내주므로 탐색기가 놓자마자 돌려주고
**복사·이동은 탐색기가 자기 진행 창으로** 한다. 앱은 파일 경로만 넘긴다(임시·가상 파일 없음 — 백신 위험 없음).

- 그냥 끌기 = 복사(`Preferred DropEffect`), Shift+끌기 = 이동(사용자 결정 '가').
- 놓는 순간 Shift 가 눌려 있으면(이동) 그 전에 `on_move_drop(paths)` 를 불러 앱이 파일을 놓게 한다(본문이 연 파일은 이동이 막힌다).
- pywin32 없이 ctypes 만(COM 개체 하나 — IDropSource).
"""
import ctypes
import os
import sys
from ctypes import wintypes as W

DROPEFFECT_NONE, DROPEFFECT_COPY, DROPEFFECT_MOVE = 0, 1, 2
DRAGDROP_S_DROP, DRAGDROP_S_CANCEL, DRAGDROP_S_USEDEFAULTCURSORS = 0x40100, 0x40101, 0x40102
MK_LBUTTON, MK_SHIFT = 0x1, 0x4
_E_NOINTERFACE = -2147467262

IID_IUnknown = "{00000000-0000-0000-C000-000000000046}"
IID_IDataObject = "{0000010E-0000-0000-C000-000000000046}"
IID_IDropSource = "{00000121-0000-0000-C000-000000000046}"
IID_IDataObjectAsyncCapability = "{3D8B0590-F691-11D2-8EA9-006097DF5BD4}"

_active = None          # 끄는 중인 경로들(표준 비교 키) — 제 책갈피창에 다시 놓으면 무시한다(is_own)


class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8)]


def _guid(s):
    g = GUID()
    ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(s), ctypes.byref(g))
    return g


class FORMATETC(ctypes.Structure):
    _fields_ = [("cfFormat", ctypes.c_ushort), ("ptd", ctypes.c_void_p), ("dwAspect", W.DWORD),
                ("lindex", ctypes.c_long), ("tymed", W.DWORD)]


class STGMEDIUM(ctypes.Structure):
    _fields_ = [("tymed", W.DWORD), ("hGlobal", ctypes.c_void_p), ("pUnkForRelease", ctypes.c_void_p)]


def available() -> bool:
    return sys.platform == "win32"


def _method(ptr, index, restype, *argtypes):
    vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    fn = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtbl[index])
    return lambda *a: fn(ptr, *a)


def release(ptr) -> None:
    if ptr:
        _method(ptr, 2, ctypes.c_ulong)()


def query(ptr, iid: str):
    """QueryInterface — 있으면 포인터(호출한 쪽이 release), 없으면 None."""
    out = ctypes.c_void_p()
    hr = _method(ptr, 0, ctypes.c_long, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))(
        ctypes.byref(_guid(iid)), ctypes.byref(out))
    return out.value if hr == 0 and out.value else None


def make_data_object(paths, prefer=DROPEFFECT_COPY):
    """경로들의 셸 끌기 자료(IDataObject 포인터 — 호출한 쪽이 release). 못 만들면 None."""
    sh = ctypes.windll.shell32
    pidls = []
    try:
        for p in paths:
            pidl = ctypes.c_void_p()
            hr = sh.SHParseDisplayName(ctypes.c_wchar_p(os.path.abspath(str(p))), None,
                                       ctypes.byref(pidl), 0, None)
            if hr != 0 or not pidl.value:
                return None
            pidls.append(pidl.value)
        arr = (ctypes.c_void_p * len(pidls))(*pidls)
        do = ctypes.c_void_p()
        # 부모 = 바탕 화면(빈 PIDL) + 절대 PIDL — 서로 다른 폴더의 파일도 한 자료로(트리 보기에서 여러 폴더를 고른 때).
        #   부모를 None 으로 주면 셸이 CF_HDROP 등을 만들지 않는 빈 자료가 된다(실측)
        desk = ctypes.create_string_buffer(2)
        hr = sh.SHCreateDataObject(desk, len(pidls), arr, None, ctypes.byref(_guid(IID_IDataObject)),
                                   ctypes.byref(do))
        if hr != 0 or not do.value:
            return None
        _set_dword(do.value, "Preferred DropEffect", prefer)
        set_async(do.value, True)
        return do.value
    finally:
        for p in pidls:
            ctypes.windll.ole32.CoTaskMemFree(ctypes.c_void_p(p))


def async_state(do):
    """(비동기 모드인가, 작업 중인가) — IDataObjectAsyncCapability 가 없으면 None."""
    a = query(do, IID_IDataObjectAsyncCapability)
    if not a:
        return None
    try:
        m, op = W.BOOL(0), W.BOOL(0)
        _method(a, 4, ctypes.c_long, ctypes.POINTER(W.BOOL))(ctypes.byref(m))     # GetAsyncMode
        _method(a, 6, ctypes.c_long, ctypes.POINTER(W.BOOL))(ctypes.byref(op))    # InOperation
        return bool(m.value), bool(op.value)
    finally:
        release(a)


def set_async(do, on: bool) -> bool:
    """탐색기가 놓기에서 곧바로 돌려주고 자기 스레드에서 복사하게 — SetAsyncMode."""
    a = query(do, IID_IDataObjectAsyncCapability)
    if not a:
        return False
    try:
        return _method(a, 3, ctypes.c_long, W.BOOL)(bool(on)) == 0
    finally:
        release(a)


def _set_dword(do, fmt_name: str, value: int) -> bool:
    k32 = ctypes.windll.kernel32
    k32.GlobalAlloc.restype = ctypes.c_void_p
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [ctypes.c_void_p]
    k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    cf = ctypes.windll.user32.RegisterClipboardFormatW(ctypes.c_wchar_p(fmt_name))
    h = k32.GlobalAlloc(0x0002, 4)                      # GMEM_MOVEABLE
    if not h:
        return False
    p = k32.GlobalLock(h)
    ctypes.c_uint32.from_address(p).value = int(value)
    k32.GlobalUnlock(h)
    fe = FORMATETC(cf, None, 1, -1, 1)                  # DVASPECT_CONTENT, TYMED_HGLOBAL
    sm = STGMEDIUM(1, h, None)
    hr = _method(do, 7, ctypes.c_long, ctypes.POINTER(FORMATETC), ctypes.POINTER(STGMEDIUM), W.BOOL)(
        ctypes.byref(fe), ctypes.byref(sm), True)       # 자료가 메모리를 갖는다
    return hr == 0


# ---- IDropSource (ctypes COM 개체) ----------------------------------------------------------
_QI = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
_REF = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
_QCD = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, W.BOOL, W.DWORD)
_GF = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, W.DWORD)


class _VT(ctypes.Structure):
    _fields_ = [("qi", _QI), ("addref", _REF), ("release", _REF), ("qcd", _QCD), ("gf", _GF)]


class _Obj(ctypes.Structure):
    _fields_ = [("vt", ctypes.POINTER(_VT))]


class DropSource:
    """끄는 동안 키 상태를 보는 IDropSource. 놓는 순간의 Shift 를 `on_drop(shift)` 로 알린다."""

    def __init__(self, on_drop=None):
        self.on_drop = on_drop
        self.dropped_shift = None
        ids = (bytes(_guid(IID_IUnknown)), bytes(_guid(IID_IDropSource)))

        def qi(this, riid, ppv):
            if bytes(riid.contents) in ids:
                ppv[0] = this
                return 0
            ppv[0] = None
            return _E_NOINTERFACE

        def qcd(this, esc, keys):
            try:
                if esc:
                    return DRAGDROP_S_CANCEL
                if not (keys & MK_LBUTTON):
                    self.dropped_shift = bool(keys & MK_SHIFT)
                    if callable(self.on_drop):
                        self.on_drop(self.dropped_shift)
                    return DRAGDROP_S_DROP
            except Exception:
                pass
            return 0

        self._fns = _VT(_QI(qi), _REF(lambda this: 1), _REF(lambda this: 1), _QCD(qcd),
                        _GF(lambda this, eff: DRAGDROP_S_USEDEFAULTCURSORS))
        self._obj = _Obj(ctypes.pointer(self._fns))

    @property
    def ptr(self):
        return ctypes.addressof(self._obj)


# ---- 비동기 끌기 자료 (IDataObject 맡김 + IDataObjectAsyncCapability) -------------------------
#   셸 자료의 SetAsyncMode 는 S_OK 를 주고도 GetAsyncMode 가 늘 FALSE 라(실측 261117), 놓기 대상이 놓기 안에서 복사를
#   끝까지 했다(3GB 3.5초 동안 Drop 이 안 돌아옴). 그래서 셸 자료를 감싸 비동기 능력만 이 개체가 맡는다 — 자료 요청은
#   모두 셸 자료로 넘긴다. 대상은 StartOperation → (자기 스레드에서 복사·이동) → EndOperation(결과, 효과)로 끝을 알린다.
_P = ctypes.c_void_p
_HR = ctypes.c_long
_FWD = {                 # IDataObject 3~11 — 인자 꼴(this 뒤)
    3: (_P, _P), 4: (_P, _P), 5: (_P,), 6: (_P, _P), 7: (_P, _P, W.BOOL),
    8: (W.DWORD, _P), 9: (_P, W.DWORD, _P, _P), 10: (W.DWORD,), 11: (_P,),
}
_live = set()            # 셸이 아직 쥐고 있는 자료(참조 0 이 되면 뺀다)


class AsyncDataObject:
    def __init__(self, inner, on_end=None):
        self.inner = inner                    # 셸 자료(이 개체가 참조 하나를 갖는다)
        self.on_end = on_end
        self.async_mode = True
        self.in_op = False
        self.started = False
        self.ended = None                     # (hr, effect)
        self._ref = 1
        uid = bytes(_guid(IID_IUnknown)); did = bytes(_guid(IID_IDataObject))
        aid = bytes(_guid(IID_IDataObjectAsyncCapability))
        self._ids = (uid, did, aid)

        def qi(this, riid, ppv):
            k = bytes(riid.contents)
            if k in (uid, did):
                ppv[0] = self._addr; self._addref(); return 0
            if k == aid:
                ppv[0] = self._addr + ctypes.sizeof(_P); self._addref(); return 0
            ppv[0] = None
            return _E_NOINTERFACE

        def addref(this):
            return self._addref()

        def rel(this):
            return self._release()

        fns = [_QI(qi), _REF(addref), _REF(rel)]
        for idx in range(3, 12):
            proto = ctypes.WINFUNCTYPE(_HR, _P, *_FWD[idx])
            fns.append(proto(self._fwd(idx, _FWD[idx])))
        self._vt_data = (_P * 12)(*[ctypes.cast(f, _P) for f in fns])

        def set_mode(this, on):
            self.async_mode = bool(on); return 0

        def get_mode(this, p):
            ctypes.cast(p, ctypes.POINTER(W.BOOL))[0] = 1 if self.async_mode else 0; return 0

        def start(this, pbc):
            self.in_op = True; self.started = True; return 0

        def in_op(this, p):
            ctypes.cast(p, ctypes.POINTER(W.BOOL))[0] = 1 if self.in_op else 0; return 0

        def end(this, hr, pbc, eff):
            self.in_op = False
            self.ended = (int(hr), int(eff))
            try:
                if callable(self.on_end):
                    self.on_end(int(eff) if int(hr) >= 0 else DROPEFFECT_NONE)
            except Exception:
                pass
            return 0

        afns = [_QI(qi), _REF(addref), _REF(rel),
                ctypes.WINFUNCTYPE(_HR, _P, W.BOOL)(set_mode),
                ctypes.WINFUNCTYPE(_HR, _P, _P)(get_mode),
                ctypes.WINFUNCTYPE(_HR, _P, _P)(start),
                ctypes.WINFUNCTYPE(_HR, _P, _P)(in_op),
                ctypes.WINFUNCTYPE(_HR, _P, _HR, _P, W.DWORD)(end)]
        self._vt_async = (_P * 8)(*[ctypes.cast(f, _P) for f in afns])
        self._fns = (fns, afns)               # 콜백을 살려 둔다
        self._obj = (_P * 2)(ctypes.addressof(self._vt_data), ctypes.addressof(self._vt_async))
        self._addr = ctypes.addressof(self._obj)
        _live.add(self)

    def _fwd(self, idx, argt):
        def f(this, *a):
            if not self.inner:
                return -2147418113                       # E_UNEXPECTED
            return _method(self.inner, idx, _HR, *argt)(*a)
        return f

    def _addref(self):
        self._ref += 1
        return self._ref

    def _release(self):
        self._ref -= 1
        if self._ref <= 0:
            self._ref = 0
            if self.inner:
                release(self.inner); self.inner = None
            _live.discard(self)
        return self._ref

    @property
    def ptr(self):
        return self._addr


def in_use(path) -> bool:
    """다른 프로그램(복사·이동 중인 탐색기)이 그 파일을 열고 있나 — 배타로 열어 본다(배경 스레드에서만 부른다)."""
    k32 = ctypes.windll.kernel32
    k32.CreateFileW.restype = ctypes.c_void_p
    k32.CreateFileW.argtypes = [ctypes.c_wchar_p, W.DWORD, W.DWORD, ctypes.c_void_p, W.DWORD, W.DWORD, ctypes.c_void_p]
    h = k32.CreateFileW(str(path), 0x80000000, 0, None, 3, 0x80, None)    # GENERIC_READ, 공유 없음, OPEN_EXISTING
    if h is None or h == ctypes.c_void_p(-1).value:
        return k32.GetLastError() == 32                                    # ERROR_SHARING_VIOLATION
    k32.CloseHandle(ctypes.c_void_p(h))
    return False


def is_own(paths) -> bool:
    """지금 이 앱이 끄는 파일들인가(제 책갈피창에 다시 놓으면 아무 일도 하지 않는다)."""
    if not _active or not paths:
        return False
    from viewer.pathutil import norm_key
    return all(norm_key(str(p)) in _active for p in paths)


def make_async_data_object(paths, on_end=None):
    """비동기 끌기 자료(AsyncDataObject) — 못 만들면 None. `on_end(효과)` 는 대상이 복사·이동을 끝냈을 때."""
    inner = make_data_object(paths, DROPEFFECT_COPY)
    return AsyncDataObject(inner, on_end) if inner else None


def drag_files(paths, hwnd=0, on_move_drop=None, on_done=None,
               effects=DROPEFFECT_COPY | DROPEFFECT_MOVE, mark_own=True) -> dict:
    """파일들을 셸 끌기로 끈다 — 놓거나 취소할 때까지 메인에서 돈다(끄는 동안만). 복사·이동은 대상(탐색기)이 자기 스레드에서.
    - `on_move_drop(paths)`: 놓는 순간 Shift(이동)면 놓기 전에 — 앱이 연 파일을 놓게.
    - `on_done(effect)`: 대상이 끝냈을 때 한 번(비동기면 나중에 EndOperation 에서, 아니면 곧바로). 취소면 DROPEFFECT_NONE.
    - `effects`: 허락할 효과(261117-7 — 스크린샷 스트립은 앱 저장 폴더라 복사만).
    - `mark_own`: False 면 `is_own` 표식을 세우지 않는다(책갈피창이 종전처럼 받는다 — 스크린샷 카드).
    돌려줌: {"result": "drop"|"cancel"|"error", "shift", "effect", "async": 대상이 비동기로 받았나}."""
    global _active
    paths = [str(p) for p in paths]
    if not available() or not paths:
        return {"result": "error", "shift": False, "effect": 0, "async": False}
    fired = []

    def _done(eff):
        if not fired:
            fired.append(eff)
            if callable(on_done):
                on_done(int(eff))

    ado = make_async_data_object(paths, _done)
    if ado is None:
        return {"result": "error", "shift": False, "effect": 0, "async": False}

    def _on_drop(shift):
        if shift and callable(on_move_drop):
            on_move_drop(list(paths))

    src = DropSource(_on_drop)
    from viewer.pathutil import norm_key
    _active = {norm_key(p) for p in paths} if mark_own else None
    eff = W.DWORD(0)
    try:
        sh = ctypes.windll.shell32
        sh.SHDoDragDrop.argtypes = [W.HWND, ctypes.c_void_p, ctypes.c_void_p, W.DWORD, ctypes.POINTER(W.DWORD)]
        sh.SHDoDragDrop.restype = ctypes.c_long
        hr = sh.SHDoDragDrop(W.HWND(int(hwnd or 0)), ado.ptr, src.ptr,
                             int(effects), ctypes.byref(eff))
    finally:
        _active = None
        ado._release()                                    # 만든 참조 — 대상이 쥐고 있으면 더 산다
    res = "drop" if hr == DRAGDROP_S_DROP else ("cancel" if hr == DRAGDROP_S_CANCEL else "error")
    is_async = res == "drop" and (ado.in_op or ado.ended is not None)
    if not is_async:
        _done(int(eff.value) if res == "drop" else DROPEFFECT_NONE)
    return {"result": res, "shift": bool(src.dropped_shift), "effect": int(eff.value), "async": is_async}
