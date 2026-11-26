"""의존성 없는 BM25(Okapi). 토큰화·파라미터를 기록해 재현 가능하게 한다."""
import math
import re
from collections import Counter

BM25_CONFIG = {"k1": 1.5, "b": 0.75, "tokenizer": "lower+[a-z0-9]+, stopwords-v1, no-stemming"}
STOP = set("a an the of to in on for and or is are was be it its that this with as by at from which what who whom how do does did can than".split())
_TOK = re.compile(r"[a-z0-9]+")


def tokenize(text):
    return [t for t in _TOK.findall(text.lower()) if t not in STOP]


class BM25:
    def __init__(self, texts, k1=None, b=None):
        self.k1 = BM25_CONFIG["k1"] if k1 is None else k1
        self.b = BM25_CONFIG["b"] if b is None else b
        self.docs = [Counter(tokenize(t)) for t in texts]
        self.lens = [sum(c.values()) for c in self.docs]
        self.avg = sum(self.lens) / max(len(self.lens), 1)
        df = Counter()
        for c in self.docs:
            df.update(c.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query):
        q = tokenize(query)
        out = []
        for c, ln in zip(self.docs, self.lens):
            s = 0.0
            for t in q:
                f = c.get(t)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * ln / self.avg))
            out.append(s)
        return out

    def search(self, query, k=10):
        sc = self.scores(query)
        order = sorted(range(len(sc)), key=lambda i: (-sc[i], i))
        return [(i, sc[i]) for i in order[:k] if sc[i] > 0]
