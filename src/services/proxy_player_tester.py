import asyncio
import aiohttp
import subprocess
import re
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from ..utils import get_logger

logger = get_logger('proxy_player_tester')


@dataclass
class ProxyPlayResult:
    proxy_host: str
    proxy_port: int
    proxy_protocol: str
    source_url: str
    is_playable: bool = False
    latency_ms: float = 0.0
    stream_speed: float = 0.0
    video_width: int = 0
    video_height: int = 0
    frame_rate: float = 0.0
    duration_tested: int = 0
    error_message: Optional[str] = None
    test_time: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if self.test_time:
            data['test_time'] = self.test_time.isoformat()
        return data


@dataclass
class InternalSource:
    url: str
    name: Optional[str] = None
    source_type: Optional[str] = None
    
    @property
    def is_multicast(self) -> bool:
        return 'rtp://' in self.url.lower() or 'udp://' in self.url.lower()
    
    @property
    def is_http(self) -> bool:
        return 'http://' in self.url.lower() or 'https://' in self.url.lower()


class ProxyPlayerTester:
    def __init__(self, timeout: int = 30, ffmpeg_path: str = 'ffmpeg'):
        self.timeout = timeout
        self.ffmpeg_path = ffmpeg_path
        self.ffmpeg_available = self._check_ffmpeg()
    
    def _check_ffmpeg(self) -> bool:
        try:
            subprocess.run(
                [self.ffmpeg_path, '-version'],
                capture_output=True,
                timeout=5
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            logger.warning("FFmpeg not found, proxy play testing will be limited")
            return False
    
    def _build_proxy_url(self, host: str, port: int, protocol: str,
                         username: str = None, password: str = None) -> str:
        if username and password:
            return f"{protocol}://{username}:{password}@{host}:{port}"
        return f"{protocol}://{host}:{port}"
    
    def _build_udpxy_url(self, proxy_host: str, proxy_port: int,
                         source_url: str) -> str:
        if 'rtp://' in source_url.lower():
            addr = source_url.lower().replace('rtp://', '')
        elif 'udp://' in source_url.lower():
            addr = source_url.lower().replace('udp://', '')
        else:
            addr = source_url
        
        return f"http://{proxy_host}:{proxy_port}/rtp/{addr}"
    
    async def test_http_proxy_play(self, proxy_host: str, proxy_port: int,
                                    source_url: str, proxy_protocol: str = 'http',
                                    username: str = None, password: str = None,
                                    test_duration: int = 10) -> ProxyPlayResult:
        result = ProxyPlayResult(
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            proxy_protocol=proxy_protocol,
            source_url=source_url,
            test_time=datetime.now()
        )
        
        if not self.ffmpeg_available:
            result.error_message = "FFmpeg not available"
            return result
        
        proxy_url = self._build_proxy_url(proxy_host, proxy_port, proxy_protocol, username, password)
        
        env = {}
        if proxy_protocol.lower() == 'http':
            env['http_proxy'] = proxy_url
            env['https_proxy'] = proxy_url
        elif proxy_protocol.lower() == 'socks5':
            env['all_proxy'] = proxy_url
        
        ffmpeg_cmd = [
            self.ffmpeg_path,
            '-i', source_url,
            '-t', str(test_duration),
            '-f', 'null',
            '-'
        ]
        
        start_time = time.time()
        
        try:
            process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**dict(subprocess.os.environ), **env}
            )
            
            stdout, stderr = process.communicate(timeout=test_duration + 15)
            
            result.latency_ms = round((time.time() - start_time) * 1000, 2)
            result.duration_tested = test_duration
            
            output = stderr.decode('utf-8', errors='ignore')
            
            if process.returncode == 0:
                result.is_playable = True
                
                speed_matches = re.findall(r'speed=(\d+\.?\d*)x', output)
                if speed_matches:
                    speeds = [float(s) for s in speed_matches]
                    result.stream_speed = round(sum(speeds) / len(speeds), 2)
                
                resolution_match = re.search(r'(\d+)x(\d+)', output)
                if resolution_match:
                    result.video_width = int(resolution_match.group(1))
                    result.video_height = int(resolution_match.group(2))
                
                fps_match = re.search(r'(\d+\.?\d*)\s*fps', output)
                if fps_match:
                    result.frame_rate = float(fps_match.group(1))
                
                logger.info(f"Proxy {proxy_host}:{proxy_port} play test succeeded for {source_url}")
            else:
                result.error_message = "FFmpeg returned non-zero exit code"
                logger.debug(f"Proxy play test failed: {output[-500:]}")
        
        except subprocess.TimeoutExpired:
            process.kill()
            result.error_message = "Test timeout"
            result.latency_ms = self.timeout * 1000
        
        except Exception as e:
            result.error_message = str(e)
            logger.error(f"Proxy play test error: {e}")
        
        return result
    
    async def test_udpxy_play(self, proxy_host: str, proxy_port: int,
                              source_url: str, test_duration: int = 10) -> ProxyPlayResult:
        result = ProxyPlayResult(
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            proxy_protocol='udpxy',
            source_url=source_url,
            test_time=datetime.now()
        )
        
        if not self.ffmpeg_available:
            result.error_message = "FFmpeg not available"
            return result
        
        udpxy_url = self._build_udpxy_url(proxy_host, proxy_port, source_url)
        
        ffmpeg_cmd = [
            self.ffmpeg_path,
            '-i', udpxy_url,
            '-t', str(test_duration),
            '-f', 'null',
            '-'
        ]
        
        start_time = time.time()
        
        try:
            process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            stdout, stderr = process.communicate(timeout=test_duration + 15)
            
            result.latency_ms = round((time.time() - start_time) * 1000, 2)
            result.duration_tested = test_duration
            
            output = stderr.decode('utf-8', errors='ignore')
            
            if process.returncode == 0:
                result.is_playable = True
                
                speed_matches = re.findall(r'speed=(\d+\.?\d*)x', output)
                if speed_matches:
                    speeds = [float(s) for s in speed_matches]
                    result.stream_speed = round(sum(speeds) / len(speeds), 2)
                
                resolution_match = re.search(r'(\d+)x(\d+)', output)
                if resolution_match:
                    result.video_width = int(resolution_match.group(1))
                    result.video_height = int(resolution_match.group(2))
                
                fps_match = re.search(r'(\d+\.?\d*)\s*fps', output)
                if fps_match:
                    result.frame_rate = float(fps_match.group(1))
                
                logger.info(f"UDPxy {proxy_host}:{proxy_port} play test succeeded for {source_url}")
            else:
                result.error_message = "FFmpeg returned non-zero exit code"
                logger.debug(f"UDPxy play test failed: {output[-500:]}")
        
        except subprocess.TimeoutExpired:
            process.kill()
            result.error_message = "Test timeout"
            result.latency_ms = self.timeout * 1000
        
        except Exception as e:
            result.error_message = str(e)
            logger.error(f"UDPxy play test error: {e}")
        
        return result
    
    async def test_socks5_play(self, proxy_host: str, proxy_port: int,
                                source_url: str, username: str = None,
                                password: str = None, test_duration: int = 10) -> ProxyPlayResult:
        return await self.test_http_proxy_play(
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            source_url=source_url,
            proxy_protocol='socks5',
            username=username,
            password=password,
            test_duration=test_duration
        )
    
    async def test_proxy_source(self, proxy_host: str, proxy_port: int,
                                 source_url: str, proxy_type: str = 'http',
                                 username: str = None, password: str = None,
                                 test_duration: int = 10) -> ProxyPlayResult:
        proxy_type = proxy_type.lower()
        
        if proxy_type == 'udpxy':
            return await self.test_udpxy_play(proxy_host, proxy_port, source_url, test_duration)
        elif proxy_type == 'socks5':
            return await self.test_socks5_play(proxy_host, proxy_port, source_url, username, password, test_duration)
        else:
            return await self.test_http_proxy_play(proxy_host, proxy_port, source_url, proxy_type, username, password, test_duration)
    
    async def batch_test_proxies(self, proxy_list: List[Dict[str, Any]],
                                  source_url: str, test_duration: int = 10,
                                  max_concurrent: int = 5) -> List[ProxyPlayResult]:
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def test_with_semaphore(proxy_info: Dict[str, Any]) -> ProxyPlayResult:
            async with semaphore:
                return await self.test_proxy_source(
                    proxy_host=proxy_info.get('host', proxy_info.get('ip', '')),
                    proxy_port=proxy_info.get('port', 0),
                    source_url=source_url,
                    proxy_type=proxy_info.get('type', proxy_info.get('protocol', 'http')),
                    username=proxy_info.get('username'),
                    password=proxy_info.get('password'),
                    test_duration=test_duration
                )
        
        tasks = [test_with_semaphore(p) for p in proxy_list]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                valid_results.append(ProxyPlayResult(
                    proxy_host=proxy_list[i].get('host', proxy_list[i].get('ip', '')),
                    proxy_port=proxy_list[i].get('port', 0),
                    proxy_protocol=proxy_list[i].get('type', 'http'),
                    source_url=source_url,
                    is_playable=False,
                    error_message=str(result),
                    test_time=datetime.now()
                ))
            else:
                valid_results.append(result)
        
        return valid_results
    
    def test_sync(self, proxy_host: str, proxy_port: int,
                  source_url: str, proxy_type: str = 'http',
                  username: str = None, password: str = None,
                  test_duration: int = 10) -> ProxyPlayResult:
        return asyncio.run(self.test_proxy_source(
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            source_url=source_url,
            proxy_type=proxy_type,
            username=username,
            password=password,
            test_duration=test_duration
        ))


