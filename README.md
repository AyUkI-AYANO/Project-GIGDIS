# Project GIGDIS (alpha0.1.0)

Project GIGDIS 是一个全球热点地图系统的 alpha0.1.0 版本，已实现基础闭环：

- 每 15 分钟自动抓取国际 RSS 热点新闻。
- 按国家进行关键词地理映射与热点评分。
- 提供热点 API 与自适应信息栏 API。
- 在地图页面展示国家热点点位，并根据点击国家动态更新信息栏内容。

## 运行方式（无第三方依赖）

```bash
python app/main.py
```

打开：`http://localhost:8000`

## API

- `GET /api/v1/health`：服务健康与刷新状态
- `GET /api/v1/hotspots`：地图热点数据（按国家聚合）
- `GET /api/v1/panel?viewport_country=China`：信息栏推荐内容
