import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from ragagent.rewrite import REWRITE_CONFIG, SYSTEM_PROMPT, Rewriter, RewritingRetriever, intent_guard, must_keep  # noqa: E402

Q1 = "Which company reports a 40-50% improvement over existing neoclouds, and is it cost or latency?"
Q2 = "Which open-source inference engine tunes its kernels on the user's hardware, and how much faster than Ollama?"


class FakeGen:
    def __init__(self, text=None, exc=None):
        self.text, self.exc, self.calls = text, exc, []

    def generate(self, system, user, max_new_tokens):
        self.calls.append((system, user, max_new_tokens))
        if self.exc:
            raise self.exc
        return self.text, 9


class MustKeepTest(unittest.TestCase):
    def test_numbers_and_inner_capitalized_tokens_are_kept_first_word_is_not(self):
        self.assertEqual(must_keep(Q1), ["40", "50"])
        self.assertEqual(must_keep(Q2), ["Ollama"])

    def test_acronyms_and_names_are_kept(self):
        self.assertEqual(must_keep("What does the GPU live migration company claim for TTFT?"), ["GPU", "TTFT"])

    def test_guard_reports_missing_tokens_case_insensitively(self):
        self.assertEqual(intent_guard(Q2, "open source inference engine faster than ollama"), [])
        self.assertEqual(intent_guard(Q2, "open source inference engine kernels"), ["Ollama"])


class RewriterTest(unittest.TestCase):
    def test_good_rewrite_is_used_and_original_is_stored(self):
        rec = Rewriter(FakeGen("neocloud 40-50% improvement cost latency")).rewrite(Q1)
        self.assertEqual((rec["used"], rec["fallback_reason"]), ("neocloud 40-50% improvement cost latency", None))
        self.assertEqual(rec["original"], Q1)

    def test_only_the_question_is_sent_to_the_rewriter(self):
        gen = FakeGen("ollama kernels inference engine")
        Rewriter(gen).rewrite(Q2)
        system, user, n = gen.calls[0]
        self.assertEqual((system, user, n), (SYSTEM_PROMPT, Q2, REWRITE_CONFIG["max_new_tokens"]))

    def test_exception_falls_back_to_original(self):
        rec = Rewriter(FakeGen(exc=RuntimeError("boom"))).rewrite(Q1)
        self.assertEqual((rec["used"], rec["fallback_reason"]), (Q1, "error"))
        self.assertIn("RuntimeError", rec["error"])

    def test_empty_output_falls_back(self):
        self.assertEqual(Rewriter(FakeGen("   ")).rewrite(Q1)["fallback_reason"], "empty")

    def test_too_long_output_falls_back(self):
        self.assertEqual(Rewriter(FakeGen("x" * 500)).rewrite(Q1)["fallback_reason"], "too_long")

    def test_dropped_number_triggers_intent_guard_and_uses_original(self):
        rec = Rewriter(FakeGen("neoclouds improvement cost or latency")).rewrite(Q1)
        self.assertEqual((rec["used"], rec["fallback_reason"], rec["missing_tokens"]), (Q1, "intent_guard", ["40", "50"]))

    def test_only_first_line_and_quotes_are_stripped(self):
        rec = Rewriter(FakeGen('"ollama kernels engine"\nExplanation: ...')).rewrite(Q2)
        self.assertEqual(rec["used"], "ollama kernels engine")


class FakeBase:
    def __init__(self):
        self.chunks, self.pos, self.runs = [{"chunk_id": "a"}], {"a": 0}, []

    def run(self, config, q):
        self.runs.append((config, q))
        return {"top": [{"chunk_id": "a", "score": 1.0}], "candidates": []}


class RewritingRetrieverTest(unittest.TestCase):
    def test_c_plus_r_searches_with_rewritten_query_using_config_c(self):
        base = FakeBase()
        res = RewritingRetriever(base, Rewriter(FakeGen("ollama kernels engine"))).run("C+R", Q2)
        self.assertEqual(base.runs, [("C", "ollama kernels engine")])
        self.assertEqual(res["rewrite"]["original"], Q2)
        self.assertEqual(res["config"], "C+R")

    def test_other_configs_pass_through_without_rewriting(self):
        base, gen = FakeBase(), FakeGen("unused")
        res = RewritingRetriever(base, Rewriter(gen)).run("B", Q2)
        self.assertEqual((base.runs, gen.calls), ([("B", Q2)], []))
        self.assertNotIn("rewrite", res)

    def test_attributes_are_forwarded(self):
        wrapper = RewritingRetriever(FakeBase(), Rewriter(FakeGen("x")))
        self.assertEqual((wrapper.chunks[0]["chunk_id"], wrapper.pos["a"]), ("a", 0))


if __name__ == "__main__":
    unittest.main()
