"""Shared asynchronous request rate limiter."""

import asyncio
import time
from collections import deque


class RateLimiter:
    """Sliding-window attempt limiter shared by all rows."""

    def __init__(self, rpm: int) -> None:
        """Configure the rolling request limit."""
        self.rpm = rpm
        self.times: deque[float] = deque()
        self.lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Count an attempt before sending it."""
        async with self.lock:
            while True:
                now_time = time.monotonic()
                while self.times and self.times[0] <= now_time - 60:
                    self.times.popleft()
                if len(self.times) < self.rpm:
                    self.times.append(now_time)
                    return
                await asyncio.sleep(max(0, self.times[0] + 60 - now_time))
