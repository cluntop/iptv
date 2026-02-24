import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Dict, List, Optional, Tuple

from ..utils import get_logger

logger = get_logger("database")


class SQLiteConnectionPool:
    def __init__(self, db_path: str, pool_size: int = 10):
        self.db_path = db_path
        self.pool_size = pool_size
        self._pool: Queue[sqlite3.Connection] = Queue(maxsize=pool_size)
        self._lock = threading.Lock()
        self._created_connections = 0

        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        for _ in range(pool_size):
            conn = self._create_connection()
            if conn:
                self._pool.put(conn)

    def _create_connection(self) -> Optional[sqlite3.Connection]:
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-64000")
            conn.execute("PRAGMA temp_store=MEMORY")
            conn.execute("PRAGMA mmap_size=268435456")

            with self._lock:
                self._created_connections += 1

            logger.debug(f"Created new SQLite connection, total: {self._created_connections}")
            return conn
        except sqlite3.Error as e:
            logger.error(f"Failed to create SQLite connection: {e}")
            return None

    @contextmanager
    def get_connection(self):
        conn = None
        try:
            try:
                conn = self._pool.get(timeout=10.0)
            except Empty:
                logger.warning("Connection pool exhausted, creating new connection")
                conn = self._create_connection()
                if conn is None:
                    raise sqlite3.Error("Failed to get database connection")

            yield conn
        finally:
            if conn:
                try:
                    self._pool.put(conn, timeout=5.0)
                except:
                    conn.close()

    def close_all(self):
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except Empty:
                break

        logger.info(f"Closed all SQLite connections")


class SQLiteManager:
    def __init__(self, db_path: str = "data/iptv.db", pool_size: int = 10):
        self.db_path = db_path
        self.pool = SQLiteConnectionPool(db_path, pool_size)
        self._initialized = False
        self._init_lock = threading.Lock()

    def initialize(self):
        with self._init_lock:
            if self._initialized:
                return

            logger.info(f"Initializing database: {self.db_path}")

            self._create_tables()
            self._create_indexes()

            self._initialized = True
            logger.info("Database initialization completed")

    def _create_tables(self):
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS iptv_category (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    psw TEXT NOT NULL,
                    type TEXT NOT NULL,
                    enable INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS iptv_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    type TEXT NOT NULL,
                    width INTEGER,
                    height INTEGER,
                    frame REAL,
                    speed REAL DEFAULT 0.00,
                    sign INTEGER DEFAULT 0,
                    time TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS iptv_hotels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    name TEXT,
                    count INTEGER DEFAULT 0,
                    status INTEGER DEFAULT 0,
                    time TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(ip, port)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS iptv_multicast (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    country TEXT,
                    province TEXT,
                    isp TEXT,
                    path TEXT,
                    city TEXT,
                    udpxy TEXT,
                    lines INTEGER DEFAULT 0,
                    status INTEGER DEFAULT 0,
                    time TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS iptv_udpxy (
                    id TEXT PRIMARY KEY,
                    mid INTEGER NOT NULL,
                    mcast TEXT NOT NULL,
                    city TEXT,
                    ip TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    actv INTEGER DEFAULT 0,
                    status INTEGER DEFAULT 0,
                    time TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (mid) REFERENCES iptv_multicast(id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS iptv_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    last_run TIMESTAMP,
                    next_run TIMESTAMP,
                    status TEXT DEFAULT 'pending',
                    result TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()
            logger.info("Database tables created successfully")

    def _create_indexes(self):
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()

            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_channels_url ON iptv_channels(url)",
                "CREATE INDEX IF NOT EXISTS idx_channels_name ON iptv_channels(name)",
                "CREATE INDEX IF NOT EXISTS idx_channels_type ON iptv_channels(type)",
                "CREATE INDEX IF NOT EXISTS idx_channels_sign ON iptv_channels(sign)",
                "CREATE INDEX IF NOT EXISTS idx_hotels_ip ON iptv_hotels(ip)",
                "CREATE INDEX IF NOT EXISTS idx_hotels_status ON iptv_hotels(status)",
                "CREATE INDEX IF NOT EXISTS idx_multicast_isp ON iptv_multicast(isp)",
                "CREATE INDEX IF NOT EXISTS idx_udpxy_mid ON iptv_udpxy(mid)",
                "CREATE INDEX IF NOT EXISTS idx_udpxy_status ON iptv_udpxy(status)",
                "CREATE INDEX IF NOT EXISTS idx_tasks_status ON iptv_tasks(status)",
            ]

            for index_sql in indexes:
                try:
                    cursor.execute(index_sql)
                except sqlite3.Error as e:
                    logger.warning(f"Index creation warning: {e}")

            conn.commit()
            logger.info("Database indexes created successfully")

    def health_check(self) -> Dict[str, Any]:
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("SELECT COUNT(*) FROM sqlite_master")
                table_count = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM iptv_channels")
                channel_count = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM iptv_hotels")
                hotel_count = cursor.fetchone()[0]

                cursor.execute("PRAGMA page_count")
                page_count = cursor.fetchone()[0]

                cursor.execute("PRAGMA page_size")
                page_size = cursor.fetchone()[0]

                db_size = page_count * page_size

                return {
                    "status": "healthy",
                    "db_path": self.db_path,
                    "table_count": table_count,
                    "channel_count": channel_count,
                    "hotel_count": hotel_count,
                    "db_size_bytes": db_size,
                    "db_size_mb": round(db_size / (1024 * 1024), 2),
                    "pool_size": self.pool.pool_size,
                    "created_connections": self.pool._created_connections,
                    "timestamp": datetime.now().isoformat(),
                }
        except sqlite3.Error as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    def execute_query(self, query: str, params: Tuple = (), fetch: bool = True) -> Optional[List[sqlite3.Row]]:
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(query, params)
                if fetch:
                    return cursor.fetchall()
                conn.commit()
                return None
            except sqlite3.Error as e:
                logger.error(f"Query execution failed: {query}, params: {params}, error: {e}")
                raise

    def execute_many(self, query: str, params_list: List[Tuple]) -> int:
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.executemany(query, params_list)
                conn.commit()
                return cursor.rowcount
            except sqlite3.Error as e:
                logger.error(f"Batch execution failed: {query}, error: {e}")
                raise

    def close(self):
        self.pool.close_all()
        logger.info("Database manager closed")


_db_manager: Optional[SQLiteManager] = None
_manager_lock = threading.Lock()


def get_db_manager(db_path: str = "data/iptv.db", pool_size: int = 10) -> SQLiteManager:
    global _db_manager

    with _manager_lock:
        if _db_manager is None:
            _db_manager = SQLiteManager(db_path, pool_size)
            _db_manager.initialize()

        return _db_manager


def init_database(db_path: str = "data/iptv.db", pool_size: int = 10) -> SQLiteManager:
    global _db_manager

    with _manager_lock:
        if _db_manager is not None:
            _db_manager.close()

        _db_manager = SQLiteManager(db_path, pool_size)
        _db_manager.initialize()

    return _db_manager
