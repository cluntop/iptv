from datetime import datetime
from typing import Any, Dict, List, Optional

from ..config import get_config
from ..database import Multicast, MulticastModel, UDPxy, UDPxyModel
from ..processors import MulticastProcessor
from ..scrapers import MulticastScraper
from ..utils import get_logger

logger = get_logger("multicast_service")


class MulticastService:
    def __init__(self, db_manager):
        self.db = db_manager
        self.config = get_config()
        self.multicast_model = MulticastModel(db_manager)
        self.udpxy_model = UDPxyModel(db_manager)
        self.multicast_processor = MulticastProcessor(db_manager, self.config.scraper.__dict__)
        self.scraper = MulticastScraper(self.config.scraper.__dict__)

    def download_sources(self) -> List[str]:
        logger.info("Starting multicast source downloading")

        try:
            files = self.scraper.scrape_sync("download")

            if files:
                logger.info(f"Downloaded {len(files)} multicast source files")

            return files

        except Exception as e:
            logger.error(f"Failed to download sources: {e}")
            return []

    def scrape_quake_udpxy(self, country: str, province: str, isp: str) -> List[UDPxy]:
        logger.info(f"Starting Quake udpxy scraping for {province}-{isp}")

        try:
            udpxy_list = self.scraper.scrape_sync("quake")

            if udpxy_list:
                inserted = self.multicast_processor.insert_udpxy(udpxy_list)
                logger.info(f"Inserted {inserted} udpxy from Quake")

            return udpxy_list

        except Exception as e:
            logger.error(f"Failed to scrape Quake udpxy: {e}")
            return []

    def validate_udpxy(self, mid: int) -> int:
        logger.info(f"Starting udpxy validation for multicast {mid}")

        try:
            udpxy_list = self.udpxy_model.get_by_mid(mid)
            validated = 0

            for udpxy in udpxy_list:
                validated_udpxy = self.multicast_processor.validate_udpxy(udpxy)

                if validated_udpxy:
                    self.multicast_processor.update_udpxy_status(udpxy.id, validated_udpxy.actv, validated_udpxy.status)
                    validated += 1

            logger.info(f"Validated {validated} udpxy")
            return validated

        except Exception as e:
            logger.error(f"Failed to validate udpxy: {e}")
            return 0

    def process_multicast_channels(self, sign: int = 2) -> int:
        logger.info("Starting multicast channel processing")

        try:
            from ..database import CategoryModel

            category_model = CategoryModel(self.db)
            categories = category_model.get_enabled()

            multicasts = self.multicast_model.get_all()
            total_channels = 0

            for multicast in multicasts:
                udpxy_list = self.udpxy_model.get_by_mid(multicast.id, status=1)

                if udpxy_list:
                    channels = self.multicast_processor.process_multicast_channels(
                        multicast, udpxy_list, categories, sign
                    )

                    if channels:
                        from ..processors import ChannelProcessor

                        channel_processor = ChannelProcessor(self.db, self.config.scraper.__dict__)
                        inserted = channel_processor.insert_channels(channels)
                        total_channels += inserted

            logger.info(f"Processed {total_channels} multicast channels")
            return total_channels

        except Exception as e:
            logger.error(f"Failed to process multicast channels: {e}")
            return 0

    def cleanup_invalid_udpxy(self, mid: int = None) -> int:
        logger.info("Starting invalid udpxy cleanup")

        try:
            if mid:
                count = self.multicast_processor.cleanup_invalid_udpxy(mid)
            else:
                count = 0
                all_multicast = self.multicast_model.get_all()
                for m in all_multicast:
                    count += self.multicast_processor.cleanup_invalid_udpxy(m.id)

            return count

        except Exception as e:
            logger.error(f"Failed to cleanup udpxy: {e}")
            return 0

    def get_statistics(self) -> Dict[str, Any]:
        try:
            return self.multicast_processor.get_statistics()
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {}

    def get_multicast_by_id(self, multicast_id: int) -> Optional[Multicast]:
        try:
            return self.multicast_model.get_by_id(multicast_id)
        except Exception as e:
            logger.error(f"Failed to get multicast by ID: {e}")
            return None

    def update_multicast(self, multicast_id: int, **kwargs) -> bool:
        try:
            return self.multicast_processor.update_multicast_status(multicast_id, **kwargs)
        except Exception as e:
            logger.error(f"Failed to update multicast: {e}")
            return False
