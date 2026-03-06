# Plugin 规范（alpha0.4.0）

本文档说明 Project GIGDIS 的插件体系（磁贴插件 + 地图标记插件）。

## 1. 总览

- 插件使用 JSON 文件。
- 目录按能力拆分：
  - `app/static/plugins/tiles/`：磁贴插件。
  - `app/static/plugins/map-markers/`：地图标记插件。
- `app/static/plugins/index.json` 为统一清单。
- 前端启动时会加载两类插件：
  - 磁贴插件渲染到“磁贴中心”。
  - 地图标记插件渲染到地图图层。

## 2. 目录结构

```text
app/static/plugins/
  ├─ index.json
  ├─ tiles/
  │   ├─ risk-summary.plugin.json
  │   └─ web-quote.plugin.json
  └─ map-markers/
      └─ conflict-focus.plugin.json
```

## 3. 清单文件格式

```json
{
  "tiles": [
    "tiles/risk-summary.plugin.json"
  ],
  "map_markers": [
    "map-markers/conflict-focus.plugin.json"
  ]
}
```

要求：

- `tiles`、`map_markers` 都应为数组（可为空）。
- 每一项是相对 `app/static/plugins/` 的路径。

## 4. 磁贴插件（type: metric/text/list）

```json
{
  "id": "riskSummary",
  "type": "metric",
  "title": { "zh": "风险摘要", "en": "Risk summary" },
  "valueTemplate": { "zh": "紧张度 {tensionScore} 分", "en": "Tension {tensionScore} pts" },
  "subTemplate": { "zh": "热度变化 {heatDelta}", "en": "Heat delta {heatDelta}" },
  "externalSources": []
}
```

## 5. 地图标记插件（type: map-marker）

```json
{
  "id": "conflictFocus",
  "type": "map-marker",
  "title": { "zh": "冲突地区标记", "en": "Conflict zone marker" },
  "markersPath": "hotspots.conflict_zones",
  "color": "#f43f5e",
  "radiusBase": 7,
  "popupTemplate": {
    "zh": "<b>{country}</b><br/>冲突事件: {event_count} 条<br/>强度: {intensity} 分",
    "en": "<b>{country}</b><br/>Conflict events: {event_count}<br/>Intensity: {intensity}"
  }
}
```

字段说明：

- `markersPath`：从上下文提取标记数组（默认 `hotspots.conflict_zones`）。
- `color`：圆点边框/填充色。
- `radiusBase`：基础半径，最终会按 `intensity` 动态增大。
- `popupTemplate`：点击标记弹窗模板（支持多语言）。

## 6. 模板变量（节选）

- `{tensionScore}`、`{tensionDelta}`、`{heatDelta}`
- `{countries}`、`{events}`
- `{activeTopics}`、`{selectedCountry}`
- `{panel.*}`、`{hotspots.*}`
- 地图标记场景常用：`{country}`、`{event_count}`、`{intensity}`、`{headline}`

## 7. 安装步骤

1. 在对应目录新增插件 JSON。
2. 在 `app/static/plugins/index.json` 中登记路径。
3. 刷新页面验证：
   - 磁贴插件在“磁贴中心”可见。
   - 地图标记插件在地图上可见。

## 8. 降级策略

- 文件读取失败或 JSON 不合法：跳过该插件。
- 缺失 `id`/`type`：跳过该插件。
- 外部变量请求失败：变量降级为空字符串，不阻塞整体渲染。
