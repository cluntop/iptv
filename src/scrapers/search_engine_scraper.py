import asyncio
import base64
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlencode

import aiohttp

from ..config import get_config
from ..database import Hotel, UDPxy
from ..utils import NetworkTools, get_logger
from .base_scraper import BaseScraper

logger = get_logger("search_engine_scraper")


class SearchQuery:
    def __init__(self, raw_query: str):
        self.raw_query = raw_query
        self.parsed = self._parse()

    def _parse(self) -> Dict[str, Any]:
        result = {
            "domain": None,
            "title": None,
            "body": None,
            "port": None,
            "country": None,
            "region": None,
            "city": None,
            "isp": None,
            "ip": None,
            "protocol": None,
            "app": None,
            "raw": self.raw_query,
        }

        patterns = {
            "domain": r'domain[=:]\s*["\']?([^"\'\s]+)["\']?',
            "title": r'title[=:]\s*["\']?([^"\'\s]+)["\']?',
            "body": r'body[=:]\s*["\']?([^"\'\s]+)["\']?',
            "port": r'port[=:]\s*["\']?(\d+)["\']?',
            "country": r'country[_cn]?[=:]\s*["\']?([^"\'\s]+)["\']?',
            "region": r'region[_cn]?[=:]\s*["\']?([^"\'\s]+)["\']?',
            "city": r'city[_cn]?[=:]\s*["\']?([^"\'\s]+)["\']?',
            "isp": r'isp[=:]\s*["\']?([^"\'\s]+)["\']?',
            "ip": r'ip[=:]\s*["\']?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})["\']?',
            "protocol": r'protocol[=:]\s*["\']?([^"\'\s]+)["\']?',
            "app": r'app[=:]\s*["\']?([^"\'\s]+)["\']?',
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, self.raw_query, re.IGNORECASE)
            if match:
                result[key] = match.group(1)

        return result

    def to_fofa_query(self) -> str:
        return self.raw_query

    def to_hunter_query(self) -> str:
        query = self.raw_query

        replacements = {
            "country_cn": "web.country",
            "region_cn": "web.region",
            "city_cn": "web.city",
            "isp": "isp",
            "port": "port",
        }

        for old, new in replacements.items():
            query = query.replace(old, new)

        return query

    def to_quake_query(self) -> str:
        query = self.raw_query

        quake_mappings = {
            "country": "country_cn",
            "region": "province_cn",
            "city": "city_cn",
        }

        for old, new in quake_mappings.items():
            if f"{old}=" in query and f"{new}=" not in query:
                query = query.replace(f"{old}=", f"{new}=")

        return query


