import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from queue import Queue
from typing import Any, Dict, List, Optional, Tuple

from ..config import DEFAULT_BATCH_SIZE
from ..database import Channel, ChannelModel, Hotel, HotelModel
from ..utils import NetworkTools, StringTools, VideoTools, get_logger

logger = get_logger("hotel_processor")


class HotelProcessor:
    def __init__(self, db_manager, config: Dict[str, Any] = None):
        self.db = db_manager
        self.config = config or {}
        self.batch_size = self.config.get("batch_size", DEFAULT_BATCH_SIZE)
        self.video_tools = VideoTools()
        self.net_tools = NetworkTools()
        self.hotel_model = HotelModel(db_manager)
        self.channel_model = ChannelModel(db_manager)

    def insert_hotels(self, hotels: List[Hotel]) -> int:
        if not hotels:
            return 0

        try:
            count = self.hotel_model.insert_many(hotels)
            logger.info(f"Inserted {count} hotels to database")
            return count
        except Exception as e:
            logger.error(f"Failed to insert hotels: {e}")
            return 0

    def scan_hotel_network(self, base_ip: str, port: int, thread_count: int = 6) -> List[Tuple[str, int]]:
        logger.info(f"Scanning network {base_ip}*:{port}")

        queues = [Queue() for _ in range(thread_count)]
        ips = [f"{base_ip}.{i}" for i in range(1, 256)]

        for i, ip in enumerate(ips):
            queues[i % thread_count].put(ip)

        active_hosts = []
        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            futures = [executor.submit(self._scan_queue, queue, port, i) for i, queue in enumerate(queues)]

            for future in as_completed(futures):
                hosts = future.result()
                active_hosts.extend(hosts)

        logger.info(f"Found {len(active_hosts)} active hosts in {base_ip}*")
        return active_hosts

    def _scan_queue(self, queue: Queue, port: int, thread_id: int) -> List[Tuple[str, int]]:
        active = []

        while not queue.empty():
            ip = queue.get()

            if self.net_tools.check_port(ip, port, timeout=2):
                active.append((ip, port))
                logger.debug(f"Thread {thread_id}: Found active host {ip}:{port}")

        return active

    def validate_hotel(self, ip: str, port: int, sign: int = 1) -> Optional[Dict[str, Any]]:
        url = f"http://{ip}:{port}/iptv/live/1000.json?key=txiptv"

        try:
            data = self.net_tools.get_json(url)
            if not data or "data" not in data:
                return None

            channels = []
            for item in data["data"]:
                name = item.get("name", "")
                url = f"http://{ip}:{port}{item.get('url', '')}"

                if ".m3u8" in url and "http" in url:
                    channels.append((name, url))

            if len(channels) < 3:
                return None

            location = self.net_tools.get_ip_location(ip)

            return {
                "ip": ip,
                "port": port,
                "name": f"酒店源-{location}",
                "count": len(channels),
                "status": 1,
                "time": datetime.now(),
                "channels": channels,
            }

        except Exception as e:
            logger.debug(f"Failed to validate hotel {ip}:{port}: {e}")
            return None

    def process_hotel_channels(self, hotel: Dict[str, Any], categories: List[Any], sign: int = 1) -> List[Channel]:
        channels = []
        ip = hotel["ip"]
        port = hotel["port"]

        channel_data = hotel.get("channels", [])
        if not channel_data:
            return channels

        processed = set()
        error_count = 0
        speed_sum = 0.0

        for i, (name, url) in enumerate(channel_data):
            if i > 3 and error_count >= 3:
                break

            normalized_name = StringTools.normalize_channel_name(name)

            category_match = StringTools.match_category(normalized_name, categories)
            if not category_match:
                continue

            category_name, category_type = category_match

            if (category_name, url) in processed:
                continue

            if i <= 3:
                speed = self.video_tools.get_stream_speed(url)
                if speed < 2.00:
                    error_count += 1
                    continue
                speed_sum += speed
            else:
                speed = round(speed_sum / (3 - error_count), 2)

            channel = Channel(
                name=category_name,
                url=url,
                type=category_type,
                speed=speed,
                sign=sign,
                time=datetime.now(),
            )

            channels.append(channel)
            processed.add((category_name, url))

        logger.info(f"Processed {len(channels)} channels for hotel {ip}:{port}")
        return channels

    def update_hotel_status(self, ip: str, status: int, count: int = 0, name: str = None) -> bool:
        try:
            updates = {"status": status, "time": datetime.now()}
            if count > 0:
                updates["count"] = count
            if name:
                updates["name"] = name

            return self.hotel_model.update(ip, **updates)
        except Exception as e:
            logger.error(f"Failed to update hotel status for {ip}: {e}")
            return False

    def cleanup_invalid_hotels(self) -> int:
        try:
            hotels = self.hotel_model.get_by_status(0)
            count = 0

            for hotel in hotels:
                if self.hotel_model.delete_by_ip(hotel.ip):
                    count += 1

            logger.info(f"Cleaned up {count} invalid hotels")
            return count

        except Exception as e:
            logger.error(f"Failed to cleanup hotels: {e}")
            return 0

    def get_statistics(self) -> Dict[str, Any]:
        try:
            total = self.hotel_model.count()
            active = len(self.hotel_model.get_by_status(1))
            inactive = total - active

            return {
                "total_hotels": total,
                "active_hotels": active,
                "inactive_hotels": inactive,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to get hotel statistics: {e}")
            return {}

    def close(self):
        self.net_tools.close()
