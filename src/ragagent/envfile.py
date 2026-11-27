"""`.env` 로딩. 값은 환경변수에만 넣고 어디에도 출력·기록하지 않는다. 이미 설정된 환경변수가 우선한다."""
import os


def load_env(path):
    """KEY=VALUE 줄을 읽어 os.environ 에 없는 키만 설정한다. 설정한 키 이름 목록(값 제외)을 돌려준다."""
    set_keys = []
    if not os.path.exists(path):
        return set_keys
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and value and key not in os.environ:
                os.environ[key] = value
                set_keys.append(key)
    return set_keys


def require_key(name="ANTHROPIC_API_KEY"):
    if not os.environ.get(name):
        raise RuntimeError(f"{name} 가 없다. 프로젝트 루트의 .env 에 `{name}=<키>` 를 추가한다(.env 는 커밋되지 않는다).")
