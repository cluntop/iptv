import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from queue import Queue
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from ..config import DEFAULT_BATCH_SIZE
from ..database import (
    Channel,
    ChannelModel,
    Multicast,
    MulticastModel,
    UDPxy,
    UDPxyModel,
)
from ..utils import FileTools, NetworkTools, StringTools, VideoTools, get_logger

logger = get_logger("multicast_processor")


class MulticastProcessor:
    def __init__(self, db_manager, config: Dict[str, Any] = None):
        self.db = db_manager
        self.config = config or {}
        self.batch_size = self.config.get("batch_size", DEFAULT_BATCH_SIZE)
        self.video_tools = VideoTools()
        self.net_tools = NetworkTools()
        self.multicast_model = MulticastModel(db_manager)
        self.udpxy_model = UDPxyModel(db_manager)
        self.channel_model = ChannelModel(db_manager)

    def insert_multicasts(self, multicasts: List[Multicast]) -> int:
        if not multicasts:
            return 0

        try:
            count = 0
            for multicast in multicasts:
                if self.multicast_model.insert(multicast):
                    count += 1

            logger.info(f"Inserted {count} multicasts to database")
            return count
        except Exception as e:
            logger.error(f"Failed to insert multicasts: {e}")
            return 0

    def insert_udpxy(self, udpxy_list: List[UDPxy]) -> int:
        if not udpxy_list:
            return 0

        try:
            count = self.udpxy_model.insert_many(udpxy_list)
            logger.info(f"Inserted {count} udpxy to database")
            return count
        except Exception as e:
            logger.error(f"Failed to insert udpxy: {e}")
            return 0

    def validate_udpxy(self, udpxy: UDPxy) -> Optional[UDPxy]:
        ip = udpxy.ip
        port = udpxy.port

        status_url = f"http://{ip}:{port}/status"
        response = self.net_tools.get_request(status_url, timeout=10)

        if not response:
            return None

        try:
            soup = BeautifulSoup(response.text, "html.parser")
            table = soup.find("table", attrs={"cellspacing": "0"})

            if not table:
                return None

            td_tags = table.find_all("td")
            if len(td_tags) < 4:
                return None

            addr = td_tags[2].text
            actv = int(td_tags[3].text)

            if "0.0.0" in addr or "192.168" in addr:
                return None

            udpxy.actv = actv
            udpxy.status = 1
            udpxy.time = datetime.now()

            return udpxy

        except Exception as e:
            logger.debug(f"Failed to validate udpxy {ip}:{port}: {e}")
            return None

    def process_multicast_channels(
        self,
        multicast: Multicast,
        udpxy_list: List[UDPxy],
        categories: List[Any],
        sign: int = 2,
    ) -> List[Channel]:
        channels = []

        if not multicast.path or not udpxy_list:
            return channels

        file_path = multicast.path
        if file_path.endswith(".m3u"):
            file_path = FileTools.convert_m3u_to_txt(file_path)

        if not file_path:
            return channels

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()

                    if not StringTools.is_valid_channel_line(line):
                        continue

                    parsed = StringTools.parse_channel_line(line)
                    if not parsed:
                        continue

                    name, links = parsed
                    m3u8_links = StringTools.extract_m3u_links(links)

                    for udpxy in udpxy_list[:3]:
                        udpxy_url = f"http://{udpxy.ip}:{udpxy.port}"

                        for m3u8_link in m3u8_links:
                            multicast_addr = self.net_tools.extract_multicast_addr(m3u8_link)
                            if not multicast_addr:
                                continue

                            full_url = f"{udpxy_url}/rtp/{multicast_addr}"

                            normalized_name = StringTools.normalize_channel_name(name)
                            category_match = StringTools.match_category(normalized_name, categories)
                            if not category_match:
                                continue

                            category_name, category_type = category_match

                            speed = self.video_tools.get_stream_speed(full_url)
                            if speed < 5.00:
                                continue

                            channel = Channel(
                                name=category_name,
                                url=full_url,
                                type=category_type,
                                speed=speed,
                                sign=sign,
                                time=datetime.now(),
                            )

                            channels.append(channel)
                            break

                        if len(channels) >= 100:
                            break

                    if len(channels) >= 100:
                        break

        except Exception as e:
            logger.error(f"Failed to process multicast file {file_path}: {e}")

        logger.info(f"Processed {len(channels)} channels for multicast {multicast.id}")
        return channels

    def update_multicast_status(
        self,
        multicast_id: int,
        status: int,
        lines: int = 0,
        city: str = None,
        udpxy: str = None,
    ) -> bool:
        try:
            updates = {"status": status, "time": datetime.now()}
            if lines > 0:
                updates["lines"] = lines
            if city:
                updates["city"] = city
            if udpxy:
                updates["udpxy"] = udpxy

            return self.multicast_model.update(multicast_id, **updates)
        except Exception as e:
            logger.error(f"Failed to update multicast status for {multicast_id}: {e}")
            return False

    def update_udpxy_status(self, udpxy_id: str, actv: int, status: int) -> bool:
        try:
            return self.udpxy_model.update(udpxy_id, actv=actv, status=status, time=datetime.now())
        except Exception as e:
            logger.error(f"Failed to update udpxy status for {udpxy_id}: {e}")
            return False

    def cleanup_invalid_udpxy(self, mid: int) -> int:
        try:
            count = self.udpxy_model.delete_by_status(mid, 0)
            logger.info(f"Cleaned up {count} invalid udpxy for multicast {mid}")
            return count
        except Exception as e:
            logger.error(f"Failed to cleanup udpxy: {e}")
            return 0

    def get_statistics(self) -> Dict[str, Any]:
        try:
            total_multicast = self.multicast_model.count()
            total_udpxy = self.udpxy_model.count()

            return {
                "total_multicast": total_multicast,
                "total_udpxy": total_udpxy,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to get multicast statistics: {e}")
            return {}

    def close(self):
        self.net_tools.close()
