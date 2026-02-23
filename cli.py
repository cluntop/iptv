import sys
import json
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.config import init_config
from src.database import init_database
from src.utils import setup_logging, get_logger
from src.services import (
    IPTVService, HotelService, MulticastService,
    ProxyService, ProxyPlayService
)
from src.scrapers import MultiSourceScraper
from src.config import CloudflarePagesService

def print_help():
    print("""
IPTV Management CLI Tool
========================

Usage: python cli.py <command> [options]

Commands:
  scrape              - Scrape IPTV channels from network
  scrape-hotel        - Scrape hotel sources
  scrape-multicast    - Scrape multicast sources
  search              - Search sources using Fofa/Hunter/Quake
  process-speed       - Process channel speeds
  generate            - Generate IPTV files
  stats               - Show statistics
  health              - Check database health
  
  Proxy Commands:
  proxy-check         - Check single proxy
  proxy-check-file    - Check proxies from file
  proxy-play-test     - Test proxy with source URL
  
  Cloudflare Commands:
  cf-generate         - Generate Cloudflare Pages config files
  cf-headers          - Generate _headers file
  cf-redirects        - Generate _redirects file

Examples:
  python cli.py scrape
  python cli.py search --engine fofa --query "iptv"
  python cli.py proxy-check --host 127.0.0.1 --port 7890
  python cli.py proxy-play-test --host 192.168.1.1 --port 8080 --url rtp://239.0.0.1:1234
  python cli.py cf-generate
""")

def main():
    config = init_config()
    setup_logging(config.log.log_dir, config.log.level)
    logger = get_logger('cli')
    
    if len(sys.argv) < 2:
        print_help()
        return
    
    command = sys.argv[1].lower()
    
    try:
        db_manager = init_database(
            config.database.db_path,
            config.database.pool_size
        )
        
        if command == 'help' or command == '-h' or command == '--help':
            print_help()
        
        elif command == 'scrape':
            logger.info("Starting network scraping")
            iptv_service = IPTVService(db_manager)
            channels = iptv_service.scrape_network_channels()
            logger.info(f"Scraped {len(channels)} channels")
        
        elif command == 'scrape-hotel':
            logger.info("Starting hotel scraping")
            hotel_service = HotelService(db_manager)
            hotels = hotel_service.scrape_hotels('gyssi')
            logger.info(f"Scraped {len(hotels)} hotels")
        
        elif command == 'scrape-multicast':
            logger.info("Starting multicast source downloading")
            multicast_service = MulticastService(db_manager)
            files = multicast_service.download_sources()
            logger.info(f"Downloaded {len(files)} multicast source files")
        
        elif command == 'search':
            handle_search_command(logger, config)
        
        elif command == 'process-speed':
            logger.info("Processing channel speeds")
            iptv_service = IPTVService(db_manager)
            processed = iptv_service.process_channel_speeds()
            logger.info(f"Processed {processed} channel speeds")
        
        elif command == 'generate':
            logger.info("Generating IPTV files")
            iptv_service = IPTVService(db_manager)
            results = iptv_service.generate_iptv_files()
            logger.info(f"Generated files: {results}")
        
        elif command == 'stats':
            logger.info("Getting statistics")
            iptv_service = IPTVService(db_manager)
            stats = iptv_service.get_statistics()
            print("\n=== IPTV Statistics ===")
            print(f"Total Channels: {stats.get('total_channels', 0)}")
            print("By Type:")
            for channel_type, count in stats.get('by_type', {}).items():
                print(f"  {channel_type}: {count}")
        
        elif command == 'health':
            logger.info("Checking database health")
            health = db_manager.health_check()
            print("\n=== Database Health ===")
            print(f"Status: {health['status']}")
            print(f"Path: {health['db_path']}")
            print(f"Channels: {health['channel_count']}")
            print(f"Hotels: {health['hotel_count']}")
            print(f"Size: {health['db_size_mb']} MB")
            print(f"Connections: {health['pool_size']}")
        
        elif command == 'proxy-check':
            handle_proxy_check(logger, config)
        
        elif command == 'proxy-check-file':
            handle_proxy_check_file(logger, config)
        
        elif command == 'proxy-play-test':
            handle_proxy_play_test(logger, config)
        
        elif command == 'cf-generate':
            handle_cf_generate(logger, config)
        
        elif command == 'cf-headers':
            handle_cf_headers(logger, config)
        
        elif command == 'cf-redirects':
            handle_cf_redirects(logger, config)
        
        else:
            logger.error(f"Unknown command: {command}")
            print_help()
            sys.exit(1)
        
        logger.info("Command completed successfully")
        
    except Exception as e:
        logger.error(f"Command failed: {e}", exc_info=True)
        sys.exit(1)