class InternalSourceTester:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.player_tester = ProxyPlayerTester(timeout=timeout)
    
    async def test_internal_source_with_proxy(self, source: InternalSource,
                                               proxy_host: str, proxy_port: int,
                                               proxy_type: str = 'udpxy',
                                               username: str = None,
                                               password: str = None) -> ProxyPlayResult:
        return await self.player_tester.test_proxy_source(
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            source_url=source.url,
            proxy_type=proxy_type,
            username=username,
            password=password
        )
    
    async def test_source_with_multiple_proxies(self, source: InternalSource,
                                                 proxies: List[Dict[str, Any]],
                                                 max_concurrent: int = 5) -> List[ProxyPlayResult]:
        return await self.player_tester.batch_test_proxies(
            proxy_list=proxies,
            source_url=source.url,
            max_concurrent=max_concurrent
        )
    
    async def find_best_proxy_for_source(self, source: InternalSource,
                                          proxies: List[Dict[str, Any]]) -> Optional[ProxyPlayResult]:
        results = await self.test_source_with_multiple_proxies(source, proxies)
        
        playable_results = [r for r in results if r.is_playable]
        
        if not playable_results:
            return None
        
        playable_results.sort(key=lambda x: x.latency_ms)
        return playable_results[0]
    
    async def test_multiple_sources_with_proxy(self, sources: List[InternalSource],
                                                proxy_host: str, proxy_port: int,
                                                proxy_type: str = 'udpxy') -> List[ProxyPlayResult]:
        results = []
        
        for source in sources:
            result = await self.player_tester.test_proxy_source(
                proxy_host=proxy_host,
                proxy_port=proxy_port,
                source_url=source.url,
                proxy_type=proxy_type
            )
            results.append(result)
        
        return results


