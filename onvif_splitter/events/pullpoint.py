from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

DEFAULT_TTL = 60  # seconds
MAX_TTL = 300


@dataclass
class Subscription:
    id: str
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    created: float = field(default_factory=time.time)
    ttl: float = DEFAULT_TTL
    last_poll: float = field(default_factory=time.time)

    @property
    def expired(self) -> bool:
        return time.time() > self.last_poll + self.ttl + 30  # grace period

    def renew(self, ttl: float | None = None):
        self.last_poll = time.time()
        if ttl is not None:
            self.ttl = min(ttl, MAX_TTL)


class PullPointManager:
    def __init__(self):
        self._subscriptions: dict[str, Subscription] = {}
        self._gc_task: asyncio.Task | None = None

    def start_gc(self):
        if self._gc_task is None:
            self._gc_task = asyncio.create_task(self._gc_loop())

    async def _gc_loop(self):
        while True:
            await asyncio.sleep(30)
            expired = [
                sid for sid, sub in self._subscriptions.items() if sub.expired
            ]
            for sid in expired:
                del self._subscriptions[sid]
                log.debug("GC'd expired subscription %s", sid)

    def create_subscription(self, ttl: float = DEFAULT_TTL) -> Subscription:
        self.start_gc()
        sub_id = str(uuid.uuid4())
        sub = Subscription(id=sub_id, ttl=min(ttl, MAX_TTL))
        self._subscriptions[sub_id] = sub
        log.info("Created subscription %s (ttl=%ds)", sub_id, sub.ttl)
        return sub

    def get_subscription(self, sub_id: str) -> Subscription | None:
        return self._subscriptions.get(sub_id)

    def remove_subscription(self, sub_id: str):
        self._subscriptions.pop(sub_id, None)
        log.info("Removed subscription %s", sub_id)

    def push_event(self, event_xml: str):
        for sub in self._subscriptions.values():
            if not sub.expired:
                try:
                    sub.queue.put_nowait(event_xml)
                except asyncio.QueueFull:
                    pass  # drop if consumer is too slow

    async def pull_messages(
        self, sub_id: str, timeout: float = 10, max_messages: int = 100
    ) -> list[str]:
        sub = self._subscriptions.get(sub_id)
        if sub is None:
            return []

        sub.last_poll = time.time()
        messages: list[str] = []

        # Drain any immediately available messages
        while len(messages) < max_messages:
            try:
                msg = sub.queue.get_nowait()
                messages.append(msg)
            except asyncio.QueueEmpty:
                break

        # If no messages yet, wait up to timeout for one
        if not messages:
            try:
                msg = await asyncio.wait_for(sub.queue.get(), timeout=min(timeout, 30))
                messages.append(msg)
                # Drain any more that arrived
                while len(messages) < max_messages:
                    try:
                        msg = sub.queue.get_nowait()
                        messages.append(msg)
                    except asyncio.QueueEmpty:
                        break
            except asyncio.TimeoutError:
                pass

        return messages

    def shutdown(self):
        if self._gc_task:
            self._gc_task.cancel()
            self._gc_task = None
        self._subscriptions.clear()
