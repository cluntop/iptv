import unittest
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import init_config, get_config
from src.database import init_database, get_db_manager
from src.utils import get_logger


class TestConfig(unittest.TestCase):
    def test_config_init(self):
        config = init_config()
        self.assertIsNotNone(config)
        self.assertEqual(config.database.db_type, "sqlite")

    def test_get_config(self):
        config = get_config()
        self.assertIsNotNone(config)
        self.assertIsNotNone(config.database)


class TestDatabase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = init_config()
        cls.db = init_database(":memory:")

    def test_database_initialization(self):
        health = self.db.health_check()
        self.assertEqual(health["status"], "healthy")

    def test_channel_operations(self):
        from src.database import Channel, ChannelModel
        from datetime import datetime

        channel_model = ChannelModel(self.db)

        channel = Channel(
            name="Test Channel",
            url="http://test.com/stream.m3u8",
            type="央视频道",
            width=1920,
            height=1080,
            frame=25.0,
            speed=5.00,
            sign=0,
            time=datetime.now(),
        )

        channel_id = channel_model.insert(channel)
        self.assertGreater(channel_id, 0)

        retrieved = channel_model.get_by_id(channel_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "Test Channel")

        channel_model.delete_by_id(channel_id)
        deleted = channel_model.get_by_id(channel_id)
        self.assertIsNone(deleted)


class TestUtils(unittest.TestCase):
    def test_string_tools(self):
        from src.utils.string_tools import StringTools

        cleaned = StringTools.clean_channel_name("CCTV1 HD")
        self.assertEqual(cleaned, "CCTV1")

        normalized = StringTools.normalize_channel_name("CCTV1 [高清]")
        self.assertEqual(normalized, "CCTV1")

    def test_file_tools(self):
        from src.utils.file_tools import FileTools

        self.assertTrue(FileTools.is_valid_file_size("data", 0))
        self.assertFalse(FileTools.is_valid_file_size("data", 1000000))


if __name__ == "__main__":
    unittest.main()
