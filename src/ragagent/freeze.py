"""고정(freeze) 검증.
1) eval/FREEZE.json : 평가셋·코퍼스·문서목록 해시(이미 고정). 누락·불일치는 모두 오류다.
2) configs/final.lock.json : 최종 평가 직전에 `src/freeze_final.py`로 만드는 고정.
   근거 매핑(chunk_map)·모델 리비전·청크 색인·모든 설정값·**평가 결과를 만드는 코드의 해시**·최종 생성 백엔드를 담는다.
   없으면 --final 은 거부된다.
3) 최종 실행 가드: 고정 시점과 다른 백엔드는 거부하고, 같은 구성의 결과가 이미 있으면 재실행 사유 없이는 거부한다.
"""
import glob
import hashlib
import json
import os

FINAL_LOCK = os.path.join("configs", "final.lock.json")
FINAL_FILES = ["eval/chunk_map.json", "configs/models.lock.json", "data/index/chunks.jsonl",
               "eval/test.json", "eval/dev.json", "docs/doc_list.csv", "data/corpus/corpus.jsonl"]
# 최종 평가 결과(검색·답변·기록)에 영향을 주는 코드. 줄바꿈 차이를 무시하고 해시한다.
CODE_FILES = ["src/ragagent/answer.py", "src/ragagent/bm25.py", "src/ragagent/chunking.py", "src/ragagent/embed.py",
              "src/ragagent/envfile.py", "src/ragagent/errors.py", "src/ragagent/factory.py", "src/ragagent/fusion.py",
              "src/ragagent/generate.py", "src/ragagent/generate_api.py", "src/ragagent/generate_openai.py",
              "src/ragagent/pipeline.py", "src/ragagent/rerank.py", "src/ragagent/rewrite.py",
              "src/ragagent/textnorm.py", "src/run_answers.py", "src/eval_retrieval.py",
              # 고정된 실행 스크립트가 불러오는 파일(비용 집계·최종 실행 가드). 검증기가 자기 자신을 완전히 잠글 수는 없으므로
              # freeze.py 의 변경은 git 이력으로도 확인한다.
              "src/ragagent/grading.py", "src/ragagent/freeze.py"]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def sha256_lf(path):
    """줄바꿈(CRLF/LF) 차이를 무시한 해시(코드 파일용)."""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()


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


def verify_code(root, code):
    errors = []
    for rel, want in code.items():
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            errors.append(f"코드 파일 없음: {rel}")
        elif sha256_lf(path) != want:
            errors.append(f"고정 이후 코드가 바뀜: {rel}")
    return errors


def current_configs():
    from .bm25 import BM25_CONFIG
    from .chunking import CHUNK_CONFIG
    from .embed import EMBED_CONFIG
    from .fusion import RRF_CONFIG
    from .generate import API_GEN_CONFIG, GEN_CONFIG, OPENAI_GEN_CONFIG
    from .pipeline import PIPELINE_CONFIG
    from .rerank import RERANK_CONFIG
    from .rewrite import REWRITE_CONFIG
    return json.loads(json.dumps({"chunk": CHUNK_CONFIG, "bm25": BM25_CONFIG, "rrf": RRF_CONFIG,
                                  "embed": EMBED_CONFIG, "rerank": RERANK_CONFIG, "pipeline": PIPELINE_CONFIG,
                                  "generation": GEN_CONFIG, "generation_api": API_GEN_CONFIG,
                                  "generation_openai": OPENAI_GEN_CONFIG,
                                  "rewrite": REWRITE_CONFIG}))


def build_final_lock(root, git_commit=None, final_backend="openai", history=None):
    missing = [f for f in FINAL_FILES + CODE_FILES if not os.path.exists(os.path.join(root, f))]
    if missing:
        raise FileNotFoundError(f"고정에 필요한 파일이 없다: {missing}")
    return {"final_backend": final_backend, "git_commit": git_commit,
            "files": {f: sha256_file(os.path.join(root, f)) for f in FINAL_FILES},
            "code": {f: sha256_lf(os.path.join(root, f)) for f in CODE_FILES},
            "configs": current_configs(),
            "history": list(history or [])}  # 재고정 이력(사유·이전 커밋·이전 고정 파일 해시). 검증에는 쓰지 않는다