class ProxyPlayService:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.tester = ProxyPlayerTester(timeout=timeout)
        self.internal_tester = InternalSourceTester(timeout=timeout)
    
    def test_proxy(self, proxy_host: str, proxy_port: int,
                   source_url: str, proxy_type: str = 'http',
                   username: str = None, password: str = None) -> Dict[str, Any]:
        result = self.tester.test_sync(
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            source_url=source_url,
            proxy_type=proxy_type,
            username=username,
            password=password
        )
        return result.to_dict()
    
    def test_udpxy(self, proxy_host: str, proxy_port: int,
                   multicast_url: str) -> Dict[str, Any]:
        result = self.tester.test_sync(
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            source_url=multicast_url,
            proxy_type='udpxy'
        )
        return result.to_dict()
    
    def test_socks5(self, proxy_host: str, proxy_port: int,
                    source_url: str, username: str = None,
                    password: str = None) -> Dict[str, Any]:
        result = self.tester.test_sync(
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            source_url=source_url,
            proxy_type='socks5',
            username=username,
            password=password
        )
        return result.to_dict()
    
    def batch_test(self, proxy_list: List[Dict[str, Any]],
                   source_url: str) -> List[Dict[str, Any]]:
        results = asyncio.run(self.tester.batch_test_proxies(proxy_list, source_url))
        return [r.to_dict() for r in results]
    
    def find_best_proxy(self, source_url: str,
                        proxies: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        source = InternalSource(url=source_url)
        result = asyncio.run(self.internal_tester.find_best_proxy_for_source(source, proxies))
        return result.to_dict() if result else None
    
    def get_playable_proxies(self, results: List[Dict[str, Any]],
                             min_speed: float = 1.0) -> List[Dict[str, Any]]:
        playable = []
        
        for result in results:
            if not result.get('is_playable'):
                continue
            
            if min_speed > 0 and result.get('stream_speed', 0) < min_speed:
                continue
            
            playable.append(result)
        
        playable.sort(key=lambda x: x.get('latency_ms', float('inf')))
        return playable
