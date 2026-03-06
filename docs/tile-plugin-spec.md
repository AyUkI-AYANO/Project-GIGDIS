# Tile Plugin 规范（alpha0.3.0）

本文档说明如何为 Project GIGDIS 编写并安装“磁贴插件”。

## 1. 总览

- 插件以 **JSON 文件** 存放在 `app/static/plugins/`。
- `index.json` 是清单文件，列出可加载插件文件名。
- 前端启动后会读取清单并逐个加载插件，成功后自动出现在“磁贴列表选择”中。

## 2. 目录结构

```text
app/static/plugins/
  ├─ index.json
  ├─ xxx.plugin.json
  └─ yyy.plugin.json
```

## 3. 清单文件格式

`app/static/plugins/index.json`:

```json
{
  "plugins": [
    "risk-summary.plugin.json",
    "my-custom.plugin.json"
  ]
}
```

要求：

- `plugins` 必须是数组。
- 每项是插件文件名（相对 `app/static/plugins/`）。

## 4. 单个插件格式

```json
{
  "id": "myPluginId",
  "type": "metric",
  "title": {
    "zh": "我的插件",
    "en": "My plugin"
  },
  "valueTemplate": {
    "zh": "紧张度 {tensionScore} 分",
    "en": "Tension {tensionScore} pts"
  },
  "subTemplate": {
    "zh": "热度变化 {heatDelta} /h",
    "en": "Heat delta {heatDelta} /h"
  }
}
```

### 必填字段

- `id`: 字符串，插件唯一 ID。
- `type`: 字符串，目前支持：
  - `metric`
  - `text`
  - `list`

> 当前版本 `type` 主要用于样式语义，渲染逻辑都基于模板字符串。

### 可选字段

- `title`: 多语言标题对象，建议至少提供 `zh` 和 `en`。
- `valueTemplate`: 磁贴主值模板。
- `subTemplate`: 磁贴副标题模板。

## 5. 支持的模板变量

模板中可以使用 `{变量名}`，渲染时会替换为当前上下文值。当前支持：

- `{tensionScore}`：全球紧张度分值
- `{tensionDelta}`：紧张度较上次刷新变化
- `{heatDelta}`：平均热度较上次刷新变化
- `{countries}`：国家数量
- `{events}`：新闻总数
- `{activeTopics}`：当前主题文本

示例：

- `"valueTemplate": {"zh": "国家 {countries}"}`
- `"subTemplate": {"zh": "主题：{activeTopics}"}`

## 6. 编写建议

- `id` 使用小驼峰或短横线，避免空格。
- 每个插件只表达一个清晰指标。
- 文案建议简短，避免撑高磁贴高度。
- 多语言缺失时会回退到 `zh` 或 `en`。

## 7. 安装步骤

1. 在 `app/static/plugins/` 新建 `your.plugin.json`。
2. 在 `index.json` 的 `plugins` 数组加入该文件名。
3. 重新刷新页面。
4. 打开“磁贴中心” → “展开磁贴列表选择”，勾选你的插件磁贴。

## 8. 错误处理

- 插件文件读取失败：该插件被跳过，不影响其他磁贴。
- JSON 格式错误：该插件被跳过。
- 缺少 `id` 或 `type`：该插件被跳过。

