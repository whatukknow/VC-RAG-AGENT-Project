"""임베딩·reranker 모델을 data/models/ 에 내려받고 리비전 해시를 configs/models.lock.json 에 고정한다.
필요한 파일(safetensors·설정·토크나이저)만 받는다. 사용: .venv/Scripts/python src/download_models.py
"""
import json
import os
import sys

from huggingface_hub import HfApi, snapshot_download

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = {
    "embedding": "BAAI/bge-small-en-v1.5",
    "reranker": "cross-encoder/ms-marco-MiniLM-L6-v2",
}
PATTERNS = ["*.json", "*.txt", "model.safetensors", "1_Pooling/*", "modules.json"]
LOCK = os.path.join(ROOT, "configs", "models.lock.json")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    api = HfApi()
    lock = json.load(open(LOCK, encoding="utf-8")) if os.path.exists(LOCK) else {}
    for role, repo in MODELS.items():
        rev = lock.get(role, {}).get("revision") or api.model_info(repo).sha  # 최초 1회만 최신 해시를 잡고 이후 고정
        local = os.path.join(ROOT, "data", "models", repo.replace("/", "__"))
        snapshot_download(repo_id=repo, revision=rev, local_dir=local, allow_patterns=PATTERNS)
        info = api.model_info(repo, revision=rev, files_metadata=True)
        files = {s.rfilename: s.size for s in info.siblings if s.rfilename == "model.safetensors"}
        lic = (info.card_data.to_dict().get("license") if info.card_data else None)
        lock[role] = {"repo": repo, "revision": rev, "license": lic, "local_dir": os.path.relpath(local, ROOT),
                      "weights_bytes": files}
        print(role, repo, rev[:10], lic, files)
    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    json.dump(lock, open(LOCK, "w", encoding="utf-8"), indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
