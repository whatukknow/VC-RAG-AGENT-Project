"""검색 구성 A/B/C.
A: Vector 단독  B: BM25+Vector(RRF)  C: B 후보를 reranker로 재정렬
설정은 결과를 보기 전에 고정했다(PIPELINE_CONFIG). 바꾸면 사유를 docs/problem.md 변경 기록에 남긴다.
"""
from .embed import top_k
from .fusion import rrf

PIPELINE_CONFIG = {"top_k": 5, "candidates_each": 20, "rerank_input_n": 10, "rrf_k": 60,
                   "rrf_weights": {"bm25": 1.0, "vector": 1.0}, "version": "pipe-v1"}


class Retriever:
    def __init__(self, chunks, bm25, matrix, embedder, reranker=None, cfg=None):
        self.chunks, self.bm25, self.matrix = chunks, bm25, matrix
        self.embedder, self.reranker = embedder, reranker
        self.cfg = cfg or PIPELINE_CONFIG
        self.ids = [c["chunk_id"] for c in chunks]
        self.pos = {cid: i for i, cid in enumerate(self.ids)}

    # --- 개별 검색기 ---
    def vector(self, q, k):
        return [(self.ids[i], s) for i, s in top_k(self.matrix, self.embedder.encode_query(q), k)]

    def lexical(self, q, k):
        return [(self.ids[i], s) for i, s in self.bm25.search(q, k)]

    # --- 구성 ---
    def run(self, config, q):
        k, n = self.cfg["top_k"], self.cfg["candidates_each"]
        if config == "A":
            res = self.vector(q, k)
            return {"config": "A", "top": [{"chunk_id": c, "score": s} for c, s in res], "candidates": []}
        vec, lex = self.vector(q, n), self.lexical(q, n)
        fused = rrf({"bm25": [c for c, _ in lex], "vector": [c for c, _ in vec]},
                    k=self.cfg["rrf_k"], weights=self.cfg["rrf_weights"])
        cands = [{"chunk_id": c, "rrf": s, "ranks": r} for c, s, r in fused]
        if config == "B":
            return {"config": "B", "top": [{"chunk_id": d["chunk_id"], "score": d["rrf"]} for d in cands[:k]],
                    "candidates": cands}
        if config == "C":
            if self.reranker is None:
                raise ValueError("구성 C 는 reranker 가 필요하다(build_retriever(with_reranker=True)).")
            pool = cands[:self.cfg["rerank_input_n"]]
            texts = [self.chunks[self.pos[d["chunk_id"]]]["text"] for d in pool]
            scores = self.reranker.score(q, texts)
            for r, d in enumerate(pool, start=1):
                d["pre_rank"] = r
            for d, s in zip(pool, scores):
                d["rerank_score"] = s
            ordered = sorted(pool, key=lambda d: (-d["rerank_score"], d["pre_rank"]))
            for r, d in enumerate(ordered, start=1):
                d["post_rank"] = r
            return {"config": "C", "top": [{"chunk_id": d["chunk_id"], "score": d["rerank_score"]} for d in ordered[:k]],
                    "candidates": pool}
        raise ValueError(f"unknown config {config}")