def parse_args():
    args = {}
    i = 2
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg.startswith('--'):
            key = arg[2:]
            if i + 1 < len(sys.argv) and not sys.argv[i + 1].startswith('--'):
                args[key] = sys.argv[i + 1]
                i += 2
            else:
                args[key] = True
                i += 1
        else:
            i += 1
    return args

def handle_search_command(logger, config):
    args = parse_args()
    
    engine = args.get('engine', 'all')
    query = args.get('query', '')
    source_type = args.get('type', 'iptv')
    
    logger.info(f"Searching sources using {engine} engine")
    
    scraper_config = {
        'fofa_api_token': config.fofa_api_token,
        'quake_api_token': config.quake_api_token,
        'hunter_api_key': config.hunter_api_key,
        'timeout': config.scraper.timeout
    }
    
    scraper = MultiSourceScraper(scraper_config)
    
    if query:
        import asyncio
        results = asyncio.run(scraper.search_all(query, [engine] if engine != 'all' else None))
        
        print(f"\n=== Search Results ===")
        for eng, items in results.items():
            print(f"\n{eng.upper()}: {len(items)} results")
            for item in items[:10]:
                print(f"  {item.get('ip', 'N/A')}:{item.get('port', 'N/A')}")
    else:
        import asyncio
        country = args.get('country', '中国')
        province = args.get('province')
        isp = args.get('isp')
        
        if source_type == 'udpxy':
            results = asyncio.run(scraper.search_udpxy_sources(country, province, isp))
            print(f"\n=== UDPxy Sources ===")
            for udpxy in results[:20]:
                print(f"  {udpxy.ip}:{udpxy.port} - {udpxy.city}")
        else:
            engines = [engine] if engine != 'all' else None
            results = asyncio.run(scraper.search_iptv_sources(country, province, isp, engines))
            print(f"\n=== IPTV Sources ===")
            for hotel in results[:20]:
                print(f"  {hotel.ip}:{hotel.port} - {hotel.name}")
    
    scraper.close()

def handle_proxy_check(logger, config):
    args = parse_args()
    
    host = args.get('host')
    port = args.get('port')
    
    if not host or not port:
        print("Usage: python cli.py proxy-check --host <ip> --port <port> [--protocol http] [--user <username>] [--pass <password>]")
        return
    
    protocol = args.get('protocol', 'http')
    username = args.get('user')
    password = args.get('pass')
    
    logger.info(f"Checking proxy {host}:{port}")
    
    service = ProxyService(
        timeout=config.proxy.timeout,
        max_concurrent=config.proxy.max_concurrent
    )
    
    result = service.check_single_proxy(
        host=host,
        port=int(port),
        protocol=protocol,
        username=username,
        password=password
    )
    
    print(f"\n=== Proxy Check Result ===")
    print(f"Proxy: {result.proxy.to_url()}")
    print(f"Valid: {result.is_valid}")
    print(f"Latency: {result.latency_ms} ms")
    if result.exit_ip:
        print(f"Exit IP: {result.exit_ip}")
        print(f"Location: {result.exit_country}, {result.exit_region}, {result.exit_city}")
        print(f"ISP: {result.exit_isp}")
        print(f"Anonymous: {result.is_anonymous}")
        print(f"High Anonymous: {result.is_high_anonymous}")
    if result.error_message:
        print(f"Error: {result.error_message}")

