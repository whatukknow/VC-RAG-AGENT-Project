import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from ragagent.grading import read_grades, score, write_sheet  # noqa: E402


def row(qid, status, answerable=True, cfg="C", total=1000.0, cites=1):
    return {"question_id": qid, "config": cfg, "type": "direct", "answerable": answerable, "status": status,
            "question": "q", "expected_key_facts": ["fact"], "answer": "a",
            "citations": [{"n": 1, "chunk_id": f"{qid}#c00"}][:cites], "allowed_chunk_ids": [f"{qid}#c00"],
            "timing_ms": {"total": total} if not status.startswith("error") else {}}


SIX_ROWS = [row("Q1", "answered"), row("Q2", "answered"), row("Q3", "insufficient_evidence"),
            row("N1", "insufficient_evidence", False), row("N2", "answered", False),
            row("N3", "error_generation", False)]


class GradingTest(unittest.TestCase):
    def test_sheet_roundtrip_and_blank_grades_are_none(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "g.csv")
            write_sheet(path, SIX_ROWS)
            g = read_grades(path)
            self.assertEqual(g[("Q1", "C")]["correct"], None)
            self.assertEqual(len(g), 6)

    def test_invalid_grade_value_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "g.csv")
            write_sheet(path, [row("Q1", "answered")])
            with open(path, encoding="utf-8-sig", newline="") as f:
                text = f.read().replace(",,,,\r\n", ",2,1,human,\r\n", 1)
            self.assertIn(",2,1,human,", text)  # 치환이 실제로 일어났는지 확인
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                f.write(text)
            with self.assertRaises(ValueError):
                read_grades(path)

    def test_score_counts_and_incomplete_flag(self):
        rows = [row("Q1", "answered"), row("Q2", "answered"), row("Q3", "insufficient_evidence"),
                row("N1", "insufficient_evidence", False), row("N2", "answered", False),
                row("N3", "error_generation", False)]
        grades = {("Q1", "C"): {"correct": 1, "grounded": 1, "grader": "human", "note": ""},
                  ("Q2", "C"): {"correct": 0, "grounded": 1, "grader": "Claude", "note": ""}}
        m = score(rows, grades)["C"]
        self.assertTrue(m["complete"])
        self.assertEqual((m["correct"], m["grounded"]), ("1/3", "2/3"))  # Q3 는 거절이라 0점
        self.assertEqual(m["no_evidence_refused"], "1/3")                  # 오류(N3)는 올바른 거절이 아님
        self.assertEqual((m["no_evidence_answered"], m["answerable_refused"]), (1, 1))
        self.assertEqual(m["call_success"], "5/6")
        self.assertEqual(m["errors"]["error_generation"], 1)
        self.assertEqual(m["graders"], {"human": 1, "Claude": 1})

    def test_answered_row_without_grade_marks_incomplete(self):
        m = score([row("Q1", "answered")], {})["C"]
        self.assertEqual((m["complete"], m["ungraded"]), (False, ["Q1"]))

    def test_response_time_uses_successful_calls_only(self):
        rows = [row("Q1", "answered", total=1000.0), row("Q2", "answered", total=3000.0), row("N3", "error_generation", False)]
        m = score(rows, {("Q1", "C"): {"correct": 1, "grounded": 1, "grader": "h", "note": ""},
                         ("Q2", "C"): {"correct": 1, "grounded": 1, "grader": "h", "note": ""}})["C"]
        self.assertEqual(m["response_ms_mean_median_n"], [2000.0, 2000.0, 2])

    def test_configs_are_scored_separately(self):
        rows = [row("Q1", "answered", cfg="B"), row("Q1", "insufficient_evidence", cfg="C")]
        res = score(rows, {("Q1", "B"): {"correct": 1, "grounded": 1, "grader": "h", "note": ""}})
        self.assertEqual((res["B"]["correct"], res["C"]["correct"]), ("1/1", "0/1"))


if __name__ == "__main__":
    unittest.main()
