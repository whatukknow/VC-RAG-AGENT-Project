"""색인·모델 로딩과 Retriever 조립."""
import json
import os

from .bm25 import BM25
from .embed import Embedder, load_or_build
from .pipeline import Retriever
from .rerank import Reranker

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def build_retriever(with_reranker=True):
    with open(os.path.join(ROOT, "data", "index", "chunks.jsonl"), encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f]
    with open(os.path.join(ROOT, "configs", "models.lock.json"), encoding="utf-8") as f:
        lock = json.load(f)
    emb = Embedder(os.path.join(ROOT, lock["embedding"]["local_dir"]))
    matrix, state = load_or_build(emb, [c["text"] for c in chunks], lock["embedding"]["revision"],
                                  os.path.join(ROOT, "data", "index"))
    rr = Reranker(os.path.join(ROOT, lock["reranker"]["local_dir"])) if with_reranker else None
    bm = BM25([c["text"] for c in chunks])
    return Retriever(chunks, bm, matrix, emb, rr), {"embedding_cache": state, "models": lock, "n_chunks": len(chunks)}
