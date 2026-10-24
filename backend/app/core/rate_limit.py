"""A small in-memory limiter for the open pages (V2-8): a sliding window per key. No Redis (MVP rule); one process, so the limit is per process.

`allow(key)` records a hit and says whether the key may go on; `retry_after(key)` says how many seconds until it may. The table of keys is
capped so a flood of different addresses cannot grow the memory.
"""
import time
from collections import deque


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float, max_keys: int = 10_000) -> None:
        self.limit = limit
        self.window = window_seconds
        self.max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}

    def _trim(self, key: str, now: float) -> deque[float]:
        hits = self._hits.get(key)
        if hits is None:
            if len(self._hits) >= self.max_keys:
                self._drop_oldest(now)
            hits = self._hits[key] = deque()
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        return hits

    def _drop_oldest(self, now: float) -> None:
        for key in [k for k, v in self._hits.items() if not v or now - v[-1] >= self.window]:
            del self._hits[key]
        while len(self._hits) >= self.max_keys:
            del self._hits[next(iter(self._hits))]

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        hits = self._trim(key, now)
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True

    def retry_after(self, key: str, now: float | None = None) -> int:
        now = time.monotonic() if now is None else now
        hits = self._hits.get(key)
        if hits is None:
            return 0
        while hits and now - hits[0] >= self.window:  # a hit that has left the window no longer counts, whoever asks
            hits.popleft()
        if len(hits) < self.limit:
            return 0
        return max(1, int(self.window - (now - hits[0])) + 1)

    def reset(self) -> None:
        self._hits.clear()
