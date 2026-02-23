import re
import socket
import requests
from typing import Optional, Tuple
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from ..utils import get_logger

logger = get_logger("network_tools")


class NetworkTools:
    def __init__(self, timeout: int = 15, user_agent: str = None):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent
                or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate",
            }
        )

    def check_url(self, url: str, timeout: int = None) -> bool:
        timeout = timeout or self.timeout
        try:
            response = self.session.get(url, stream=True, timeout=timeout)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def check_ip(self, ip: str) -> bool:
        pattern = r"^(\d{1,3}\.){3}\d{1,3}$"
        if not re.match(pattern, ip):
            return False

        parts = ip.split(".")
        return all(0 <= int(part) <= 255 for part in parts)

    def check_port(self, ip: str, port: int, timeout: int = 2) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        except socket.error:
            return False

    def get_request(self, url: str, timeout: int = None) -> Optional[requests.Response]:
        timeout = timeout or self.timeout
        try:
            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            logger.debug(f"Request failed for {url}: {e}")
            return None

    def get_json(self, url: str, timeout: int = None) -> Optional[dict]:
        response = self.get_request(url, timeout)
        if response:
            try:
                return response.json()
            except ValueError:
                logger.debug(f"Failed to parse JSON from {url}")
        return None

    def get_html(self, url: str, timeout: int = None) -> Optional[BeautifulSoup]:
        response = self.get_request(url, timeout)
        if response:
            try:
                return BeautifulSoup(response.text, "html.parser")
            except Exception as e:
                logger.debug(f"Failed to parse HTML from {url}: {e}")
        return None

    def download_file(self, url: str, file_path: str, timeout: int = None) -> bool:
        timeout = timeout or self.timeout
        try:
            response = self.session.get(url, stream=True, timeout=timeout)
            response.raise_for_status()

            with open(file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            return True
        except requests.RequestException as e:
            logger.error(f"Failed to download {url} to {file_path}: {e}")
            return False

    def extract_multicast_addr(self, url: str) -> Optional[str]:
        match = re.search(r"(rtp/|rtp://|udp/|udp://)(.*)", url)
        if match:
            return match.group(2)
        return None

    def parse_url(self, url: str) -> Tuple[str, int, str]:
        parsed = urlparse(url)
        return parsed.hostname or "", parsed.port or 0, parsed.path

    def get_ip_location(self, ip: str) -> str:
        try:
            ip_url = f"https://www.ipshudi.com/{ip}.htm"
            response = self.get_request(ip_url, timeout=10)

            if response:
                response.encoding = "utf-8"
                soup = BeautifulSoup(response.text, "html.parser")
                table = soup.find("table")

                if table:
                    rows = table.find_all("tr")
                    if len(rows) > 2:
                        ip_add = (
                            rows[1]
                            .find_all("td")[1]
                            .text.replace("上报纠错", "")
                            .replace(" ", "")
                            .strip()
                        )
                        ip_ips = (
                            rows[2]
                            .find_all("td")[1]
                            .text.replace("上报纠错", "")
                            .replace(" ", "")
                            .strip()
                        )
                        return f"{ip_add}【{ip_ips}】"
        except Exception as e:
            logger.debug(f"Failed to get IP location for {ip}: {e}")

        return ""

    def close(self):
        self.session.close()
