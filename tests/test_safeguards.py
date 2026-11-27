"""고정(freeze)·근거 매핑·정규화·청킹 한도 등 안전장치 테스트(리뷰 지적 사항 회귀 방지)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from build_index import map_evidence  # noqa: E402
from eval_retrieval import score_question  # noqa: E402
from ragagent.chunking import chunk_document, wrap_span  # noqa: E402
from ragagent.freeze import (CODE_FILES, FINAL_FILES, FINAL_LOCK, build_final_lock, check_final_run,  # noqa: E402
                             final_results_exist, plan_refreeze, sha256_file, verify_files, verify_final_lock)
from ragagent.pipeline import Retriever  # noqa: E402
from ragagent.textnorm import find_span, norm  # noqa: E402

DOC = {"doc_id": "yc-x", "name": "X", "one_liner": "o", "long_description": "NVIDIA’s GPUs are fast. Second sentence here."}


class TextNormTest(unittest.TestCase):
    def test_curly_and_ascii_quotes_match_with_same_offsets(self):
        text = "NVIDIA’s confidential compute mode"
        for quote in ("NVIDIA's confidential", "NVIDIA’s confidential"):
            self.assertEqual(find_span(text, quote), (0, len("NVIDIA's confidential")))

    def test_whitespace_differences_are_tolerated_and_missing_returns_minus_one(self):
        self.assertEqual(find_span("a   b\nc", "a b c"), (0, 7))
        self.assertEqual(find_span("abc", "xyz"), (-1, -1))

    def test_norm_collapses_whitespace_and_folds_quotes(self):
        self.assertEqual(norm("It’s  a\n test"), "It's a test")


class ChunkLimitTest(unittest.TestCase):
    def test_long_sentence_without_terminal_punctuation_is_wrapped_within_limit(self):
        s = "- item " * 200  # 문장부호 없는 긴 목록(1400자)
        d = {"doc_id": "yc-l", "name": "L", "one_liner": "", "long_description": s}
        chunks = chunk_document(d, max_chars=300)
        self.assertGreater(len(chunks), 3)
        self.assertTrue(all(len(c.body) <= 300 for c in chunks))
        for c in chunks:
            self.assertEqual(s[c.start:c.end], c.body)

    def test_unbroken_token_is_hard_cut(self):
        spans = wrap_span("x" * 1000, (0, 1000), 400)
        self.assertEqual([b - a for a, b in spans], [400, 400, 200])


class EvidenceMappingTest(unittest.TestCase):
    def setUp(self):
        self.chunks = chunk_document(DOC, max_chars=30, overlap_sentences=0)
        self.by_doc = {"yc-x": self.chunks}
        self.text = {"yc-x": DOC["long_description"]}

    def q(self, quote, answerable=True):
        return {"id": "Q1", "answerable": answerable,
                "allowed_evidence": [{"doc_id": "yc-x", "quote": quote}] if quote else []}

    def test_ascii_quote_against_curly_source_resolves(self):
        cmap, fatal, _ = map_evidence([self.q("NVIDIA's GPUs")], self.by_doc, self.text)
        self.assertEqual(fatal, [])
        self.assertTrue(cmap["Q1"]["allowed_chunk_ids"])

    def test_unresolvable_quote_is_fatal_not_silent(self):
        cmap, fatal, _ = map_evidence([self.q("not in the document")], self.by_doc, self.text)
        self.assertTrue(any("인용 위치 없음" in m for _, m in fatal))
        self.assertTrue(any("비어 있다" in m for _, m in fatal))

    def test_no_evidence_question_may_have_empty_allowed_set(self):
        _, fatal, _ = map_evidence([self.q(None, answerable=False)], self.by_doc, self.text)
        self.assertEqual(fatal, [])

    def test_quote_straddling_chunks_warns_but_resolves_via_overlap(self):
        d = {"doc_id": "yc-x", "name": "X", "one_liner": "", "long_description": "aaaa bbbb cccc dddd eeee ffff"}
        chunks = chunk_document(d, max_chars=12, overlap_sentences=0)
        cmap, fatal, warn = map_evidence([self.q("bbbb cccc dddd eeee")],
                                         {"yc-x": chunks}, {"yc-x": d["long_description"]})
        self.assertEqual(fatal, [])
        self.assertTrue(warn)
        self.assertGreaterEqual(len(cmap["Q1"]["allowed_chunk_ids"]), 2)


class FullEvidenceMetricTest(unittest.TestCase):
    ENTRY = {"allowed_chunk_ids": ["d#c00", "d#c01"], "evidence_groups": [["d#c00"], ["d#c01"]]}

    def test_partial_recovery_is_hit_but_not_full(self):
        r = score_question(self.ENTRY, ["d#c00", "z#c00"])
        self.assertEqual((r["hit_at_5"], r["full_evidence_at_5"], r["rank"]), (1, 0, 1))

    def test_both_recovered_is_full(self):
        self.assertEqual(score_question(self.ENTRY, ["d#c01", "d#c00"])["full_evidence_at_5"], 1)

    def test_miss(self):
        r = score_question(self.ENTRY, ["z#c00"])
        self.assertEqual((r["hit_at_5"], r["full_evidence_at_5"], r["rank"]), (0, 0, None))


class FreezeTest(unittest.TestCase):
    def test_verify_files_detects_missing_and_modified(self):
        with tempfile.TemporaryDirectory() as root:
            p = os.path.join(root, "a.json")
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write('{"a": 1}')
            files = {"a.json": sha256_file(p), "gone.json": "0" * 64}
            self.assertEqual(verify_files(root, {"a.json": files["a.json"]}), [])
            errs = verify_files(root, files)
            self.assertEqual(errs, ["파일 없음: gone.json"])
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write('{"a": 2}')
            self.assertEqual(verify_files(root, {"a.json": files["a.json"]}), ["해시 불일치: a.json"])

    def _make_root(self, root):
        for rel in list(FINAL_FILES) + list(CODE_FILES):
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(rel)

    def _write_lock(self, root, **kw):
        lock = build_final_lock(root, git_commit="abc", **kw)
        os.makedirs(os.path.join(root, "configs"), exist_ok=True)
        with open(os.path.join(root, FINAL_LOCK), "w", encoding="utf-8") as f:
            json.dump(lock, f)
        return lock

    def test_code_change_after_freeze_is_detected_but_line_endings_are_ignored(self):
        with tempfile.TemporaryDirectory() as root:
            self._make_root(root)
            self._write_lock(root)
            target = os.path.join(root, "src/ragagent/answer.py")
            with open(target, "w", encoding="utf-8", newline="\r\n") as f:  # 같은 내용, 줄바꿈만 CRLF
                f.write("src/ragagent/answer.py")
            self.assertEqual(verify_final_lock(root), [])
            with open(target, "w", encoding="utf-8", newline="\n") as f:
                f.write("src/ragagent/answer.py\n# 한 줄 수정")
            self.assertEqual(verify_final_lock(root), ["고정 이후 코드가 바뀜: src/ragagent/answer.py"])

    def test_missing_code_file_blocks_freeze_creation(self):
        with tempfile.TemporaryDirectory() as root:
            self._make_root(root)
            os.remove(os.path.join(root, "src/run_answers.py"))
            with self.assertRaises(FileNotFoundError):
                build_final_lock(root)

    def test_final_run_rejects_a_backend_different_from_the_locked_one(self):
        with tempfile.TemporaryDirectory() as root:
            self._make_root(root)
            self._write_lock(root, final_backend="openai")
            self.assertEqual(check_final_run(root, "openai", ["C"], os.path.join(root, "r"), "answers"), [])
            errs = check_final_run(root, "local", ["C"], os.path.join(root, "r"), "answers")
            self.assertEqual(len(errs), 1)
            self.assertIn("openai", errs[0])

    def test_final_rerun_requires_reason_and_ignores_incomplete_files(self):
        with tempfile.TemporaryDirectory() as root:
            self._make_root(root)
            self._write_lock(root)
            res = os.path.join(root, "results", "test")
            os.makedirs(res)
            for name in ("answers_C_20261201T000000_INCOMPLETE.json", "answers_B_20261201T000000.json"):
                with open(os.path.join(res, name), "w", encoding="utf-8") as f:
                    f.write("{}")
            # 불완전 실행만 있는 구성은 다시 실행할 수 있고, 완료된 결과가 있는 구성은 사유가 필요하다
            self.assertEqual(check_final_run(root, "openai", ["C"], res, "answers"), [])
            self.assertEqual(len(check_final_run(root, "openai", ["B", "C"], res, "answers")), 1)
            self.assertEqual(check_final_run(root, "openai", ["B"], res, "answers", "API 일시 장애로 전체 재실행"), [])
            self.assertEqual(len(check_final_run(root, "openai", ["B"], res, "answers", "   ")), 1)  # 공백 사유는 무효

    def _results(self, root, *names):
        res = os.path.join(root, "results", "test")
        os.makedirs(res, exist_ok=True)
        for n in names:
            with open(os.path.join(res, n), "w", encoding="utf-8") as f:
                f.write("{}")

    def test_first_freeze_needs_no_flags(self):
        with tempfile.TemporaryDirectory() as root:
            self._make_root(root)
            self.assertEqual(plan_refreeze(root), ([], None))

    def test_refreeze_requires_force_and_a_reason(self):
        with tempfile.TemporaryDirectory() as root:
            self._make_root(root)
            self._write_lock(root)
            self.assertIn("--force", plan_refreeze(root)[1])
            self.assertIn("--reason", plan_refreeze(root, force=True)[1])
            self.assertIn("--reason", plan_refreeze(root, force=True, reason="   ")[1])

    def test_refreeze_after_final_results_is_refused_unless_explicitly_acknowledged(self):
        with tempfile.TemporaryDirectory() as root:
            self._make_root(root)
            self._write_lock(root)
            self._results(root, "answers_C_20261201T000000.json")
            history, err = plan_refreeze(root, force=True, reason="버그 수정")
            self.assertIsNone(history)
            self.assertIn("--after-final", err)
            history, err = plan_refreeze(root, force=True, reason="버그 수정", after_final=True)
            self.assertIsNone(err)
            self.assertTrue(history[-1]["final_results_existed"])

    def test_incomplete_results_do_not_count_as_final_results(self):
        with tempfile.TemporaryDirectory() as root:
            self._make_root(root)
            self._write_lock(root)
            self._results(root, "answers_C_20261201T000000_INCOMPLETE.json")
            self.assertEqual(final_results_exist(root), [])
            history, err = plan_refreeze(root, force=True, reason="리뷰 수정")
            self.assertIsNone(err)
            self.assertFalse(history[-1]["final_results_existed"])

    def test_history_is_chained_with_previous_commit_and_lock_hash(self):
        with tempfile.TemporaryDirectory() as root:
            self._make_root(root)
            first = self._write_lock(root)
            h1, _ = plan_refreeze(root, force=True, reason="1차", today="2026-11-27")
            self.assertEqual(h1[0]["previous_git_commit"], first["git_commit"])
            self.assertEqual(h1[0]["previous_lock_sha256"], sha256_file(os.path.join(root, FINAL_LOCK)))
            second = build_final_lock(root, "def", history=h1)
            with open(os.path.join(root, FINAL_LOCK), "w", encoding="utf-8") as f:
                json.dump(second, f)
            h2, _ = plan_refreeze(root, force=True, reason="2차", today="2026-11-28")
            self.assertEqual([h["reason"] for h in h2], ["1차", "2차"])  # 앞선 이력이 보존된다
            self.assertEqual(h2[1]["previous_git_commit"], "def")

    def test_history_does_not_affect_verification(self):
        with tempfile.TemporaryDirectory() as root:
            self._make_root(root)
            lock = build_final_lock(root, "abc", history=[{"reason": "x"}])
            os.makedirs(os.path.join(root, "configs"), exist_ok=True)
            with open(os.path.join(root, FINAL_LOCK), "w", encoding="utf-8") as f:
                json.dump(lock, f)
            self.assertEqual(verify_final_lock(root), [])

    def test_dependencies_of_locked_scripts_are_locked(self):
        self.assertIn("src/ragagent/grading.py", CODE_FILES)  # run_answers 가 불러오는 비용 집계
        self.assertIn("src/ragagent/freeze.py", CODE_FILES)   # run_answers·eval_retrieval 이 부르는 실행 가드

    def test_plus_in_config_name_is_matched_literally(self):
        with tempfile.TemporaryDirectory() as root:
            self._make_root(root)
            self._write_lock(root)
            res = os.path.join(root, "results", "test")
            os.makedirs(res)
            with open(os.path.join(res, "answers_C+R_20261201T000000.json"), "w", encoding="utf-8") as f:
                f.write("{}")
            self.assertEqual(len(check_final_run(root, "openai", ["C+R"], res, "answers")), 1)
            self.assertEqual(check_final_run(root, "openai", ["C"], res, "answers"), [])  # C 는 C+R 결과와 구분

    def test_final_lock_missing_blocks_and_changes_are_detected(self):
        with tempfile.TemporaryDirectory() as root:
            self._make_root(root)
            self.assertTrue(any("고정되지 않았다" in e for e in verify_final_lock(root)))
            lock = build_final_lock(root, git_commit="abc")
            os.makedirs(os.path.join(root, "configs"), exist_ok=True)
            with open(os.path.join(root, FINAL_LOCK), "w", encoding="utf-8") as f:
                json.dump(lock, f)
            self.assertEqual(verify_final_lock(root), [])
            # chunk_map 이 바뀌면 검출된다(리뷰 지적 3번)
            with open(os.path.join(root, "eval/chunk_map.json"), "w", encoding="utf-8", newline="\n") as f:
                f.write("changed")
            self.assertEqual(verify_final_lock(root), ["해시 불일치: eval/chunk_map.json"])

    def test_config_drift_is_detected(self):
        with tempfile.TemporaryDirectory() as root:
            self._make_root(root)
            lock = build_final_lock(root)
            lock["configs"]["pipeline"]["top_k"] = 99
            os.makedirs(os.path.join(root, "configs"), exist_ok=True)
            with open(os.path.join(root, FINAL_LOCK), "w", encoding="utf-8") as f:
                json.dump(lock, f)
            self.assertIn("검색·청킹·모델 설정이 고정 시점과 다르다", verify_final_lock(root))


class RerankerGuardTest(unittest.TestCase):
    def test_config_c_without_reranker_raises_clear_error(self):
        class E:
            def encode_query(self, q):
                import numpy as np
                return np.array([1.0, 0.0], dtype="float32")

        import numpy as np
        from ragagent.bm25 import BM25
        r = Retriever([{"chunk_id": "a#c00", "text": "gpu"}], BM25(["gpu"]), np.array([[1.0, 0.0]], dtype="float32"), E(), None)
        with self.assertRaises(ValueError):
            r.run("C", "gpu")


if __name__ == "__main__":
    unittest.main()
