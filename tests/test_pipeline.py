import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from ragagent.bm25 import BM25  # noqa: E402
from ragagent.embed import load_or_build, top_k  # noqa: E402
from ragagent.pipeline import PIPELINE_CONFIG, Retriever  # noqa: E402

VOCAB = ["gpu", "kernel", "cloud", "photo", "voice", "cost", "router", "chip"]


class FakeEmbedder:
    """단어 포함 여부로 만든 결정적 벡터(정규화)."""
    def __init__(self):
        self.calls = 0

    def _v(self, t):
        v = np.array([1.0 if w in t.lower() else 0.0 for w in VOCAB], dtype="float32")
        n = np.linalg.norm(v)
        return v / n if n else v

    def encode_docs(self, texts):
        self.calls += 1
        return np.stack([self._v(t) for t in texts])

    def encode_query(self, q):
        return self._v(q)


class FakeReranker:
    """질의와 겹치는 단어 수가 많을수록 높은 점수. 호출한 입력 수를 기록한다."""
    def __init__(self):
        self.seen = []

    def score(self, q, texts):
        self.seen.append(len(texts))
        qs = set(q.lower().split())
        return [float(len(qs & set(t.lower().split()))) for t in texts]


TEXTS = ["gpu kernel cloud", "photo sharing", "voice gpu", "cost router", "chip gpu kernel", "cloud cost"]
CHUNKS = [{"chunk_id": f"d{i}#c00", "text": t} for i, t in enumerate(TEXTS)]


def make(rr=None, cfg=None):
    emb = FakeEmbedder()
    return Retriever(CHUNKS, BM25(TEXTS), emb.encode_docs(TEXTS), emb, rr, cfg), emb


class EmbedCacheTest(unittest.TestCase):
    def test_cache_hit_rebuild_on_change_and_revision(self):
        emb = FakeEmbedder()
        with tempfile.TemporaryDirectory() as d:
            _, s1 = load_or_build(emb, TEXTS, "rev1", d)
            _, s2 = load_or_build(emb, TEXTS, "rev1", d)
            _, s3 = load_or_build(emb, TEXTS + ["new chunk"], "rev1", d)
            _, s4 = load_or_build(emb, TEXTS + ["new chunk"], "rev2", d)
        self.assertEqual((s1, s2, s3, s4), ("built", "hit", "built", "built"))
        self.assertEqual(emb.calls, 3)

    def test_top_k_orders_by_cosine_and_breaks_ties_by_index(self):
        m = np.array([[1, 0], [0, 1], [1, 0]], dtype="float32")
        self.assertEqual([i for i, _ in top_k(m, np.array([1, 0], dtype="float32"), 3)], [0, 2, 1])


class PipelineTest(unittest.TestCase):
    def test_A_is_vector_only_and_limited_to_top_k(self):
        r, _ = make()
        out = r.run("A", "gpu kernel")
        self.assertEqual(len(out["top"]), PIPELINE_CONFIG["top_k"])
        self.assertEqual(out["top"][0]["chunk_id"], "d0#c00")
        self.assertEqual(out["candidates"], [])

    def test_B_fuses_both_rankers_and_records_ranks(self):
        r, _ = make()
        out = r.run("B", "gpu kernel")
        first = out["candidates"][0]
        self.assertEqual(first["chunk_id"], "d0#c00")
        self.assertEqual(set(first["ranks"]), {"bm25", "vector"})

    def test_B_lexical_only_hit_survives_fusion(self):
        # 벡터 어휘에 없는 단어는 벡터로 못 찾지만 BM25가 찾아 결합 후보에 남아야 한다.
        texts = TEXTS + ["zebra unique term"]
        emb = FakeEmbedder()
        chunks = CHUNKS + [{"chunk_id": "d6#c00", "text": texts[-1]}]
        r = Retriever(chunks, BM25(texts), emb.encode_docs(texts), emb, None)
        ids = [c["chunk_id"] for c in r.run("B", "zebra")["candidates"]]
        self.assertIn("d6#c00", ids)

    def test_C_reranks_only_top_n_and_records_pre_post_rank(self):
        rr = FakeReranker()
        r, _ = make(rr, dict(PIPELINE_CONFIG, rerank_input_n=3))
        out = r.run("C", "gpu kernel cloud")
        self.assertEqual(rr.seen, [3])
        self.assertEqual(len(out["candidates"]), 3)
        self.assertEqual(sorted(d["post_rank"] for d in out["candidates"]), [1, 2, 3])
        self.assertTrue(all("pre_rank" in d and "rerank_score" in d for d in out["candidates"]))
        scores = [t["score"] for t in out["top"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_C_can_change_order_relative_to_B(self):
        class Inverse(FakeReranker):
            def score(self, q, texts):
                return [-s for s in super().score(q, texts)]
        r, _ = make(Inverse(), dict(PIPELINE_CONFIG, rerank_input_n=4))
        b = [c["chunk_id"] for c in r.run("B", "gpu kernel cloud")["candidates"][:4]]
        c = [t["chunk_id"] for t in r.run("C", "gpu kernel cloud")["top"]]
        self.assertNotEqual(b, c)
        self.assertEqual(set(b), set(c))

    def test_unknown_config_raises(self):
        r, _ = make()
        with self.assertRaises(ValueError):
            r.run("Z", "x")


if __name__ == "__main__":
    unittest.main()
