# Plugin 规范（beta4.4）

本文档说明 Project GIGDIS 的插件体系（磁贴插件 + 主题插件）。

## 1. 总览

- 插件使用 JSON 文件。
- 目录按能力拆分：
  - `app/static/plugins/tiles/`：磁贴插件。
  - `app/static/plugins/themes/`：主题插件。
- `app/static/plugins/index.json` 为统一清单。

## 2. 目录结构

```text
app/static/plugins/
  ├─ index.json
  ├─ tiles/
  └─ themes/
      └─ ocean-public.theme.json
```

## 3. 清单文件格式

```json
{
  "tiles": ["tiles/risk-summary.plugin.json"],
  "themes": ["themes/ocean-public.theme.json"]
}
```

## 4. 磁贴插件（type: metric/text/list）

沿用 alpha 版本字段：`id`、`type`、`title`、`valueTemplate`、`subTemplate`、`externalSources`。

## 5. 主题插件（type: theme）

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

## 6. 安装步骤

1. 在对应目录新增插件 JSON。
2. 在 `app/static/plugins/index.json` 中登记路径。
3. 刷新页面：
   - 磁贴插件在“磁贴中心”可见；
   - 主题插件可在“主题插件”下拉中切换。

## 7. 降级策略

- 文件读取失败或 JSON 非法：跳过该插件。
- 缺失 `id`/`type`：跳过该插件。
- 主题插件加载失败时回退默认主题。

## 8. 模板函数调用（beta4.4）

磁贴插件 `valueTemplate/subTemplate` 支持两种占位符：

- 路径变量：`{tensionScore}`、`{panel.global_top.0.country}`
- 函数调用：`{fixed:globalEconomy|2}`（函数名后接 `:`，参数以 `|` 分隔）

### 8.1 语法

```text
{functionName:arg1|arg2|...}
```

### 8.2 内置函数

- `upper(value)`、`lower(value)`
- `fixed(value, digits=2)`、`percent(value, digits=2)`
- `add(a,b,...)`、`multiply(a,b,...)`
- `join(separator,v1,v2,...)`、`default(primary,fallback)`
- `trendSign(value)`
- `length(value)`：返回字符串/数组/对象长度。
- `slice(value,start,end)`：字符串切片。
- `replace(value,from,to)`：字符串替换。
- `json(value)`：对象转 JSON 字符串。
- `pick(value,path)`：提取对象子路径。
- `truncate(value,maxLen)`：超长文本截断。

## 9. externalSources（beta4.4 扩展）

`externalSources` 的每个条目支持：

- `key`：注入模板上下文字段名。
- `url`：远程接口 URL（支持模板变量）。
- `sourceApi`：信息源桥接字段（如 `Reuters`），会自动调用 `/api/v1/source-content?source=Reuters`。
- `method` / `headers` / `body`：自定义请求方式与请求体。
- `responseType`：`json` / `text` / `html`。
- `path`：对 JSON（或处理后的内容）做路径提取。
- `regex` / `regexFlags` / `regexGroup`：正则抽取。
- `selector` / `attr`：当 `responseType=html` 时可用 CSS 选择器提取内容。
- `ttlSeconds`：缓存秒数。

> `url` 与 `sourceApi` 二选一即可；优先使用 `sourceApi` 访问系统内信息源聚合接口。
