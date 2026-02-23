# IPTV System

一个现代化的IPTV直播源采集、处理和管理系统。

## 项目特性

- 模块化架构，易于维护和扩展
- SQLite3数据库，支持连接池和健康检查
- 多源数据采集（网络扫描、酒店源、组播源）
- 高性能并发处理，支持异步IO
- 定时任务调度，自动化数据更新
- 完善的日志系统和异常处理
- 支持M3U和TXT格式转换

## 项目结构

```
iptv/
├── src/                    # 源代码
│   ├── config/             # 配置管理
│   ├── database/           # 数据库模块
│   ├── scrapers/           # 数据抓取
│   ├── processors/         # 数据处理
│   ├── schedulers/         # 任务调度
│   ├── services/           # 业务服务
│   └── utils/             # 工具类
├── data/                  # 数据目录
│   ├── downloads/         # 下载文件
│   ├── output/            # 输出文件
│   └── logs/              # 日志文件
├── tests/                 # 测试文件
├── scripts/               # 脚本文件
├── .github/               # GitHub Actions
├── config.json            # 配置文件
├── main.py            # 主程序入口
├── cli.py                # 命令行工具
└── requirements.txt   # 依赖包
```

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置系统

编辑 `config.json` 文件，配置数据库路径、API密钥等参数。

### 运行主程序

```bash
python main.py
```

### 使用命令行工具

```bash
# 抓取网络频道
python cli.py scrape

# 抓取酒店源
python cli.py scrape-hotel

# 处理频道速度
python cli.py process-speed

# 生成IPTV文件
python cli.py generate

# 查看统计信息
python cli.py stats

# 检查数据库健康
python cli.py health
```

## 配置说明

### 数据库配置

```json
{
  "database": {
    "db_type": "sqlite",
    "db_path": "data/iptv.db",
    "pool_size": 10,
    "connection_timeout": 30
  }
}
```

### 抓取器配置

```json
{
  "scraper": {
    "timeout": 15,
    "max_retries": 3,
    "retry_delay": 1.0,
    "concurrency_limit": 800
  }
}
```

### 调度器配置

```json
{
  "scheduler": {
    "enabled": true,
    "hotel_update_hour": 2,
    "multicast_update_hour": 4,
    "speed_check_hour": 6
  }
}
```

## 模块说明

### 数据库模块

- 支持SQLite3连接池
- 自动初始化和表创建
- 健康检查功能
- ORM模型封装

### 抓取器模块

- IPTV网络扫描
- 酒店源采集
- 组播源下载
- 支持异步并发

### 处理器模块

- 频道速度检测
- 酒店源验证
- 组播源处理
- 批量数据操作

### 服务模块

- IPTV服务
- 酒店服务
- 组播服务
- 统一业务接口

## 开发指南

### 添加新的抓取源

1. 在 `src/scrapers/` 中创建新的抓取器类
2. 继承 `BaseScraper` 基类
3. 实现 `scrape()` 方法
4. 在服务层集成

### 添加新的处理器

1. 在 `src/processors/` 中创建处理器类
2. 实现数据处理逻辑
3. 在服务层调用

### 添加定时任务

```python
from src.schedulers import get_scheduler

scheduler = get_scheduler()
scheduler.add_task(
    name='my_task',
    func=my_function,
    schedule='daily@6'
)
scheduler.start()
```

## CI/CD

项目使用 GitHub Actions 进行自动化部署：

- 代码质量检查
- 自动化测试
- 定时数据更新
- 文件生成和提交
- 健康检查通知

## 注意事项

1. 确保系统已安装 `ffprobe` 和 `ffmpeg` 用于视频检测
2. 配置适当的并发限制，避免资源耗尽
3. 定期清理无效数据，保持数据库性能
4. 监控日志文件大小，及时归档

## 许可证

本项目遵循原有许可证。
