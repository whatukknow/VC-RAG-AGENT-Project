import json
import os
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from ragagent.answer import AnswerPipeline  # noqa: E402
from ragagent.errors import BudgetExceeded  # noqa: E402
from ragagent.generate import OPENAI_GEN_CONFIG, SYSTEM_PROMPT_API  # noqa: E402
from ragagent.generate_openai import OpenAIGenerator  # noqa: E402
from ragagent.rewrite import Rewriter  # noqa: E402


def response(text="STATUS: ANSWER\nANSWER: x [1].", in_tok=1000, out_tok=100, reasoning=40, status="completed",
             reason=None):
    return types.SimpleNamespace(
        output_text=text, status=status, model="gpt-6-luna-served", id="resp_1", _request_id="req_abc",
        incomplete_details=types.SimpleNamespace(reason=reason) if reason else None,
        usage=types.SimpleNamespace(input_tokens=in_tok, output_tokens=out_tok,
                                    output_tokens_details=types.SimpleNamespace(reasoning_tokens=reasoning)))


class FakeClient:
    def __init__(self, resp=None, exc=None):
        self.calls, self._resp, self._exc = [], resp or response(), exc
        self.responses = types.SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        if self._exc:
            raise self._exc
        return self._resp


def make(tmp, client=None, cap=5.0):
    return OpenAIGenerator(os.path.join(tmp, "ledger.jsonl"), client=client or FakeClient(),
                           cfg=dict(OPENAI_GEN_CONFIG, budget_usd=cap))


class RequestShapeTest(unittest.TestCase):
    def test_request_has_only_verified_params_no_sampling_no_prefill_store_false(self):
        with tempfile.TemporaryDirectory() as d:
            client = FakeClient()
            make(d, client).generate("sys", "usr", 1024)
            kw = client.calls[0]
            self.assertEqual(set(kw), {"model", "instructions", "input", "max_output_tokens", "reasoning", "store"})
            self.assertEqual((kw["model"], kw["reasoning"], kw["store"]), ("gpt-6-luna", {"effort": "low"}, False))
            self.assertEqual((kw["instructions"], kw["input"]), ("sys", "usr"))
            for banned in ("temperature", "top_p", "seed", "text"):
                self.assertNotIn(banned, kw)

    def test_short_requests_still_get_reasoning_headroom(self):
        with tempfile.TemporaryDirectory() as d:
            client = FakeClient()
            make(d, client).generate("s", "u", 48)
            self.assertEqual(client.calls[0]["max_output_tokens"], OPENAI_GEN_CONFIG["min_max_tokens"])

    def test_prefill_is_rejected_before_any_call(self):
        with tempfile.TemporaryDirectory() as d:
            client = FakeClient()
            with self.assertRaises(ValueError):
                make(d, client).generate("s", "u", 100, prefill="STATUS:")
            self.assertEqual(client.calls, [])

    def test_text_and_output_tokens_returned(self):
        with tempfile.TemporaryDirectory() as d:
            text, n = make(d, FakeClient(response("  STATUS: ANSWER\nANSWER: ok [1].  ", out_tok=77))).generate("s", "u")
            self.assertEqual((text, n), ("STATUS: ANSWER\nANSWER: ok [1].", 77))


class FailureHandlingTest(unittest.TestCase):
    def test_incomplete_response_is_an_error_not_a_truncated_answer(self):
        with tempfile.TemporaryDirectory() as d:
            gen = make(d, FakeClient(response("STATUS: ANSWER\nANSWER: cut", status="incomplete", reason="max_output_tokens")))
            with self.assertRaises(RuntimeError) as cm:
                gen.generate("s", "u")
            self.assertIn("max_output_tokens", str(cm.exception))
            self.assertGreater(gen.ledger.spent(), 0)  # 실패한 호출의 비용도 기록한다

    def test_empty_output_text_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):
                make(d, FakeClient(response(text="   "))).generate("s", "u")

    def test_failed_status_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):
                make(d, FakeClient(response(status="failed"))).generate("s", "u")


class LedgerTest(unittest.TestCase):
    def test_cost_counts_reasoning_inside_output_and_records_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            gen = make(d, FakeClient(response(in_tok=1_000_000, out_tok=1_000_000, reasoning=900_000)))
            gen.generate("s", "u")
            with open(os.path.join(d, "ledger.jsonl"), encoding="utf-8") as f:
                e = json.loads(f.readline())
            self.assertAlmostEqual(e["cost_usd"], 0.10 + 0.50, places=6)  # 추론 토큰은 출력에 포함돼 이미 합산됨
            self.assertEqual((e["request_id"], e["response_id"], e["served_model"], e["reasoning_tokens"]),
                             ("req_abc", "resp_1", "gpt-6-luna-served", 900_000))

    def test_budget_blocks_before_calling_the_api(self):
        with tempfile.TemporaryDirectory() as d:
            client = FakeClient()
            gen = make(d, client, cap=0.0001)
            gen.ledger.record({"cost_usd": 0.0001})
            with self.assertRaises(BudgetExceeded):
                gen.generate("s", "u")
            self.assertEqual(client.calls, [])


class PipelineIntegrationTest(unittest.TestCase):
    CHUNKS = [{"chunk_id": "d1#c00", "doc_id": "d1", "text": "Co1: x\nbody", "start": 0, "end": 5}]

    class Retr:
        def __init__(self, chunks):
            self.chunks, self.pos = chunks, {c["chunk_id"]: i for i, c in enumerate(chunks)}

        def run(self, config, q):
            return {"top": [{"chunk_id": "d1#c00", "score": 1.0}], "candidates": []}

    def test_answer_uses_api_prompt_and_records_meta(self):
        with tempfile.TemporaryDirectory() as d:
            client = FakeClient()
            rec = AnswerPipeline(self.Retr(self.CHUNKS), make(d, client)).answer("q?", "C")
            self.assertEqual(rec["status"], "answered")
            self.assertEqual(rec["llm_meta"]["request_id"], "req_abc")
            self.assertEqual(client.calls[0]["instructions"], SYSTEM_PROMPT_API)
            self.assertIn("Question: q?", client.calls[0]["input"])

    def test_incomplete_generation_becomes_error_generation(self):
        with tempfile.TemporaryDirectory() as d:
            gen = make(d, FakeClient(response(status="incomplete", reason="max_output_tokens")))
            rec = AnswerPipeline(self.Retr(self.CHUNKS), gen).answer("q?", "C")
            self.assertEqual(rec["status"], "error_generation")

    def test_budget_exceeded_propagates_through_pipeline_and_rewriter(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(BudgetExceeded):
                AnswerPipeline(self.Retr(self.CHUNKS), make(d, FakeClient(), cap=0.0)).answer("q?", "C")
            with self.assertRaises(BudgetExceeded):
                Rewriter(make(d, FakeClient(), cap=0.0)).rewrite("Which company?")


if __name__ == "__main__":
    unittest.main()
