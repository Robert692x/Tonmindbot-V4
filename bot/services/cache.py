from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from redis.asyncio import Redis

log = logging.getLogger(__name__)


class CacheService(ABC):
    @abstractmethod
    async def get_json(self, key: str) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        raise NotImplementedError

    @abstractmethod
    async def increment(self, key: str, ttl_seconds: int) -> int:
        raise NotImplementedError

    @abstractmethod
    async def remember_once(self, key: str, ttl_seconds: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError


class MemoryCacheService(CacheService):
    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()

    async def _get_raw(self, key: str) -> Any:
        cached = self._store.get(key)
        if cached is None:
            return None
        value, expires_at = cached
        if expires_at <= time.monotonic():
            self._store.pop(key, None)
            return None
        return value

    async def get_json(self, key: str) -> Any:
        async with self._lock:
            return await self._get_raw(key)

    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        async with self._lock:
            self._store[key] = (value, time.monotonic() + ttl_seconds)

    async def increment(self, key: str, ttl_seconds: int) -> int:
        async with self._lock:
            current = await self._get_raw(key)
            next_value = int(current or 0) + 1
            self._store[key] = (next_value, time.monotonic() + ttl_seconds)
            return next_value

    async def remember_once(self, key: str, ttl_seconds: int) -> bool:
        async with self._lock:
            current = await self._get_raw(key)
            if current is not None:
                return False
            self._store[key] = (True, time.monotonic() + ttl_seconds)
            return True

    async def close(self) -> None:
        self._store.clear()


class RedisCacheService(CacheService):
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get_json(self, key: str) -> Any:
        value = await self._redis.get(key)
        return None if value is None else json.loads(value)

    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        await self._redis.set(key, json.dumps(value), ex=ttl_seconds)

    async def increment(self, key: str, ttl_seconds: int) -> int:
        async with self._redis.pipeline() as pipeline:
            pipeline.incr(key)
            pipeline.expire(key, ttl_seconds)
            result = await pipeline.execute()
        return int(result[0])

    async def remember_once(self, key: str, ttl_seconds: int) -> bool:
        return bool(await self._redis.set(key, "1", ex=ttl_seconds, nx=True))

    async def close(self) -> None:
        await self._redis.close()


async def build_cache_service(redis_url: str | None) -> CacheService:
    if not redis_url:
        return MemoryCacheService()
    try:
        redis = Redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        await redis.ping()
        return RedisCacheService(redis)
    except Exception as exc:
        log.warning("Redis unavailable, using in-memory cache: %s", exc)
        return MemoryCacheService()
