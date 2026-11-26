"""질의-청크 쌍을 cross-encoder로 다시 채점하는 reranker. 결합 점수 정렬과는 별개의 관련도 재평가다."""

RERANK_CONFIG = {"model": "cross-encoder/ms-marco-MiniLM-L6-v2", "input": "(query, chunk.text)", "device": "cpu"}


class Reranker:
    def __init__(self, local_dir, device=None):
        from sentence_transformers import CrossEncoder
        self.model = CrossEncoder(local_dir, device=device or RERANK_CONFIG["device"])

    def score(self, query, texts):
        if not texts:
            return []
        return [float(s) for s in self.model.predict([(query, t) for t in texts], show_progress_bar=False)]
