"""임베딩·reranker·생성 모델을 data/models/ 에 내려받고 리비전 해시를 configs/models.lock.json 에 고정한다.
필요한 파일(safetensors·설정·토크나이저)만 받는다.
사용: .venv/Scripts/python src/download_models.py [역할 ...]   (역할: embedding reranker generator, 생략하면 전체)
"""
import json
import os
import sys

from huggingface_hub import HfApi, snapshot_download

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = {
    "embedding": "BAAI/bge-small-en-v1.5",
    "reranker": "cross-encoder/ms-marco-MiniLM-L6-v2",
    "generator": "Qwen/Qwen2.5-1.5B-Instruct",  # 4B(Qwen3-4B-Instruct-2507)는 이 회선에서 1~2시간 걸려 전환(2026-11-26)
}
PATTERNS = ["*.json", "*.txt", "model.safetensors", "model-*.safetensors", "1_Pooling/*", "modules.json"]
LOCK = os.path.join(ROOT, "configs", "models.lock.json")


def main(roles):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    api = HfApi()
    lock = {}
    if os.path.exists(LOCK):
        with open(LOCK, encoding="utf-8") as f:
            lock = json.load(f)
    for role in roles:
        repo = MODELS[role]
        rev = lock.get(role, {}).get("revision") or api.model_info(repo).sha  # 최초 1회만 최신 해시를 잡고 이후 고정
        local = os.path.join(ROOT, "data", "models", repo.replace("/", "__"))
        snapshot_download(repo_id=repo, revision=rev, local_dir=local, allow_patterns=PATTERNS)
        info = api.model_info(repo, revision=rev, files_metadata=True)
        files = {s.rfilename: s.size for s in info.siblings if s.rfilename.endswith(".safetensors")}
        lic = (info.card_data.to_dict().get("license") if info.card_data else None)
        lock[role] = {"repo": repo, "revision": rev, "license": lic,
                      "local_dir": os.path.relpath(local, ROOT).replace(os.sep, "/"),  # 운영체제와 무관한 경로
                      "weights_bytes": files}
        print(role, repo, rev[:10], lic, f"{sum(files.values()) / 1e9:.2f} GB")
        os.makedirs(os.path.dirname(LOCK), exist_ok=True)
        with open(LOCK, "w", encoding="utf-8", newline="\n") as f:  # 역할마다 저장해 중간에 끊겨도 기록이 남는다
            json.dump(lock, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    selected = sys.argv[1:] or list(MODELS)
    unknown = [r for r in selected if r not in MODELS]
    if unknown:
        sys.exit(f"알 수 없는 역할: {unknown} (가능: {list(MODELS)})")
    main(selected)
