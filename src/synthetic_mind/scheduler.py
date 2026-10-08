from __future__ import annotations

import asyncio
import heapq
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

from .config import GovernorConfig
from .schemas import ScheduledWork


class Scheduler:
    def __init__(self, capacity: int = 2048):
        self.capacity = capacity
        self.queue: list[ScheduledWork] = []
        self.sequence = 0
        self.closed = False

    def schedule(self, name: str, callback: Callable[[], Awaitable[Any]], priority: int = 50) -> None:
        if self.closed:
            raise RuntimeError("Scheduler is closed")
        if len(self.queue) >= self.capacity:
            raise OverflowError("Scheduler capacity exceeded")
        self.sequence += 1
        heapq.heappush(self.queue, ScheduledWork(priority, self.sequence, name, callback))

    async def run(self) -> None:
        while self.queue:
            task = heapq.heappop(self.queue)
            await task.callback()

    async def close(self) -> None:
        await self.run()
        self.closed = True


class BudgetExceeded(RuntimeError):
    pass


class ComputeGovernor:
    def __init__(self, config: GovernorConfig, clock: Callable[[], float] = time.monotonic):
        self.config, self.clock = config, clock
        self.reservations: deque[tuple[float, int]] = deque()
        self.active = 0
        self.total_calls = 0

    async def execute(self, callback: Callable[[], Awaitable[Any]], *, input_tokens: int, output_tokens: int) -> Any:
        if min(input_tokens, output_tokens) < 0:
            raise ValueError("Negative token reservation")
        now = self.clock()
        while self.reservations and now - self.reservations[0][0] >= 60:
            self.reservations.popleft()
        tokens = input_tokens + output_tokens
        if (len(self.reservations) >= self.config.calls_per_minute
                or sum(item[1] for item in self.reservations) + tokens > self.config.tokens_per_minute
                or self.active >= self.config.max_concurrent):
            raise BudgetExceeded("Inference reservation exceeds compute budget")
        # Reservations survive failed calls: unsuccessful inference can still cost compute.
        self.reservations.append((now, tokens))
        self.active += 1
        self.total_calls += 1
        try:
            return await asyncio.wait_for(callback(), self.config.max_seconds_per_call)
        finally:
            self.active -= 1
