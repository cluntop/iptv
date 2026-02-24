import asyncio
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypeVar

import aiohttp

from .logger import get_logger

logger = get_logger("concurrency")

T = TypeVar("T")
R = TypeVar("R")


@dataclass
class ConcurrencyConfig:
    max_workers: int = field(default_factory=lambda: min(32, (os.cpu_count() or 4) * 4))
    async_semaphore_limit: int = field(default_factory=lambda: min(800, int(os.cpu_count() or 4) * 100))
    batch_size: int = 50
    timeout: int = 30
    retry_count: int = 3
    retry_delay: float = 1.0


class AsyncBatcher:
    def __init__(self, config: ConcurrencyConfig = None):
        self.config = config or ConcurrencyConfig()
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self._semaphore = asyncio.Semaphore(self.config.async_semaphore_limit)
        connector = aiohttp.TCPConnector(
            limit=self.config.async_semaphore_limit,
            limit_per_host=min(100, self.config.async_semaphore_limit // 2),
            ttl_dns_cache=300,
            use_dns_cache=True,
            keepalive_timeout=30,
        )
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.timeout, connect=10),
            connector=connector,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()

    @property
    def session(self) -> aiohttp.ClientSession:
        return self._session

    @property
    def semaphore(self) -> asyncio.Semaphore:
        return self._semaphore

    async def run_tasks(
        self,
        items: List[T],
        handler: Callable[[T], Awaitable[R]],
        progress_callback: Callable[[int, int], None] = None,
    ) -> List[R]:
        if not items:
            return []

        results = []
        completed = []
        progress_lock = asyncio.Lock()

        async def process_with_semaphore(idx: int, item: T):
            async with self._semaphore:
                result = await handler(item)
                async with progress_lock:
                    completed.append(item)
                    if progress_callback:
                        progress_callback(len(completed), len(items))
                return result

        tasks = [asyncio.create_task(process_with_semaphore(i, item)) for i, item in enumerate(items)]

        for future in asyncio.as_completed(tasks):
            try:
                result = await future
                if result is not None:
                    results.append(result)
            except Exception as e:
                logger.error(f"Task failed: {e}")

        return results

    async def run_batched(
        self,
        items: List[T],
        handler: Callable[[List[T]], Awaitable[List[R]]],
        batch_size: int = None,
    ) -> List[R]:
        if not items:
            return []

        batch_size = batch_size or self.config.batch_size
        all_results = []

        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]
            logger.info(f"Processing batch {i // batch_size + 1}: {len(batch)} items")
            results = await handler(batch)
            all_results.extend(results)

        return all_results


class ThreadPoolBatcher:
    def __init__(self, config: ConcurrencyConfig = None):
        self.config = config or ConcurrencyConfig()
        self._executor: Optional[ThreadPoolExecutor] = None

    def __enter__(self):
        self._executor = ThreadPoolExecutor(max_workers=self.config.max_workers)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._executor:
            self._executor.shutdown(wait=True)

    @property
    def executor(self) -> ThreadPoolExecutor:
        return self._executor

    def map(self, func: Callable[[T], R], items: List[T]) -> List[R]:
        if not items:
            return []

        results = list(self._executor.map(func, items))
        return results

    def submit_batch(
        self,
        items: List[T],
        handler: Callable[[T], R],
        callback: Callable[[R], None] = None,
    ) -> List[R]:
        if not items:
            return []

        futures = {self._executor.submit(handler, item): item for item in items}
        results = []

        for future in as_completed(futures):
            try:
                result = future.result()
                results.append(result)
                if callback:
                    callback(result)
            except Exception as e:
                logger.error(f"Task failed: {e}")

        return results

    def submit_with_results(self, items: List[T], handler: Callable[[T], R]) -> List[R]:
        if not items:
            return []

        futures = [self._executor.submit(handler, item) for item in items]
        results = []

        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                logger.error(f"Task failed: {e}")

        return results


class RateLimiter:
    def __init__(self, rate: int, per_seconds: float = 1.0):
        self.rate = rate
        self.per_seconds = per_seconds
        self.tokens = rate
        self.last_update = asyncio.get_event_loop().time()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            while self.tokens <= 0:
                await asyncio.sleep(0.1)
                self._refill()
            self.tokens -= 1

    def _refill(self):
        now = asyncio.get_event_loop().time()
        elapsed = now - self.last_update
        self.tokens = min(self.rate, self.tokens + elapsed * (self.rate / self.per_seconds))
        self.last_update = now


async def run_async_tasks(
    items: List[T],
    handler: Callable[[T], Awaitable[R]],
    max_concurrent: int = 100,
    progress_callback: Callable[[int, int], None] = None,
) -> List[R]:
    semaphore = asyncio.Semaphore(max_concurrent)
    results = []
    completed = []
    lock = asyncio.Lock()

    async def process(item: T):
        async with semaphore:
            result = await handler(item)
            async with lock:
                completed.append(item)
                if progress_callback:
                    progress_callback(len(completed), len(items))
            return result

    tasks = [asyncio.create_task(process(item)) for item in items]

    for future in asyncio.as_completed(tasks):
        try:
            result = await future
            if result is not None:
                results.append(result)
        except Exception as e:
            logger.error(f"Task failed: {e}")

    return results


def run_thread_tasks(
    items: List[T],
    handler: Callable[[T], R],
    max_workers: int = None,
) -> List[R]:
    if not items:
        return []

    if max_workers is None:
        max_workers = min(32, (os.cpu_count() or 4) * 4)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(handler, item) for item in items]
        results = []

        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                logger.error(f"Task failed: {e}")

    return results


async def retry_async(
    func: Callable[..., Awaitable[T]],
    *args,
    max_retries: int = 3,
    delay: float = 1.0,
    **kwargs,
) -> Optional[T]:
    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            if attempt < max_retries - 1:
                logger.debug(f"Retry {attempt + 1}/{max_retries} for {func.__name__}: {e}")
                await asyncio.sleep(delay * (attempt + 1))
            else:
                logger.error(f"All retries failed for {func.__name__}: {e}")
    return None


class TaskQueue:
    def __init__(self, config: ConcurrencyConfig = None):
        self.config = config or ConcurrencyConfig()
        self._queue: asyncio.Queue = asyncio.Queue()
        self._workers: List[asyncio.Task] = []
        self._running = False

    async def _worker(self, handler: Callable[[T], Awaitable[None]]):
        while self._running:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await handler(item)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Worker error: {e}")

    async def start(self, handler: Callable[[T], Awaitable[None]], num_workers: int = None):
        num_workers = num_workers or self.config.max_workers
        self._running = True
        self._workers = [asyncio.create_task(self._worker(handler)) for _ in range(num_workers)]

    async def put(self, item: T):
        await self._queue.put(item)

    async def stop(self):
        self._running = False
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)

    def size(self) -> int:
        return self._queue.qsize()


def get_concurrency_config() -> ConcurrencyConfig:
    try:
        from ..config import get_config

        config = get_config()
        return ConcurrencyConfig(
            max_workers=config.scraper.concurrency_limit // 10 if hasattr(config, "scraper") else 32,
            async_semaphore_limit=config.scraper.concurrency_limit if hasattr(config, "scraper") else 800,
            batch_size=getattr(config, "batch_size", 50),
            timeout=config.scraper.timeout if hasattr(config, "scraper") else 30,
        )
    except Exception:
        return ConcurrencyConfig()
