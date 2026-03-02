# A股选股平台 — 技术方案

## 功能需求

1. 输入A股个股名称（如"洲际油气"）
2. 自动拆字（洲、际、油、气）作为检索标签
3. 拉取该股所属概念/板块作为检索标签
4. 交易所筛选（主板、创业板、科创板、北交所）
5. 勾选组合条件 → 搜索匹配的所有个股
6. 结果展示：股票代码、名称、现价、流通市值、所属概念、涨停标记

## 技术栈

| 层 | 选型 | 理由 |
|----|------|------|
| 后端 | Python + FastAPI | 轻量、AKShare 生态、跨平台 |
| 前端 | 内嵌 HTML + Vue 3 (CDN) | 无需 Node 构建，单文件 |
| 数据 | SQLite | 零配置、Windows/Mac 都能跑 |
| 数据源 | AKShare | 开源免费，覆盖A股行情+板块概念 |

## 项目结构

```
a-stock-screener/
├── app.py              # FastAPI 主程序 + API
├── data.py             # AKShare 数据采集 + SQLite 写入
├── db.py               # 数据库初始化 + 查询封装
├── templates/
│   └── index.html      # 前端页面（Vue 3 CDN）
├── stock.db            # SQLite（自动生成）
├── requirements.txt
└── README.md           # 中文使用说明
```

## 数据库（3张表）

```sql
stocks (code PK, name, market, price, market_cap, is_limit_up, updated_at)
concepts (id PK, name UNIQUE)
stock_concepts (stock_code, concept_id) -- 多对多
```

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 主页面 |
| GET | `/api/search?name=洲际油气` | 拆字 + 返回概念标签 |
| POST | `/api/match` | 勾选条件 → 返回匹配股票 |
| POST | `/api/refresh` | 手动刷新数据 |

## 交易所判断

- 60xxxx → 主板（沪）
- 00xxxx → 主板（深）
- 30xxxx → 创业板
- 68xxxx → 科创板
- 8x/4x → 北交所

## 匹配逻辑

- 字匹配：OR（包含任一字）或 AND（包含所有字），用户可选
- 概念匹配：股票属于勾选的任一概念
- 交易所：勾选的市场
- 三个条件取交集
- 排序：流通市值 / 涨停优先

## 跨平台

- Python 3.9+，SQLite 内置，无 Node 依赖
- README 提供 Windows + Mac 安装步骤

## 依赖

```
fastapi, uvicorn, akshare, jinja2
```

## 启动

```bash
pip install -r requirements.txt
python data.py    # 首次拉数据（~5-10分钟，概念板块多）
python app.py     # http://localhost:8000
```

## 注意

- AKShare 底层抓东方财富，非交易时间也能拉（略有延迟）
- 概念板块 ~500个，首次拉取需要耐心
- 后续可加：定时自动更新、历史涨停、CSV导出
