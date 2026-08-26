"""Abuse protection for a publicly reachable deployment.

A public URL means strangers (and crawlers) can call the AI endpoints, and
every call spends *your* Gemini quota. Two independent limits:

* **Per-IP rate limit** — stops one visitor hammering the endpoint.
* **Global daily cap** — bounds the worst case for the whole service, so a
  bad day costs a known maximum rather than an open-ended bill.

Both are in-process (no Redis needed). That's the right trade-off for a
single small instance; if you ever scale to several instances, move the
counters to Redis so they're shared.

Tunable via env::

    LAWHUB_RATE_PER_MIN=5        # AI calls per IP per minute
    LAWHUB_RATE_PER_DAY=40       # AI calls per IP per day
    LAWHUB_GLOBAL_PER_DAY=500    # AI calls across all users per day
    LAWHUB_PUBLIC=1              # set on the public deploy
"""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import HTTPException, Request


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass
class Limits:
    per_min: int = _int_env("LAWHUB_RATE_PER_MIN", 5)
    per_day: int = _int_env("LAWHUB_RATE_PER_DAY", 40)
    global_per_day: int = _int_env("LAWHUB_GLOBAL_PER_DAY", 500)


class RateLimiter:
    def __init__(self, limits: Limits | None = None):
        self.limits = limits or Limits()
        self._minute: dict[str, deque[float]] = defaultdict(deque)
        self._day: dict[str, deque[float]] = defaultdict(deque)
        self._global: deque[float] = deque()

    @staticmethod
    def client_ip(request: Request) -> str:
        # Behind a proxy (Render/Fly/Cloud Run) the real IP is in this header.
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    @staticmethod
    def _prune(dq: deque[float], window: float, now: float) -> None:
        while dq and now - dq[0] > window:
            dq.popleft()

    def check(self, request: Request) -> None:
        """Raise 429 when a limit is exceeded; otherwise record the hit."""
        now = time.time()
        ip = self.client_ip(request)

        self._prune(self._global, 86400, now)
        if len(self._global) >= self.limits.global_per_day:
            raise HTTPException(
                429,
                "本服務今日的 AI 使用額度已達上限，請明日再試。"
                "（這是示範站的成本保護機制）",
            )

        m = self._minute[ip]
        self._prune(m, 60, now)
        if len(m) >= self.limits.per_min:
            raise HTTPException(429, "請求過於頻繁，請稍候再試（每分鐘上限 "
                                     f"{self.limits.per_min} 次）。")

        d = self._day[ip]
        self._prune(d, 86400, now)
        if len(d) >= self.limits.per_day:
            raise HTTPException(429, "您今日的使用次數已達上限（每日 "
                                     f"{self.limits.per_day} 次），請明日再試。")

        m.append(now)
        d.append(now)
        self._global.append(now)

    def snapshot(self) -> dict:
        now = time.time()
        self._prune(self._global, 86400, now)
        return {
            "global_used_today": len(self._global),
            "global_limit": self.limits.global_per_day,
            "per_ip_per_min": self.limits.per_min,
            "per_ip_per_day": self.limits.per_day,
        }


limiter = RateLimiter()


def is_public() -> bool:
    return os.getenv("LAWHUB_PUBLIC", "").lower() in ("1", "true", "yes")
