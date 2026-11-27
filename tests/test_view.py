import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from ragagent import view  # noqa: E402

CHUNKS = [
    {"chunk_id": "yc-a#c00", "doc_id": "yc-a", "name": "Alpha", "start": 0, "end": 20, "body": "Alpha body text.", "text": "t"},
    {"chunk_id": "yc-b#c00", "doc_id": "yc-b", "name": "Beta", "start": 5, "end": 30, "body": "Beta body text.", "text": "t"},
]
BY_ID = view.chunk_index(CHUNKS)
LINKS = {"yc-a": "https://example.com/a"}


def rec(**kw):
    base = {"status": "answered", "answer": "x [1]", "citations": [{"n": 1, "chunk_id": "yc-a#c00", "doc_id": "yc-a",
            "span": [0, 20]}], "retrieved": [{"n": 1, "chunk_id": "yc-a#c00", "doc_id": "yc-a", "span": [0, 20], "score": 0.91234},
            {"n": 2, "chunk_id": "yc-b#c00", "doc_id": "yc-b", "span": [5, 30], "score": 0.5}], "timing_ms": {}}
    base.update(kw)
    return base


class StatusTest(unittest.TestCase):
    def test_errors_are_visually_distinct_from_insufficient_evidence(self):
        self.assertEqual(view.status_view("answered")[1], "success")
        self.assertEqual(view.status_view("insufficient_evidence")[1], "warning")
        self.assertEqual(view.status_view("error_generation")[1], "error")
        self.assertEqual(view.status_view("error_retrieval")[1], "error")
        self.assertIn("근거 부족이 아님", view.status_view("error_generation")[0])

    def test_unknown_status_is_shown_as_error_not_hidden(self):
        label, level = view.status_view("weird")
        self.assertEqual(level, "error")
        self.assertIn("weird", label)


class TableTest(unittest.TestCase):
    def test_citation_rows_use_retrieved_chunks_with_source_link(self):
        rows = view.citation_rows(rec(), BY_ID, LINKS)
        self.assertEqual(rows, [{"번호": "[1]", "회사": "Alpha", "청크 ID": "yc-a#c00", "원문 위치": "0–20",
                                 "출처": "https://example.com/a"}])

    def test_missing_link_and_unknown_chunk_do_not_crash(self):
        r = rec(citations=[{"n": 2, "chunk_id": "yc-b#c00", "doc_id": "yc-b", "span": [5, 30]},
                           {"n": 3, "chunk_id": "ghost#c00", "doc_id": "ghost", "span": [0, 1]}])
        rows = view.citation_rows(r, BY_ID, LINKS)
        self.assertEqual((rows[0]["출처"], rows[1]["회사"]), ("", "(알 수 없음)"))
        self.assertEqual(view.evidence_blocks(r, BY_ID)[1][3], "")

    def test_evidence_blocks_show_original_body(self):
        self.assertEqual(view.evidence_blocks(rec(), BY_ID), [(1, "Alpha", "yc-a#c00", "Alpha body text.")])

    def test_retrieved_rows_mark_cited_chunks_and_round_scores(self):
        rows = view.retrieved_rows(rec()["retrieved"], BY_ID, LINKS, cited_ids={"yc-a#c00"})
        self.assertEqual([(r["순위"], r["회사"], r["점수"], r["인용됨"]) for r in rows],
                         [(1, "Alpha", 0.9123, "예"), (2, "Beta", 0.5, "")])
        self.assertEqual(rows[0]["출처"], "https://example.com/a")

    def test_retrieval_only_record_adds_doc_id(self):
        out = view.retrieval_only_record({"top": [{"chunk_id": "yc-b#c00", "score": 0.3}]}, BY_ID)
        self.assertEqual(out, [{"n": 1, "chunk_id": "yc-b#c00", "doc_id": "yc-b", "score": 0.3}])


class InfoTest(unittest.TestCase):
    def test_rewrite_view_none_without_rewrite_and_shows_fallback(self):
        self.assertIsNone(view.rewrite_view(rec()))
        r = rec(rewrite={"original": "Q", "rewritten": "q2", "used": "Q", "fallback_reason": "intent_guard",
                         "missing_tokens": ["40"], "error": None})
        v = view.rewrite_view(r)
        self.assertEqual((v["fallback"], v["누락된 필수 토큰"], v["검색에 사용한 질의"]), ("intent_guard", "40", "Q"))

    def test_timing_text(self):
        self.assertEqual(view.timing_text(rec(timing_ms={})), "측정 없음")
        t = view.timing_text(rec(timing_ms={"retrieval": 1500, "generation": 1000, "total": 2500}, rewrite={"original": "q"}))
        self.assertEqual(t, "검색(리라이트 포함) 1.50초 · 생성 1.00초 · 전체 2.50초")

    def test_llm_text_empty_without_meta_and_never_contains_key_like_data(self):
        self.assertEqual(view.llm_text(rec()), "")
        t = view.llm_text(rec(llm_meta={"served_model": "m", "input_tokens": 10, "output_tokens": 5, "cost_usd": 0.00001,
                                        "request_id": "req_1"}))
        self.assertIn("req_1", t)
        self.assertNotIn("sk-", t)

    def test_spent_text_sums_ledger_and_handles_missing_file(self):
        self.assertEqual(view.spent_text("/no/such/ledger.jsonl", 5.0)[1], 0.0)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "l.jsonl")
            with open(p, "w", encoding="utf-8") as f:
                f.write(json.dumps({"cost_usd": 0.25}) + "\n\n" + json.dumps({"cost_usd": 0.5}) + "\n")
            text, total = view.spent_text(p, 5.0)
            self.assertAlmostEqual(total, 0.75)
            self.assertEqual(text, "누적 $0.7500 / 한도 $5.00")

    def test_load_doc_links_reads_bom_csv_and_missing_file(self):
        self.assertEqual(view.load_doc_links("/no/such.csv"), {})
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "l.csv")
            with open(p, "w", encoding="utf-8-sig", newline="") as f:
                f.write("doc_id,title,source_url\r\nyc-a,A,https://x/a\r\n")
            self.assertEqual(view.load_doc_links(p), {"yc-a": "https://x/a"})


if __name__ == "__main__":
    unittest.main()
