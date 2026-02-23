import json
import re
import subprocess
from typing import List, Optional, Tuple

from ..utils import get_logger

logger = get_logger("video_tools")


class VideoTools:
    def __init__(self):
        self.ffprobe_available = self._check_ffprobe()
        self.ffmpeg_available = self._check_ffmpeg()

    def _check_ffprobe(self) -> bool:
        try:
            subprocess.run(["ffprobe", "-version"], capture_output=True, timeout=5)
            return True
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            logger.warning("ffprobe not found, video info extraction will be limited")
            return False

    def _check_ffmpeg(self) -> bool:
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
            return True
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            logger.warning("ffmpeg not found, speed testing will be limited")
            return False

    def get_video_info(self, url: str, timeout: int = 15) -> List:
        if not self.ffprobe_available:
            return []

        command = [
            "ffprobe",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            "-v",
            "quiet",
            url,
        ]

        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=timeout
            )
            output = result.stdout
            data = json.loads(output)

            video_streams = data.get("streams", [])
            if not video_streams:
                return []

            stream = video_streams[0]
            width = stream.get("width") or 0
            height = stream.get("height") or 0
            frame_str = stream.get("r_frame_rate", "0/0")

            if frame_str and frame_str != "0/0":
                try:
                    frame = eval(frame_str)
                except:
                    frame = 0.0
            else:
                frame = 0.0

            if width == 0 or height == 0 or frame == 0.0:
                return []

            return [width, height, frame]

        except (KeyError, json.JSONDecodeError, subprocess.TimeoutExpired) as e:
            logger.debug(f"Failed to get video info for {url}: {e}")
            return []
        except Exception as e:
            logger.warning(f"Unexpected error getting video info for {url}: {e}")
            return []

    def get_stream_speed(self, url: str, duration: int = 10) -> float:
        if not self.ffmpeg_available:
            return 0.00

        ffmpeg_command = f"ffmpeg -i {url} -t {duration} -f null -"

        try:
            process = subprocess.Popen(
                ffmpeg_command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = process.communicate(timeout=duration + 10)

            output_str = stderr.decode("utf-8", errors="ignore")
            matches = re.findall(r"speed=(.*?)x", output_str)

            if matches:
                speeds = [float(speed) for speed in matches]
                avg_speed = sum(speeds) / len(speeds)
                speed_mbps = float(f"{avg_speed:.2f}")
                return max(speed_mbps, 1.00)

            return 0.00

        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
            logger.debug(f"Failed to get stream speed for {url}: {e}")
            return 0.00
        except Exception as e:
            logger.warning(f"Unexpected error getting stream speed for {url}: {e}")
            return 0.00

    def validate_stream(self, url: str, timeout: int = 5) -> bool:
        if not self.ffmpeg_available:
            return False

        ffmpeg_command = f"ffmpeg -i {url} -t 1 -f null -"

        try:
            process = subprocess.Popen(
                ffmpeg_command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            process.communicate(timeout=timeout + 2)
            return process.returncode == 0

        except subprocess.TimeoutExpired:
            return False
        except Exception:
            return False
