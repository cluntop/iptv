import asyncio
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from typing import Any, Callable, Dict, List, Optional

import aiohttp

from ..utils import get_logger

logger = get_logger("base_scraper")


class BaseScraper(ABC):
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.timeout = self.config.get("timeout", 15)
        self.max_retries = self.config.get("max_retries", 3)
        self.retry_delay = self.config.get("retry_delay", 1.0)
        self.concurrency_limit = self.config.get("concurrency_limit", 100)
        self.thread_pool_size = self.config.get("thread_pool_size", min(32, (self.concurrency_limit // 10) + 4))

        self.session = None
        self.executor = None
        self.results_queue = Queue()
        self._semaphore: Optional[asyncio.Semaphore] = None

    async def __aenter__(self):
        connector = aiohttp.TCPConnector(
            limit=self.concurrency_limit,
            limit_per_host=min(100, self.concurrency_limit // 2),
            ttl_dns_cache=300,
            use_dns_cache=True,
            keepalive_timeout=30,
            enable_cleanup_closed=True,
        )
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout, connect=10, sock_read=self.timeout),
            connector=connector,
        )
        self.executor = ThreadPoolExecutor(max_workers=self.thread_pool_size)
        self._semaphore = asyncio.Semaphore(self.concurrency_limit)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
        if self.executor:
            self.executor.shutdown(wait=True)

    async def fetch_url(self, url: str, method: str = "GET", **kwargs) -> Optional[aiohttp.ClientResponse]:
        for attempt in range(self.max_retries):
            try:
                async with self.session.request(method, url, **kwargs) as response:
                    if response.status == 200:
                        return response
                    logger.warning(f"Request to {url} returned status {response.status}")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.debug(f"Attempt {attempt + 1} failed for {url}: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)

        return None

    async def fetch_text(self, url: str, encoding: str = "utf-8") -> Optional[str]:
        response = await self.fetch_url(url)
        if response:
            try:
                return await response.text(encoding=encoding)
            except Exception as e:
                logger.error(f"Failed to decode response from {url}: {e}")
        return None

    async def fetch_json(self, url: str) -> Optional[Dict[str, Any]]:
        response = await self.fetch_url(url)
        if response:
            try:
                return await response.json()
            except Exception as e:
                logger.error(f"Failed to parse JSON from {url}: {e}")
        return None

    async def fetch_binary(self, url: str) -> Optional[bytes]:
        response = await self.fetch_url(url)
        if response:
            try:
                return await response.read()
            except Exception as e:
                logger.error(f"Failed to read binary from {url}: {e}")
        return None

    async def fetch_multiple(self, urls: List[str], handler: Callable[[str, Any], None] = None) -> List[Any]:
        if not urls:
            return []

        results = [None] * len(urls)
        pending = {}

        async def fetch_with_semaphore(idx: int, url: str):
            async with self._semaphore:
                return idx, await self.fetch_text(url)

        tasks = [asyncio.create_task(fetch_with_semaphore(i, url)) for i, url in enumerate(urls)]
        for task in tasks:
            pending[task] = task

        for future in asyncio.as_completed(tasks):
            idx, result = await future
            results[idx] = result
            if result and handler:
                handler(urls[idx], result)

        return results

    def run_in_thread(self, func: Callable, *args, **kwargs) -> Any:
        if self.executor:
            future = self.executor.submit(func, *args, **kwargs)
            return future.result()
        return func(*args, **kwargs)

    @abstractmethod
    async def scrape(self, *args, **kwargs) -> Any:
        pass

    def scrape_sync(self, *args, **kwargs) -> Any:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            with ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self.scrape(*args, **kwargs))
                return future.result()
        else:
            return asyncio.run(self.scrape(*args, **kwargs))

    def process_queue(self, handler: Callable, batch_size: int = 100) -> int:
        processed = 0
        batch = []

        while not self.results_queue.empty():
            item = self.results_queue.get()
            batch.append(item)

            if len(batch) >= batch_size:
                handler(batch)
                processed += len(batch)
                batch = []

        if batch:
            handler(batch)
            processed += len(batch)

        return processed

    def log_progress(self, current: int, total: int, message: str = ""):
        if total > 0:
            progress = (current / total) * 100
            logger.info(f"{message} Progress: {current}/{total} ({progress:.1f}%)")
        else:
            logger.info(f"{message} Processed: {current}")
