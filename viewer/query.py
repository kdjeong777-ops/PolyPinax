# -*- coding: utf-8 -*-
"""검색 연산자 해석기 하나 — 띄어쓰기 AND · `|` OR · `-` NOT · 괄호 · "따옴표" 구절 (검색창 SOT §4.2, 261117-30).

앱 안 검색 지점(색인 결과·본문 강조·책갈피 거르기·명함찾기·사진 검색·오른쪽 창 본문 찾기·사용자 뜻·태그 찾기·설정 찾기)은
모두 `parse(질의)` 로 읽고 같은 규칙으로 평가한다. Qt·fitz 를 쓰지 않는다.

빈칸·줄바꿈·하이픈 무시(검색창 SOT §3.1 `flat_text`·`flat_pattern`)도 여기가 소유한다 — `viewer.indexer` 는 다시 내보내기만.

우선순위는 구글과 같다: `-` > `|` > 띄어쓰기. 틀린 질의는 오류 없이 관대하게 읽는다(SOT §4.2).
"""
from __future__ import annotations

import re

# ── 빈칸·하이픈 무시 (검색창 SOT §3.1) ──
# 261101-1: 하이픈(`-`·소프트 하이픈·‐·‑)도 빈칸처럼 뺀다 — 글자층 줄 끝 분철·합성어 띄어쓰기
FLAT_SKIP = r"\s\-­‐‑"
_WS = re.compile("[" + FLAT_SKIP + "]+")


def flat_text(s: str) -> str:
    """261019-4(검색창 SOT §3.1): 빈칸·줄바꿈(·하이픈, 261101-1)을 모두 뺀 글 — 색인과 질의를 같은 모양으로 맞춘다.
    글자층은 줄 끝마다 줄바꿈이 들어 있어(문단 안에서도) '아스팔트 포장' 이 '아스팔트\\n포장' 으로 남는다."""
    return _WS.sub("", s or "")


def _flat_rx(q: str) -> str:
    qf = flat_text(q)
    return ("[" + FLAT_SKIP + "]*").join(re.escape(c) for c in qf)


def flat_pattern(q: str):
    """질의 글자 사이에 빈칸·줄바꿈·하이픈이 얼마든 있어도 맞는 정규식 — 개수·미리보기용(색인 비교와 같은 뜻)."""
    rx = _flat_rx(q)
    return re.compile(rx, re.IGNORECASE) if rx else None


