"""Batch embeddings at reduced dimensions (ADR-0016), paced under the deployment's
tokens-per-minute limit (ADR-0014 revision) and retried on transient errors (pipeline.http).

Pacing: every request reserves its estimated tokens from a shared one-minute budget
before it is sent, so parallel workers slow down together instead of all hitting
429 and backing off at random."""
import threading
import time
from collections import deque

from . import http
from .config import SETTINGS as S


class TokenBudget:
    """Sliding one-minute window shared by all threads."""

    def __init__(self, tokens_per_minute: int):
        self.limit = tokens_per_minute
        self.window: deque[tuple[float, int]] = deque()
        self.lock = threading.Lock()

    def acquire(self, tokens: int) -> None:
        tokens = min(tokens, self.limit)
        while True:
            with self.lock:
                now = time.monotonic()
                while self.window and now - self.window[0][0] >= 60:
                    self.window.popleft()
                used = sum(t for _, t in self.window)
                if used + tokens <= self.limit:
                    self.window.append((now, tokens))
                    return
                wait = 60 - (now - self.window[0][0]) + 0.1
            time.sleep(wait)


_budget = TokenBudget(S.embed_tpm)


def _estimate(texts: list[str]) -> int:
    return sum(len(t) // 4 + 1 for t in texts)


def embed(texts: list[str]) -> tuple[list[list[float]], int]:
    """Return (vectors, prompt_tokens_used)."""
    vectors, used = [], 0
    for start in range(0, len(texts), S.embed_batch):
        batch = texts[start:start + S.embed_batch]
        _budget.acquire(_estimate(batch))
        resp = http.request("POST", f"{S.aoai_endpoint}/embeddings", http.COGNITIVE_SCOPE,
                            json={"model": S.embed_model, "input": batch,
                                  "dimensions": S.embed_dims}).json()
        ordered = sorted(resp["data"], key=lambda d: d["index"])
        vectors.extend(d["embedding"] for d in ordered)
        used += resp.get("usage", {}).get("prompt_tokens", 0)
    return vectors, used
