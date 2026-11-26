"""문서 -> 청크. 청크마다 안정적인 ID와 원문(long_description) 위치를 가진다.
max_chars 는 하드 한도다: 문장이 한도보다 길면 공백 기준으로 추가 분할한다."""
import re
from dataclasses import dataclass, asdict

CHUNK_CONFIG = {"max_chars": 500, "overlap_sentences": 1, "title_prefix": True, "version": "chunk-v2"}

_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[-])|\n{2,}")
_WS = re.compile(r"\s")


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    name: str
    start: int          # long_description 내 문자 시작 위치(포함)
    end: int            # 끝 위치(제외)
    body: str           # 원문 그대로
    text: str           # 색인용 텍스트(제목 접두 포함)

    def to_dict(self):
        return asdict(self)


def split_sentences(s):
    """(start, end) 구간 목록. 원문 오프셋을 보존한다."""
    spans, pos = [], 0
    for m in _SENT.finditer(s):
        if s[pos:m.start()].strip():
            spans.append((pos, m.start()))
        pos = m.end()
    if s[pos:].strip():
        spans.append((pos, len(s)))
    return spans


def wrap_span(s, span, max_chars):
    """max_chars 를 넘는 구간을 공백 위치에서 나눈다. 공백이 없으면 max_chars 에서 자른다."""
    a, b = span
    out = []
    while b - a > max_chars:
        ws = list(_WS.finditer(s, a + 1, a + max_chars + 1))
        cut = ws[-1].start() if ws else a + max_chars
        out.append((a, cut))
        a = cut
        while a < b and s[a].isspace():
            a += 1
    if b > a:
        out.append((a, b))
    return out


def chunk_document(doc, max_chars=None, overlap_sentences=None, title_prefix=None):
    cfg = CHUNK_CONFIG
    max_chars = max_chars or cfg["max_chars"]
    overlap = cfg["overlap_sentences"] if overlap_sentences is None else overlap_sentences
    title_prefix = cfg["title_prefix"] if title_prefix is None else title_prefix
    s = doc["long_description"]
    sents = [w for sp in split_sentences(s) for w in wrap_span(s, sp, max_chars)]
    if not sents:
        return []
    groups, cur = [], []
    for sp in sents:
        if cur and sp[1] - cur[0][0] > max_chars:
            groups.append(cur)
            cur = cur[-overlap:] if overlap else []
            # 겹침 문장 때문에 이미 한도를 넘으면 겹침을 버린다
            if cur and sp[1] - cur[0][0] > max_chars:
                cur = []
        cur.append(sp)
    groups.append(cur)  # 루프는 항상 마지막 문장을 cur 에 넣으므로 비어 있지 않다
    chunks = []
    for i, g in enumerate(groups):
        start, end = g[0][0], g[-1][1]
        body = s[start:end]
        head = f"{doc['name']}: {doc.get('one_liner') or ''}\n" if title_prefix else ""
        chunks.append(Chunk(f"{doc['doc_id']}#c{i:02d}", doc["doc_id"], doc["name"], start, end, body, head + body))
    return chunks
