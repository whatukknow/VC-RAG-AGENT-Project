"""결합: Reciprocal Rank Fusion. BM25와 벡터 점수는 척도가 달라 점수 합산 대신 순위만 쓴다."""

RRF_CONFIG = {"k": 60, "weights": {"bm25": 1.0, "vector": 1.0}, "dedup": "chunk_id", "method": "rrf"}


def rrf(rankings, k=None, weights=None, top=None):
    """rankings: {name: [chunk_id, ...]} (순위 순). 반환: [(chunk_id, score, {name: rank})]"""
    k = RRF_CONFIG["k"] if k is None else k
    weights = weights or RRF_CONFIG["weights"]
    score, ranks = {}, {}
    for name, ids in rankings.items():
        seen = set()
        w = weights.get(name, 1.0)
        for r, cid in enumerate(ids, start=1):
            if cid in seen:          # 같은 목록 내 중복 제거
                continue
            seen.add(cid)
            score[cid] = score.get(cid, 0.0) + w / (k + r)
            ranks.setdefault(cid, {})[name] = r
    order = sorted(score, key=lambda c: (-score[c], c))
    out = [(c, score[c], ranks[c]) for c in order]
    return out[:top] if top else out
