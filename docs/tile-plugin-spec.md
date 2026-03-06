# Plugin 规范（beta1.0）

本文档说明 Project GIGDIS 的插件体系（磁贴插件 + 地图标记插件 + 主题插件）。

## 1. 总览

- 插件使用 JSON 文件。
- 目录按能力拆分：
  - `app/static/plugins/tiles/`：磁贴插件。
  - `app/static/plugins/map-markers/`：地图标记插件。
  - `app/static/plugins/themes/`：主题插件。
- `app/static/plugins/index.json` 为统一清单。

## 2. 目录结构

```text
app/static/plugins/
  ├─ index.json
  ├─ tiles/
  ├─ map-markers/
  └─ themes/
      └─ ocean-public.theme.json
```

## 3. 清单文件格式

```json
{
  "tiles": ["tiles/risk-summary.plugin.json"],
  "map_markers": [],
  "themes": ["themes/ocean-public.theme.json"]
}
```

## 4. 磁贴插件（type: metric/text/list）

沿用 alpha 版本字段：`id`、`type`、`title`、`valueTemplate`、`subTemplate`、`externalSources`。

## 5. 地图标记插件（type: map-marker）

沿用 alpha 版本字段：`id`、`type`、`title`、`markersPath`、`color`、`radiusBase`、`popupTemplate`。

## 6. 主题插件（type: theme）

```json
{
  "id": "oceanPublicTheme",
  "type": "theme",
  "title": { "zh": "海洋公测主题", "en": "Ocean public beta" },
  "backgroundImage": "https://...",
  "variables": {
    "--bg": "#020617",
    "--text": "#e0f2fe",
    "--button-bg": "#0ea5e9"
  }
}
```

字段说明：

- `backgroundImage`：可选，页面背景图 URL。
- `variables`：可选，CSS 变量覆盖。
- 支持覆盖按钮、卡片、标签、文本、边框等配色。

## 7. 安装步骤

1. 在对应目录新增插件 JSON。
2. 在 `app/static/plugins/index.json` 中登记路径。
3. 刷新页面：
   - 磁贴插件在“磁贴中心”可见；
   - 主题插件可在“主题插件”下拉中切换；
   - 地图标记插件自动加载。

## 8. 降级策略

- 文件读取失败或 JSON 非法：跳过该插件。
- 缺失 `id`/`type`：跳过该插件。
- 主题插件加载失败时回退默认主题。
