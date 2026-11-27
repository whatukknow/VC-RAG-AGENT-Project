"""Streamlit 앱 화면 테스트(AppTest). 로컬 색인·모델(data/)이 없는 환경(예: 새 clone)에서는 건너뛴다.
생성 단계는 API 를 부르지 않도록 가짜로 바꿔 끼운다(키·비용 없음)."""
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

HAVE_DATA = all(os.path.exists(os.path.join(ROOT, p)) for p in (
    "data/index/chunks.jsonl", "data/index/embeddings.npy", "data/models/BAAI__bge-small-en-v1.5"))

try:
    from streamlit.testing.v1 import AppTest
except Exception:  # streamlit 미설치
    AppTest = None

APP = os.path.join(ROOT, "src", "app.py")


def fake_init(self, ledger_path, client=None, cfg=None):
    self.cfg = cfg or type(self).cfg
    self.last_meta = {"requested_model": "fake", "served_model": "fake", "request_id": "req_test", "input_tokens": 1,
                      "output_tokens": 1, "cost_usd": 0.0}


def run_app(retrieval_only, question, text=None, config=None):
    import streamlit as st
    st.cache_resource.clear()
    at = AppTest.from_file(APP, default_timeout=180).run()
    assert not at.exception, [e.value for e in at.exception]
    at.sidebar.checkbox(key="retrieval_only").set_value(retrieval_only).run()
    if config:
        at.sidebar.selectbox(key="config").set_value(config).run()
    at.text_area(key="question").set_value(question).run()
    if text is None:
        at.button(key="ask").click().run()
    else:
        with mock.patch("ragagent.generate_openai.OpenAIGenerator.__init__", fake_init), \
                mock.patch("ragagent.generate_openai.OpenAIGenerator.generate", lambda self, s, u, n=None, prefill=None: (text, 7)):
            at.button(key="ask").click().run()
    return at


@unittest.skipUnless(AppTest and HAVE_DATA, "streamlit 또는 로컬 색인·모델(data/)이 없다")
class AppTestCase(unittest.TestCase):
    def test_initial_page_renders_without_error_and_ask_disabled_when_empty(self):
        import streamlit as st
        st.cache_resource.clear()
        at = AppTest.from_file(APP, default_timeout=180).run()
        self.assertFalse(at.exception)
        self.assertEqual(at.title[0].value, "VC 딜소싱 Knowledge Agent")
        self.assertTrue(at.button(key="ask").disabled)

    def test_retrieval_only_shows_table_without_answer(self):
        at = run_app(True, "Which serverless GPU platform offers over 12 varieties of GPU chips?", config="B")
        self.assertFalse(at.exception)
        self.assertEqual(len(at.dataframe), 1)
        self.assertIn("검색만 실행", at.info[0].value)
        self.assertEqual(len(at.dataframe[0].value), 5)

    def test_answered_flow_shows_answer_citation_and_five_retrieved(self):
        at = run_app(False, "Which serverless GPU platform offers over 12 varieties of GPU chips?",
                     text="STATUS: ANSWER\nANSWER: Cerebrium offers over 12 varieties of GPU chips [1].")
        self.assertFalse(at.exception)
        self.assertTrue(at.success)
        self.assertTrue(any("Cerebrium offers over 12 varieties" in m.value for m in at.markdown))  # 답변 본문
        self.assertEqual(len(at.dataframe), 2)  # 인용 표 + 검색 결과 표
        self.assertEqual(len(at.dataframe[1].value), 5)

    def test_insufficient_evidence_is_a_warning_not_an_error(self):
        at = run_app(False, "What is Beam's price per GPU-hour for an H100?",
                     text="STATUS: INSUFFICIENT\nANSWER: The provided documents do not contain this information.")
        self.assertFalse(at.exception)
        self.assertTrue(at.warning)
        self.assertFalse(at.error)

    def test_format_failure_is_shown_as_error_not_as_refusal(self):
        at = run_app(False, "Which company?", text="Sure, here is some text without the required format.")
        self.assertFalse(at.exception)
        self.assertTrue(at.error)
        self.assertIn("근거 부족이 아님", at.error[0].value)

    def test_uncited_answer_is_blocked_and_reason_shown(self):
        at = run_app(False, "Which company?", text="STATUS: ANSWER\nANSWER: Some company.")
        self.assertTrue(at.warning)
        self.assertTrue(any("no_valid_citation" in c.value for c in at.caption))

    def test_missing_api_key_message_names_the_key_only(self):
        import streamlit as st
        st.cache_resource.clear()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_API_KEY", None)
            with mock.patch("ragagent.envfile.load_env", lambda p: []):
                at = AppTest.from_file(APP, default_timeout=180).run()
                at.text_area(key="question").set_value("Which company?").run()
                at.button(key="ask").click().run()
        self.assertTrue(at.error)
        self.assertIn("OPENAI_API_KEY", at.error[0].value)


if __name__ == "__main__":
    unittest.main()
