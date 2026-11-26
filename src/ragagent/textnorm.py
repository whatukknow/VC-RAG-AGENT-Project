"""평가셋 검증(check_eval)과 근거 매핑(build_index)이 공유하는 텍스트 정규화.
곡선 따옴표를 1:1로 ASCII로 바꾸므로 문자 오프셋이 보존된다."""
import re

_MAP = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})


def fold(s):
    """곡선 따옴표 -> ASCII(길이 불변)."""
    return s.translate(_MAP)


def norm(s):
    """검증용: 따옴표 정리 + 공백 접기."""
    return " ".join(fold(s).split())


def find_span(text, quote):
    """원문(text) 안의 quote 위치 (start, end). 따옴표 종류와 공백 차이를 허용한다. 없으면 (-1, -1)."""
    t, q = fold(text), fold(quote)
    i = t.find(q)
    if i >= 0:
        return i, i + len(q)
    pat = r"\s+".join(re.escape(w) for w in q.split())
    m = re.search(pat, t)
    return (m.start(), m.end()) if m else (-1, -1)
