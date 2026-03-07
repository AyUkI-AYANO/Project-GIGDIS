# Plugin 规范（beta2.2）

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


## 9. 模板函数调用（beta2.2 新增）

磁贴插件 `valueTemplate/subTemplate` 现支持两种占位符：

- 路径变量：`{tensionScore}`、`{panel.global_top.0.country}`
- 函数调用：`{fixed:globalEconomy|2}`（函数名后接 `:`，参数以 `|` 分隔）

### 9.1 语法

```text
{functionName:arg1|arg2|...}
```

参数解析规则：

- 如果参数可在上下文命中同名路径（如 `globalEconomy`），则取上下文值。
- 否则按字面量处理（可使用 `'文本'` 或 `"文本"` 包裹）。

### 9.2 内置函数

- `upper(value)`：转大写。
- `lower(value)`：转小写。
- `fixed(value, digits=2)`：数字保留指定位数。
- `percent(value, digits=2)`：格式化百分比。
- `add(a,b,...)`：求和。
- `multiply(a,b,...)`：连乘。
- `join(separator,v1,v2,...)`：按分隔符拼接。
- `default(primary,fallback)`：空值回退。
- `trendSign(value)`：正数自动补 `+` 号。

### 9.3 示例

```json
{
  "id": "economyPulse",
  "type": "metric",
  "title": { "zh": "经济脉冲", "en": "Economy pulse" },
  "functions": ["fixed", "trendSign", "join"],
  "valueTemplate": {
    "zh": "指数 {fixed:globalEconomy|2}（{trendSign:globalEconomyDelta}%）",
    "en": "Index {fixed:globalEconomy|2} ({trendSign:globalEconomyDelta}%)"
  },
  "subTemplate": {
    "zh": "筛选：{default:activeTopics|'全部'}",
    "en": "Topics: {default:activeTopics|'All'}"
  }
}
```

> 可选字段 `functions` 仅用于元数据展示，运行时真正可调用函数以系统内置函数为准。
