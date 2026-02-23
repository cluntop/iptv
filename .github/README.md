# iptv


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
├── main.py               # 主程序
├── cli.py                # 命令行工具
└── requirements.txt       # 依赖包
```

## 使用说明

### 快速开始
1. 安装依赖: `pip install -r requirements.txt`
2. 配置系统: 编辑 `config.json`
3. 运行程序: `python main.py`
