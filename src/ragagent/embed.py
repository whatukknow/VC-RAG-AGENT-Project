"""임베딩 모델 래퍼와 벡터 색인(디스크 캐시). 모델 리비전·청크 내용이 바뀌면 캐시를 무효화한다."""
import hashlib
import json
import os

import numpy as np

EMBED_CONFIG = {
    "model": "BAAI/bge-small-en-v1.5",
    "query_prefix": "Represent this sentence for searching relevant passages: ",  # bge 권장 질의 접두
    "normalize": True,
    "device": "cpu",
    "similarity": "cosine(=dot of normalized)",
}


class Embedder:
    def __init__(self, local_dir, device=None):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(local_dir, device=device or EMBED_CONFIG["device"])

    def encode_docs(self, texts):
        return np.asarray(self.model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False),
                          dtype="float32")

    def encode_query(self, q):
        return np.asarray(self.model.encode([EMBED_CONFIG["query_prefix"] + q], normalize_embeddings=True,
                                            show_progress_bar=False)[0], dtype="float32")


def content_key(texts, revision):
    h = hashlib.sha256(revision.encode())
    for t in texts:
        h.update(b"\x00" + t.encode("utf-8"))
    return h.hexdigest()


def load_or_build(embedder, texts, revision, cache_dir):
    """캐시 키(청크 텍스트+모델 리비전)가 같으면 재사용, 다르면 재계산. 반환: (matrix, 'hit'|'built')"""
    os.makedirs(cache_dir, exist_ok=True)
    npy, meta = os.path.join(cache_dir, "embeddings.npy"), os.path.join(cache_dir, "embeddings_meta.json")
    key = content_key(texts, revision)
    if os.path.exists(npy) and os.path.exists(meta):
        with open(meta, encoding="utf-8") as f:
            cached_key = json.load(f).get("key")
        if cached_key == key:
            m = np.load(npy)
            if m.shape[0] == len(texts):
                return m, "hit"
    m = embedder.encode_docs(texts)
    np.save(npy, m)
    with open(meta, "w", encoding="utf-8") as f:
        json.dump({"key": key, "revision": revision, "n": len(texts), "dim": int(m.shape[1])}, f)
    return m, "built"


def top_k(matrix, qvec, k):
    """코사인 유사도 상위 k. 동점은 인덱스 순. 반환: [(idx, score)]"""
    sims = matrix @ qvec
    order = sorted(range(len(sims)), key=lambda i: (-float(sims[i]), i))
    return [(i, float(sims[i])) for i in order[:k]]
