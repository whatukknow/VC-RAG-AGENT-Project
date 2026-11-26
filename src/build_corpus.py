"""YC 일괄 JSON에서 'AI 추론 인프라' 문서 후보를 규칙 기반으로 추출한다.

범위 규칙(SCOPE_V1)은 결과를 보기 전에 고정했다. 수정하면 SCOPE 버전을 올리고 기록한다.
사용: python -I src/build_corpus.py data/raw/all.json data/corpus/candidates.jsonl
"""
import json
import re
import sys

SCOPE = "scope_v1"
# 한 개 이상 매칭되면 후보. 단독 'llm'은 노이즈가 커서 제외한다.
PATTERN = re.compile(
    r"\binference\b|\bgpus?\b|\bcuda\b|\btpus?\b|\bkernels?\b|quantiz|speculative decoding"
    r"|model serving|\bvllm\b|tensorrt|llm (gateway|router|routing|proxy)"
    r"|model (routing|router|gateway)|\btokens?\b[^.]{0,30}\b(cost|price|pricing)"
)


def text_of(c):
    return " ".join([c.get("one_liner") or "", c.get("long_description") or "",
                     " ".join(c.get("tags") or [])])


def main(src, dst):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    data = json.load(open(src, encoding="utf-8"))
    out = []
    for c in data:
        t = text_of(c).lower()
        hits = sorted({m.group(0) for m in PATTERN.finditer(t)})
        if not hits or not (c.get("long_description") or "").strip():
            continue
        out.append({
            "doc_id": f"yc-{c['slug']}", "yc_id": c["id"], "slug": c["slug"], "name": c["name"],
            "url": c.get("url"), "website": c.get("website"), "batch": c.get("batch"),
            "status": c.get("status"), "one_liner": c.get("one_liner"),
            "tags": c.get("tags"), "long_description": c.get("long_description"),
            "scope": SCOPE, "hits": hits,
        })
    with open(dst, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{SCOPE}: {len(out)} candidates from {len(data)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
