import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from queue import Queue
from typing import Any, Dict, List

from ..config import DEFAULT_BATCH_SIZE
from ..database import Category, CategoryModel, Channel, ChannelModel
from ..utils import StringTools, VideoTools, get_logger

logger = get_logger("channel_processor")


class ChannelProcessor:
    def __init__(self, db_manager, config: Dict[str, Any] = None):
        self.db = db_manager
        self.config = config or {}
        self.batch_size = self.config.get("batch_size", DEFAULT_BATCH_SIZE)
        self.max_workers = self.config.get("max_workers", min(8, (os.cpu_count() or 4) * 2))
        self.video_tools = VideoTools()
        self.channel_model = ChannelModel(db_manager)
        self.category_model = CategoryModel(db_manager)
        self._executor: ThreadPoolExecutor = None

    def _get_executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        return self._executor

    def insert_channels(self, channels: List[Channel]) -> int:
        if not channels:
            return 0

        try:
            count = self.channel_model.insert_many(channels)
            logger.info(f"Inserted {count} channels to database")
            return count
        except Exception as e:
            logger.error(f"Failed to insert channels: {e}")
            return 0

    def process_channel_speeds(self, channel_ids: List[int], thread_count: int = None) -> int:
        if not channel_ids:
            return 0

        if thread_count is None:
            thread_count = self.max_workers

        logger.info(f"Processing speeds for {len(channel_ids)} channels with {thread_count} threads")

        chunk_size = (len(channel_ids) + thread_count - 1) // thread_count
        chunks = [channel_ids[i : i + chunk_size] for i in range(0, len(channel_ids), chunk_size)]

        processed = 0
        executor = self._get_executor()
        futures = [executor.submit(self._process_speed_chunk, chunk, i) for i, chunk in enumerate(chunks)]

        for future in as_completed(futures):
            try:
                processed += future.result()
            except Exception as e:
                logger.error(f"Error in speed processing: {e}")

        logger.info(f"Processed speeds for {processed} channels")
        return processed

    def _process_speed_chunk(self, channel_ids: List[int], thread_id: int) -> int:
        processed = 0
        updates = []

        for channel_id in channel_ids:
            channel = self.channel_model.get_by_id(channel_id)

            if not channel:
                continue

            try:
                video_info = self.video_tools.get_video_info(channel.url)
                if not video_info:
                    continue

                width, height, frame = video_info

                if channel.speed == 0.00:
                    speed = self.video_tools.get_stream_speed(channel.url)
                    logger.info(
                        f"Thread {thread_id}: Channel {channel_id}:{channel.name} - "
                        f"Speed: {speed} Mbps, Resolution: {width}*{height}, FPS: {frame}"
                    )
                else:
                    speed = channel.speed
                    logger.debug(
                        f"Thread {thread_id}: Channel {channel_id}:{channel.name} - " f"Existing speed: {speed} Mbps"
                    )

                updates.append(
                    {
                        "id": channel_id,
                        "speed": speed,
                        "width": width,
                        "height": height,
                        "frame": frame,
                        "time": datetime.now(),
                    }
                )

                processed += 1

                if len(updates) >= self.batch_size:
                    self.channel_model.update_many(updates)
                    updates = []

            except Exception as e:
                logger.error(f"Error processing channel {channel_id}: {e}")

        if updates:
            self.channel_model.update_many(updates)

        return processed

    def _process_speed_queue(self, queue: Queue, thread_id: int) -> int:
        processed = 0
        updates = []

        while not queue.empty():
            channel_id = queue.get()
            channel = self.channel_model.get_by_id(channel_id)

            if not channel:
                continue

            try:
                video_info = self.video_tools.get_video_info(channel.url)
                if not video_info:
                    continue

                width, height, frame = video_info

                if channel.speed == 0.00:
                    speed = self.video_tools.get_stream_speed(channel.url)
                    logger.info(
                        f"Thread {thread_id}: Channel {channel_id}:{channel.name} - "
                        f"Speed: {speed} Mbps, Resolution: {width}*{height}, FPS: {frame}"
                    )
                else:
                    speed = channel.speed
                    logger.debug(
                        f"Thread {thread_id}: Channel {channel_id}:{channel.name} - " f"Existing speed: {speed} Mbps"
                    )

                updates.append(
                    {
                        "id": channel_id,
                        "speed": speed,
                        "width": width,
                        "height": height,
                        "frame": frame,
                        "time": datetime.now(),
                    }
                )

                processed += 1

                if len(updates) >= self.batch_size:
                    self.channel_model.update_many(updates)
                    updates = []

            except Exception as e:
                logger.error(f"Error processing channel {channel_id}: {e}")

        if updates:
            self.channel_model.update_many(updates)

        return processed

    def validate_channels(self, channels: List[Channel], categories: List[Category]) -> List[Channel]:
        valid_channels = []
        seen = set()

        for channel in channels:
            if (channel.name, channel.url) in seen:
                continue

            category_match = StringTools.match_category(channel.name, categories)
            if not category_match:
                continue

            category_name, category_type = category_match
            channel.name = category_name
            channel.type = category_type

            seen.add((channel.name, channel.url))
            valid_channels.append(channel)

        logger.info(f"Validated {len(valid_channels)}/{len(channels)} channels")
        return valid_channels

    def generate_iptv_file(self, output_file: str) -> int:
        categories = self.category_model.get_enabled()

        if not categories:
            logger.warning("No categories found")
            return 0

        content_lines = []
        total_channels = 0

        for category in categories:
            category_type = category.type

            content_lines.append(f"{category_type},#genre#\n")

            channels = self.channel_model.get_by_type(category_type)

            processed = set()
            for channel in channels:
                if (channel.name, channel.url) in processed:
                    continue

                if channel.speed > 0 and channel.width >= 1280:
                    content_lines.append(f"{channel.name},{channel.url}\n")
                    processed.add((channel.name, channel.url))
                    total_channels += 1

            logger.info(f"Generated {len(processed)} channels for {category_type}")

        update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        content_lines.append(f"更新时间,#genre#\n{update_time},https://taoiptv.com/time.mp4\n")

        try:
            with open(output_file, "w", encoding="utf-8") as f:
                f.writelines(content_lines)

            logger.info(f"Generated IPTV file: {output_file} with {total_channels} channels")
            return total_channels

        except Exception as e:
            logger.error(f"Failed to generate IPTV file: {e}")
            return 0

    def cleanup_invalid_channels(self, sign: int = 0) -> int:
        try:
            count = self.channel_model.delete_by_sign(sign)
            logger.info(f"Cleaned up {count} invalid channels with sign={sign}")
            return count
        except Exception as e:
            logger.error(f"Failed to cleanup channels: {e}")
            return 0

    def get_statistics(self) -> Dict[str, Any]:
        try:
            total = self.channel_model.count()

            by_type = {}
            categories = self.category_model.get_enabled()
            for category in categories:
                channels = self.channel_model.get_by_type(category.type)
                by_type[category.type] = len(channels)

            return {
                "total_channels": total,
                "by_type": by_type,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {}