def handle_proxy_check_file(logger, config):
    args = parse_args()
    
    file_path = args.get('file')
    if not file_path:
        print("Usage: python cli.py proxy-check-file --file <path>")
        return
    
    output = args.get('output')
    
    logger.info(f"Checking proxies from file: {file_path}")
    
    service = ProxyService(
        timeout=config.proxy.timeout,
        max_concurrent=config.proxy.max_concurrent
    )
    
    results = service.check_proxies_from_file(file_path)
    
    valid_count = sum(1 for r in results if r.is_valid)
    
    print(f"\n=== Proxy Check Results ===")
    print(f"Total: {len(results)}")
    print(f"Valid: {valid_count}")
    print(f"Invalid: {len(results) - valid_count}")
    
    if output:
        service.export_results(results, output)
        print(f"Results exported to: {output}")

def handle_proxy_play_test(logger, config):
    args = parse_args()
    
    host = args.get('host')
    port = args.get('port')
    url = args.get('url')
    proxy_type = args.get('type', 'udpxy')
    
    if not host or not port or not url:
        print("Usage: python cli.py proxy-play-test --host <ip> --port <port> --url <source_url> [--type udpxy|http|socks5]")
        return
    
    logger.info(f"Testing proxy {host}:{port} with source {url}")
    
    service = ProxyPlayService(timeout=config.proxy.timeout)
    
    result = service.test_proxy(
        proxy_host=host,
        proxy_port=int(port),
        source_url=url,
        proxy_type=proxy_type
    )
    
    print(f"\n=== Proxy Play Test Result ===")
    print(f"Proxy: {host}:{port} ({proxy_type})")
    print(f"Source: {url}")
    print(f"Playable: {result.get('is_playable', False)}")
    print(f"Latency: {result.get('latency_ms', 0)} ms")
    if result.get('stream_speed'):
        print(f"Stream Speed: {result.get('stream_speed')}x")
    if result.get('video_width') and result.get('video_height'):
        print(f"Resolution: {result.get('video_width')}x{result.get('video_height')}")
    if result.get('error_message'):
        print(f"Error: {result.get('error_message')}")

def handle_cf_generate(logger, config):
    args = parse_args()
    
    output_dir = args.get('output', config.output_dir)
    base_path = args.get('path', '.')
    
    logger.info("Generating Cloudflare Pages configuration files")
    
    service = CloudflarePagesService(project_name=config.cloudflare_pages.project_name)
    
    results = service.save_all_configs(output_dir=output_dir, base_path=base_path)
    
    print(f"\n=== Cloudflare Pages Config Generation ===")
    for file_name, success in results.items():
        status = "SUCCESS" if success else "FAILED"
        print(f"  {file_name}: {status}")

def handle_cf_headers(logger, config):
    args = parse_args()
    
    output_dir = args.get('output', config.output_dir)
    file_path = args.get('path', '_headers')
    
    logger.info("Generating Cloudflare Pages _headers file")
    
    service = CloudflarePagesService(project_name=config.cloudflare_pages.project_name)
    
    success = service.create_headers_file(output_dir=output_dir, file_path=file_path)
    
    print(f"\n=== _headers File Generation ===")
    print(f"Status: {'SUCCESS' if success else 'FAILED'}")
    print(f"Path: {file_path}")

def handle_cf_redirects(logger, config):
    args = parse_args()
    
    file_path = args.get('path', '_redirects')
    
    logger.info("Generating Cloudflare Pages _redirects file")
    
    service = CloudflarePagesService(project_name=config.cloudflare_pages.project_name)
    
    success = service.create_redirects_file(file_path=file_path)
    
    print(f"\n=== _redirects File Generation ===")
    print(f"Status: {'SUCCESS' if success else 'FAILED'}")
    print(f"Path: {file_path}")

if __name__ == "__main__":
    main()
