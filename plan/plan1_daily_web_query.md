# 方案一：每日特勤处制造自动查询

## 目标

每天在自动制造前，爬取 orzice.com 的今日特勤处制造推荐，动态更新制造队列，确保始终制造当日利润最高的物品。

## 数据源分析

**orzice.com/v/rb** 页面提供：
- 特勤处四大台（技术中心/工作台/制药台/防具台）的**每日最优制造配方**
- 基于实时交易行价格计算的**利润排序**
- 数据每日更新

## 架构设计

### 1. 新增模块：`daily_fetcher.py`

独立于主循环的爬取模块，职责单一：

```
daily_fetcher.py
├── fetch_daily_recipes()      # 请求网页，解析今日配方
├── parse_recipes(html)        # 从 HTML 中提取四大台的推荐物品
├── update_user_config(recipes) # 将推荐物品写入 user_config.yaml
└── should_update_today()      # 检查今天是否已经更新过（避免重复请求）
```

### 2. 数据流

```
orzice.com ──HTTP GET──> daily_fetcher ──解析──> 今日配方 dict
                                                      │
                                                      ▼
                                              user_config.yaml
                                               (覆盖制造队列)
                                                      │
                                                      ▼
                                              main.py 主循环
                                              (照常读取配置制造)
```

### 3. 关键设计决策

| 决策点 | 方案 | 理由 |
|--------|------|------|
| 请求时机 | 每天首次运行 main.py 时 | 减少网络请求，避免运行中变更队列 |
| 更新策略 | 完全覆盖 user_config 中四大台的制造项 | 简单直接，用户可手动改回 |
| 失败处理 | 网络不可用则跳过，使用现有配置 | 不影响正常制造流程 |
| 缓存 | 记录上次更新日期，同一天不重复请求 | 避免浪费请求和被封 |

### 4. 解析策略

针对 orzice.com 页面结构，使用 `requests` + `BeautifulSoup` 或正则表达式提取：

- 定位四大台的 HTML 区块
- 提取每个台下推荐物品名称（中文）
- 映射到 `config.yaml` 中 `departments` 下已定义的物品名
- 选择利润最高的物品（或取推荐列表第一个）

### 5. 与主循环集成

在 `main()` 函数入口处增加：

```python
def main():
    # 新增：每天首次运行时更新制造队列
    try:
        from daily_fetcher import maybe_update_recipes
        maybe_update_recipes()
    except Exception as e:
        print(f"[WARN] 获取今日配方失败: {e}，将使用现有配置")
    
    # ... 原有主循环逻辑不变 ...
```

### 6. 依赖变更

新增依赖：
- `requests` — HTTP 请求
- `beautifulsoup4` — HTML 解析（或使用 `lxml` + XPath）

## 运行流程

```
main.py 启动
    │
    ├── 检查今天是否已经更新
    │     ├── 是 → 跳过，使用现有配置
    │     └── 否 → GET orzice.com/v/rb
    │               │
    │               ├── 成功 → 解析 HTML → 提取推荐物品
    │               │            │
    │               │            ├── 匹配 config.yaml 中存在的物品名
    │               │            └── 写入 user_config.yaml
    │               │
    │               └── 失败 → 打印警告，继续运行
    │
    └── 进入主循环（原有逻辑不变）
```

## 注意事项

1. **物品名匹配**：网站使用的物品名可能与 config.yaml 不完全一致，需要 fuzzy match（可复用现有的 `rapidfuzz`）
2. **请求频率**：每天仅一次请求，对网站无压力
3. **网络环境**：用户需要能访问 orzice.com，如无法访问则静默跳过
4. **对抗反爬**：目前 orzice.com 无明显反爬措施，如有必要可加 User-Agent 伪装
