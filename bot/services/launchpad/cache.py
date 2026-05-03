from __future__ import annotations

import asyncio
from time import monotonic

_SEEN_TTL = 4 * 3600  # 4 hours — long enough to survive restarts between polling cycles


class LaunchpadCache:
    """
    In-memory dedup store for seen pair addresses.

    Thread-safe via asyncio.Lock. Expired entries are lazily pruned on read
    and explicitly by cleanup(), which the background worker calls periodically.
    """

    def __init__(self) -> None:
        self._seen: dict[str, float] = {}  # pair_address -> monotonic timestamp
        self._lock = asyncio.Lock()

    async def is_seen(self, pair_address: str) -> bool:
        async with self._lock:
            ts = self._seen.get(pair_address)
            if ts is None:
                return False
            if monotonic() - ts > _SEEN_TTL:
                del self._seen[pair_address]
                return False
            return True

    async def mark_seen(self, pair_address: str) -> None:
        async with self._lock:
            self._seen[pair_address] = monotonic()

    async def cleanup(self) -> int:
        """Purge expired entries. Returns the count removed."""
        now = monotonic()
        async with self._lock:
            expired = [k for k, v in self._seen.items() if now - v > _SEEN_TTL]
            for k in expired:
                del self._seen[k]
        return len(expired)

    @property
    def size(self) -> int:
        return len(self._seen)
