import aiohttp
import asyncio
import re
import datetime
import time
import sys
from urllib.parse import urlparse, urljoin

# 尝试引入高性能事件循环
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass

# ================= 1. 全量抓取地址 (严格保留原列表) =================
urls = [
   "http://1.87.218.1:7878", "http://1.195.130.1:9901", "http://1.195.131.1:9901",
   "http://1.197.250.1:9901", "http://39.152.171.1:9901", "http://47.109.181.1:88",
   "http://47.116.70.1:9901", "http://49.232.48.1:9901", "http://58.19.133.1:9901",
   "http://58.57.40.1:9901", "http://59.38.45.1:8090", "http://60.255.47.1:8801",
   "http://61.136.172.1:9901", "http://61.156.228.1:8154", "http://101.66.194.1:9901",
   "http://101.66.195.1:9901", "http://101.66.198.1:9901", "http://101.66.199.1:9901",
   "http://101.74.28.1:9901", "http://103.39.222.1:9999", "http://106.42.34.1:888",
   "http://106.42.35.1:888", "http://106.118.70.1:9901", "http://110.253.83.1:888",
   "http://111.8.242.1:8085", "http://111.9.163.1:9901", "http://112.14.1:9901",
   "http://112.16.14.1:9901", "http://112.26.18.1:9901", "http://112.27.145.1:9901",
   "http://112.91.103.1:9919", "http://112.99.193.1:9901", "http://112.234.23.1:9901",
   "http://112.132.160.1:9901", "http://113.57.93.1:9900", "http://113.195.162.1:9901",
   "http://113.201.61.1:9901", "http://115.48.160.1:9901", "http://115.59.9.1:9901",
   "http://116.128.242.1:9901", "http://117.174.99.1:9901", "http://119.125.131.1:9901",
   "http://121.19.134.1:808", "http://121.29.191.1:8000", "http://121.43.180.1:9901",
   "http://121.56.39.1:808", "http://122.227.100.1:9901", "http://123.13.247.1:7000",
   "http://123.54.220.1:9901", "http://123.129.70.1:9901", "http://123.130.84.1:8154",
   "http://123.139.57.1:9901", "http://123.182.60.1:9002", "http://124.152.247.1:2001",
   "http://125.42.148.1:9901", "http://125.42.228.1:9999", "http://125.43.244.1:9901",
   "http://125.125.236.1:9901", "http://159.75.75.1:8888", "http://171.9.68.1:8099",
   "http://180.213.174.1:9901", "http://182.114.48.1:9901", "http://182.114.49.1:9901",
   "http://182.114.214.1:9901", "http://182.120.229.1:9901", "http://183.10.180.1:9901",
   "http://183.131.246.1:9901", "http://183.166.62.1:81", "http://183.255.41.1:9901",
   "http://211.142.224.1:2023", "http://218.13.170.1:9901", "http://218.77.81.1:9901",
   "http://218.87.237.1:9901", "http://220.248.173.1:9901", "http://221.2.148.1:8154",
   "http://221.13.235.1:9901", "http://222.172.183.1:808", "http://222.243.221.1:9901",
   "http://223.241.247.1:9901"
]

# ================= 2. 频道排序权重与元数据 =================
LOGO_BASE = "https://gitee.com/mytv-android/myTVlogo/raw/main/img/"

SORT_WEIGHT = {
    "CCTV1": 1, "CCTV2": 2, "CCTV3": 3, "CCTV4": 4, "CCTV5": 5, "CCTV5+": 6,
    "CCTV6": 7, "CCTV7": 8, "CCTV8": 9, "CCTV9": 10, "CCTV10": 11,
    "CCTV11": 12, "CCTV12": 13, "CCTV13": 14, "CCTV14": 15, "CCTV15": 16,
    "CCTV16": 17, "CCTV17": 18, "CCTV4K": 19, "CCTV8K": 20,
    "北京卫视": 100, "东方卫视": 101, "湖南卫视": 102, "浙江卫视": 103, "江苏卫视": 104,
    "广东卫视": 105, "安徽卫视": 106, "山东卫视": 107, "湖北卫视": 108, "天津卫视": 109,
    "河北卫视": 110, "山西卫视": 111, "辽宁卫视": 112, "吉林卫视": 113, "黑龙江卫视": 114
}

# ================= 3. 辅助功能函数 =================

def clean_name(name):
    name = name.upper().replace(" ", "")
    match = re.search(r'(CCTV\d+[\+]?)', name)
    if match: return match.group(1)
    if "卫视" in name:
        return name.split("-")[0].replace("HD", "").replace("高清", "")
    return name

def get_meta(name):
    cname = clean_name(name)
    if "CCTV" in cname:
        return cname, "央视频道", f"{LOGO_BASE}{cname}.png"
    elif "卫视" in cname:
        return cname, "卫视频道", f"{LOGO_BASE}{cname}.png"
    return cname, "其他频道", ""

