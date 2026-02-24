import asyncio
import csv
import socket
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from ..utils import get_logger

logger = get_logger("proxy_detector")


@dataclass
class ProxyInfo:
    host: str
    port: int
    protocol: str = "http"
    username: Optional[str] = None
    password: Optional[str] = None

    def to_url(self) -> str:
        if self.username and self.password:
            return f"{self.protocol}://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"{self.protocol}://{self.host}:{self.port}"

    def __str__(self) -> str:
        return self.to_url()


@dataclass
class ProxyCheckResult:
    proxy: ProxyInfo
    is_valid: bool = False
    latency_ms: float = 0.0
    exit_ip: Optional[str] = None
    exit_country: Optional[str] = None
    exit_region: Optional[str] = None
    exit_city: Optional[str] = None
    exit_isp: Optional[str] = None
    exit_asn: Optional[str] = None
    is_anonymous: bool = False
    is_high_anonymous: bool = False
    error_message: Optional[str] = None
    check_time: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["proxy"] = self.proxy.to_url()
        if self.check_time:
            data["check_time"] = self.check_time.isoformat()
        return data


class ProxyDetector:
    IP_CHECK_URLS = [
        "http://ip-api.com/json/",
        "http://ipinfo.io/json",
        "https://api.ipify.org?format=json",
    ]

    ANONYMITY_CHECK_URL = "http://httpbin.org/headers"

    def __init__(self, timeout: int = 15, max_concurrent: int = 50):
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.semaphore = None

    async def _create_session_with_proxy(self, proxy: ProxyInfo) -> aiohttp.ClientSession:
        connector = aiohttp.TCPConnector(ssl=False)

        if proxy.protocol.lower() == "socks5":
            try:
                from aiohttp_socks import ProxyConnector

                connector = ProxyConnector.from_url(proxy.to_url())
                return aiohttp.ClientSession(
                    connector=connector,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                )
            except ImportError:
                logger.warning("aiohttp-socks not installed, SOCKS5 proxy may not work")

        return aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))

    async def check_proxy_basic(self, proxy: ProxyInfo, test_url: str = "http://www.google.com") -> Tuple[bool, float]:
        start_time = time.time()

        try:
            if proxy.protocol.lower() == "socks5":
                session = await self._create_session_with_proxy(proxy)
                try:
                    async with session.get(test_url, proxy=None) as response:
                        latency = (time.time() - start_time) * 1000
                        return response.status == 200, latency
                finally:
                    await session.close()
            else:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                    async with session.get(test_url, proxy=proxy.to_url()) as response:
                        latency = (time.time() - start_time) * 1000
                        return response.status == 200, latency

        except Exception as e:
            logger.debug(f"Proxy {proxy} basic check failed: {e}")
            return False, 0.0

    async def get_exit_ip_info(self, proxy: ProxyInfo) -> Dict[str, Any]:
        result = {
            "exit_ip": None,
            "country": None,
            "region": None,
            "city": None,
            "isp": None,
            "asn": None,
        }

        try:
            if proxy.protocol.lower() == "socks5":
                session = await self._create_session_with_proxy(proxy)
                try:
                    async with session.get(self.IP_CHECK_URLS[0]) as response:
                        if response.status == 200:
                            data = await response.json()
                            result["exit_ip"] = data.get("query")
                            result["country"] = data.get("country")
                            result["region"] = data.get("regionName")
                            result["city"] = data.get("city")
                            result["isp"] = data.get("isp")
                            result["asn"] = data.get("as")
                finally:
                    await session.close()
            else:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                    async with session.get(self.IP_CHECK_URLS[0], proxy=proxy.to_url()) as response:
                        if response.status == 200:
                            data = await response.json()
                            result["exit_ip"] = data.get("query")
                            result["country"] = data.get("country")
                            result["region"] = data.get("regionName")
                            result["city"] = data.get("city")
                            result["isp"] = data.get("isp")
                            result["asn"] = data.get("as")

        except Exception as e:
            logger.debug(f"Failed to get exit IP info for {proxy}: {e}")

        return result

    async def check_anonymity(self, proxy: ProxyInfo) -> Tuple[bool, bool]:
        is_anonymous = False
        is_high_anonymous = False

        try:
            local_ip = await self._get_local_ip()

            if proxy.protocol.lower() == "socks5":
                session = await self._create_session_with_proxy(proxy)
                try:
                    async with session.get(self.ANONYMITY_CHECK_URL) as response:
                        if response.status == 200:
                            data = await response.json()
                            headers = data.get("headers", {})

                            proxy_headers = [
                                "X-Forwarded-For",
                                "X-Real-Ip",
                                "Via",
                                "X-Proxy-Id",
                            ]
                            has_proxy_headers = any(h in headers for h in proxy_headers)

                            forwarded_for = headers.get("X-Forwarded-For", "")

                            if local_ip not in forwarded_for and local_ip not in str(headers):
                                is_anonymous = True
                                if not has_proxy_headers:
                                    is_high_anonymous = True
                finally:
                    await session.close()
            else:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                    async with session.get(self.ANONYMITY_CHECK_URL, proxy=proxy.to_url()) as response:
                        if response.status == 200:
                            data = await response.json()
                            headers = data.get("headers", {})

                            proxy_headers = [
                                "X-Forwarded-For",
                                "X-Real-Ip",
                                "Via",
                                "X-Proxy-Id",
                            ]
                            has_proxy_headers = any(h in headers for h in proxy_headers)

                            forwarded_for = headers.get("X-Forwarded-For", "")

                            if local_ip not in forwarded_for and local_ip not in str(headers):
                                is_anonymous = True
                                if not has_proxy_headers:
                                    is_high_anonymous = True

        except Exception as e:
            logger.debug(f"Anonymity check failed for {proxy}: {e}")

        return is_anonymous, is_high_anonymous

    async def _get_local_ip(self) -> str:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get("https://api.ipify.org?format=json") as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("ip", "")
        except Exception:
            pass

        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return ""

    async def check_proxy_full(self, proxy: ProxyInfo) -> ProxyCheckResult:
        async with self.semaphore:
            result = ProxyCheckResult(proxy=proxy, check_time=datetime.now())

            is_valid, latency = await self.check_proxy_basic(proxy)
            result.latency_ms = round(latency, 2)

            if not is_valid:
                result.error_message = "Connection failed"
                return result

            result.is_valid = True

            ip_info = await self.get_exit_ip_info(proxy)
            result.exit_ip = ip_info.get("exit_ip")
            result.exit_country = ip_info.get("country")
            result.exit_region = ip_info.get("region")
            result.exit_city = ip_info.get("city")
            result.exit_isp = ip_info.get("isp")
            result.exit_asn = ip_info.get("asn")

            is_anon, is_high_anon = await self.check_anonymity(proxy)
            result.is_anonymous = is_anon
            result.is_high_anonymous = is_high_anon

            logger.info(
                f"Proxy {proxy} check completed: valid={result.is_valid}, "
                f"latency={result.latency_ms}ms, exit_ip={result.exit_ip}"
            )

            return result

    async def check_proxies_batch(self, proxies: List[ProxyInfo]) -> List[ProxyCheckResult]:
        self.semaphore = asyncio.Semaphore(self.max_concurrent)

        tasks = [self.check_proxy_full(proxy) for proxy in proxies]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                valid_results.append(
                    ProxyCheckResult(
                        proxy=proxies[i],
                        is_valid=False,
                        error_message=str(result),
                        check_time=datetime.now(),
                    )
                )
            else:
                valid_results.append(result)

        return valid_results

    def check_proxies_sync(self, proxies: List[ProxyInfo]) -> List[ProxyCheckResult]:
        return asyncio.run(self.check_proxies_batch(proxies))


