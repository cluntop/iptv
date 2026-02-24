import re
from pathlib import Path
from typing import Optional

from ..config.constants import LOGO_BASE_URL
from . import get_logger

logger = get_logger("file_tools")


class FileTools:
    @staticmethod
    def convert_m3u_to_txt(m3u_file: str) -> Optional[str]:
        m3u_path = Path(m3u_file)
        if not m3u_path.exists():
            logger.error(f"File not found: {m3u_file}")
            return None

        if not m3u_path.suffix.lower() == ".m3u":
            logger.warning(f"File is not .m3u format: {m3u_file}")
            return None

        txt_file = m3u_path.with_suffix(".txt")

        try:
            txt_output = ""
            current_group = None

            with open(m3u_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

                for i, line in enumerate(lines):
                    trimmed_line = line.strip()

                    if not trimmed_line:
                        continue

                    if trimmed_line.startswith("#EXTINF"):
                        channel_name = trimmed_line[trimmed_line.rfind(",") + 1 :]
                        if i + 1 < len(lines):
                            channel_link = lines[i + 1].strip()

                            if 'group-title="' in trimmed_line:
                                group_title = trimmed_line.split('group-title="')[1].split('"')[0]
                                if group_title and group_title != current_group:
                                    if current_group:
                                        txt_output += f"{current_group},#genre#\n"
                                    current_group = group_title

                            txt_output += f"{channel_name},{channel_link}\n"

            with open(txt_file, "w", encoding="utf-8") as f:
                f.write(txt_output)

            logger.info(f"Converted {m3u_file} to {txt_file}")
            return str(txt_file)

        except Exception as e:
            logger.error(f"Failed to convert {m3u_file}: {e}")
            return None

    @staticmethod
    def convert_txt_to_m3u(txt_file: str, logo_base: str = LOGO_BASE_URL) -> Optional[str]:
        txt_path = Path(txt_file)
        if not txt_path.exists():
            logger.error(f"File not found: {txt_file}")
            return None

        if not txt_path.suffix.lower() == ".txt":
            logger.warning(f"File is not .txt format: {txt_file}")
            return None

        m3u_file = txt_path.with_suffix(".m3u")

        try:
            m3u_output = '#EXTM3U x-tvg-url="https://live.fanmingming.com/e.xml"\n'
            current_group = None

            with open(txt_path, "r", encoding="utf-8") as f:
                for line in f:
                    trimmed_line = line.strip()

                    if not trimmed_line:
                        continue

                    if "#genre#" in trimmed_line:
                        current_group = trimmed_line.replace(",#genre#", "").strip()
                    else:
                        parts = trimmed_line.split(",", 1)
                        if len(parts) == 2:
                            channel_name, channel_link = parts
                            logo_url = f"{logo_base}{channel_name}.png"

                            m3u_output += f'#EXTINF:-1 tvg-name="{channel_name}" tvg-logo="{logo_url}"'
                            if current_group:
                                m3u_output += f' group-title="{current_group}"'
                            m3u_output += f",{channel_name}\n{channel_link}\n"

            with open(m3u_file, "w", encoding="utf-8") as f:
                f.write(m3u_output)

            logger.info(f"Converted {txt_file} to {m3u_file}")
            return str(m3u_file)

        except Exception as e:
            logger.error(f"Failed to convert {txt_file}: {e}")
            return None

    @staticmethod
    def ensure_dir(file_path: str) -> Path:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def get_file_size(file_path: str) -> int:
        try:
            return Path(file_path).stat().st_size
        except FileNotFoundError:
            return 0

    @staticmethod
    def is_valid_file_size(file_path: str, min_size: int = 1024) -> bool:
        return FileTools.get_file_size(file_path) >= min_size

    @staticmethod
    def clean_filename(filename: str) -> str:
        invalid_chars = r'[<>:"/\\|?*]'
        return re.sub(invalid_chars, "_", filename)
