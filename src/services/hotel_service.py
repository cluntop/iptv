from datetime import datetime
from typing import Any, Dict, List, Optional

from ..config import get_config
from ..database import Hotel, HotelModel
from ..processors import HotelProcessor
from ..scrapers import HotelScraper
from ..utils import get_logger

logger = get_logger("hotel_service")


class HotelService:
    def __init__(self, db_manager):
        self.db = db_manager
        self.config = get_config()
        self.hotel_model = HotelModel(db_manager)
        self.hotel_processor = HotelProcessor(db_manager, self.config.scraper.__dict__)
        self.scraper = HotelScraper(self.config.scraper.__dict__)

    def scrape_hotels(self, source: str = "gyssi") -> List[Hotel]:
        logger.info(f"Starting hotel scraping from {source}")

        try:
            hotels = self.scraper.scrape_sync(source)

            if hotels:
                inserted = self.hotel_processor.insert_hotels(hotels)
                logger.info(f"Inserted {inserted} hotels from {source}")

            return hotels

        except Exception as e:
            logger.error(f"Failed to scrape hotels: {e}")
            return []

    def scan_hotel_networks(self) -> int:
        logger.info("Starting hotel network scanning")

        try:
            hotels = self.hotel_model.get_by_status(0)
            scanned = 0

            for hotel in hotels:
                base_ip = hotel.ip[: hotel.ip.rfind(".")]
                port = hotel.port

                active_hosts = self.hotel_processor.scan_hotel_network(base_ip, port)
                scanned += len(active_hosts)

            logger.info(f"Scanned {scanned} hotel network hosts")
            return scanned

        except Exception as e:
            logger.error(f"Failed to scan hotel networks: {e}")
            return 0

    def validate_hotels(self) -> int:
        logger.info("Starting hotel validation")

        try:
            hotels = self.hotel_model.get_by_status(0)
            validated = 0

            for hotel in hotels:
                result = self.hotel_processor.validate_hotel(hotel.ip, hotel.port)

                if result:
                    self.hotel_processor.update_hotel_status(
                        hotel.ip, status=1, count=result["count"], name=result["name"]
                    )
                    validated += 1

            logger.info(f"Validated {validated} hotels")
            return validated

        except Exception as e:
            logger.error(f"Failed to validate hotels: {e}")
            return 0

    def process_hotel_channels(self, sign: int = 1) -> int:
        logger.info("Starting hotel channel processing")

        try:
            from ..database import CategoryModel

            category_model = CategoryModel(self.db)
            categories = category_model.get_enabled()

            hotels = self.hotel_model.get_by_status(1)
            total_channels = 0

            for hotel in hotels:
                result = self.hotel_processor.validate_hotel(hotel.ip, hotel.port, sign)

                if result:
                    channels = self.hotel_processor.process_hotel_channels(
                        result, categories, sign
                    )

                    if channels:
                        from ..processors import ChannelProcessor

                        channel_processor = ChannelProcessor(
                            self.db, self.config.scraper.__dict__
                        )
                        inserted = channel_processor.insert_channels(channels)
                        total_channels += inserted

            logger.info(f"Processed {total_channels} hotel channels")
            return total_channels

        except Exception as e:
            logger.error(f"Failed to process hotel channels: {e}")
            return 0

    def cleanup_invalid_hotels(self) -> int:
        logger.info("Starting invalid hotels cleanup")

        try:
            count = self.hotel_processor.cleanup_invalid_hotels()
            return count
        except Exception as e:
            logger.error(f"Failed to cleanup hotels: {e}")
            return 0

    def get_statistics(self) -> Dict[str, Any]:
        try:
            return self.hotel_processor.get_statistics()
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {}

    def get_hotel_by_ip(self, ip: str) -> Optional[Hotel]:
        try:
            return self.hotel_model.get_by_ip(ip)
        except Exception as e:
            logger.error(f"Failed to get hotel by IP: {e}")
            return None

    def update_hotel(self, ip: str, **kwargs) -> bool:
        try:
            return self.hotel_processor.update_hotel_status(ip, **kwargs)
        except Exception as e:
            logger.error(f"Failed to update hotel: {e}")
            return False
