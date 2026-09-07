"""Rate-limit-safe request queue with delays, backoff, and progress logging."""

from __future__ import annotations

import time
from typing import Callable


ProgressCallback = Callable[[str, str], None]


class RateLimitQueue:
    """Serializes cloud AI calls with minimum spacing and 429 backoff."""

    def __init__(
        self,
        *,
        min_delay_sec: float = 1.5,
        max_retries: int = 4,
        base_backoff_sec: float = 6.0,
        max_backoff_sec: float = 120.0,
        on_progress: ProgressCallback | None = None,
    ):
        self.min_delay_sec = min_delay_sec
        self.max_retries = max_retries
        self.base_backoff_sec = base_backoff_sec
        self.max_backoff_sec = max_backoff_sec
        self.on_progress = on_progress
        self._last_request_at = 0.0
        self.logs: list[dict[str, str]] = []

    def log(self, level: str, message: str) -> None:
        entry = {"level": level, "message": message, "ts": str(int(time.time()))}
        self.logs.append(entry)
        if self.on_progress:
            self.on_progress(level, message)

    def wait_turn(self, label: str = "") -> None:
        elapsed = time.time() - self._last_request_at
        if self._last_request_at and elapsed < self.min_delay_sec:
            wait = self.min_delay_sec - elapsed
            self.log("wait", f"Queue delay ({wait:.0f}s){f' — {label}' if label else ''}...")
            time.sleep(wait)

    def mark_sent(self) -> None:
        self._last_request_at = time.time()

    def backoff(self, attempt: int, retry_after: int | None = None, provider: str = "API") -> None:
        if retry_after is not None and retry_after > 0:
            wait = min(float(retry_after), self.max_backoff_sec)
        else:
            wait = min(self.base_backoff_sec * (2**attempt), self.max_backoff_sec)
        self.log(
            "retry",
            f"{provider} rate limit (429). Pausing {wait:.0f}s before retry {attempt + 1}/{self.max_retries}...",
        )
        time.sleep(wait)
