import re
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from urllib.parse import urlparse, quote

from .base_scraper import BaseScraper
from ..database import Hotel
from ..utils import get_logger, NetworkTools, StringTools
from ..config import PROVINCE_NAMES, SEARCH_URLS

logger = get_logger('hotel_scraper')

class HotelScraper(BaseScraper):
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.net_tools = NetworkTools(
            timeout=self.timeout,
            user_agent=self.config.get('user_agent')
        )
    
    async def scrape_gyssi(self) -> List[Hotel]:
        hotels = []
        token_url = 'https://gyssi.link/iptv/jwt.html'
        base_url = 'https://gyssi.link/iptv/chinaiptv/'
        
        try:
            token_content = await self.fetch_text(token_url)
            if not token_content:
                logger.warning("Failed to fetch token from gyssi")
                return hotels
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(token_content, 'html.parser')
            token_element = soup.find(id="token")
            
            if not token_element:
                logger.warning("Token not found in gyssi response")
                return hotels
            
            token = token_element.text
            
            for province in PROVINCE_NAMES:
                m3u_url = base_url + quote(province, safe=':/') + ".m3u?token=" + token
                content = await self.fetch_text(m3u_url)
                
                if not content or len(content) < 1024:
                    logger.debug(f"Invalid content for province: {province}")
                    continue
                
                ips_ports = re.findall(r'http://(.*?)\/tsfile\/live', content)
                
                for ip_port in ips_ports:
                    if ':' in ip_port:
                        ip, port = ip_port.split(':', 1)
                        
                        if not self.net_tools.check_ip(ip):
                            continue
                        
                        channel_count = await self.get_channel_count(ip, port)
                        
                        if channel_count > 3:
                            hotel = Hotel(
                                ip=ip,
                                port=int(port),
                                name=f'初始采集酒店源-{province}',
                                count=channel_count,
                                status=0,
                                time=datetime.now()
                            )
                            hotels.append(hotel)
                            logger.info(f"Found hotel: {ip}:{port} with {channel_count} channels")
        
        except Exception as e:
            logger.error(f"Error scraping gyssi: {e}")
        
        return hotels
    
    async def get_channel_count(self, ip: str, port: int) -> int:
        url = f"http://{ip}:{port}/iptv/live/1000.json?key=txiptv"
        data = await self.fetch_json(url)
        
        if data and isinstance(data, dict):
            return data.get('count', 0)
        
        return 0
    
    async def scrape_fofa(self) -> List[Hotel]:
        hotels = []
        
        for search_url in SEARCH_URLS:
            content = await self.fetch_text(search_url)
            if not content:
                continue
            
            pattern = r"http://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+"
            urls = re.findall(pattern, content)
            
            for url in set(urls):
                parsed = urlparse(url)
                ip = parsed.hostname
                port = parsed.port
                
                if not ip or not port:
                    continue
                
                if not self.net_tools.check_ip(ip):
                    continue
                
                channel_count = await self.get_channel_count(ip, port)
                
                if channel_count > 3:
                    location = self.net_tools.get_ip_location(ip)
                    hotel = Hotel(
                        ip=ip,
                        port=port,
                        name=f'初始采集酒店源-{location}',
                        count=channel_count,
                        status=0,
                        time=datetime.now()
                    )
                    hotels.append(hotel)
                    logger.info(f"Found hotel from FOFA: {ip}:{port} with {channel_count} channels")
        
        return hotels
    
    async def scan_network_range(self, base_ip: str, port: int) -> List[Tuple[str, int]]:
        results = []
        last_dot = base_ip.rfind('.')
        if last_dot == -1:
            return results
        
        network = base_ip[:last_dot + 1]
        
        semaphore = asyncio.Semaphore(self.concurrency_limit)
        
        async def check_ip_suffix(suffix: int) -> Optional[Tuple[str, int]]:
            async with semaphore:
                ip = f"{network}{suffix}"
                if self.net_tools.check_port(ip, port, timeout=2):
                    return (ip, port)
            return None
        
        tasks = [check_ip_suffix(i) for i in range(1, 256)]
        
        for future in asyncio.as_completed(tasks):
            result = await future
            if result:
                results.append(result)
                
                if len(results) % 10 == 0:
                    logger.info(f"Scanned {len(results)} active hosts in {network}*")
        
        logger.info(f"Found {len(results)} active hosts in {network}*")
        return results
    
    async def validate_hotel(self, ip: str, port: int) -> Optional[Dict[str, Any]]:
        try:
            channel_count = await self.get_channel_count(ip, port)
            
            if channel_count > 3:
                location = self.net_tools.get_ip_location(ip)
                return {
                    'ip': ip,
                    'port': port,
                    'name': f'酒店源-{location}',
                    'count': channel_count,
                    'status': 1,
                    'time': datetime.now()
                }
        except Exception as e:
            logger.debug(f"Failed to validate hotel {ip}:{port}: {e}")
        
        return None
    
    async def scrape(self, source: str = 'gyssi') -> List[Hotel]:
        logger.info(f"Starting hotel scraping: {source}")
        
        if source == 'gyssi':
            return await self.scrape_gyssi()
        elif source == 'fofa':
            return await self.scrape_fofa()
        elif source == 'scan':
            pass
        
        return []
    
    def close(self):
        self.net_tools.close()
