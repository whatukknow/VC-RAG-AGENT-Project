"""VC 딜소싱 Knowledge Agent — Streamlit 실행 인터페이스(질문·답변·근거·오류 확인용, 디자인 경쟁은 하지 않는다).
실행: .venv/Scripts/streamlit run src/app.py
- 정답표(eval/)는 화면·검색·프롬프트 어디에도 쓰지 않는다. 검색 대상은 공개 프로필 소개문 코퍼스뿐이다.
- 생성 단계를 쓰면 질문과 검색된 공개 프로필 문구가 선택한 외부 API 로 전송된다('검색만 보기'는 전송 없음).
- API 호출은 비용 한도(원장)에 포함되며, 한도에 도달하면 실행을 멈추고 알린다.
"""
import os
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")  # 모델은 data/models 의 로컬 파일만 쓴다
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st  # noqa: E402

from ragagent import view  # noqa: E402
from ragagent.answer import AnswerPipeline  # noqa: E402
from ragagent.envfile import load_env  # noqa: E402
from ragagent.errors import BudgetExceeded  # noqa: E402
from ragagent.factory import build_retriever  # noqa: E402
from ragagent.generate import GEN_CONFIG, OPENAI_GEN_CONFIG, API_GEN_CONFIG, Generator  # noqa: E402
from ragagent.generate_api import ApiGenerator  # noqa: E402
from ragagent.generate_openai import OpenAIGenerator  # noqa: E402
from ragagent.rewrite import Rewriter, RewritingRetriever  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = [
    "Which serverless GPU platform offers over 12 varieties of GPU chips?",
    "Which company hardcodes LLM weights into silicon, and what are its chips called?",
    "What is Beam's price per GPU-hour for an H100?",
]
LEDGERS = {"openai": ("openai_cost_ledger.jsonl", OPENAI_GEN_CONFIG), "anthropic": ("api_cost_ledger.jsonl", API_GEN_CONFIG)}

st.set_page_config(page_title="VC 딜소싱 Knowledge Agent", layout="wide")


@st.cache_resource(show_spinner="검색 색인과 임베딩·reranker 모델을 불러오는 중...")
def get_retriever():
    retr, meta = build_retriever()
    return retr, view.chunk_index(retr.chunks), view.load_doc_links(os.path.join(ROOT, "docs", "doc_list.csv"))


@st.cache_resource(show_spinner="생성 모델을 준비하는 중...")
def get_generator(backend):
    load_env(os.path.join(ROOT, ".env"))  # 키 값은 환경변수에만 들어가고 화면·기록에 나오지 않는다
    if backend == "openai":
        return OpenAIGenerator(os.path.join(ROOT, "results", LEDGERS["openai"][0]))
    if backend == "anthropic":
        return ApiGenerator(os.path.join(ROOT, "results", LEDGERS["anthropic"][0]))
    import json
    with open(os.path.join(ROOT, "configs", "models.lock.json"), encoding="utf-8") as f:
        local_dir = json.load(f)["generator"]["local_dir"]
    return Generator(os.path.join(ROOT, local_dir))


def set_example(text):
    st.session_state["question"] = text


# ------------------------------------------------------------------ 사이드바
with st.sidebar:
    st.header("설정")
    retrieval_only = st.checkbox("검색만 보기(생성·API 호출 없음)", value=False, key="retrieval_only")
    config = st.selectbox("검색 구성", ["A", "B", "C"] if retrieval_only else ["A", "B", "C", "C+R"], index=2,
                          key="config", help="A=벡터, B=BM25+벡터(RRF), C=B+re-ranking, C+R=쿼리 리라이트 후 C")
    backend = st.selectbox("생성 백엔드", ["openai", "anthropic", "local"], index=0, key="backend",
                           disabled=retrieval_only, help="openai=gpt-6-luna(기본), anthropic=Claude Haiku 5.5, local=Qwen2.5-1.5B")
    if not retrieval_only and backend in LEDGERS:
        text, spent = view.spent_text(os.path.join(ROOT, "results", LEDGERS[backend][0]), LEDGERS[backend][1]["budget_usd"])
        st.caption(f"API 비용 {text}")
    st.divider()
    st.caption("검색 대상: YC 공개 프로필 소개문 68개(AI 추론 인프라). 답변은 검색된 문서에만 근거하며, "
               "문서에 없으면 답하지 않는다. 평가 결과가 아니라 동작 확인용 화면이다.")
    if not retrieval_only:
        st.caption("⚠ 생성 단계에서는 질문과 검색된 공개 프로필 문구가 선택한 외부 API로 전송됩니다(로컬 제외).")

