import os
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List


@dataclass
class DatabaseConfig:
    db_type: str = "sqlite"
    db_path: str = "data/iptv.db"
    pool_size: int = 10
    connection_timeout: int = 30

    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "iptv"
    mysql_password: str = ""
    mysql_database: str = "iptv"


@dataclass
class ScraperConfig:
    timeout: int = 15
    max_retries: int = 3
    retry_delay: float = 1.0
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    concurrency_limit: int = 800
    download_timeout: int = 30


@dataclass
class SchedulerConfig:
    enabled: bool = True
    hotel_update_hour: int = 2
    multicast_update_hour: int = 4
    speed_check_hour: int = 6
    cleanup_hour: int = 0


@dataclass
class LogConfig:
    level: str = "INFO"
    log_dir: str = "data/logs"
    max_file_size: int = 10 * 1024 * 1024
    backup_count: int = 5
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


@dataclass
class ProxyConfig:
    timeout: int = 15
    max_concurrent: int = 50
    test_duration: int = 10


@dataclass
class CloudflarePagesConfigData:
    enabled: bool = False
    project_name: str = "iptv"
    output_dir: str = "data/output"


@dataclass
class Config:
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    scraper: ScraperConfig = field(default_factory=ScraperConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    log: LogConfig = field(default_factory=LogConfig)
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    cloudflare_pages: CloudflarePagesConfigData = field(
        default_factory=CloudflarePagesConfigData
    )

    data_dir: str = "data"
    output_dir: str = "data/output"
    download_dir: str = "data/downloads"

    quake_api_token: str = ""
    fofa_api_token: str = ""
    hunter_api_key: str = ""

    @classmethod
    def from_file(cls, config_path: str) -> "Config":
        path = Path(config_path)
        if not path.exists():
            return cls()

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        config = cls()

        if "database" in data:
            config.database = DatabaseConfig(**data["database"])
        if "scraper" in data:
            config.scraper = ScraperConfig(**data["scraper"])
        if "scheduler" in data:
            config.scheduler = SchedulerConfig(**data["scheduler"])
        if "log" in data:
            config.log = LogConfig(**data["log"])
        if "proxy" in data:
            config.proxy = ProxyConfig(**data["proxy"])
        if "cloudflare_pages" in data:
            config.cloudflare_pages = CloudflarePagesConfigData(
                **data["cloudflare_pages"]
            )

        for key in [
            "data_dir",
            "output_dir",
            "download_dir",
            "quake_api_token",
            "fofa_api_token",
            "hunter_api_key",
        ]:
            if key in data:
                setattr(config, key, data[key])

        return config

    @classmethod
    def from_env(cls) -> "Config":
        config = cls()

        if db_path := os.getenv("IPTV_DB_PATH"):
            config.database.db_path = db_path
        if db_type := os.getenv("IPTV_DB_TYPE"):
            config.database.db_type = db_type
        if mysql_host := os.getenv("MYSQL_HOST"):
            config.database.mysql_host = mysql_host
        if mysql_user := os.getenv("MYSQL_USER"):
            config.database.mysql_user = mysql_user
        if mysql_password := os.getenv("MYSQL_PASSWORD"):
            config.database.mysql_password = mysql_password
        if mysql_database := os.getenv("MYSQL_DATABASE"):
            config.database.mysql_database = mysql_database
        if quake_token := os.getenv("QUAKE_API_TOKEN"):
            config.quake_api_token = quake_token
        if fofa_token := os.getenv("FOFA_API_TOKEN"):
            config.fofa_api_token = fofa_token
        if hunter_key := os.getenv("HUNTER_API_KEY"):
            config.hunter_api_key = hunter_key
        if log_level := os.getenv("LOG_LEVEL"):
            config.log.level = log_level

        return config

    def to_dict(self) -> Dict[str, Any]:
        return {
            "database": self.database.__dict__,
            "scraper": self.scraper.__dict__,
            "scheduler": self.scheduler.__dict__,
            "log": self.log.__dict__,
            "proxy": self.proxy.__dict__,
            "cloudflare_pages": self.cloudflare_pages.__dict__,
            "data_dir": self.data_dir,
            "output_dir": self.output_dir,
            "download_dir": self.download_dir,
            "quake_api_token": "***" if self.quake_api_token else "",
            "fofa_api_token": "***" if self.fofa_api_token else "",
            "hunter_api_key": "***" if self.hunter_api_key else "",
        }


_config_instance: Optional[Config] = None


def get_config(config_path: Optional[str] = None, reload: bool = False) -> Config:
    global _config_instance

    if _config_instance is None or reload:
        if config_path and Path(config_path).exists():
            _config_instance = Config.from_file(config_path)
        else:
            _config_instance = Config.from_env()

    return _config_instance


def init_config(config_path: Optional[str] = None) -> Config:
    return get_config(config_path, reload=True)
