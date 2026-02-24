from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..utils import get_logger

logger = get_logger("models")


@dataclass
class Channel:
    name: str
    url: str
    type: str
    width: Optional[int] = None
    height: Optional[int] = None
    frame: Optional[float] = None
    speed: float = 0.00
    sign: int = 0
    time: Optional[datetime] = None
    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if self.time:
            data["time"] = self.time.isoformat() if isinstance(self.time, datetime) else self.time
        return data


@dataclass
class Hotel:
    ip: str
    port: int
    name: Optional[str] = None
    count: int = 0
    status: int = 0
    time: Optional[datetime] = None
    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if self.time:
            data["time"] = self.time.isoformat() if isinstance(self.time, datetime) else self.time
        return data


@dataclass
class Multicast:
    country: Optional[str] = None
    province: Optional[str] = None
    isp: Optional[str] = None
    path: Optional[str] = None
    city: Optional[str] = None
    udpxy: Optional[str] = None
    lines: int = 0
    status: int = 0
    time: Optional[datetime] = None
    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if self.time:
            data["time"] = self.time.isoformat() if isinstance(self.time, datetime) else self.time
        return data


@dataclass
class Category:
    name: str
    psw: str
    type: str
    enable: int = 1
    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UDPxy:
    id: str
    mid: int
    mcast: str
    city: Optional[str] = None
    ip: str = ""
    port: int = 0
    actv: int = 0
    status: int = 0
    time: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if self.time:
            data["time"] = self.time.isoformat() if isinstance(self.time, datetime) else self.time
        return data


class SimpleCache:
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 300):
        self._cache: Dict[str, Any] = {}
        self._timestamps: Dict[str, datetime] = {}
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None

        timestamp = self._timestamps.get(key)
        if timestamp:
            elapsed = (datetime.now() - timestamp).total_seconds()
            if elapsed > self._ttl_seconds:
                del self._cache[key]
                del self._timestamps[key]
                return None

        return self._cache[key]

    def set(self, key: str, value: Any) -> None:
        if len(self._cache) >= self._max_size:
            oldest_key = min(self._timestamps, key=self._timestamps.get)
            del self._cache[oldest_key]
            del self._timestamps[oldest_key]

        self._cache[key] = value
        self._timestamps[key] = datetime.now()

    def clear(self) -> None:
        self._cache.clear()
        self._timestamps.clear()

    def invalidate(self, pattern: str = None) -> None:
        if pattern is None:
            self.clear()
        else:
            keys_to_delete = [k for k in self._cache if pattern in k]
            for key in keys_to_delete:
                del self._cache[key]
                del self._timestamps[key]