class ProxyFileParser:
    @staticmethod
    def parse_line(line: str) -> Optional[ProxyInfo]:
        line = line.strip()
        if not line or line.startswith("#"):
            return None

        parts = None

        if "://" in line:
            protocol_rest = line.split("://", 1)
            protocol = protocol_rest[0].lower()
            rest = protocol_rest[1]

            if "@" in rest:
                auth_host = rest.split("@")
                if len(auth_host) == 2:
                    user_pass = auth_host[0].split(":")
                    host_port = auth_host[1].split(":")
                    if len(user_pass) == 2 and len(host_port) == 2:
                        return ProxyInfo(
                            host=host_port[0],
                            port=int(host_port[1]),
                            protocol=protocol,
                            username=user_pass[0],
                            password=user_pass[1],
                        )
            else:
                parts = rest.split(":")
                if len(parts) >= 2:
                    return ProxyInfo(host=parts[0], port=int(parts[1]), protocol=protocol)

        parts = line.split(":")
        if len(parts) >= 2:
            host = parts[0]
            port = int(parts[1])
            username = parts[2] if len(parts) > 2 else None
            password = parts[3] if len(parts) > 3 else None
            protocol = parts[4] if len(parts) > 4 else "http"

            return ProxyInfo(
                host=host,
                port=port,
                protocol=protocol,
                username=username,
                password=password,
            )

        return None

    @staticmethod
    def parse_txt_file(file_path: str) -> List[ProxyInfo]:
        proxies = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    proxy = ProxyFileParser.parse_line(line)
                    if proxy:
                        proxies.append(proxy)

        except Exception as e:
            logger.error(f"Failed to parse TXT file {file_path}: {e}")

        logger.info(f"Parsed {len(proxies)} proxies from {file_path}")
        return proxies

    @staticmethod
    def parse_csv_file(file_path: str) -> List[ProxyInfo]:
        proxies = []

        try:
            with open(file_path, "r", encoding="utf-8", newline="") as f:
                reader = csv.reader(f)
                header = next(reader, None)

                if header:
                    header = [h.lower().strip() for h in header]

                    host_idx = next(
                        (i for i, h in enumerate(header) if h in ["host", "ip", "proxy"]),
                        None,
                    )
                    port_idx = next((i for i, h in enumerate(header) if h == "port"), None)
                    protocol_idx = next(
                        (i for i, h in enumerate(header) if h in ["protocol", "type"]),
                        None,
                    )
                    username_idx = next(
                        (i for i, h in enumerate(header) if h in ["username", "user"]),
                        None,
                    )
                    password_idx = next(
                        (i for i, h in enumerate(header) if h in ["password", "pass"]),
                        None,
                    )

                    if host_idx is not None and port_idx is not None:
                        for row in reader:
                            if len(row) > max(host_idx, port_idx):
                                proxy = ProxyInfo(
                                    host=row[host_idx],
                                    port=int(row[port_idx]),
                                    protocol=(
                                        row[protocol_idx] if protocol_idx and len(row) > protocol_idx else "http"
                                    ),
                                    username=(row[username_idx] if username_idx and len(row) > username_idx else None),
                                    password=(row[password_idx] if password_idx and len(row) > password_idx else None),
                                )
                                proxies.append(proxy)
                else:
                    for row in reader:
                        if len(row) >= 2:
                            proxy = ProxyFileParser.parse_line(":".join(row[:2]))
                            if proxy:
                                proxies.append(proxy)

        except Exception as e:
            logger.error(f"Failed to parse CSV file {file_path}: {e}")

        logger.info(f"Parsed {len(proxies)} proxies from {file_path}")
        return proxies

    @staticmethod
    def parse_file(file_path: str) -> List[ProxyInfo]:
        path = Path(file_path)

        if not path.exists():
            logger.error(f"File not found: {file_path}")
            return []

        suffix = path.suffix.lower()

        if suffix == ".csv":
            return ProxyFileParser.parse_csv_file(file_path)
        else:
            return ProxyFileParser.parse_txt_file(file_path)


