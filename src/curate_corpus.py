"""candidates.jsonl(규칙 추출) + 수동 검토 결과 -> corpus.jsonl, docs/doc_list.csv

수동 검토: 작성자(Claude)가 소개문을 읽고 판단했고, 사용자 승인 전의 초안이다.
role=core        : AI 추론 인프라(서빙·GPU 클라우드/컴퓨트·커널/런타임 최적화·라우팅/게이트웨이·비용 절감·추론 칩)
role=distractor  : 키워드는 겹치지만 업종이 다른 문서. 혼동 질문과 '근거 없음' 질문 설계용.
사용: python -I src/curate_corpus.py data/raw/all.json data/corpus/candidates.jsonl data/corpus/corpus.jsonl docs/doc_list.csv
"""
import csv
import json
import sys
from datetime import date

CORE = """mystic cerebrium beam posh poplarml texel-ai litellm cedana baud trainy shadeform morph
ncompass-technologies tamarind-bio unsloth-ai runlocal-ai thunder-compute starcloud pipeshift dotwave
woz tensorpool tinfoil wafer lilac magnitude luminal sf-tensor onetriangle runanywhere cumulus-labs
compresr overshoot chamber zibra-labs expanse reasonblocks rightnow orchestra touchmark liquid-energy
lamb-labs isoquant tracer munito-ai nodus-compute hopper lucebox dreamscale-labs routerplus baymachines
reduced-energy-microsystems tensil rain-neuromorphics""".split()

DISTRACTOR = {
    "axial": "물리 시뮬레이션 커널(AI 아님)",
    "kernel": "AI 에이전트용 브라우저 인프라(이름이 KERNEL)",
    "aurorin-cad": "기계설계 CAD 에이전트(kernel 단어)",
    "riften": "AI 연구소(model routing 단어, 인프라 제품 아님)",
    "sentient-os": "개인 에이전트(inference cost 언급)",
    "jcode": "코딩 에이전트(고성능 추론 언급)",
    "ubicloud": "일반 클라우드(AWS 대안)",
    "deepgram": "음성 AI 모델 회사",
    "comfy-deploy": "ComfyUI 팀 배포 도구",
    "decohere": "실시간 생성형 AI 서비스",
    "paraquery": "GPU 가속 Spark/SQL(데이터 처리)",
    "rescale": "HPC 클라우드(AI 추론 전용 아님)",
    "stoa": "AI 하드웨어 마켓플레이스",
    "unify": "파일럿에서 라우터 사례로 언급된 회사. 현재 소개문은 지속 학습 모델만 설명(근거 없음 질문 후보)",
}


def main(raw, cand, out, listcsv):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cands = {json.loads(l)["slug"]: json.loads(l) for l in open(cand, encoding="utf-8")}
    rawmap = {c["slug"]: c for c in json.load(open(raw, encoding="utf-8"))}
    rows, missing = [], []
    for slug, role, note in [(s, "core", "") for s in CORE] + [(s, "distractor", n) for s, n in DISTRACTOR.items()]:
        c = rawmap.get(slug)
        if not c:
            missing.append(slug)
            continue
        rows.append({
            "doc_id": f"yc-{slug}", "slug": slug, "name": c["name"], "url": c.get("url"),
            "website": c.get("website"), "batch": c.get("batch"), "status": c.get("status"),
            "one_liner": c.get("one_liner"), "tags": c.get("tags"),
            "long_description": c.get("long_description") or "",
            "role": role, "role_note": note, "in_rule_candidates": slug in cands,
        })
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(listcsv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["doc_id", "title", "source_url", "terms", "collected_at", "location", "role", "batch", "status", "role_note"])
        for r in rows:
            w.writerow([r["doc_id"], r["name"], r["url"],
                        "unofficial yc-oss API 사본, 라이선스 명시 없음. 원문 재배포 금지, URL·ID만 공개",
                        date.today().isoformat(), "all.json 의 long_description 필드", r["role"],
                        r["batch"], r["status"], r["role_note"]])
    n_core = sum(r["role"] == "core" for r in rows)
    print(f"docs={len(rows)} core={n_core} distractor={len(rows) - n_core} missing={missing}")
    print("core not in rule candidates:", [r["slug"] for r in rows if r["role"] == "core" and not r["in_rule_candidates"]])


if __name__ == "__main__":
    main(*sys.argv[1:5])
