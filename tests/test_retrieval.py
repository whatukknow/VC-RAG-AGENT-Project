import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from ragagent.bm25 import BM25, tokenize  # noqa: E402
from ragagent.chunking import chunk_document, split_sentences  # noqa: E402
from ragagent.fusion import rrf  # noqa: E402


def doc(text, name="X", one="one liner"):
    return {"doc_id": "yc-x", "name": name, "one_liner": one, "long_description": text}


class ChunkingTest(unittest.TestCase):
    def test_short_doc_is_single_chunk_with_offsets(self):
        t = "Alpha does inference. It is fast."
        cs = chunk_document(doc(t))
        self.assertEqual(len(cs), 1)
        self.assertEqual(cs[0].chunk_id, "yc-x#c00")
        self.assertEqual(t[cs[0].start:cs[0].end], cs[0].body)
        self.assertTrue(cs[0].text.startswith("X: one liner\n"))

    def test_long_doc_splits_with_overlap_and_offsets_valid(self):
        t = " ".join(f"Sentence number {i} talks about GPUs." for i in range(40))
        cs = chunk_document(doc(t), max_chars=200)
        self.assertGreater(len(cs), 3)
        for c in cs:
            self.assertEqual(t[c.start:c.end], c.body)
            self.assertLessEqual(len(c.body), 200)
        self.assertLess(cs[1].start, cs[0].end)          # 겹침
        self.assertEqual(cs[-1].end, len(t))             # 끝까지 덮음
        self.assertEqual(len({c.chunk_id for c in cs}), len(cs))

    def test_paragraph_break_splits_sentences(self):
        self.assertEqual(len(split_sentences("One thing\n\nAnother thing")), 2)

    def test_empty_doc(self):
        self.assertEqual(chunk_document(doc("   ")), [])


class Bm25Test(unittest.TestCase):
    def test_ranks_matching_doc_first_and_ignores_zero(self):
        b = BM25(["gpu kernels for inference", "photo sharing app", "serverless gpu cloud"])
        r = b.search("gpu kernels", 5)
        self.assertEqual(r[0][0], 0)
        self.assertNotIn(1, [i for i, _ in r])

    def test_tokenize_lowercases_and_drops_stopwords(self):
        self.assertEqual(tokenize("The GPU, and TTFT 10x!"), ["gpu", "ttft", "10x"])


class FusionTest(unittest.TestCase):
    def test_rrf_prefers_agreement(self):
        out = rrf({"bm25": ["a", "b", "c"], "vector": ["b", "a", "d"]})
        self.assertEqual([c for c, _, _ in out][:2], ["a", "b"])
        self.assertEqual(out[0][2], {"bm25": 1, "vector": 2})

    def test_rrf_dedups_within_list_and_handles_empty(self):
        out = rrf({"bm25": ["a", "a"], "vector": []})
        self.assertEqual(len(out), 1)
        self.assertEqual(rrf({}), [])

    def test_weights(self):
        out = rrf({"bm25": ["a"], "vector": ["b"]}, weights={"bm25": 1.0, "vector": 2.0})
        self.assertEqual(out[0][0], "b")


if __name__ == "__main__":
    unittest.main()
