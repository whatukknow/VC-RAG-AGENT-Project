"""고정(freeze) 검증.
1) eval/FREEZE.json : 평가셋·코퍼스·문서목록 해시(이미 고정). 누락·불일치는 모두 오류다.
2) configs/final.lock.json : 최종 평가 직전에 `src/freeze_final.py`로 만드는 검색 설정 고정.
   근거 매핑(chunk_map)·모델 리비전·청크 색인과 모든 설정값을 담는다. 없으면 --final 은 거부된다.
"""
import hashlib
import json
import os

FINAL_LOCK = os.path.join("configs", "final.lock.json")
FINAL_FILES = ["eval/chunk_map.json", "configs/models.lock.json", "data/index/chunks.jsonl",
               "eval/test.json", "eval/dev.json", "docs/doc_list.csv", "data/corpus/corpus.jsonl"]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verify_files(root, files):
    """files: {상대경로: sha256}. 누락·불일치 목록을 돌려준다(없으면 빈 리스트)."""
    errors = []
    for rel, want in files.items():
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            errors.append(f"파일 없음: {rel}")
        elif sha256_file(path) != want:
            errors.append(f"해시 불일치: {rel}")
    return errors


def current_configs():
    from .bm25 import BM25_CONFIG
    from .chunking import CHUNK_CONFIG
    from .embed import EMBED_CONFIG
    from .fusion import RRF_CONFIG
    from .pipeline import PIPELINE_CONFIG
    from .rerank import RERANK_CONFIG
    return json.loads(json.dumps({"chunk": CHUNK_CONFIG, "bm25": BM25_CONFIG, "rrf": RRF_CONFIG,
                                  "embed": EMBED_CONFIG, "rerank": RERANK_CONFIG, "pipeline": PIPELINE_CONFIG}))


def build_final_lock(root, git_commit=None):
    missing = [f for f in FINAL_FILES if not os.path.exists(os.path.join(root, f))]
    if missing:
        raise FileNotFoundError(f"고정에 필요한 파일이 없다: {missing}")
    return {"files": {f: sha256_file(os.path.join(root, f)) for f in FINAL_FILES},
            "configs": current_configs(), "git_commit": git_commit}


def verify_final_lock(root):
    path = os.path.join(root, FINAL_LOCK)
    if not os.path.exists(path):
        return [f"최종 설정이 고정되지 않았다({FINAL_LOCK} 없음). src/freeze_final.py 를 먼저 실행한다."]
    with open(path, encoding="utf-8") as f:
        lock = json.load(f)
    errors = verify_files(root, lock["files"])
    if lock["configs"] != current_configs():
        errors.append("검색·청킹·모델 설정이 고정 시점과 다르다")
    return errors
