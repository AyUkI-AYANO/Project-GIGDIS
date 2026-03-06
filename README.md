# Project GIGDIS (alpha0.2.3)

Project GIGDIS 是一个全球热点地图系统的 alpha0.2.3 版本。

## 本版本新增能力

- 新增基础多语言支持：中文、英语、俄语、法语、德语。
- 界面文案支持多语言切换，筛选器、统计卡片、提示文案同步翻译。
- 新闻条目支持基础翻译（话题标签翻译 + 常用标题短语映射）。
- 数据概览新增“全球紧张度”（0-100）：依据军事类新闻数量与热度综合计算。
- 鼠标悬浮在“全球紧张度”指标时，显示：
  - 主要热点区域（军事热点国家）；
  - 每小时紧张度变化折线图（最近 24 次刷新数据）。

## Update Log

### alpha0.2.3
- 服务端与页面版本号同步为 `0.2.3`。
- 新增 `lang` 参数（`zh/en/ru/fr/de`）驱动 API 返回多语言字段。
- `hotspots` 接口新增 `global_tension` 指标，包含 `score`、`top_regions`、`hourly_trend`。
- 右侧数据概览新增全球紧张度卡片及悬浮详情。
- 页面新增语言切换器，新闻条目/话题标签/界面文案支持多语言。

### alpha0.2.2
- 增加 CNN World 信息源。
- 服务端抓取上限提升为每源 40 条。
- 服务端与页面版本号同步为 `0.2.2`。
- 前端筛选交互改为实时自动生效，移除“应用筛选”按钮。
- 话题筛选由复选框切换为按钮式交互，使用光效色调区分选中状态。

## 运行方式（无第三方依赖）

```bash
python app/main.py
```

打开：`http://localhost:8000`

## API

- `GET /api/v1/health`：服务健康、版本、可用类型。
- `GET /api/v1/hotspots?topics=technology,military&lang=en`：按类型筛选地图热点数据，并返回全球紧张度。
- `GET /api/v1/panel?viewport_country=China&topics=politics,technology&lang=fr`：按国家+类型+语言筛选信息栏内容。
