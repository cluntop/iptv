import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from ..config import DOWNLOAD_URLS
from ..database import Multicast, UDPxy
from ..utils import FileTools, StringTools, get_logger
from .base_scraper import BaseScraper

logger = get_logger("multicast_scraper")


class MulticastScraper(BaseScraper):
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.download_dir = self.config.get("download_dir", "data/downloads")

    async def download_sources(self) -> List[str]:
        downloaded_files = []

        for url, file_path in DOWNLOAD_URLS:
            FileTools.ensure_dir(file_path)

            content = await self.fetch_text(url)
            if content and len(content) > 1024:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)

                if file_path.endswith(".m3u"):
                    txt_file = FileTools.convert_m3u_to_txt(file_path)
                    if txt_file:
                        downloaded_files.append(txt_file)
                else:
                    downloaded_files.append(file_path)

                logger.info(f"Downloaded: {file_path}")

        return downloaded_files

    async def scrape_sichuan(self) -> Optional[str]:
        url = "http://epg.51zmt.top:8000/sctvmulticast.html"
        file_path = "data/downloads/四川-电信-239.93.0.txt"

        try:
            content = await self.fetch_text(url)
            if not content:
                return None

            from bs4 import BeautifulSoup

            soup = BeautifulSoup(content, "html.parser")
            table = soup.find("table", {"border": "1"})

            if not table:
                return None

            rows_even = table.find_all("tr", class_="even")
            rows_odd = table.find_all("tr", class_="odd")
            rows = rows_even + rows_odd

            result_txt = ""

            for row in rows:
                td_tags = row.find_all("td")
                if len(td_tags) >= 3:
                    name = td_tags[1].text
                    ip_port = td_tags[2].text

                    if "画中画" not in name and "单音轨" not in name:
                        result_txt += f"{name},rtp://{ip_port}\n"

            FileTools.ensure_dir(file_path)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(result_txt)

            logger.info(f"Scraped Sichuan multicast to {file_path}")
            return file_path

        except Exception as e:
            logger.error(f"Error scraping Sichuan multicast: {e}")
            return None

    def parse_multicast_file(self, file_path: str) -> List[Tuple[str, str]]:
        channels = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()

                    if not StringTools.is_valid_channel_line(line):
                        continue

                    parsed = StringTools.parse_channel_line(line)
                    if parsed:
                        channels.append(parsed)

        except Exception as e:
            logger.error(f"Error parsing multicast file {file_path}: {e}")

        logger.info(f"Parsed {len(channels)} channels from {file_path}")
        return channels

    async def scrape_quake(self, country: str, province: str, isp: str, api_token: str = "") -> List[UDPxy]:
        udpxy_list = []

        if not api_token:
            logger.warning("Quake API token not provided")
            return udpxy_list

        api_url = "https://quake.360.net/api/v3/search/quake_service"

        headers = {"X-QuakeToken": api_token, "Content-Type": "application/json"}

        query = f'udpxy AND country_cn: "{country}" AND province_cn: "{province}" AND isp: "{isp}"'

        data = {
            "query": query,
            "start": 0,
            "size": 50,
            "ignore_cache": False,
            "latest": True,
            "include": ["ip", "port", "location.city_cn"],
        }

        try:
            async with self.session.post(api_url, headers=headers, json=data) as response:
                if response.status == 200:
                    result = await response.json()

                    if result.get("code") == 0:
                        for item in result.get("data", []):
                            udpxy = UDPxy(
                                id=item["id"],
                                mid=0,
                                mcast=f"{province}-{isp}",
                                city=item.get("location", {}).get("city_cn", ""),
                                ip=item["ip"],
                                port=item["port"],
                                actv=0,
                                status=0,
                                time=datetime.now(),
                            )
                            udpxy_list.append(udpxy)

            logger.info(f"Found {len(udpxy_list)} udpxy from Quake for {province}-{isp}")

        except Exception as e:
            logger.error(f"Error scraping Quake: {e}")

        return udpxy_list

    async def scrape(self, source: str = "download") -> Any:
        logger.info(f"Starting multicast scraping: {source}")

        if source == "download":
            return await self.download_sources()
        elif source == "sichuan":
            return await self.scrape_sichuan()
        elif source == "quake":
            pass

        return []

    def create_multicast_entry(self, country: str, province: str, isp: str, path: str) -> Multicast:
        return Multicast(
            country=country,
            province=province,
            isp=isp,
            path=path,
            city="",
            udpxy="",
            lines=0,
            status=0,
            time=datetime.now(),
        )
