from typing import Dict, Any, List, Optional
from datetime import datetime

from ..database import Channel, Category, ChannelModel, CategoryModel
from ..scrapers import IPTVScraper
from ..processors import ChannelProcessor
from ..utils import get_logger, FileTools
from ..config import get_config

logger = get_logger('iptv_service')

class IPTVService:
    def __init__(self, db_manager):
        self.db = db_manager
        self.config = get_config()
        self.channel_model = ChannelModel(db_manager)
        self.category_model = CategoryModel(db_manager)
        self.channel_processor = ChannelProcessor(db_manager, self.config.scraper.__dict__)
        self.scraper = IPTVScraper(self.config.scraper.__dict__)
    
    def scrape_network_channels(self) -> List[Channel]:
        logger.info("Starting network channel scraping")
        
        try:
            channels_data = self.scraper.scrape_sync('network')
            categories = self.category_model.get_enabled()
            
            channels = self.scraper.convert_to_channels(channels_data, categories)
            valid_channels = self.channel_processor.validate_channels(channels, categories)
            
            if valid_channels:
                inserted = self.channel_processor.insert_channels(valid_channels)
                logger.info(f"Inserted {inserted} network channels")
            
            return valid_channels
            
        except Exception as e:
            logger.error(f"Failed to scrape network channels: {e}")
            return []
    
    def process_channel_speeds(self) -> int:
        logger.info("Starting channel speed processing")
        
        try:
            channels = self.channel_model.get_all()
            channel_ids = [c.id for c in channels if c.width is None]
            
            if not channel_ids:
                logger.info("No channels need speed processing")
                return 0
            
            processed = self.channel_processor.process_channel_speeds(channel_ids)
            return processed
            
        except Exception as e:
            logger.error(f"Failed to process channel speeds: {e}")
            return 0
    
    def generate_iptv_files(self) -> Dict[str, int]:
        logger.info("Starting IPTV file generation")
        
        results = {}
        
        try:
            txt_file = f"{self.config.output_dir}/iptv.txt"
            count = self.channel_processor.generate_iptv_file(txt_file)
            results['txt'] = count
            
            m3u_file = FileTools.convert_txt_to_m3u(txt_file)
            if m3u_file:
                results['m3u'] = count
                logger.info(f"Generated M3U file: {m3u_file}")
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to generate IPTV files: {e}")
            return results
    
    def cleanup_invalid_channels(self) -> int:
        logger.info("Starting invalid channels cleanup")
        
        try:
            count = self.channel_processor.cleanup_invalid_channels(sign=0)
            return count
        except Exception as e:
            logger.error(f"Failed to cleanup invalid channels: {e}")
            return 0
    
    def get_statistics(self) -> Dict[str, Any]:
        try:
            return self.channel_processor.get_statistics()
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {}
    
    def export_channels(self, format: str = 'm3u', output_file: str = None) -> bool:
        try:
            if not output_file:
                output_file = f"{self.config.output_dir}/channels.{format}"
            
            channels = self.channel_model.get_all()
            
            if format == 'm3u':
                self.scraper.save_to_m3u(
                    [{'name': c.name, 'url': c.url, 'group': c.type, 
                      'logo': f"https://live.fanmingming.com/tv/{c.name}.png"}
                     for c in channels],
                    output_file
                )
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to export channels: {e}")
            return False
    
    def search_channels(self, keyword: str) -> List[Channel]:
        try:
            all_channels = self.channel_model.get_all()
            return [c for c in all_channels if keyword.lower() in c.name.lower()]
        except Exception as e:
            logger.error(f"Failed to search channels: {e}")
            return []
