# Project GIGDIS (alpha0.2.0)

Project GIGDIS 是一个全球热点地图系统的 alpha0.2.0 版本。

## 本版本新增能力

- 视觉升级：新增品牌 Logo，统一头部识别风格。
- 布局升级：地图区域固定展示，右侧信息栏改为独立滚动，避免长列表影响地图浏览。
- 地图表达升级：国家圆点的大小与颜色同时按“事件数量 + 热度”动态映射，信息密度和风险等级更直观。
- README 增补 Update Log，便于持续追踪版本迭代。

## Update Log

### alpha0.2.0
- 新增头部 Logo，并同步页面版本标识。
- 拆分地图与右侧信息栏滚动行为：右栏可独立滚动，地图保持稳定。
- 优化热点圆点渲染逻辑：
  - 圆点大小按国家事件数占比 + 热度占比综合计算。
  - 圆点颜色按热度梯度动态变化（冷色到暖色）。
- 服务端版本号同步为 `0.2.0`。

### alpha0.1.2
- 每 15 分钟自动抓取国际 RSS 热点新闻。
- 新闻类型扩展到：科技、军事、政治、科学、灾害、公共卫生、外交、经济等。
- 地图页面新增筛选菜单，用户可选择想看的新闻类型，并实时作用于地图与信息栏。
- 程序启动后会在 PowerShell/终端显示当前端口，并提示可通过 `Ctrl+C` 结束进程。

## 运行方式（无第三方依赖）

```bash
python app/main.py
```

打开：`http://localhost:8000`

## API

- `GET /api/v1/health`：服务健康、版本、可用类型。
- `GET /api/v1/hotspots?topics=technology,military`：按类型筛选地图热点数据。
- `GET /api/v1/panel?viewport_country=China&topics=politics,technology`：按国家+类型筛选信息栏内容。
