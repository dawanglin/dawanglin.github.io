# 崇州市区大众点评商铺爬虫（快速部署版）

> 这是一个“开箱可跑”的最小实现：抓取频道列表页中的店铺信息，过滤出崇州市区相关店铺，保存到 SQLite + CSV。

## 1) 快速启动

```bash
cd dianping_chongzhou_spider
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.env .env
python spider.py
```

## 2) 输出位置

- SQLite：`./data/chongzhou_shops.db`
- CSV：`./data/chongzhou_shops.csv`

## 3) 配置说明（`.env`）

- `CHANNEL_URLS`：多个频道入口用 `;` 分隔。
- `MAX_PAGES_PER_CHANNEL`：每个频道抓取页数。
- `DIANPING_COOKIE`：若被风控，填浏览器登录态 Cookie。
- `MIN_SLEEP_SECONDS` / `MAX_SLEEP_SECONDS`：请求间隔抖动。

## 4) 重要说明

1. 大众点评页面结构和反爬策略可能变化，若选择器失效需更新 `parse_shops`。
2. 本实现默认只做列表页采集（更稳定），暂不抓取评论。
3. 请确保采集行为符合目标站点服务条款与相关法律法规。
