"""명함 인식 배우기 — 확인 표에서 확정한 결과로 이 PC 안에서만 (명함 SOT §5.11, 사용자 결정 '둘 다').

1. **이름 점수 가중치** — 확정한 명함마다 후보들의 특징(`Cand.feat`)과 '확정한 것인가' 를 표본으로 남기고
   (이름 글자는 남기지 않는다), 로지스틱 회귀로 `recognize.NAME_W` 를 고친다. 표본이 적을 때 엉뚱해지지 않게
   기본 가중치 쪽으로 당기는 벌점(사전)을 둔다. 표본 `MIN_SAMPLES` 명 이상일 때만 쓴다.
2. **양식 위치** — 확정 이름·회사가 후보였으면 그 줄 가운데 둘레 상자를 회사 열쇠(`layout_key`)로 기억한다(자동, 두 번 이상 맞으면 씀).
   사용자가 미리 보기에 그린 상자는 곧바로 쓴다(`manual`).
3. **도메인 → 직장** — 회사를 확정한 명함의 회사 도메인을 기억한다.
외부로 보내는 것은 없다(§2.1).
"""
from __future__ import annotations

import math
from typing import Optional

from viewer.bizcard import recognize as R

MIN_SAMPLES = 30          # 이만큼 확정해야 배운 가중치를 쓴다
PRIOR = 0.5               # 기본 가중치 쪽으로 당기는 힘(L2)
EPOCHS = 300
LR = 0.05
AUTO_BOX = (0.10, 0.05)   # 자동 양식 상자 — 줄 가운데에서 가로·세로 반폭(그림 비율)
WEIGHTS_KEY = "name_weights"


def sample_of(row: dict, result: dict) -> Optional[dict]:
    """확정 이름과 후보 특징 → 표본 {"feats": [[…]], "y": [0/1]} — 확정 이름이 후보에 없으면 None(배울 것이 없다)."""
    cands = result.get("name_cands") or []
    name = row.get("name") or ""
    if not name or not any(c.get("text") == name for c in cands):
        return None
    feats, ys = [], []
    for c in cands:
        f = c.get("feat") or {}
        if not f:
            continue
        feats.append([float(f.get(k, 0.0)) for k in R.NAME_FEATS])
        ys.append(1 if c.get("text") == name else 0)
    return {"feats": feats, "y": ys} if feats and any(ys) else None


def train(samples: list, base: Optional[dict] = None) -> Optional[dict]:
    """표본들 → 가중치 사전. 표본이 모자라면 None(기본값을 쓴다)."""
    if len(samples) < MIN_SAMPLES:
        return None
    import numpy as np
    base = dict(base or R.NAME_W)
    keys = list(R.NAME_FEATS)
    w0 = np.array([base.get(k, 0.0) for k in keys], dtype=float)
    X = np.array([x for s in samples for x in s["feats"]], dtype=float)
    Y = np.array([y for s in samples for y in s["y"]], dtype=float)
    if not len(X) or X.shape[1] != len(keys):
        return None
    w = w0.copy()
    for _ in range(EPOCHS):
        p = 1.0 / (1.0 + np.exp(-np.clip(X @ w, -30, 30)))
        g = X.T @ (p - Y) / len(X) + PRIOR * (w - w0) / len(samples)
        w -= LR * 10 * g
    return {k: round(float(v), 4) for k, v in zip(keys, w)}


def top1_accuracy(samples: list, weights: Optional[dict] = None) -> float:
    """표본에서 1위 후보가 확정 이름인 비율 — 배운 가중치가 실제로 나은지 견준다."""
    if not samples:
        return 0.0
    keys = list(R.NAME_FEATS)
    w = [(weights or R.NAME_W).get(k, 0.0) for k in keys]
    ok = 0
    for s in samples:
        scores = [sum(a * b for a, b in zip(w, x)) for x in s["feats"]]
        best = max(range(len(scores)), key=lambda i: scores[i])
        ok += int(s["y"][best] == 1)
    return ok / len(samples)


def learn_from(store, rows: list, results: dict) -> dict:
    """[적용] 뒤 — 표본·양식·도메인을 남기고 가중치를 다시 배운다. 반환 {'weights': 사전 또는 None, 'acc': (기본, 배운)}."""
    for row in rows:
        res = results.get(row["key"]) or {}
        smp = sample_of(row, res)
        if smp:
            store.sample_put(row["key"], smp)
        key = R.layout_key(row.get("emails"), row.get("urls"), row.get("company", ""))
        for fld, cands in (("name", res.get("name_cands")), ("company", res.get("company_cands"))):
            val = row.get(fld) or ""
            hit = next((c for c in cands or [] if c.get("text") == val and (c.get("feat") or {}).get("cx") is not None
                        and not (c.get("feat") or {}).get("back")), None)
            if key and hit:
                f = hit["feat"]
                store.layout_put(key, fld, (f["cx"] - AUTO_BOX[0], f["cy"] - AUTO_BOX[1],
                                            f["cx"] + AUTO_BOX[0], f["cy"] + AUTO_BOX[1]))
        comp = R.strip_corp(row.get("company") or "")
        if comp:
            for raw in list(row.get("urls") or []) + list(row.get("emails") or []):
                d = R.domain_of(raw)
                if d and not any(d == f or d.startswith(f + ".") for f in R.FREE_MAIL) and not d.endswith("korea.kr"):
                    store.domain_put(d, comp)
                    break
    smps = store.samples()
    w = train(smps)
    acc = (top1_accuracy(smps), top1_accuracy(smps, w) if w else None)
    if w and acc[1] is not None and acc[1] >= acc[0]:
        store.meta_set(WEIGHTS_KEY, w)                # 기본보다 나쁘지 않을 때만 바꾼다
    return {"weights": w, "acc": acc}


def weights_of(store) -> Optional[dict]:
    return store.meta_get(WEIGHTS_KEY)
