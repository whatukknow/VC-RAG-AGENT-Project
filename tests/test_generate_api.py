import json
import os
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from ragagent.answer import AnswerPipeline  # noqa: E402
from ragagent.envfile import load_env, require_key  # noqa: E402
from ragagent.errors import BudgetExceeded  # noqa: E402
from ragagent.generate import API_GEN_CONFIG, SYSTEM_PROMPT_API, parse_output  # noqa: E402
from ragagent.generate_api import ApiGenerator, CostLedger  # noqa: E402
from ragagent.rewrite import Rewriter  # noqa: E402


def block(type_, text=None):
    return types.SimpleNamespace(type=type_, text=text, thinking=text if type_ == "thinking" else None)


def response(text="STATUS: ANSWER\nANSWER: x [1].", in_tok=1000, out_tok=100, stop="end_turn", with_thinking=False):
    content = ([block("thinking", "hidden reasoning")] if with_thinking else []) + [block("text", text)]
    return types.SimpleNamespace(content=content, usage=types.SimpleNamespace(input_tokens=in_tok, output_tokens=out_tok),
                                 model="claude-haiku-5-5-served", stop_reason=stop, stop_details=None, _request_id="req_123")


class FakeClient:
    def __init__(self, resp=None, exc=None):
        self.calls, self._resp, self._exc = [], resp or response(), exc
        self.messages = types.SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        if self._exc:
            raise self._exc
        return self._resp


def make(tmp, client=None, cap=5.0):
    cfg = dict(API_GEN_CONFIG, budget_usd=cap)
    return ApiGenerator(os.path.join(tmp, "ledger.jsonl"), client=client or FakeClient(), cfg=cfg)


class RequestShapeTest(unittest.TestCase):
    def test_request_has_no_sampling_params_and_no_prefill(self):
        with tempfile.TemporaryDirectory() as d:
            client = FakeClient()
            make(d, client).generate("sys", "usr", 1024)
            kw = client.calls[0]
            self.assertEqual(set(kw), {"model", "max_tokens", "system", "messages", "output_config"})
            self.assertEqual((kw["model"], kw["output_config"]), ("claude-haiku-5-5", {"effort": "low"}))
            self.assertEqual(kw["messages"], [{"role": "user", "content": "usr"}])  # 마지막이 user: prefill 없음

    def test_short_requests_still_get_thinking_headroom(self):
        with tempfile.TemporaryDirectory() as d:
            client = FakeClient()
            make(d, client).generate("sys", "usr", 48)  # 리라이트처럼 짧은 출력 요청
            self.assertEqual(client.calls[0]["max_tokens"], API_GEN_CONFIG["min_max_tokens"])

    def test_prefill_is_rejected_before_any_call(self):
        with tempfile.TemporaryDirectory() as d:
            client = FakeClient()
            with self.assertRaises(ValueError):
                make(d, client).generate("s", "u", 100, prefill="STATUS:")
            self.assertEqual(client.calls, [])

    def test_only_text_blocks_are_returned_thinking_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            text, n = make(d, FakeClient(response("STATUS: ANSWER\nANSWER: ok [1].", out_tok=77, with_thinking=True))).generate("s", "u")
            self.assertEqual((text, n), ("STATUS: ANSWER\nANSWER: ok [1].", 77))
            self.assertEqual(parse_output(text)["status"], "ANSWER")

    def test_prompt_v3_has_no_fewshot_examples_and_demands_status_line(self):
        self.assertNotIn("Acme", SYSTEM_PROMPT_API)
        self.assertNotIn("Example", SYSTEM_PROMPT_API)
        self.assertIn('first line must start with "STATUS:"', SYSTEM_PROMPT_API)


