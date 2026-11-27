import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from ragagent.answer import AnswerPipeline  # noqa: E402
from ragagent.generate import GEN_CONFIG, INSUFFICIENT_TEXT, build_documents, parse_output  # noqa: E402

CHUNKS = [
    {"chunk_id": f"d{i}#c00", "doc_id": f"d{i}", "text": f"Company{i}: one\nbody {i}", "start": 0, "end": 10}
    for i in range(1, 4)
]


class FakeRetriever:
    def __init__(self, chunks=CHUNKS, fail=False):
        self.chunks = chunks
        self.pos = {c["chunk_id"]: i for i, c in enumerate(chunks)}
        self.fail = fail

    def run(self, config, q):
        if self.fail:
            raise RuntimeError("index missing")
        return {"top": [{"chunk_id": c["chunk_id"], "score": 1.0 - i * 0.1} for i, c in enumerate(self.chunks)],
                "candidates": []}


class FakeGen:
    def __init__(self, text=None, exc=None):
        self.text, self.exc, self.prompts, self.prefills = text, exc, [], []

    def generate(self, system, user, max_new_tokens, prefill=None):
        self.prompts.append((system, user))
        self.prefills.append(prefill)
        if self.exc:
            raise self.exc
        return self.text, 12


def run(text=None, exc=None, retriever=None):
    gen = FakeGen(text, exc)
    return AnswerPipeline(retriever or FakeRetriever(), gen).answer("q?", "C"), gen


class ParseTest(unittest.TestCase):
    def test_answer_with_citations(self):
        p = parse_output("STATUS: ANSWER\nANSWER: Foo is fast [1] and cheap [2][1].")
        self.assertEqual((p["status"], p["citations"]), ("ANSWER", [1, 2]))

    def test_insufficient(self):
        p = parse_output("STATUS: INSUFFICIENT\nANSWER: " + INSUFFICIENT_TEXT)
        self.assertEqual((p["status"], p["citations"]), ("INSUFFICIENT", []))

    def test_missing_status_is_none(self):
        self.assertIsNone(parse_output("The answer is 42 [1].")["status"])

    def test_status_word_inside_answer_is_not_confused(self):
        self.assertEqual(parse_output("STATUS: ANSWER\nANSWER: status quo [1]")["status"], "ANSWER")

    def test_documents_are_numbered_from_one(self):
        doc = build_documents(CHUNKS[:2])
        self.assertTrue(doc.startswith("[1] Company1") and "\n\n[2] Company2" in doc)


class AnswerFlowTest(unittest.TestCase):
    def test_valid_citation_is_answered_and_resolved(self):
        rec, gen = run("STATUS: ANSWER\nANSWER: It is fast [2].")
        self.assertEqual(rec["status"], "answered")
        self.assertEqual(rec["citations"][0]["chunk_id"], "d2#c00")
        self.assertIn("Question: q?", gen.prompts[0][1])

    def test_answer_without_citation_is_blocked_not_returned(self):
        rec, _ = run("STATUS: ANSWER\nANSWER: It is fast.")
        self.assertEqual((rec["status"], rec["blocked_reason"]), ("insufficient_evidence", "no_valid_citation"))
        self.assertEqual(rec["answer"], INSUFFICIENT_TEXT)

    def test_citation_to_nonexistent_document_is_invalid(self):
        rec, _ = run("STATUS: ANSWER\nANSWER: It is fast [9].")
        self.assertEqual(rec["status"], "insufficient_evidence")
        self.assertEqual(rec["invalid_citations"], [9])

    def test_mixed_valid_and_invalid_keeps_only_valid(self):
        rec, _ = run("STATUS: ANSWER\nANSWER: A [1] B [9].")
        self.assertEqual((rec["status"], [c["n"] for c in rec["citations"]], rec["invalid_citations"]),
                         ("answered", [1], [9]))

    def test_model_refusal_is_insufficient_evidence(self):
        rec, _ = run("STATUS: INSUFFICIENT\nANSWER: " + INSUFFICIENT_TEXT)
        self.assertEqual(rec["status"], "insufficient_evidence")
        self.assertIsNone(rec["blocked_reason"])

    def test_format_error_is_error_not_refusal(self):
        rec, _ = run("Sure! The answer is 42.")
        self.assertEqual(rec["status"], "error_generation")

    def test_generation_exception_is_error_not_refusal(self):
        rec, _ = run(exc=TimeoutError("slow"))
        self.assertEqual(rec["status"], "error_generation")
        self.assertIn("TimeoutError", rec["error"])

    def test_retrieval_exception_is_error_retrieval(self):
        rec, gen = run("x", retriever=FakeRetriever(fail=True))
        self.assertEqual(rec["status"], "error_retrieval")
        self.assertEqual(gen.prompts, [])

    def test_context_is_limited_to_configured_chunks(self):
        many = [dict(CHUNKS[0], chunk_id=f"d{i}#c00", doc_id=f"d{i}", text=f"C{i}: x") for i in range(10)]
        rec, gen = run("STATUS: ANSWER\nANSWER: x [1].", retriever=FakeRetriever(many))
        self.assertEqual(len(rec["retrieved"]), GEN_CONFIG["context_chunks"])
        self.assertNotIn("[6]", gen.prompts[0][1])

    def test_prefill_from_config_is_passed_to_generator(self):
        _, gen = run("STATUS: ANSWER\nANSWER: x [1].")
        self.assertEqual(gen.prefills, [GEN_CONFIG["prefill"]])
        self.assertEqual(GEN_CONFIG["prefill"], "STATUS:")

    def test_prefilled_output_parses(self):
        # prefill 이 붙은 실제 출력 형태: 'STATUS:' + ' ANSWER\nANSWER: ... [1]'
        p = parse_output("STATUS:" + " ANSWER\nANSWER: Acme is fast [1].")
        self.assertEqual((p["status"], p["citations"]), ("ANSWER", [1]))

    def test_prompt_examples_do_not_use_eval_documents(self):
        from ragagent.generate import SYSTEM_PROMPT
        for name in ("Cerebrium", "Magnitude", "OneTriangle", "Touchmark", "Lucebox", "Cedana", "RunAnywhere"):
            self.assertNotIn(name, SYSTEM_PROMPT)

    def test_document_instructions_are_marked_as_data_in_prompt(self):
        _, gen = run("STATUS: ANSWER\nANSWER: x [1].")
        self.assertIn("untrusted data", gen.prompts[0][0])


if __name__ == "__main__":
    unittest.main()