def show_bar(curr, total, found, stage):
    length = 25
    progress = int(length * curr // total) if total > 0 else 0
    bar = "█" * progress + "░" * (length - progress)
    # 使用 \033[K 清除行尾残余字符，防止覆盖刷新时闪烁或残留
    sys.stdout.write(f"\r{stage} |{bar}| {curr}/{total} 有效:{found}\033[K")
    sys.stdout.flush()

# ================= 4. 核心逻辑 =================

async def check_stream(session, sem, item_data):
    """带信号量控制的稳定性检测，优化超时管理"""
    name_raw, url = item_data
    # 细化超时控制：连接建立最多 2 秒，读取首包最多 3 秒
    timeout = aiohttp.ClientTimeout(total=5, connect=2, sock_read=3)
    
    async with sem:
        try:
            target = url + ("&" if "?" in url else "?") + "playlive=1"
            start = time.time()
            async with session.get(target, timeout=timeout) as r:
                if r.status == 200:
                    chunk = await r.content.read(10240) 
                    if chunk:
                        rt = int((time.time() - start) * 1000)
                        return True, item_data, rt
        except Exception:
            pass
        return False, item_data, 9999

async def get_json_list(session, sem, base_url):
    """带信号量的 JSON 接口抓取"""
    api = f"{base_url}/iptv/live/1000.json?key=txiptv"
    timeout = aiohttp.ClientTimeout(total=3, connect=1.5)
    
    async with sem:
        try:
            async with session.get(api, timeout=timeout) as r:
                if r.status == 200:
                    # 防止服务器返回错误的 Content-Type 或无效 JSON 导致崩溃
                    data = await r.json(content_type=None)
                    if isinstance(data, dict) and 'data' in data:
                        return [(i.get('name', 'Unknown'), urljoin(base_url, i.get('url', ''))) for i in data['data'] if 'url' in i]
        except Exception:
            pass
        return []

async def main():
    print(f"🚀 启动地毯式扫描 - {datetime.datetime.now().strftime('%H:%M:%S')}")
    
    print("📡 阶段 1: 生成网段扫描任务...")
    scan_ips = []
    for u in urls:
        p = urlparse(u)
        segments = p.hostname.split('.')
        base = ".".join(segments[:3])
        port = f":{p.port}" if p.port else ""
        for i in range(1, 255):
            scan_ips.append(f"{p.scheme}://{base}.{i}{port}")

    # 并发限制器：针对 GitHub Actions 的 2 核环境，600-800 个并发连接最佳
    CONCURRENCY_LIMIT = 800 
    
    found_raw = []
    # 扩大连接池以匹配并发需求
    connector = aiohttp.TCPConnector(limit=CONCURRENCY_LIMIT, ssl=False)
    
    async with aiohttp.ClientSession(connector=connector) as sess:
        print(f"🔍 正在从 {len(scan_ips)} 个潜在接口并发抓取频道 (并发量: {CONCURRENCY_LIMIT})...")
        
        sem_api = asyncio.Semaphore(CONCURRENCY_LIMIT)
        tasks = [get_json_list(sess, sem_api, ip) for ip in scan_ips]
        
        completed_api = 0
        total_api = len(scan_ips)
        
        # 使用 as_completed 替代 manual batching，彻底消除短板效应
        for coro in asyncio.as_completed(tasks):
            res = await coro
            if res:
                found_raw.extend(res)
            completed_api += 1
            if completed_api % 50 == 0 or completed_api == total_api:
                show_bar(completed_api, total_api, len(found_raw), "接口扫描")

        unique_channels = list(set(found_raw))
        print(f"\n✅ 发现 {len(unique_channels)} 个待测频道，开始并发稳定性检测...")

        final_list = []
        sem_stream = asyncio.Semaphore(CONCURRENCY_LIMIT)
        check_tasks = [check_stream(sess, sem_stream, item) for item in unique_channels]
        
        completed_check = 0
        total_check = len(unique_channels)
        
        for coro in asyncio.as_completed(check_tasks):
            ok, item_data, rt = await coro
            if ok:
                name_raw, url = item_data
                cname, group, logo = get_meta(name_raw)
                final_list.append({
                    "name": cname, "url": url, "rt": rt,
                    "group": group, "logo": logo,
                    "weight": SORT_WEIGHT.get(cname, 999)
                })
            completed_check += 1
            if completed_check % 20 == 0 or completed_check == total_check:
                show_bar(completed_check, total_check, len(final_list), "稳定性检测")

        # 排序：权重优先(CCTV在前)，同频道则按延迟 RT 排序
        final_list.sort(key=lambda x: (x['weight'], x['rt']))

        # 保存 M3U
        with open("itvlist.m3u", "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for item in final_list:
                f.write(f'#EXTINF:-1 tvg-name="{item["name"]}" tvg-logo="{item["logo"]}" '
                        f'group-title="{item["group"]}" response-time="{item["rt"]}ms",'
                        f'{item["name"]}\n{item["url"]}\n')

    print(f"\n\n✨ 完成！已按源项目顺序保存 {len(final_list)} 条源至 itvlist.m3u")

if __name__ == "__main__":
    # 在 Windows 上由于底层缺陷需屏蔽特定报错，在 Linux/Actions 环境下无影响
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