# ------------------------------------------------------------------ 본문
st.title("VC 딜소싱 Knowledge Agent")
st.caption("YC 공개 프로필에서 AI 추론 인프라 회사를 찾아 근거와 함께 답합니다.")

cols = st.columns(len(EXAMPLES))
for i, (col, ex) in enumerate(zip(cols, EXAMPLES)):
    col.button(f"예시 {i + 1}", key=f"ex{i}", on_click=set_example, args=(ex,), help=ex, width="stretch")
question = st.text_area("질문(영문 권장 — 문서가 영어입니다)", key="question", height=90)
ask = st.button("질문하기", key="ask", type="primary", disabled=not question.strip())

if ask:
    try:
        retr, by_id, links = get_retriever()
        if retrieval_only:
            with st.spinner("검색 중..."):
                res = retr.run(config, question.strip())
            st.session_state["result"] = {"mode": "retrieval", "config": config, "question": question.strip(),
                                          "retrieved": view.retrieval_only_record(res, by_id)}
        else:
            gen = get_generator(backend)
            pipe = AnswerPipeline(RewritingRetriever(retr, Rewriter(gen)), gen)
            with st.spinner("검색하고 답변을 만드는 중..."):
                rec = pipe.answer(question.strip(), config)
            st.session_state["result"] = {"mode": "answer", "config": config, "question": question.strip(), "rec": rec}
    except BudgetExceeded as e:
        st.session_state["result"] = {"mode": "fatal", "message": f"API 비용 한도에 도달해 중단했습니다: {e}"}
    except RuntimeError as e:  # 예: API 키 없음(키 이름만 안내하고 값은 다루지 않는다)
        st.session_state["result"] = {"mode": "fatal", "message": str(e)}

result = st.session_state.get("result")
if result:
    st.divider()
    if result["mode"] == "fatal":
        st.error(result["message"])
    else:
        retr, by_id, links = get_retriever()
        st.caption(f"질문: {result['question']}  |  구성 {result['config']}")
        if result["mode"] == "retrieval":
            st.info("검색만 실행했습니다(답변 없음).")
            st.dataframe(view.retrieved_rows(result["retrieved"], by_id, links), width="stretch", hide_index=True)
        else:
            rec = result["rec"]
            label, level = view.status_view(rec["status"])
            getattr(st, level)(label)
            if rec["status"] == "answered":
                st.markdown(f"### 답변\n{rec['answer']}")
            elif rec["status"] == "insufficient_evidence":
                st.markdown(f"### 답변\n{rec['answer']}")
                if rec.get("blocked_reason"):
                    st.caption(f"차단 사유: {rec['blocked_reason']} (모델 답변에 유효한 문서 번호 인용이 없어 내보내지 않았습니다)")
            else:
                st.markdown(f"**오류 내용:** `{rec.get('error')}`")
            if rec.get("invalid_citations"):
                st.warning(f"검색 결과에 없는 문서 번호 인용을 무시했습니다: {rec['invalid_citations']}")
            tabs = st.tabs(["근거(인용)", "검색 결과 상위 5개", "쿼리 리라이트", "실행 정보"])
            with tabs[0]:
                rows = view.citation_rows(rec, by_id, links)
                if rows:
                    st.dataframe(rows, width="stretch", hide_index=True)
                    for n, name, cid, body in view.evidence_blocks(rec, by_id):
                        with st.expander(f"[{n}] {name} — {cid} (원문 발췌)", expanded=True):
                            st.write(body)
                else:
                    st.caption("인용된 근거가 없습니다.")
            with tabs[1]:
                cited = {c["chunk_id"] for c in rec.get("citations", [])}
                st.dataframe(view.retrieved_rows(rec["retrieved"], by_id, links, cited), width="stretch",
                             hide_index=True)
            with tabs[2]:
                rw = view.rewrite_view(rec)
                st.table(rw) if rw else st.caption("이 구성(C+R 아님)에서는 쿼리 리라이트를 쓰지 않습니다.")
            with tabs[3]:
                st.write(f"응답 시간: {view.timing_text(rec)}")
                if view.llm_text(rec):
                    st.write(view.llm_text(rec))
                if rec.get("raw_output"):
                    with st.expander("모델 원본 출력"):
                        st.code(rec["raw_output"])