class ProxyService:
    def __init__(self, timeout: int = 15, max_concurrent: int = 50):
        self.detector = ProxyDetector(timeout=timeout, max_concurrent=max_concurrent)

    def check_single_proxy(
        self,
        host: str,
        port: int,
        protocol: str = "http",
        username: str = None,
        password: str = None,
    ) -> ProxyCheckResult:
        proxy = ProxyInfo(
            host=host,
            port=port,
            protocol=protocol,
            username=username,
            password=password,
        )
        return self.detector.check_proxies_sync([proxy])[0]

    def check_proxies_from_file(self, file_path: str) -> List[ProxyCheckResult]:
        proxies = ProxyFileParser.parse_file(file_path)
        if not proxies:
            return []
        return self.detector.check_proxies_sync(proxies)

    def check_proxies_list(self, proxy_list: List[Dict[str, Any]]) -> List[ProxyCheckResult]:
        proxies = []
        for item in proxy_list:
            proxy = ProxyInfo(
                host=item.get("host", item.get("ip", "")),
                port=int(item.get("port", 0)),
                protocol=item.get("protocol", item.get("type", "http")),
                username=item.get("username", item.get("user")),
                password=item.get("password", item.get("pass")),
            )
            if proxy.host and proxy.port:
                proxies.append(proxy)

        if not proxies:
            return []

        return self.detector.check_proxies_sync(proxies)

    def get_valid_proxies(
        self,
        results: List[ProxyCheckResult],
        min_latency: float = 0,
        require_anonymous: bool = False,
    ) -> List[ProxyCheckResult]:
        valid = []

        for result in results:
            if not result.is_valid:
                continue

            if min_latency > 0 and result.latency_ms > min_latency:
                continue

            if require_anonymous and not result.is_anonymous:
                continue

            valid.append(result)

        valid.sort(key=lambda x: x.latency_ms)
        return valid

    def export_results(self, results: List[ProxyCheckResult], output_path: str, format: str = "txt") -> bool:
        try:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            if format.lower() == "csv":
                with open(path, "w", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        [
                            "proxy",
                            "valid",
                            "latency_ms",
                            "exit_ip",
                            "country",
                            "region",
                            "city",
                            "isp",
                            "asn",
                            "anonymous",
                            "high_anonymous",
                            "error",
                        ]
                    )

                    for result in results:
                        writer.writerow(
                            [
                                result.proxy.to_url(),
                                result.is_valid,
                                result.latency_ms,
                                result.exit_ip or "",
                                result.exit_country or "",
                                result.exit_region or "",
                                result.exit_city or "",
                                result.exit_isp or "",
                                result.exit_asn or "",
                                result.is_anonymous,
                                result.is_high_anonymous,
                                result.error_message or "",
                            ]
                        )
            else:
                with open(path, "w", encoding="utf-8") as f:
                    for result in results:
                        if result.is_valid:
                            f.write(f"{result.proxy.to_url()}\n")

            logger.info(f"Exported {len(results)} proxy results to {output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to export results: {e}")
            return False
