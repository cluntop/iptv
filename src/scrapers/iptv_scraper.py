import re
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from urllib.parse import urljoin, urlparse

from .base_scraper import BaseScraper
from ..database import Channel, Category
from ..utils import get_logger, StringTools, FileTools
from ..config import IPTV_SCAN_URLS, LOGO_BASE_URL

logger = get_logger('iptv_scraper')

class IPTVScraper(BaseScraper):
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.scan_urls = IPTV_SCAN_URLS
    
    async def scan_network(self, base_urls: List[str] = None) -> List[Tuple[str, str]]:
        base_urls = base_urls or self.scan_urls
        scan_ips = []
        
        for url in base_urls:
            parsed = urlparse(url)
            if parsed.hostname:
                segments = parsed.hostname.split('.')
                if len(segments) >= 3:
                    base = ".".join(segments[:3])
                    port = f":{parsed.port}" if parsed.port else ""
                    for i in range(1, 255):
                        scan_ips.append(f"{parsed.scheme}://{base}.{i}{port}")
        
        logger.info(f"Generated {len(scan_ips)} IPs to scan")
        
        results = []
        async with self:
            for ip_url in scan_ips:
                api_url = f"{ip_url}/iptv/live/1000.json?key=txiptv"
                data = await self.fetch_json(api_url)
                
                if data and isinstance(data, dict) and 'data' in data:
                    for item in data['data']:
                        name = item.get('name', 'Unknown')
                        url = urljoin(ip_url, item.get('url', ''))
                        results.append((name, url))
                        
                        if len(results) % 100 == 0:
                            self.log_progress(len(results), len(scan_ips), "IPTV scan")
        
        logger.info(f"Found {len(results)} channels from network scan")
        return results
    
    async def check_stream(self, name: str, url: str) -> Optional[Dict[str, Any]]:
        try:
            timeout = aiohttp.ClientTimeout(total=5, connect=2, sock_read=3)
            async with self.session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    chunk = await response.content.read(10240)
                    if chunk:
                        cname = StringTools.clean_channel_name(name)
                        
                        group = "其他频道"
                        if "CCTV" in cname:
                            group = "央视频道"
                        elif "卫视" in cname:
                            group = "卫视频道"
                        
                        return {
                            "name": cname,
                            "url": url,
                            "group": group,
                            "logo": f"{LOGO_BASE_URL}{cname}.png"
                        }
        except Exception as e:
            logger.debug(f"Stream check failed for {name}: {e}")
        
        return None
    
    async def validate_channels(self, channels: List[Tuple[str, str]]) -> List[Dict[str, Any]]:
        valid_channels = []
        semaphore = asyncio.Semaphore(self.concurrency_limit)
        
        async def check_with_semaphore(name: str, url: str):
            async with semaphore:
                return await self.check_stream(name, url)
        
        tasks = [check_with_semaphore(name, url) for name, url in channels]
        
        completed = 0
        total = len(tasks)
        
        for future in asyncio.as_completed(tasks):
            result = await future
            if result:
                valid_channels.append(result)
            
            completed += 1
            if completed % 50 == 0 or completed == total:
                self.log_progress(completed, total, "Channel validation")
        
        logger.info(f"Validated {len(valid_channels)}/{total} channels")
        return valid_channels
    
    async def scrape_m3u(self, url: str) -> List[Tuple[str, str]]:
        content = await self.fetch_text(url)
        if not content:
            return []
        
        channels = []
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            if line.startswith('#EXTINF'):
                if i + 1 < len(lines):
                    name = line[line.rfind(',') + 1:].strip()
                    url = lines[i + 1].strip()
                    
                    if url and url.startswith('http'):
                        channels.append((name, url))
        
        logger.info(f"Parsed {len(channels)} channels from M3U")
        return channels
    
    async def scrape(self, source_type: str = 'network') -> List[Dict[str, Any]]:
        logger.info(f"Starting IPTV scraping: {source_type}")
        
        if source_type == 'network':
            channels = await self.scan_network()
            valid_channels = await self.validate_channels(channels)
            return valid_channels
        
        elif source_type == 'm3u':
            pass
        
        return []
    
    def save_to_m3u(self, channels: List[Dict[str, Any]], output_file: str):
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")
                
                for channel in channels:
                    f.write(
                        f'#EXTINF:-1 tvg-name="{channel["name"]}" '
                        f'tvg-logo="{channel["logo"]}" '
                        f'group-title="{channel["group"]}",'
                        f'{channel["name"]}\n{channel["url"]}\n'
                    )
            
            logger.info(f"Saved {len(channels)} channels to {output_file}")
            
        except Exception as e:
            logger.error(f"Failed to save M3U file: {e}")
    
    def convert_to_channels(self, channels: List[Dict[str, Any]], 
                          categories: List[Category]) -> List[Channel]:
        result = []
        
        for channel_data in channels:
            name = channel_data['name']
            url = channel_data['url']
            group = channel_data['group']
            
            category_match = StringTools.match_category(name, categories)
            if category_match:
                category_name, category_type = category_match
                name = category_name
                group = category_type
            
            result.append(Channel(
                name=name,
                url=url,
                type=group,
                width=1280,
                height=720,
                frame=25.0,
                speed=5.00,
                sign=0
            ))
        
        return result
