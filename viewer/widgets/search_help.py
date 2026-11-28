# -*- coding: utf-8 -*-
"""검색 도움말 창 — 검색 막대 [?] 단추 (검색창 SOT §4.3, 261128-9).

차례는 **많이 쓰는 것 먼저**: 보통 검색 → 연산자(띄어쓰기 AND·|·-·"구절"·괄호) → 정규식(.* 켬) → Aa(한국어 화면엔 없다).
비모달 하나 — 떠 있는 채로 검색하고, 다시 누르면 앞으로. 꼴은 디자인 SOT §2.3 '검색 도움말'.
"""
from __future__ import annotations

import html

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QDialogButtonBox

from viewer.i18n import tr, language, KO

_dlg = None


def _rows(rows) -> str:
    out = []
    for sym, desc, ex in rows:
        out.append("<tr><td><code>%s</code></td><td>%s</td><td><code>%s</code></td></tr>"
                   % (html.escape(sym), html.escape(desc), html.escape(ex)))
    return ("<table cellspacing='0' cellpadding='4' border='1' style='border-collapse:collapse'>"
            "<tr><th>%s</th><th>%s</th><th>%s</th></tr>%s</table>"
            % (html.escape(tr("기호")), html.escape(tr("뜻")), html.escape(tr("예시")), "".join(out)))


def help_html() -> str:
    """도움말 글(HTML) — 많이 쓰는 것 먼저(검색창 SOT §4.3)."""
    p = []
    p.append("<h3>%s</h3><p>%s</p>" % (html.escape(tr("1. 보통 검색")),
             html.escape(tr("낱말을 그대로 치면 그 낱말이 든 쪽을 찾습니다. 빈칸·줄바꿈은 무시하고 대소문자는 가리지 않습니다."))))
    p.append(_rows([(tr("낱말"), tr("그 낱말이 든 쪽"), tr("아스팔트"))]))
    p.append("<h3>%s</h3>" % html.escape(tr("2. 여러 낱말 — 연산자 (가장 많이 씀)")))
    p.append(_rows([
        (tr("띄어쓰기"), tr("AND — 둘 다 든 쪽. & 는 AND 가 아니라 보통 글자입니다"), tr("아스팔트 균열")),
        ("|", tr("또는 — 어느 하나라도 든 쪽"), tr("다짐|포설")),
        ("-", tr("빼기 — 이 낱말이 든 쪽은 뺍니다"), tr("포장 -콘크리트")),
        ('"…"', tr("구절 — 띄어쓰기까지 그대로 붙은 글"), tr('"품질 관리"')),
        ("( )", tr("묶기 — 먼저 계산합니다"), tr("(다짐|포설) 온도")),
    ]))
    p.append("<p>%s</p>" % html.escape(tr("먼저 계산하는 차례: - → | → 띄어쓰기. 예) 아스팔트 포장|도로 = 아스팔트 AND (포장 OR 도로)")))
    p.append("<h3>%s</h3><p>%s</p>" % (html.escape(tr("3. 정규식 — [.*] 단추를 켰을 때")),
             html.escape(tr("켜면 위 연산자를 읽지 않고 칸 전체를 정규식으로 봅니다. 빈칸도 무시하지 않으니 빈칸이 있을 수 있는 곳엔 \\s* 를 씁니다. "
                            "한 줄 안에서만 맞추고, 정규식이 틀리면 칸이 붉어집니다."))))
    p.append(_rows([
        (".*", tr("사이에 아무 글이나(없어도 됨)"), tr("검사.*기준")),
        (".", tr("아무 글자 하나"), tr("제.장")),
        ("\\d", tr("숫자 하나"), "\\d+mm"),
        ("+", tr("앞 것이 1번 이상"), "\\d+mm"),
        ("*", tr("앞 것이 0번 이상"), tr("아스팔트\\s*포장")),
        ("?", tr("앞 것이 있어도 없어도"), tr("포장(공사)?")),
        ("|", tr("또는"), tr("다짐|포설")),
        ("[ ]", tr("그중 한 글자"), tr("제[1-3]장")),
        ("\\s", tr("빈칸 하나"), "\\d+\\s*℃"),
        ("^  $", tr("줄의 처음 / 끝"), tr("^제1장")),
        ("\\", tr("특수 기호를 글자 그대로"), "3\\.5"),
    ]))
    if language() != KO:                                 # 한국어 화면엔 Aa 가 없다(검색창 SOT §4.1)
        p.append("<h3>%s</h3>" % html.escape(tr("4. [Aa] — 대소문자 구분")))
        p.append(_rows([("Aa", tr("켜면 대소문자를 가립니다(ASTM 과 astm 이 다름)"), "ASTM")]))
    return "".join(p)


class SearchHelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("검색 도움말"))
        self.setModal(False)
        self.resize(560, 640)
        lay = QVBoxLayout(self)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        self.browser.setHtml(help_html())
        lay.addWidget(self.browser, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.button(QDialogButtonBox.StandardButton.Close).setText(tr("닫기"))
        bb.rejected.connect(self.close)
        lay.addWidget(bb)


def open_help(parent=None) -> SearchHelpDialog:
    """도움말 창을 연다 — 하나만, 떠 있으면 앞으로."""
    global _dlg
    try:
        alive = _dlg is not None and _dlg.isVisible() is not None
    except RuntimeError:                                 # 부모와 함께 지워졌다
        alive = False
    if not alive:
        _dlg = SearchHelpDialog(parent)
    _dlg.show()
    _dlg.raise_()
    _dlg.activateWindow()
    return _dlg