def like_escape(s: str) -> str:
    """SQL LIKE 와일드카드 이스케이프(`ESCAPE '\\'` 와 함께)."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


from viewer.i18n import tr_noop                       # noqa: E402 — Qt 없는 가벼운 모듈(뽑기만 표시, 화면에서 tr)

NEG_ONLY_TEXT = tr_noop("'-' 낱말만으로는 찾지 않습니다 — 찾을 낱말을 함께 쓰세요.")   # tr() 는 부르는 쪽(Qt 화면)이


# ── 식 나무 ──
class Node:
    """op: 'term' | 'and' | 'or' | 'not'. term 은 `text`(친 글 그대로)·`phrase`(따옴표였나)."""
    __slots__ = ("op", "kids", "text", "phrase")

    def __init__(self, op, kids=(), text="", phrase=False):
        self.op = op
        self.kids = list(kids)
        self.text = text
        self.phrase = phrase

    def __repr__(self):
        if self.op == "term":
            return ('"%s"' % self.text) if self.phrase else self.text
        if self.op == "not":
            return "-(%r)" % (self.kids[0],)
        return "%s(%s)" % (self.op.upper(), ", ".join(repr(k) for k in self.kids))


def _tokens(q: str) -> list:
    """('(' | ')' | '|' | '-' | ('w', 글, 구절?)). `-` 는 낱말 맨 앞(처음·빈칸·`(`·`|` 뒤)일 때만 연산자."""
    out = []
    i, n = 0, len(q)
    while i < n:
        c = q[i]
        if c.isspace():
            i += 1
            continue
        if c in "()|":
            out.append(c)
            i += 1
            continue
        if c == '"':
            j = q.find('"', i + 1)
            if j < 0:
                j = n                                   # 닫히지 않은 따옴표 — 끝에서 닫힌 것으로
            out.append(("w", q[i + 1:j], True))
            i = j + 1
            continue
        if c == "-" and i + 1 < n and not q[i + 1].isspace() and q[i + 1] not in ")|":
            out.append("-")                             # 낱말 맨 앞 '-' = NOT (앞은 빈칸·처음·괄호·| 뿐 — 낱말 안은 여기 오지 않는다)
            i += 1
            continue
        j = i
        while j < n and not q[j].isspace() and q[j] not in '()|"':
            j += 1
        out.append(("w", q[i:j], False))
        i = j
    return out


class _P:
    def __init__(self, toks):
        self.t = toks
        self.i = 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def seq(self, inner: bool):
        """AND — 띄어쓰기로 이은 OR 들. 안쪽이면 ')' 에서 멈춘다."""
        items = []
        while True:
            tok = self.peek()
            if tok is None:
                break
            if tok == ")":
                if inner:
                    break
                self.take()                             # 짝 없는 ')' 는 버린다
                continue
            if tok == "|":
                self.take()                             # 앞에 갈래가 없는 '|' 는 버린다
                continue
            node = self.alt(inner)
            if node is not None:
                items.append(node)
        return Node("and", items)

    def alt(self, inner):
        """OR — `a | b | c`."""
        kids = []
        first = self.unary(inner)
        if first is not None:
            kids.append(first)
        while self.peek() == "|":
            self.take()
            while self.peek() == "|":                   # 겹친 '|'
                self.take()
            nxt = self.peek()
            if nxt is None or nxt == ")":
                break                                   # 끝의 '|' 는 버린다
            k = self.unary(inner)
            if k is not None:
                kids.append(k)
        if not kids:
            return None
        return kids[0] if len(kids) == 1 else Node("or", kids)

    def unary(self, inner):
        tok = self.peek()
        if tok == "-":
            self.take()
            k = self.unary(inner)
            return Node("not", [k]) if k is not None else None
        if tok == "(":
            self.take()
            node = self.seq(True)
            if self.peek() == ")":
                self.take()                             # 닫히지 않은 '(' 는 끝에서 닫힌 것으로
            return node if node.kids else None
        if isinstance(tok, tuple):
            self.take()
            _w, text, phrase = tok
            if not flat_text(text):
                return None                             # 빈 낱말·빈 "" · 하이픈뿐
            return Node("term", text=text, phrase=phrase)
        return None


def _norm(node):
    """한 갈래 묶음 펴기 · NOT 은 AND 안에서만(긍정 형제가 있을 때) · OR 의 NOT 갈래는 버린다. 긍정 낱말이 없으면 None."""
    if node is None:
        return None
    if node.op == "term":
        return node
    if node.op == "not":
        k = _norm_any(node.kids[0])
        return Node("not", [k]) if k is not None else None
    if node.op == "or":
        kids = []
        for k in node.kids:
            nk = _norm(k)
            if nk is None or nk.op == "not":
                continue                                # 'a | -b' → a
            kids.extend(nk.kids if nk.op == "or" else [nk])
        if not kids:
            return None
        return kids[0] if len(kids) == 1 else Node("or", kids)
    # and
    pos, neg = [], []
    for k in node.kids:
        if k.op == "not":
            nk = _norm(k)
            if nk is not None:
                neg.append(nk)
            continue
        nk = _norm(k)
        if nk is None:
            continue
        if nk.op == "and":
            pos.extend(x for x in nk.kids if x.op != "not")
            neg.extend(x for x in nk.kids if x.op == "not")
        else:
            pos.append(nk)
    if not pos:
        return None                                     # NOT 뿐 — 찾을 낱말이 없다
    kids = pos + neg
    return kids[0] if len(kids) == 1 else Node("and", kids)


def _norm_any(node):
    """NOT 아래 — 긍정이 없어도 버리지 않을 만큼만 편다(`-(a | b)` 는 그대로)."""
    if node is None:
        return None
    if node.op in ("term",):
        return node
    if node.op == "not":
        return _norm_any(node.kids[0])                  # --a 는 a 를 뺀 것의 뺀 것 — 단순히 a 를 빼는 것으로 본다
    n = _norm(node)
    return n


def _has_term(node) -> bool:
    if node is None:
        return False
    if node.op == "term":
        return True
    return any(_has_term(k) for k in node.kids)


class Query:
    """질의 한 줄을 읽은 결과.

    - `root` — 식 나무(None = 찾을 낱말 없음)
    - `empty` — 낱말이 하나도 없음(빈 칸) · `neg_only` — 낱말은 있으나 NOT 뿐(빈 결과 + `NEG_ONLY_TEXT`)
    - `single` — 연산자 없는 낱말 하나(또는 구절 하나)면 그 글, 아니면 None → 부르는 쪽은 종전 길 그대로
    - `positives` — 긍정 낱말 글(강조·개수·조각 글)
    """

    def __init__(self, raw: str):
        self.raw = str(raw or "")
        tree = _P(_tokens(self.raw)).seq(False)
        self.root = _norm(tree)
        self.empty = not _has_term(tree)
        self.neg_only = (not self.empty) and self.root is None
        self.single = self.root.text if (self.root is not None and self.root.op == "term") else None
        self.positives = []
        self._collect(self.root, False)
        self._pat = None

    def _collect(self, node, neg):
        if node is None:
            return
        if node.op == "term":
            if not neg and node.text not in self.positives:
                self.positives.append(node.text)
            return
        for k in node.kids:
            self._collect(k, neg or node.op == "not")

    @property
    def ok(self) -> bool:
        return self.root is not None

    # ── 평가 ──
    def test(self, pred) -> bool:
        """`pred(낱말 글) → bool` 로 식을 평가. 찾을 낱말이 없으면 False."""
        if self.root is None:
            return False

        def ev(n):
            if n.op == "term":
                return bool(pred(n.text))
            if n.op == "not":
                return not ev(n.kids[0])
            if n.op == "and":
                return all(ev(k) for k in n.kids)
            return any(ev(k) for k in n.kids)
        return ev(self.root)

    def matches(self, text: str) -> bool:
        """글 하나(단위)에 대해 — 낱말마다 대소문자·빈칸·하이픈 무시 부분일치(§3.1)."""
        hay = flat_text(text or "").lower()
        return self.test(lambda w: flat_text(w).lower() in hay)

    def matches_flat(self, flat_lower: str) -> bool:
        """이미 `flat_text(...).lower()` 한 글로 평가(본문 쪽 글 캐시 — `PdfDocument._flat_page`)."""
        return self.test(lambda w: flat_text(w).lower() in (flat_lower or ""))

    def pattern(self):
        """긍정 낱말 중 하나에 맞는 정규식(빈칸·하이픈 무시, 대소문자 무시) — 개수·조각 글·강조. 긴 낱말 먼저."""
        if self._pat is None:
            parts = sorted({_flat_rx(w) for w in self.positives if _flat_rx(w)}, key=len, reverse=True)
            self._pat = re.compile("|".join("(?:%s)" % p for p in parts), re.IGNORECASE) if parts else False
        return self._pat or None

    # ── SQL ──
    def sql(self, col: str, flat: bool = True):
        """식 나무 → (`WHERE` 조각, 매개변수 목록). 낱말마다 `col LIKE ? ESCAPE '\\'`(NOT 은 `NOT LIKE`).
        `flat=True` 면 낱말을 `flat_text` 로(새 표 `pages2.flat`), False 면 원문 그대로(옛 표 `pages_fts.text`).
        `col` 은 부르는 쪽이 정한 컬럼 이름 — 값은 모두 매개변수로 묶는다(글 이어 붙이기 금지, SOT §4.2)."""
        if self.root is None:
            return "0", []
        args: list = []

        def gen(n):
            if n.op == "term":
                w = flat_text(n.text) if flat else n.text
                args.append("%" + like_escape(w) + "%")
                return "%s LIKE ? ESCAPE '\\'" % col
            if n.op == "not":
                return "NOT (%s)" % gen(n.kids[0])
            j = " AND " if n.op == "and" else " OR "
            return "(" + j.join(gen(k) for k in n.kids) + ")"
        return gen(self.root), args

    # ── FTS5 ──
    def fts(self, prefix: bool = True, xform=None) -> str:
        """식 나무 → FTS5 MATCH 식. 낱말은 `"글"*`(앞부분 일치), AND 의 NOT 은 FTS5 이항 NOT 으로(`(a AND b) NOT c`).
        낱말 안 큰따옴표는 두 겹으로. `xform(글)` 로 낱말을 바꿔 쓸 수 있다(사진 검색은 앞 `#` 를 뗀다). 찾을 낱말이 없으면 ''(부르는 쪽이 빈 결과)."""
        if self.root is None:
            return ""

        def term(n):
            w = (xform(n.text) if xform else n.text).replace('"', '""')
            return '"%s"%s' % (w, "*" if prefix else "")

        def gen(n):
            if n.op == "term":
                return term(n)
            if n.op == "or":
                return "(" + " OR ".join(gen(k) for k in n.kids) + ")"
            if n.op == "not":                           # _norm 뒤에는 AND 안에만 있다
                return gen(n.kids[0])
            pos = [gen(k) for k in n.kids if k.op != "not"]
            neg = [gen(k.kids[0]) for k in n.kids if k.op == "not"]
            s = "(" + " AND ".join(pos) + ")"
            for x in neg:
                s += " NOT " + (x if x.startswith("(") else "(" + x + ")")
            return s
        return gen(self.root)


def parse(q: str) -> Query:
    return Query(q)


def has_operators(q: str) -> bool:
    """질의가 연산자로 읽히는가(낱말 하나가 아님) — 종전 길을 탈지 가르는 데."""
    p = Query(q)
    return p.single is None
