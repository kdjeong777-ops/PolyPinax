"""손잡이 더블클릭으로 인접 패널을 접기/펴기하는 QSplitter (260616-12).

손잡이(handle[i])를 마우스로 더블클릭하면 그 **왼쪽(작은 인덱스) 패널**을
숨김/보이기 토글한다. 접을 때의 폭을 기억해 다시 펼 때 복원한다.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QSplitter, QSplitterHandle


class _ToggleHandle(QSplitterHandle):
    # 261128-5(디자인 SOT §2.4): 손잡이 표식(점 3개)은 앱 스타일 CE_Splitter 한 곳이 그린다 — 종전 가운데 회색 막대는
    #   스크롤 손잡이와 같은 꼴이라 헷갈렸다. 여기서 따로 그리지 않는다(맨 QSplitter 와 같은 그림).

    def mouseDoubleClickEvent(self, ev):
        sp = self.splitter()
        idx = None
        for k in range(sp.count()):
            if sp.handle(k) is self:
                idx = k
                break
        if idx is not None and idx > 0:
            sp.toggle_section(idx - 1)
        super().mouseDoubleClickEvent(ev)


class ToggleSplitter(QSplitter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setChildrenCollapsible(True)
        self._saved_sizes: dict = {}

    def createHandle(self):
        return _ToggleHandle(self.orientation(), self)

    def toggle_section(self, idx: int):
        sizes = self.sizes()
        n = len(sizes)
        if not (0 <= idx < n):
            return
        if sizes[idx] > 4:                       # 펼쳐져 있음 → 접기
            self._saved_sizes[idx] = sizes[idx]
            freed = sizes[idx]
            sizes[idx] = 0
            others = [k for k in range(n) if k != idx]
            if others:
                j = max(others, key=lambda k: sizes[k])
                sizes[j] += freed
        else:                                    # 접혀 있음 → 펴기
            w = self._saved_sizes.get(idx, 220)
            j = max(range(n), key=lambda k: sizes[k])
            take = min(w, max(0, sizes[j] - 80))
            if take <= 0:
                take = w
            sizes[idx] = take
            sizes[j] = max(0, sizes[j] - take)
        self.setSizes(sizes)
