# Project GIGDIS (alpha0.1.1)

Project GIGDIS 是一个全球热点地图系统的 alpha0.1.1 版本。

## 本版本新增能力

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