class ChannelModel:
    def __init__(self, db_manager):
        self.db = db_manager

    def insert(self, channel: Channel) -> int:
        query = """
            INSERT OR IGNORE INTO iptv_channels
            (name, url, type, width, height, frame, speed, sign, time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            return self.db.execute_insert(
                query,
                (
                    channel.name,
                    channel.url,
                    channel.type,
                    channel.width,
                    channel.height,
                    channel.frame,
                    channel.speed,
                    channel.sign,
                    channel.time,
                ),
            )
        except Exception as e:
            logger.error(f"Failed to insert channel: {e}")
            return 0

    def insert_many(self, channels: List[Channel]) -> int:
        if not channels:
            return 0

        query = """
            INSERT OR IGNORE INTO iptv_channels
            (name, url, type, width, height, frame, speed, sign, time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = [(c.name, c.url, c.type, c.width, c.height, c.frame, c.speed, c.sign, c.time) for c in channels]
        return self.db.execute_many(query, params)

    def update(self, channel_id: int, **kwargs) -> bool:
        if not kwargs:
            return False

        set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        query = f"UPDATE iptv_channels SET {set_clause} WHERE id = ?"
        params = list(kwargs.values()) + [channel_id]

        try:
            self.db.execute_query(query, tuple(params), fetch=False)
            return True
        except Exception as e:
            logger.error(f"Failed to update channel {channel_id}: {e}")
            return False

    def update_many(self, updates: List[Dict[str, Any]]) -> int:
        if not updates:
            return 0

        query = """
            UPDATE iptv_channels
            SET speed = ?, width = ?, height = ?, frame = ?, time = ?
            WHERE id = ?
        """
        params = [
            (
                u.get("speed", 0),
                u.get("width"),
                u.get("height"),
                u.get("frame"),
                u.get("time"),
                u["id"],
            )
            for u in updates
        ]
        return self.db.execute_many(query, params)

    def get_by_id(self, channel_id: int) -> Optional[Channel]:
        query = "SELECT * FROM iptv_channels WHERE id = ?"
        rows = self.db.execute_query(query, (channel_id,))
        if rows:
            return self._row_to_channel(rows[0])
        return None

    def get_by_url(self, url: str) -> Optional[Channel]:
        query = "SELECT * FROM iptv_channels WHERE url = ?"
        rows = self.db.execute_query(query, (url,))
        if rows:
            return self._row_to_channel(rows[0])
        return None

    def get_all(self, limit: int = None, offset: int = 0) -> List[Channel]:
        query = "SELECT * FROM iptv_channels ORDER BY id DESC"
        if limit:
            query += f" LIMIT {limit} OFFSET {offset}"

        rows = self.db.execute_query(query)
        return [self._row_to_channel(row) for row in rows]

    def get_by_type(self, channel_type: str, sign: int = None) -> List[Channel]:
        if sign is not None:
            query = "SELECT * FROM iptv_channels WHERE type = ? AND sign = ?"
            rows = self.db.execute_query(query, (channel_type, sign))
        else:
            query = "SELECT * FROM iptv_channels WHERE type = ?"
            rows = self.db.execute_query(query, (channel_type,))

        return [self._row_to_channel(row) for row in rows]

    def delete_by_id(self, channel_id: int) -> bool:
        query = "DELETE FROM iptv_channels WHERE id = ?"
        try:
            self.db.execute_query(query, (channel_id,), fetch=False)
            return True
        except Exception as e:
            logger.error(f"Failed to delete channel {channel_id}: {e}")
            return False

    def delete_by_sign(self, sign: int) -> int:
        query = "DELETE FROM iptv_channels WHERE sign = ?"
        try:
            self.db.execute_query(query, (sign,), fetch=False)
            return self.db.execute_query("SELECT changes()")[0][0]
        except Exception as e:
            logger.error(f"Failed to delete channels by sign {sign}: {e}")
            return 0

    def count(self) -> int:
        query = "SELECT COUNT(*) FROM iptv_channels"
        rows = self.db.execute_query(query)
        return rows[0][0] if rows else 0

    def _row_to_channel(self, row) -> Channel:
        return Channel(
            id=row["id"],
            name=row["name"],
            url=row["url"],
            type=row["type"],
            width=row["width"],
            height=row["height"],
            frame=row["frame"],
            speed=row["speed"],
            sign=row["sign"],
            time=datetime.fromisoformat(row["time"]) if row["time"] else None,
        )


class HotelModel:
    def __init__(self, db_manager):
        self.db = db_manager

    def insert(self, hotel: Hotel) -> int:
        query = """
            INSERT OR IGNORE INTO iptv_hotels
            (ip, port, name, count, status, time)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        try:
            return self.db.execute_insert(
                query,
                (
                    hotel.ip,
                    hotel.port,
                    hotel.name,
                    hotel.count,
                    hotel.status,
                    hotel.time,
                ),
            )
        except Exception as e:
            logger.error(f"Failed to insert hotel: {e}")
            return 0

    def insert_many(self, hotels: List[Hotel]) -> int:
        if not hotels:
            return 0

        query = """
            INSERT OR IGNORE INTO iptv_hotels
            (ip, port, name, count, status, time)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        params = [(h.ip, h.port, h.name, h.count, h.status, h.time) for h in hotels]
        return self.db.execute_many(query, params)

    def update(self, ip: str, **kwargs) -> bool:
        if not kwargs:
            return False

        set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        query = f"UPDATE iptv_hotels SET {set_clause} WHERE ip = ?"
        params = list(kwargs.values()) + [ip]

        try:
            self.db.execute_query(query, tuple(params), fetch=False)
            return True
        except Exception as e:
            logger.error(f"Failed to update hotel {ip}: {e}")
            return False

    def get_by_ip(self, ip: str) -> Optional[Hotel]:
        query = "SELECT * FROM iptv_hotels WHERE ip = ?"
        rows = self.db.execute_query(query, (ip,))
        if rows:
            return self._row_to_hotel(rows[0])
        return None

    def get_by_status(self, status: int) -> List[Hotel]:
        query = "SELECT * FROM iptv_hotels WHERE status = ?"
        rows = self.db.execute_query(query, (status,))
        return [self._row_to_hotel(row) for row in rows]

    def get_all(self) -> List[Hotel]:
        query = "SELECT * FROM iptv_hotels ORDER BY id DESC"
        rows = self.db.execute_query(query)
        return [self._row_to_hotel(row) for row in rows]

    def delete_by_ip(self, ip: str) -> bool:
        query = "DELETE FROM iptv_hotels WHERE ip = ?"
        try:
            self.db.execute_query(query, (ip,), fetch=False)
            return True
        except Exception as e:
            logger.error(f"Failed to delete hotel {ip}: {e}")
            return False

    def count(self) -> int:
        query = "SELECT COUNT(*) FROM iptv_hotels"
        rows = self.db.execute_query(query)
        return rows[0][0] if rows else 0

    def _row_to_hotel(self, row) -> Hotel:
        return Hotel(
            id=row["id"],
            ip=row["ip"],
            port=row["port"],
            name=row["name"],
            count=row["count"],
            status=row["status"],
            time=datetime.fromisoformat(row["time"]) if row["time"] else None,
        )


class MulticastModel:
    def __init__(self, db_manager):
        self.db = db_manager

    def insert(self, multicast: Multicast) -> int:
        query = """
            INSERT INTO iptv_multicast
            (country, province, isp, path, city, udpxy, lines, status, time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            return self.db.execute_insert(
                query,
                (
                    multicast.country,
                    multicast.province,
                    multicast.isp,
                    multicast.path,
                    multicast.city,
                    multicast.udpxy,
                    multicast.lines,
                    multicast.status,
                    multicast.time,
                ),
            )
        except Exception as e:
            logger.error(f"Failed to insert multicast: {e}")
            return 0

    def update(self, multicast_id: int, **kwargs) -> bool:
        if not kwargs:
            return False

        set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        query = f"UPDATE iptv_multicast SET {set_clause} WHERE id = ?"
        params = list(kwargs.values()) + [multicast_id]

        try:
            self.db.execute_query(query, tuple(params), fetch=False)
            return True
        except Exception as e:
            logger.error(f"Failed to update multicast {multicast_id}: {e}")
            return False

    def get_by_id(self, multicast_id: int) -> Optional[Multicast]:
        query = "SELECT * FROM iptv_multicast WHERE id = ?"
        rows = self.db.execute_query(query, (multicast_id,))
        if rows:
            return self._row_to_multicast(rows[0])
        return None

    def get_all(self) -> List[Multicast]:
        query = "SELECT * FROM iptv_multicast ORDER BY id DESC"
        rows = self.db.execute_query(query)
        return [self._row_to_multicast(row) for row in rows]

    def count(self) -> int:
        query = "SELECT COUNT(*) FROM iptv_multicast"
        rows = self.db.execute_query(query)
        return rows[0][0] if rows else 0

    def _row_to_multicast(self, row) -> Multicast:
        return Multicast(
            id=row["id"],
            country=row["country"],
            province=row["province"],
            isp=row["isp"],
            path=row["path"],
            city=row["city"],
            udpxy=row["udpxy"],
            lines=row["lines"],
            status=row["status"],
            time=datetime.fromisoformat(row["time"]) if row["time"] else None,
        )


class CategoryModel:
    _cache: SimpleCache = SimpleCache(max_size=100, ttl_seconds=300)

    def __init__(self, db_manager):
        self.db = db_manager

    def insert(self, category: Category) -> int:
        query = """
            INSERT INTO iptv_category (name, psw, type, enable)
            VALUES (?, ?, ?, ?)
        """
        try:
            result = self.db.execute_insert(
                query,
                (category.name, category.psw, category.type, category.enable),
            )
            self._cache.invalidate("categories")
            return result
        except Exception as e:
            logger.error(f"Failed to insert category: {e}")
            return 0

    def get_enabled(self) -> List[Category]:
        cache_key = "categories_enabled"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        query = "SELECT * FROM iptv_category WHERE enable = 1 ORDER BY id DESC"
        rows = self.db.execute_query(query)
        result = [self._row_to_category(row) for row in rows]
        self._cache.set(cache_key, result)
        return result

    def get_by_type(self, category_type: str) -> List[Category]:
        cache_key = f"categories_type_{category_type}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        query = "SELECT * FROM iptv_category WHERE type = ? AND enable = 1"
        rows = self.db.execute_query(query, (category_type,))
        result = [self._row_to_category(row) for row in rows]
        self._cache.set(cache_key, result)
        return result

    def get_all(self) -> List[Category]:
        cache_key = "categories_all"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        query = "SELECT * FROM iptv_category ORDER BY id DESC"
        rows = self.db.execute_query(query)
        result = [self._row_to_category(row) for row in rows]
        self._cache.set(cache_key, result)
        return result

    def _row_to_category(self, row) -> Category:
        return Category(
            id=row["id"],
            name=row["name"],
            psw=row["psw"],
            type=row["type"],
            enable=row["enable"],
        )


class UDPxyModel:
    def __init__(self, db_manager):
        self.db = db_manager

    def insert(self, udpxy: UDPxy) -> bool:
        query = """
            INSERT OR IGNORE INTO iptv_udpxy
            (id, mid, mcast, city, ip, port, actv, status, time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            self.db.execute_query(
                query,
                (
                    udpxy.id,
                    udpxy.mid,
                    udpxy.mcast,
                    udpxy.city,
                    udpxy.ip,
                    udpxy.port,
                    udpxy.actv,
                    udpxy.status,
                    udpxy.time,
                ),
                fetch=False,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to insert udpxy: {e}")
            return False

    def insert_many(self, udpxy_list: List[UDPxy]) -> int:
        if not udpxy_list:
            return 0

        query = """
            INSERT OR IGNORE INTO iptv_udpxy
            (id, mid, mcast, city, ip, port, actv, status, time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = [(u.id, u.mid, u.mcast, u.city, u.ip, u.port, u.actv, u.status, u.time) for u in udpxy_list]
        return self.db.execute_many(query, params)

    def update(self, udpxy_id: str, **kwargs) -> bool:
        if not kwargs:
            return False

        set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        query = f"UPDATE iptv_udpxy SET {set_clause} WHERE id = ?"
        params = list(kwargs.values()) + [udpxy_id]

        try:
            self.db.execute_query(query, tuple(params), fetch=False)
            return True
        except Exception as e:
            logger.error(f"Failed to update udpxy {udpxy_id}: {e}")
            return False

    def get_by_mid(self, mid: int, status: int = None) -> List[UDPxy]:
        if status is not None:
            query = "SELECT * FROM iptv_udpxy WHERE mid = ? AND status = ?"
            rows = self.db.execute_query(query, (mid, status))
        else:
            query = "SELECT * FROM iptv_udpxy WHERE mid = ?"
            rows = self.db.execute_query(query, (mid,))

        return [self._row_to_udpxy(row) for row in rows]

    def delete_by_status(self, mid: int, status: int) -> int:
        query = "DELETE FROM iptv_udpxy WHERE mid = ? AND status = ?"
        try:
            self.db.execute_query(query, (mid, status), fetch=False)
            return self.db.execute_query("SELECT changes()")[0][0]
        except Exception as e:
            logger.error(f"Failed to delete udpxy by status: {e}")
            return 0

    def count(self, mid: int = None, status: int = None) -> int:
        if mid is not None and status is not None:
            query = "SELECT COUNT(*) FROM iptv_udpxy WHERE mid = ? AND status = ?"
            rows = self.db.execute_query(query, (mid, status))
        elif mid is not None:
            query = "SELECT COUNT(*) FROM iptv_udpxy WHERE mid = ?"
            rows = self.db.execute_query(query, (mid,))
        else:
            query = "SELECT COUNT(*) FROM iptv_udpxy"
            rows = self.db.execute_query(query)

        return rows[0][0] if rows else 0

    def _row_to_udpxy(self, row) -> UDPxy:
        return UDPxy(
            id=row["id"],
            mid=row["mid"],
            mcast=row["mcast"],
            city=row["city"],
            ip=row["ip"],
            port=row["port"],
            actv=row["actv"],
            status=row["status"],
            time=datetime.fromisoformat(row["time"]) if row["time"] else None,
        )