def final_results_exist(root):
    """results/test 에 완료된 최종 결과(INCOMPLETE 제외)가 있는지. 있으면 해당 파일 목록."""
    found = []
    for prefix in ("answers", "retrieval"):
        found += [p for p in glob.glob(os.path.join(root, "results", "test", f"{prefix}_*.json")) if "INCOMPLETE" not in p]
    return sorted(found)


def plan_refreeze(root, force=False, reason=None, after_final=False, today=None):
    """재고정 계획. 반환: (history 목록, 오류 메시지). 오류가 있으면 history 는 None.
    - 고정 파일이 없으면 최초 고정이다.
    - 이미 있으면 --force 와 --reason 이 모두 있어야 한다.
    - 최종 결과가 이미 있으면 --after-final 로 '결과를 본 뒤의 재고정'임을 명시해야 하며, 이 사실이 이력에 남는다."""
    old = load_final_lock(root)
    if old is None:
        return [], None
    if not force:
        return None, f"이미 고정되어 있다: {FINAL_LOCK} (덮어쓰려면 --force --reason \"사유\")"
    if not (reason or "").strip():
        return None, "--force 에는 --reason \"사유\" 가 필요하다(이력에 기록된다)"
    results = final_results_exist(root)
    if results and not after_final:
        return None, (f"최종 결과가 이미 있다({len(results)}개). 결과를 본 뒤의 재고정은 기본적으로 허용하지 않는다. "
                      "불가피하면 --after-final 로 명시하고 problem.md 에 사유를 남긴다")
    import datetime
    entry = {"date": today or datetime.date.today().isoformat(), "reason": reason.strip(),
             "previous_git_commit": old.get("git_commit"),
             "previous_lock_sha256": sha256_file(os.path.join(root, FINAL_LOCK)),
             "final_results_existed": bool(results)}
    return list(old.get("history", [])) + [entry], None


def load_final_lock(root):
    path = os.path.join(root, FINAL_LOCK)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def verify_final_lock(root):
    lock = load_final_lock(root)
    if lock is None:
        return [f"최종 설정이 고정되지 않았다({FINAL_LOCK} 없음). src/freeze_final.py 를 먼저 실행한다."]
    errors = verify_files(root, lock["files"])
    errors += verify_code(root, lock.get("code", {}))
    if lock["configs"] != current_configs():
        errors.append("검색·청킹·모델 설정이 고정 시점과 다르다")
    return errors


def check_final_run(root, backend, configs, results_dir, prefix, rerun_reason=None):
    """최종 실행 가드. 오류 목록을 돌려준다.
    - backend 가 None 이 아니면 고정된 최종 백엔드와 같아야 한다.
    - results_dir 에 같은 구성의 결과(<prefix>_<구성>_*.json, INCOMPLETE 제외)가 이미 있으면 rerun_reason 이 필요하다."""
    errors = []
    lock = load_final_lock(root)
    if backend is not None and lock is not None and lock.get("final_backend") != backend:
        errors.append(f"고정된 최종 백엔드는 '{lock.get('final_backend')}' 인데 '{backend}' 로 실행하려 한다")
    for cfg in configs:
        found = [p for p in glob.glob(os.path.join(results_dir, f"{prefix}_{cfg}_*.json")) if "INCOMPLETE" not in p]
        if found and not (rerun_reason or "").strip():
            errors.append(f"구성 {cfg} 의 최종 결과가 이미 있다({len(found)}개). 재실행은 --rerun-reason 으로 사유를 남겨야 하며 "
                          "기존 결과는 삭제하지 않는다")
    return errors
