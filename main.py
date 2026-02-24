import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.config import init_config
from src.database import init_database
from src.utils import setup_logging, get_logger, get_concurrency_config
from src.services import IPTVService, HotelService, MulticastService


async def run_iptv_tasks_async(iptv_service: IPTVService):
    logger = get_logger('main')

    tasks_def = [
        ("scrape_network", lambda: iptv_service.scrape_network_channels()),
        ("process_speeds", lambda: iptv_service.process_channel_speeds()),
        ("generate_files", lambda: iptv_service.generate_iptv_files()),
    ]

    results = {}

    async def run_task(name, func):
        logger.info(f"Starting task: {name}")
        try:
            result = func()
            logger.info(f"Completed task: {name}")
            return name, result
        except Exception as e:
            logger.error(f"Task {name} failed: {e}")
            return name, None

    task_coroutines = [run_task(name, func) for name, func in tasks_def]
    task_results = await asyncio.gather(*task_coroutines, return_exceptions=True)

    for result in task_results:
        if isinstance(result, Exception):
            logger.error(f"Task exception: {result}")
        elif result:
            name, value = result
            results[name] = value

    return results


def main():
    config = init_config()
    setup_logging(config.log.log_dir, config.log.level)
    logger = get_logger('main')

    logger.info("=" * 60)
    logger.info("IPTV System Starting")
    logger.info("=" * 60)

    try:
        db_manager = init_database(
            config.database.db_path,
            config.database.pool_size
        )

        health = db_manager.health_check()
        logger.info(f"Database health: {health['status']}")
        logger.info(f"Database path: {health['db_path']}")
        logger.info(f"Channel count: {health['channel_count']}")
        logger.info(f"Hotel count: {health['hotel_count']}")

        iptv_service = IPTVService(db_manager)
        hotel_service = HotelService(db_manager)
        multicast_service = MulticastService(db_manager)

        if config.scheduler.enabled:
            from src.schedulers import init_scheduler
            scheduler = init_scheduler(db_manager)

            scheduler.add_task(
                name='hotel_scrape',
                func=hotel_service.scrape_hotels,
                schedule='weekly@5',
                args=('gyssi',)
            )

            scheduler.add_task(
                name='hotel_validate',
                func=hotel_service.validate_hotels,
                schedule='daily@3'
            )

            scheduler.add_task(
                name='multicast_download',
                func=multicast_service.download_sources,
                schedule='weekly@6'
            )

            scheduler.add_task(
                name='channel_speed_check',
                func=iptv_service.process_channel_speeds,
                schedule='daily@6'
            )

            scheduler.add_task(
                name='generate_iptv_files',
                func=iptv_service.generate_iptv_files,
                schedule='daily@7'
            )

            scheduler.start()
            logger.info("Scheduler started with configured tasks")

        asyncio.run(run_iptv_tasks_async(iptv_service))

        stats = iptv_service.get_statistics()
        logger.info(f"IPTV Statistics: {stats}")

        logger.info("=" * 60)
        logger.info("IPTV System Completed Successfully")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if 'scheduler' in locals():
            scheduler.stop()

if __name__ == "__main__":
    main()