class FofaScraper(BaseScraper):
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.api_url = "https://fofa.info/api/v1/search/all"
        self.api_token = (
            self.config.get("fofa_api_token") or get_config().fofa_api_token
        )
        self.net_tools = NetworkTools(timeout=self.timeout)

    async def search(
        self, query: str, size: int = 100, page: int = 1
    ) -> List[Dict[str, Any]]:
        if not self.api_token:
            logger.warning("FOFA API token not configured")
            return []

        search_query = SearchQuery(query)
        query_base64 = base64.b64encode(search_query.to_fofa_query().encode()).decode()

        params = {
            "email": "",
            "key": self.api_token,
            "qbase64": query_base64,
            "size": size,
            "page": page,
            "fields": "ip,port,protocol,server,domain",
        }

        results = []

        try:
            async with self.session.get(self.api_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    if data.get("error") and data.get("errmsg"):
                        logger.error(f"FOFA API error: {data['errmsg']}")
                        return []

                    for item in data.get("results", []):
                        results.append(
                            {
                                "ip": item[0],
                                "port": int(item[1]) if item[1] else 0,
                                "protocol": item[2] if len(item) > 2 else "",
                                "server": item[3] if len(item) > 3 else "",
                                "domain": item[4] if len(item) > 4 else "",
                                "source": "fofa",
                            }
                        )

                    logger.info(f"FOFA found {len(results)} results for query: {query}")

        except Exception as e:
            logger.error(f"FOFA search error: {e}")

        return results

    async def search_iptv_sources(
        self,
        country: str = "CN",
        region: str = None,
        isp: str = None,
        min_port: int = 8000,
        max_port: int = 9999,
    ) -> List[Hotel]:
        query_parts = ['"iptv/live/zh_cn.js"', f'country="{country}"']

        if region:
            query_parts.append(f'region="{region}"')
        if isp:
            query_parts.append(f'isp="{isp}"')

        query = " && ".join(query_parts)
        results = await self.search(query, size=200)

        hotels = []
        for item in results:
            ip = item["ip"]
            port = item["port"]

            if not min_port <= port <= max_port:
                continue

            if not self.net_tools.check_ip(ip):
                continue

            location = self.net_tools.get_ip_location(ip)

            hotel = Hotel(
                ip=ip,
                port=port,
                name=f"FOFA酒店源-{location}",
                count=0,
                status=0,
                time=datetime.now(),
            )
            hotels.append(hotel)

        logger.info(f"FOFA found {len(hotels)} potential hotel sources")
        return hotels

    async def scrape(self, query: str = None, **kwargs) -> Any:
        if query:
            return await self.search(query, **kwargs)
        return await self.search_iptv_sources(**kwargs)


class HunterScraper(BaseScraper):
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.api_url = "https://hunter.qianxin.com/openApi/search"
        self.api_key = self.config.get("hunter_api_key", "")
        self.net_tools = NetworkTools(timeout=self.timeout)

    async def search(
        self, query: str, size: int = 100, page: int = 1
    ) -> List[Dict[str, Any]]:
        if not self.api_key:
            logger.warning("Hunter API key not configured")
            return []

        search_query = SearchQuery(query)
        hunter_query = search_query.to_hunter_query()

        params = {
            "api-key": self.api_key,
            "search": hunter_query,
            "page": page,
            "page_size": size,
            "is_web": 1,
        }

        results = []

        try:
            async with self.session.get(self.api_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    if data.get("code") != 200:
                        logger.error(
                            f"Hunter API error: {data.get('message', 'Unknown error')}"
                        )
                        return []

                    for item in data.get("data", {}).get("arr", []):
                        results.append(
                            {
                                "ip": item.get("ip", ""),
                                "port": int(item.get("port", 0)),
                                "protocol": item.get("protocol", ""),
                                "domain": item.get("domain", ""),
                                "title": item.get("web_title", ""),
                                "source": "hunter",
                            }
                        )

                    logger.info(
                        f"Hunter found {len(results)} results for query: {query}"
                    )

        except Exception as e:
            logger.error(f"Hunter search error: {e}")

        return results

    async def search_iptv_sources(
        self, country: str = "中国", province: str = None, city: str = None
    ) -> List[Hotel]:
        query_parts = ["iptv/live/zh_cn.js"]

        if country:
            query_parts.append(f'web.country="{country}"')
        if province:
            query_parts.append(f'web.region="{province}"')
        if city:
            query_parts.append(f'web.city="{city}"')

        query = " && ".join(query_parts)
        results = await self.search(query, size=200)

        hotels = []
        for item in results:
            ip = item["ip"]
            port = item["port"]

            if not self.net_tools.check_ip(ip):
                continue

            location = self.net_tools.get_ip_location(ip)

            hotel = Hotel(
                ip=ip,
                port=port,
                name=f"Hunter酒店源-{location}",
                count=0,
                status=0,
                time=datetime.now(),
            )
            hotels.append(hotel)

        logger.info(f"Hunter found {len(hotels)} potential hotel sources")
        return hotels

    async def scrape(self, query: str = None, **kwargs) -> Any:
        if query:
            return await self.search(query, **kwargs)
        return await self.search_iptv_sources(**kwargs)


class QuakeScraper(BaseScraper):
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.api_url = "https://quake.360.net/api/v3/search/quake_service"
        self.api_token = (
            self.config.get("quake_api_token") or get_config().quake_api_token
        )
        self.net_tools = NetworkTools(timeout=self.timeout)

    async def search(
        self, query: str, size: int = 100, start: int = 0
    ) -> List[Dict[str, Any]]:
        if not self.api_token:
            logger.warning("Quake API token not configured")
            return []

        search_query = SearchQuery(query)
        quake_query = search_query.to_quake_query()

        headers = {"X-QuakeToken": self.api_token, "Content-Type": "application/json"}

        data = {
            "query": quake_query,
            "start": start,
            "size": size,
            "ignore_cache": False,
            "latest": True,
            "include": ["ip", "port", "service", "location", "time"],
        }

        results = []

        try:
            async with self.session.post(
                self.api_url, headers=headers, json=data
            ) as response:
                if response.status == 200:
                    result = await response.json()

                    if result.get("code") != 0:
                        logger.error(
                            f"Quake API error: {result.get('message', 'Unknown error')}"
                        )
                        return []

                    for item in result.get("data", []):
                        location = item.get("location", {})
                        results.append(
                            {
                                "ip": item.get("ip", ""),
                                "port": int(item.get("port", 0)),
                                "service": item.get("service", {}).get("name", ""),
                                "country": location.get("country_cn", ""),
                                "province": location.get("province_cn", ""),
                                "city": location.get("city_cn", ""),
                                "isp": location.get("isp", ""),
                                "source": "quake",
                            }
                        )

                    logger.info(
                        f"Quake found {len(results)} results for query: {query}"
                    )

        except Exception as e:
            logger.error(f"Quake search error: {e}")

        return results

    async def search_udpxy(
        self, country: str = "中国", province: str = None, isp: str = None
    ) -> List[UDPxy]:
        query_parts = ["udpxy"]

        if country:
            query_parts.append(f'country_cn: "{country}"')
        if province:
            query_parts.append(f'province_cn: "{province}"')
        if isp:
            query_parts.append(f'isp: "{isp}"')

        query = " AND ".join(query_parts)
        results = await self.search(query, size=100)

        udpxy_list = []
        for item in results:
            udpxy = UDPxy(
                id=f"quake_{item['ip']}_{item['port']}",
                mid=0,
                mcast=f"{item.get('province', '')}-{item.get('isp', '')}",
                city=item.get("city", ""),
                ip=item["ip"],
                port=item["port"],
                actv=0,
                status=0,
                time=datetime.now(),
            )
            udpxy_list.append(udpxy)

        logger.info(f"Quake found {len(udpxy_list)} udpxy sources")
        return udpxy_list

    async def search_iptv_sources(
        self, country: str = "中国", province: str = None, isp: str = None
    ) -> List[Hotel]:
        query_parts = ['app: "iptv"']

        if country:
            query_parts.append(f'country_cn: "{country}"')
        if province:
            query_parts.append(f'province_cn: "{province}"')
        if isp:
            query_parts.append(f'isp: "{isp}"')

        query = " AND ".join(query_parts)
        results = await self.search(query, size=200)

        hotels = []
        for item in results:
            ip = item["ip"]
            port = item["port"]

            if not self.net_tools.check_ip(ip):
                continue

            location = f"{item.get('province', '')}{item.get('city', '')}"
            if not location:
                location = self.net_tools.get_ip_location(ip)

            hotel = Hotel(
                ip=ip,
                port=port,
                name=f"Quake酒店源-{location}",
                count=0,
                status=0,
                time=datetime.now(),
            )
            hotels.append(hotel)

        logger.info(f"Quake found {len(hotels)} potential hotel sources")
        return hotels

    async def scrape(self, query: str = None, **kwargs) -> Any:
        if query:
            return await self.search(query, **kwargs)

        source_type = kwargs.pop("source_type", "iptv")
        if source_type == "udpxy":
            return await self.search_udpxy(**kwargs)
        return await self.search_iptv_sources(**kwargs)


class MultiSourceScraper(BaseScraper):
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.fofa = FofaScraper(config)
        self.hunter = HunterScraper(config)
        self.quake = QuakeScraper(config)

    async def search_all(
        self, query: str, engines: List[str] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        engines = engines or ["fofa", "hunter", "quake"]
        results = {}

        tasks = []
        if "fofa" in engines:
            tasks.append(("fofa", self.fofa.search(query)))
        if "hunter" in engines:
            tasks.append(("hunter", self.hunter.search(query)))
        if "quake" in engines:
            tasks.append(("quake", self.quake.search(query)))

        for engine, task in tasks:
            try:
                result = await task
                results[engine] = result
            except Exception as e:
                logger.error(f"Error searching {engine}: {e}")
                results[engine] = []

        return results

    async def search_iptv_sources(
        self,
        country: str = "中国",
        province: str = None,
        isp: str = None,
        engines: List[str] = None,
    ) -> List[Hotel]:
        engines = engines or ["fofa", "quake"]
        all_hotels = []
        seen = set()

        if "fofa" in engines:
            try:
                hotels = await self.fofa.search_iptv_sources(
                    country="CN" if country == "中国" else country,
                    region=province,
                    isp=isp,
                )
                for hotel in hotels:
                    key = f"{hotel.ip}:{hotel.port}"
                    if key not in seen:
                        seen.add(key)
                        all_hotels.append(hotel)
            except Exception as e:
                logger.error(f"FOFA IPTV search error: {e}")

        if "hunter" in engines:
            try:
                hotels = await self.hunter.search_iptv_sources(
                    country=country, province=province
                )
                for hotel in hotels:
                    key = f"{hotel.ip}:{hotel.port}"
                    if key not in seen:
                        seen.add(key)
                        all_hotels.append(hotel)
            except Exception as e:
                logger.error(f"Hunter IPTV search error: {e}")

        if "quake" in engines:
            try:
                hotels = await self.quake.search_iptv_sources(
                    country=country, province=province, isp=isp
                )
                for hotel in hotels:
                    key = f"{hotel.ip}:{hotel.port}"
                    if key not in seen:
                        seen.add(key)
                        all_hotels.append(hotel)
            except Exception as e:
                logger.error(f"Quake IPTV search error: {e}")

        logger.info(f"Multi-source search found {len(all_hotels)} unique hotel sources")
        return all_hotels

    async def search_udpxy_sources(
        self, country: str = "中国", province: str = None, isp: str = None
    ) -> List[UDPxy]:
        return await self.quake.search_udpxy(country, province, isp)

    async def scrape(self, query: str = None, **kwargs) -> Any:
        if query:
            return await self.search_all(query, **kwargs)

        source_type = kwargs.pop("source_type", "iptv")
        if source_type == "udpxy":
            return await self.search_udpxy_sources(**kwargs)
        return await self.search_iptv_sources(**kwargs)

    def close(self):
        self.fofa.net_tools.close()
        self.hunter.net_tools.close()
        self.quake.net_tools.close()