class LedgerTest(unittest.TestCase):
    def test_cost_formula_and_ledger_entry_with_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            gen = make(d, FakeClient(response(in_tok=1_000_000, out_tok=1_000_000)))
            gen.generate("s", "u")
            with open(os.path.join(d, "ledger.jsonl"), encoding="utf-8") as f:
                entry = json.loads(f.readline())
            self.assertAlmostEqual(entry["cost_usd"], 0.10 + 0.50, places=6)
            self.assertEqual((entry["request_id"], entry["served_model"], entry["requested_model"]),
                             ("req_123", "claude-haiku-5-5-served", "claude-haiku-5-5"))
            self.assertEqual(gen.last_meta["input_tokens"], 1_000_000)

    def test_budget_blocks_before_calling_the_api(self):
        with tempfile.TemporaryDirectory() as d:
            client = FakeClient()
            gen = make(d, client, cap=0.0001)
            gen.ledger.record({"cost_usd": 0.0001})  # 이미 한도만큼 썼다
            with self.assertRaises(BudgetExceeded):
                gen.generate("s", "u")
            self.assertEqual(client.calls, [])  # 호출 자체를 하지 않았다

    def test_spent_accumulates_across_calls_and_instances(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "l.jsonl")
            prices = API_GEN_CONFIG["prices_usd_per_mtok"]
            CostLedger(path, 5.0, prices).record({"cost_usd": 1.25})
            CostLedger(path, 5.0, prices).record({"cost_usd": 0.75})
            self.assertAlmostEqual(CostLedger(path, 5.0, prices).spent(), 2.0)

    def test_refusal_is_recorded_as_cost_and_raised_as_error(self):
        with tempfile.TemporaryDirectory() as d:
            gen = make(d, FakeClient(response(stop="refusal")))
            with self.assertRaises(RuntimeError):
                gen.generate("s", "u")
            self.assertGreater(gen.ledger.spent(), 0)


class PipelineIntegrationTest(unittest.TestCase):
    CHUNKS = [{"chunk_id": "d1#c00", "doc_id": "d1", "text": "Co1: x\nbody", "start": 0, "end": 5}]

    class Retr:
        def __init__(self, chunks):
            self.chunks, self.pos = chunks, {c["chunk_id"]: i for i, c in enumerate(chunks)}

        def run(self, config, q):
            return {"top": [{"chunk_id": "d1#c00", "score": 1.0}], "candidates": []}

    def test_success_records_llm_meta_and_uses_api_prompt_without_prefill(self):
        with tempfile.TemporaryDirectory() as d:
            client = FakeClient()
            pipe = AnswerPipeline(self.Retr(self.CHUNKS), make(d, client))
            rec = pipe.answer("q?", "C")
            self.assertEqual(rec["status"], "answered")
            self.assertEqual(rec["llm_meta"]["request_id"], "req_123")
            self.assertEqual(client.calls[0]["system"], SYSTEM_PROMPT_API)

    def test_budget_exceeded_is_not_swallowed_as_a_question_error(self):
        with tempfile.TemporaryDirectory() as d:
            gen = make(d, FakeClient(), cap=0.0)
            with self.assertRaises(BudgetExceeded):
                AnswerPipeline(self.Retr(self.CHUNKS), gen).answer("q?", "C")

    def test_api_error_becomes_error_generation_not_refusal(self):
        with tempfile.TemporaryDirectory() as d:
            pipe = AnswerPipeline(self.Retr(self.CHUNKS), make(d, FakeClient(exc=TimeoutError("slow"))))
            rec = pipe.answer("q?", "C")
            self.assertEqual(rec["status"], "error_generation")
            self.assertIn("TimeoutError", rec["error"])

    def test_rewriter_does_not_swallow_budget_exceeded(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(BudgetExceeded):
                Rewriter(make(d, FakeClient(), cap=0.0)).rewrite("Which company?")


class EnvFileTest(unittest.TestCase):
    def test_load_env_sets_only_missing_keys_and_never_returns_values(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, ".env")
            with open(path, "w", encoding="utf-8") as f:
                f.write("# comment\nTEST_KEY_NEW=secret-value\nTEST_KEY_EXIST=from-file\nEMPTY=\n\nbad line\n")
            os.environ["TEST_KEY_EXIST"] = "from-env"
            os.environ.pop("TEST_KEY_NEW", None)
            try:
                keys = load_env(path)
                self.assertEqual(keys, ["TEST_KEY_NEW"])
                self.assertEqual((os.environ["TEST_KEY_NEW"], os.environ["TEST_KEY_EXIST"]), ("secret-value", "from-env"))
                self.assertNotIn("secret-value", repr(keys))
            finally:
                os.environ.pop("TEST_KEY_NEW", None)
                os.environ.pop("TEST_KEY_EXIST", None)

    def test_missing_file_is_fine_and_missing_key_error_names_the_key_only(self):
        self.assertEqual(load_env(os.path.join(tempfile.gettempdir(), "no-such-dir-xyz", ".env")), [])
        os.environ.pop("ZZ_TEST_API_KEY", None)
        with self.assertRaises(RuntimeError) as cm:
            require_key("ZZ_TEST_API_KEY")
        self.assertIn("ZZ_TEST_API_KEY", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
