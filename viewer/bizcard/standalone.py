"""명함 프로그램 — 본 뷰어와 따로 도는 프로세스 (명함 SOT §5.27, D32).

`main.py --bizcard` 가 부른다. 본 창·스플래시·색인 없이 명함찾기 창 하나를 최상위 창으로 띄운다.
★ 경계: 이 모듈과 명함 창들은 `viewer.app` 을 import 하지 않는다 — 본 뷰어에서 쓰던 것은 `Host` 한 객체로만.
★ 명함 글·경로는 로그에 싣지 않는다(§2.1).
"""
from __future__ import annotations

import os
import subprocess
import sys

from PyQt6.QtCore import QObject

from viewer.i18n import tr

SERVER_SUFFIX = "-bizcard"            # 단일 실행 통로 이름 = <앱 이름> + 이것
ARG = "--bizcard"


APP_TITLE = "PolyCardex"            # 프로그램 이름(사용자 결정 261119, D32) — 제품 이름이라 번역하지 않는다. 바꿀 때는 여기 한 곳


def app_title() -> str:
    """창 제목·작업 표시줄 이름."""
    return APP_TITLE


def main_cmd(extra=()) -> list:
    """본 뷰어(같은 실행 파일)를 부르는 명령 — 설치본은 exe, 개발판은 python main.py."""
    if getattr(sys, "frozen", False):
        return [sys.executable] + list(extra)
    main = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "main.py")
    return [sys.executable, main] + list(extra)


def launch(popen=subprocess.Popen):
    """본 뷰어의 명함 아이콘 — 명함 프로그램을 따로 띄운다(이미 떠 있으면 그쪽이 앞으로 나온다). 반환 = Popen 또는 None."""
    try:
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        return popen(main_cmd([ARG]), close_fds=True, creationflags=flags if sys.platform == "win32" else 0)
    except Exception:
        return None


def bizcard_folder() -> str:
    from viewer import settings_store
    pic = settings_store.peek_pref("picture")
    return str((pic or {}).get("bizcard_folder") or "").strip() if isinstance(pic, dict) else ""


class Host(QObject):
    """명함 창이 본 뷰어(MainWindow)에게 하던 일 — 별도 프로그램에서는 이 객체가 한다(경계, §5.27)."""

    def __init__(self, popen=subprocess.Popen):
        super().__init__()
        self._thread_keep = []
        self._popen = popen
        self._bizcard_dlg = None
        self.find_dlg = None

    def _action_bizcard_import(self, folder=None):
        """[명함 관리] — 지정한 명함 폴더(없으면 묻기)로 확인 표 창. 창은 하나."""
        from PyQt6.QtWidgets import QFileDialog
        folder = folder or bizcard_folder()
        if not folder or not os.path.isdir(folder):
            folder = QFileDialog.getExistingDirectory(self.find_dlg, tr("명함 관리"), "")
            if not folder:
                return None
        old = self._bizcard_dlg
        try:
            from PyQt6 import sip
            if old is not None and not sip.isdeleted(old) and old.isVisible():
                if os.path.normcase(os.path.abspath(str(old._folder))) == os.path.normcase(os.path.abspath(folder)):
                    old.raise_()
                    old.activateWindow()
                    return old
                old.close()
        except Exception:
            pass
        from PyQt6.QtCore import Qt
        from viewer.widgets.bizcard_import_dialog import BizcardImportDialog
        dlg = BizcardImportDialog(folder, None)
        dlg._mw = self                                # 호스트(경계) — 스레드 보관·휴지통 길
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._bizcard_dlg = dlg
        dlg.show()
        return dlg

    def _trash_bg(self, paths, photo: bool = True) -> dict:
        """휴지통 — 본 뷰어 `_trash_bg` 와 같은 이름·같은 반환 {경로: None(지움)|예외}(§5.27 '경계', 261120-68).
        배경 스레드에서 `trash_when_free`(잠깐 잡히면 다시), 0.3초가 넘으면 진행 창 — 부른 쪽은 끝날 때까지 기다린다.
        별도 프로그램엔 사진 정보 색인이 없어 photo 는 받기만 한다."""
        from PyQt6.QtCore import QThread, Qt
        from PyQt6.QtWidgets import QProgressDialog
        import viewer.widgets.bookmark_tree as _btm
        from viewer.pathutil import trash_when_free
        trash = _btm._trash_fn()
        ps = [str(p) for p in paths]
        out = {}

        class _T(QThread):
            def run(self_):
                for p in ps:
                    try:
                        trash_when_free(p, trash)
                        out[p] = None
                    except Exception as e:            # noqa: BLE001
                        out[p] = e

        prog = QProgressDialog(tr("휴지통으로 보내는 중: {n}개").format(n=len(ps)), None, 0, 0, self.find_dlg)
        prog.setWindowTitle(tr("파일 지우기"))
        prog.setWindowModality(Qt.WindowModality.ApplicationModal)
        prog.setMinimumDuration(300)
        prog.setCancelButton(None)
        th = _T()
        th.finished.connect(prog.close)
        th.finished.connect(prog.deleteLater)
        th.start()
        if th.isRunning():
            prog.exec()                                   # 진행 창(0.3초 뒤 보임) — 본 뷰어 `_file_op_bg` 와 같은 모달 기다림
        th.wait()
        for p in ps:
            out.setdefault(p, RuntimeError(tr("휴지통으로 보내지 못했습니다")))
        return out

    def _photo_open_arg(self, path) -> bool:
        """[명함 보기] — 본 뷰어에 사진을 넘긴다(사진 모드 창이 있으면 그 창이 받음 — 사진 SOT §4.45)."""
        try:
            self._popen(main_cmd([str(path)]), close_fds=True)
            return True
        except Exception:
            return False


def _single_instance(name: str, on_show):
    """단일 실행 — 첫째면 서버를 열어 돌려주고, 둘째면 첫째에게 'show' 를 보내고 None."""
    from PyQt6.QtNetwork import QLocalServer, QLocalSocket
    sock = QLocalSocket()
    sock.connectToServer(name)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return None
    srv = QLocalServer()
    QLocalServer.removeServer(name)
    srv.listen(name)

    def _on_new():
        c = srv.nextPendingConnection()
        if c is not None:
            c.readyRead.connect(lambda: (c.readAll(), on_show()))
    srv.newConnection.connect(_on_new)
    return srv


def run(app, server_name: str) -> int:
    """`main.py --bizcard` — 명함찾기 창 하나. 반환 = 끝 코드."""
    from PyQt6.QtCore import Qt
    from viewer.widgets.bizcard_find_dialog import BizcardFindDialog
    host = Host()
    box = {}

    def show_front():
        d = box.get("dlg")
        if d is not None:
            if d.isMinimized():
                d.showNormal()
            d.show()
            d.raise_()
            d.activateWindow()
    srv = _single_instance(server_name, show_front)
    if srv is None:
        return 0                                       # 이미 떠 있음 — 그 창을 앞으로
    dlg = BizcardFindDialog(None, host=host)
    dlg.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowMinimizeButtonHint
                       | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowCloseButtonHint)
    dlg.setWindowTitle(app_title())
    host.find_dlg = dlg
    box["dlg"] = dlg
    box["srv"] = srv
    app.setQuitOnLastWindowClosed(True)
    dlg.finished.connect(lambda _r: app.quit())
    dlg.show()
    return app.exec()
