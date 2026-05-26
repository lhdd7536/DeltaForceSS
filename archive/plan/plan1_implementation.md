# 方案一实施文档：每日特勤处制造自动查询

## 一、新增依赖

向 `requirements.txt` 追加：

```
requests==2.32.3
beautifulsoup4==4.13.4
```

## 二、新增文件：`daily_fetcher.py`

### 完整代码

```python
"""
每日从 orzice.com/v/rb 抓取今日特勤处制造推荐，
更新 user_config.yaml 中的制造队列。
"""

import requests
from bs4 import BeautifulSoup
import yaml
import re
from datetime import date, datetime
from rapidfuzz import fuzz
import os

# ============================================================
# 配置常量
# ============================================================

ORZICE_URL = "https://orzice.com/v/rb"
CACHE_FILE = "data/last_update_date.txt"  # 记录上次更新日期

# 四大台在页面中对应的 HTML 标识关键词
# 用于定位每个制造台的推荐区块
DEPARTMENT_KEYWORDS = {
    "tech":    "技术中心",
    "work":    "工作台",
    "medical": "制药台",
    "armor":   "防具台",
}

# ============================================================
# 日期缓存
# ============================================================

def _get_cache_dir() -> str:
    """确保 data/ 目录存在并返回路径"""
    os.makedirs("data", exist_ok=True)
    return "data"


def should_update_today() -> bool:
    """
    检查今天是否已经更新过。
    返回 True 表示需要更新（尚未更新），False 表示今天已更新过。
    """
    cache_file = os.path.join(_get_cache_dir(), "last_update_date.txt")
    if not os.path.exists(cache_file):
        return True
    with open(cache_file, "r", encoding="utf-8") as f:
        saved = f.read().strip()
    return saved != str(date.today())


def mark_updated_today():
    """记录今天已更新。"""
    cache_file = os.path.join(_get_cache_dir(), "last_update_date.txt")
    with open(cache_file, "w", encoding="utf-8") as f:
        f.write(str(date.today()))


# ============================================================
# 网络请求
# ============================================================

def fetch_page_html(url: str = ORZICE_URL) -> str | None:
    """
    请求页面，返回 HTML 文本。
    失败时返回 None，由调用方处理。
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        return resp.text
    except requests.RequestException as e:
        print(f"[daily_fetcher] 请求失败: {e}")
        return None


# ============================================================
# HTML 解析 — 需要根据 orzice.com/v/rb 实际页面结构调整
# ============================================================

def parse_recipes(html: str) -> dict[str, list[str]]:
    """
    从 HTML 中提取四大台的推荐物品名称。

    返回格式:
    {
        "tech":    ["M249轻机枪", "先进热融合全息瞄准镜"],
        "work":    ["9x39mm BP", ...],
        "medical": ["战地医疗箱", ...],
        "armor":   ["精英防弹背心", ...],
    }

    实现策略（按优先级尝试，直到一种方法成功）:
      策略 A: 查找页面中 class/id 包含特定关键词的容器，提取其中物品列表
      策略 B: 通过页面文本特征（"技术中心" 等标题后的列表项）正则提取
      策略 C: 查找所有表格行，按列内容归类

    注意: orzice.com 页面结构可能更新，以下实现基于常见模式，
          实际部署时需根据页面真实结构调整选择器。
    """
    soup = BeautifulSoup(html, "html.parser")
    recipes: dict[str, list[str]] = {dep: [] for dep in DEPARTMENT_KEYWORDS}

    # ---------- 策略 A: 结构化容器提取 ----------
    # 假设每个制造台在一个独立的 panel/card 容器中
    # 容器标题包含 "技术中心"/"工作台"/"制药台"/"防具台"
    panels = soup.find_all(["div", "section", "article"],
                           class_=re.compile(r"(panel|card|section|block|item)", re.I))

    for panel in panels:
        panel_text = panel.get_text()
        matched_dep = None
        for dep_key, keyword in DEPARTMENT_KEYWORDS.items():
            if keyword in panel_text:
                matched_dep = dep_key
                break
        if matched_dep is None:
            continue

        # 从面板内提取所有列表项 / 链接 / 文本行
        items = []
        # 尝试 <li> 标签
        for li in panel.find_all("li"):
            text = li.get_text(strip=True)
            if text and len(text) >= 2:
                items.append(text)
        # 尝试 <a> 标签
        if not items:
            for a in panel.find_all("a"):
                text = a.get_text(strip=True)
                if text and len(text) >= 2:
                    items.append(text)
        # 尝试 <p> / <span> 文本行
        if not items:
            for tag in panel.find_all(["p", "span", "div"]):
                text = tag.get_text(strip=True)
                if text and len(text) >= 2:
                    items.append(text)

        recipes[matched_dep] = items

    # ---------- 策略 B: 所有策略都失败后的正则兜底 ----------
    if not any(recipes.values()):
        recipes = _parse_by_regex(html)

    return recipes


def _parse_by_regex(html: str) -> dict[str, list[str]]:
    """
    正则表达式兜底策略:
    按制造台关键词分段，提取每个段落后紧邻的中文/物品名列表。
    """
    recipes: dict[str, list[str]] = {dep: [] for dep in DEPARTMENT_KEYWORDS}

    for dep_key, keyword in DEPARTMENT_KEYWORDS.items():
        # 在 keyword 之后查找物品名（中文 + 字母 + 数字 + 特殊字符 的组合）
        pattern = re.compile(
            re.escape(keyword) + r".*?(?=" +
            "|".join(re.escape(kw) for k in DEPARTMENT_KEYWORDS.values()) +
            "|$)",
            re.DOTALL
        )
        match = pattern.search(html)
        if not match:
            continue
        section = match.group()

        # 提取疑似物品名的行（去掉空白行、纯数字行、过短行）
        lines = section.split("\n")
        for line in lines:
            line = line.strip()
            # 过滤: 至少 2 个字符，不能全是标点/数字
            if len(line) < 2:
                continue
            if re.match(r"^[\d\s:：\-—/\\|]+$", line):
                continue
            # 过滤制造台标题头关键词
            if line in DEPARTMENT_KEYWORDS.values():
                continue
            recipes[dep_key].append(line)

    return recipes


# ============================================================
# 物品名匹配 — 与 config.yaml 对齐
# ============================================================

def load_config_departments(config_path: str = "config.yaml") -> dict[str, set[str]]:
    """
    读取 config.yaml 中所有部门下的物品名，返回:
    { "tech": {"M249轻机枪", "先进热融合全息瞄准镜", ...}, ... }
    """
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    result: dict[str, set[str]] = {}
    for dep, categories in cfg.get("departments", {}).items():
        names: set[str] = set()
        for category_items in categories.values():
            for item in category_items:
                names.add(item)
        result[dep] = names
    return result


def match_site_to_config(
    site_recipes: dict[str, list[str]],
    config_items: dict[str, set[str]],
    threshold: int = 60,
) -> dict[str, str | None]:
    """
    将网站推荐物品名与 config.yaml 中已定义的物品名做 fuzzy match。
    对每个部门，选取匹配分数最高的物品作为制造目标。

    返回:
    { "tech": "M249轻机枪", "work": "9x39mm BP", ... }
    如果某个部门没有匹配到任何物品，值为 None（维持原有配置）。
    """
    result: dict[str, str | None] = {}

    for dep in DEPARTMENT_KEYWORDS:
        candidates = site_recipes.get(dep, [])
        known_items = config_items.get(dep, set())
        if not candidates or not known_items:
            result[dep] = None
            continue

        best_item = None
        best_score = 0
        for site_name in candidates:
            for known_name in known_items:
                score = fuzz.ratio(site_name, known_name)
                if score > best_score:
                    best_score = score
                    best_item = known_name

        if best_score >= threshold:
            result[dep] = best_item
            print(f"[daily_fetcher] {dep}: 网站推荐 \"{candidates[0]}\" → 匹配 \"{best_item}\" (score={best_score})")
        else:
            result[dep] = None
            print(f"[daily_fetcher] {dep}: 未匹配到合适的物品 (最佳: {best_item}, score={best_score})")

    return result


# ============================================================
# 写入 user_config.yaml
# ============================================================

def update_user_config(recipes: dict[str, str | None]):
    """
    将匹配到的制造目标写入 user_config.yaml。
    每个部门写入一个 [物品名, -1]（表示无限制造）。
    如果 recipes[dep] 为 None，则不清空该部门（维持用户原有配置）。
    """
    user_config_path = "user_config.yaml"

    # 用 ruamel.yaml 保持注释和格式（与 main.py 一致）
    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedSeq

    yaml_loader = YAML()
    yaml_loader.indent(mapping=2, sequence=4, offset=2)
    yaml_loader.preserve_quotes = True
    yaml_loader.width = 120

    with open(user_config_path, "r", encoding="utf-8") as f:
        user_cfg = yaml_loader.load(f)

    changed = False
    for dep, item_name in recipes.items():
        if item_name is None:
            continue  # 维持原配置不变
        # 如果已经是一样的物品，跳过写入
        current = user_cfg.get(dep)
        if current and len(current) > 0 and current[0][0] == item_name:
            print(f"[daily_fetcher] {dep}: 已经是 \"{item_name}\"，无需更新")
            continue

        new_entry = CommentedSeq([item_name, -1])
        new_entry.fa.set_flow_style()
        user_cfg[dep] = [new_entry]
        changed = True
        print(f"[daily_fetcher] {dep}: 更新为 \"{item_name}\"")

    if changed:
        with open(user_config_path, "w", encoding="utf-8") as f:
            yaml_loader.dump(user_cfg, f)
        print("[daily_fetcher] user_config.yaml 已更新")
    else:
        print("[daily_fetcher] 无变更")


# ============================================================
# 对外入口
# ============================================================

def maybe_update_recipes():
    """
    供 main.py 调用的唯一入口。
    检查今天是否已更新 → 抓取页面 → 解析 → 匹配 → 写入。
    任何步骤失败都不影响后续主循环。
    """
    if not should_update_today():
        print("[daily_fetcher] 今天已更新，跳过")
        return

    print("[daily_fetcher] 正在获取今日特勤处制造推荐...")
    html = fetch_page_html()
    if html is None:
        print("[daily_fetcher] 跳过本次更新")
        return

    site_recipes = parse_recipes(html)
    if not any(site_recipes.values()):
        print("[daily_fetcher] 未解析到任何推荐物品，跳过更新")
        return

    config_items = load_config_departments()
    matched = match_site_to_config(site_recipes, config_items)

    if not any(matched.values()):
        print("[daily_fetcher] 没有任何部门匹配到可制造的物品，跳过更新")
        return

    update_user_config(matched)
    mark_updated_today()
    print("[daily_fetcher] 今日配方更新完成")


# ============================================================
# 独立测试入口
# ============================================================

if __name__ == "__main__":
    maybe_update_recipes()
```

## 三、修改 `main.py`

### 修改 1：文件头部新增 import（第 21 行后）

在第 21 行 `import ctypes` 之后插入：

```python
try:
    from daily_fetcher import maybe_update_recipes
    _HAS_FETCHER = True
except ImportError:
    _HAS_FETCHER = False
```

这样即使 `daily_fetcher.py` 或其依赖未安装，也不会阻塞主程序启动。

### 修改 2：`main()` 函数入口处新增（第 610 行，`print('###### 程序初始化 ######')` 之后）

在 `print('###### 程序初始化 ######')` 之后、`background_mode = user_config['background_mode']` 之前插入：

```python
    # 每天首次运行时，从 orzice.com 获取今日制造推荐
    if _HAS_FETCHER:
        try:
            maybe_update_recipes()
        except Exception as e:
            print(f"[WARN] 获取今日配方失败: {e}，将使用现有配置继续")
    else:
        print("[INFO] daily_fetcher 未就绪（缺少依赖？），跳过自动更新")
```

### 修改后的 `main()` 函数对照

```python
def main():
    print('###### 程序初始化 ######')
    # ==== 新增开始 ====
    if _HAS_FETCHER:
        try:
            maybe_update_recipes()
        except Exception as e:
            print(f"[WARN] 获取今日配方失败: {e}，将使用现有配置继续")
    else:
        print("[INFO] daily_fetcher 未就绪（缺少依赖？），跳过自动更新")
    # ==== 新增结束 ====
    background_mode = user_config['background_mode']
    hwnd = win32gui.FindWindow('UnrealWindow', '三角洲行动  ')
    # ... 后续代码不变 ...
```

## 四、测试方案

### 4.1 单元测试文件 `test_daily_fetcher.py`

```python
"""
测试 daily_fetcher 各模块。
运行: python test_daily_fetcher.py
"""

import os
import sys
import tempfile
from datetime import date
from unittest.mock import Mock, patch

# 将被测试模块所在目录加入路径
sys.path.insert(0, os.path.dirname(__file__))

from daily_fetcher import (
    should_update_today,
    mark_updated_today,
    fetch_page_html,
    parse_recipes,
    match_site_to_config,
    load_config_departments,
    update_user_config,
    maybe_update_recipes,
)
import yaml


def reset_date_cache():
    """清理日期缓存文件，使 should_update_today() 返回 True"""
    cache = "data/last_update_date.txt"
    if os.path.exists(cache):
        os.remove(cache)


# ---------- 测试 1: 日期缓存 ----------

def test_date_cache():
    """验证日期缓存逻辑"""
    reset_date_cache()
    assert should_update_today() is True, "无缓存文件时应返回 True"

    mark_updated_today()
    assert should_update_today() is False, "今天已标记，应返回 False"

    # 模拟缓存文件被篡改为昨天
    cache = "data/last_update_date.txt"
    from datetime import timedelta
    yesterday = date.today() - timedelta(days=1)
    with open(cache, "w") as f:
        f.write(str(yesterday))
    assert should_update_today() is True, "昨天日期应触发更新"

    reset_date_cache()


# ---------- 测试 2: 网络请求 ----------

def test_fetch_page_html():
    """验证网络请求函数（需要联网）"""
    html = fetch_page_html()
    if html is None:
        print("[SKIP] 网络不可用，跳过 fetch 测试")
        return
    assert len(html) > 100, f"返回内容太短: {len(html)} chars"
    assert "技术中心" in html or "特勤处" in html, "页面应包含制造相关文本"


# ---------- 测试 3: HTML 解析 ----------

def test_parse_recipes_with_mock():
    """使用模拟 HTML 测试解析逻辑"""
    mock_html = """
    <html>
    <body>
        <div class="panel">
            <h2>技术中心</h2>
            <ul>
                <li>M249轻机枪</li>
                <li>先进热融合全息瞄准镜</li>
            </ul>
        </div>
        <div class="panel">
            <h2>工作台</h2>
            <ul>
                <li>9x39mm BP</li>
            </ul>
        </div>
        <div class="panel">
            <h2>制药台</h2>
            <ul>
                <li>战地医疗箱</li>
            </ul>
        </div>
        <div class="panel">
            <h2>防具台</h2>
            <ul>
                <li>精英防弹背心</li>
            </ul>
        </div>
    </body>
    </html>
    """
    result = parse_recipes(mock_html)
    assert "tech" in result
    assert "M249轻机枪" in result["tech"]
    assert "战地医疗箱" in result["medical"]
    assert "精英防弹背心" in result["armor"]


def test_parse_recipes_real():
    """使用 orzice.com 真实页面数据测试解析（需要联网）"""
    html = fetch_page_html()
    if html is None:
        print("[SKIP] 网络不可用")
        return
    result = parse_recipes(html)
    for dep in ["tech", "work", "medical", "armor"]:
        print(f"  {dep}: {result.get(dep, [])}")
    # 至少解析出一些内容
    total = sum(len(v) for v in result.values())
    assert total > 0, f"应该至少解析出一些物品，但得到: {result}"


# ---------- 测试 4: 物品名匹配 ----------

def test_match_site_to_config():
    """验证 fuzzy match 逻辑"""
    # 使用 config.yaml 真实数据
    config_items = load_config_departments()

    # 模拟网站返回的推荐物品
    site_recipes = {
        "tech":    ["M249轻机枪", "PKM通用机枪"],
        "work":    ["9x39mm BP"],
        "medical": ["战地医疗箱"],
        "armor":   ["精英防弹背心"],
    }

    result = match_site_to_config(site_recipes, config_items, threshold=60)
    assert result["tech"] == "M249轻机枪"
    assert result["work"] == "9x39mm BP"
    assert result["medical"] == "战地医疗箱"
    assert result["armor"] == "精英防弹背心"


def test_match_site_to_config_fuzzy():
    """验证网站使用近似名时的匹配能力"""
    config_items = load_config_departments()
    site_recipes = {
        "tech":    ["M249机枪", "M4A1步"],        # 近似名
        "work":    ["9x39mmBP"],                  # 缺少空格
    }
    result = match_site_to_config(site_recipes, config_items, threshold=50)
    assert result["tech"] is not None, "即使名称不完全一致也应匹配到"


def test_match_site_to_config_low_score():
    """验证分数过低时不会误匹配"""
    config_items = {
        "tech": {"M249轻机枪", "PKM通用机枪"},
    }
    site_recipes = {
        "tech": ["不锈钢脸盆"],
    }
    result = match_site_to_config(site_recipes, config_items, threshold=60)
    assert result["tech"] is None, "完全不相关的物品不应匹配"


# ---------- 测试 5: 写入 user_config ----------

def test_update_user_config():
    """验证写入 user_config.yaml 的正确性"""
    # 备份原始 user_config.yaml
    orig = "user_config.yaml"
    backup = "user_config.yaml.bak"
    if os.path.exists(orig):
        os.rename(orig, backup)

    try:
        # 创建一个测试用 user_config.yaml
        test_config = {
            "tech":    [["M249轻机枪", -1]],
            "work":    [["9x39mm BP", -1]],
            "medical": [["战地医疗箱", -1]],
            "armor":   [["精英防弹背心", -1]],
            "TESSERACT_PATH": ".\\dist\\Tesseract-OCR\\tesseract.exe",
            "background_mode": False,
            "debug_mode": False,
        }
        with open(orig, "w", encoding="utf-8") as f:
            yaml.dump(test_config, f, allow_unicode=True)

        # 调用更新
        update_user_config({
            "tech":    "PKM通用机枪",
            "work":    None,           # 不应修改
            "medical": "M2肌肉注射剂",
            "armor":   None,
        })

        # 验证
        with open(orig, "r", encoding="utf-8") as f:
            result = yaml.safe_load(f)

        assert result["tech"][0][0] == "PKM通用机枪", "tech 应被更新"
        assert result["work"][0][0] == "9x39mm BP", "work 应保持不变（None）"
        assert result["medical"][0][0] == "M2肌肉注射剂", "medical 应被更新"
        assert result["armor"][0][0] == "精英防弹背心", "armor 应保持不变"

    finally:
        # 恢复原始文件
        if os.path.exists(backup):
            if os.path.exists(orig):
                os.remove(orig)
            os.rename(backup, orig)


# ---------- 测试 6: 集成测试（端到端） ----------

def test_maybe_update_recipes():
    """
    端到端测试: 从网络获取 → 解析 → 匹配 → 写入。
    验证整体流程不抛出异常，且 user_config.yaml 被合理更新。
    """
    reset_date_cache()

    # 备份
    orig = "user_config.yaml"
    backup = "user_config.yaml.bak"
    if os.path.exists(orig):
        os.rename(orig, backup)

    try:
        # 创建一个干净的测试配置
        test_config = {
            "tech":    [["M249轻机枪", -1]],
            "work":    [["9x39mm BP", -1]],
            "medical": [["战地医疗箱", -1]],
            "armor":   [["精英防弹背心", -1]],
            "TESSERACT_PATH": ".\\dist\\Tesseract-OCR\\tesseract.exe",
            "background_mode": False,
            "debug_mode": False,
        }
        with open(orig, "w", encoding="utf-8") as f:
            yaml.dump(test_config, f, allow_unicode=True)

        # 运行入口函数
        maybe_update_recipes()

        # 验证日期缓存被标记
        assert should_update_today() is False, "执行后应标记为已更新"

    finally:
        reset_date_cache()
        if os.path.exists(backup):
            if os.path.exists(orig):
                os.remove(orig)
            os.rename(backup, orig)


# ---------- 运行测试 ----------

if __name__ == "__main__":
    tests = [
        ("日期缓存", test_date_cache),
        ("网络请求", test_fetch_page_html),
        ("HTML解析(模拟)", test_parse_recipes_with_mock),
        ("HTML解析(真实)", test_parse_recipes_real),
        ("物品名匹配", test_match_site_to_config),
        ("模糊匹配", test_match_site_to_config_fuzzy),
        ("低分过滤", test_match_site_to_config_low_score),
        ("配置写入", test_update_user_config),
        ("端到端集成", test_maybe_update_recipes),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  [PASS] {name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            failed += 1

    print(f"\n{'='*40}")
    print(f"总计: {len(tests)}, 通过: {passed}, 失败: {failed}")
```

### 4.2 测试步骤

#### 阶段一：环境准备

```bash
conda activate deltaforce
pip install requests beautifulsoup4
```

#### 阶段二：单元测试

```bash
python test_daily_fetcher.py
```

预期输出：所有 9 项测试通过，其中"网络请求"和"HTML解析(真实)"在网络不通时 SKIP。

| 测试用例 | 验证内容 | 网络要求 |
|----------|----------|----------|
| 日期缓存 | `should_update_today` 在无缓存/今天/昨天三种场景返回值正确 | 否 |
| 网络请求 | `fetch_page_html` 返回合法 HTML | 是 |
| HTML解析(模拟) | 使用模拟 HTML 正确提取四大台物品 | 否 |
| HTML解析(真实) | 真实页面数据下解析不崩溃且返回非空结果 | 是 |
| 物品名匹配 | 精确名称匹配 | 否 |
| 模糊匹配 | 近似名称通过 fuzzy match 找到 | 否 |
| 低分过滤 | 完全不相关的物品不被匹配 | 否 |
| 配置写入 | user_config.yaml 被正确更新/保留 | 否 |
| 端到端集成 | `maybe_update_recipes` 完整链路不抛异常 | 是 |

#### 阶段三：与主循环联调

1. **手动触发测试**：
   在 `main.py` 中 `print('###### 程序初始化 ######')` 后临时加一行 `input("按回车触发配方更新...")`，观察控制台输出的更新日志。

2. **正常模式测试**：
   确保每天首次启动时显示 `[daily_fetcher] 正在获取今日特勤处制造推荐...` 和后续匹配信息，第二次启动显示 `[daily_fetcher] 今天已更新，跳过`。

3. **离线容错测试**：
   断开网络后启动程序，应输出 `[WARN] 获取今日配方失败: ...` 并正常进入主循环，不崩溃。

### 4.3 调试辅助

如果页面结构解析失败，可在 `daily_fetcher.py` 中添加以下调试代码（仅用于测试，不提交）：

```python
def debug_dump_html(html: str, path: str = "log/orzice_debug.html"):
    """保存页面 HTML 到本地，便于离线分析页面结构"""
    os.makedirs("log", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[DEBUG] HTML 已保存到 {path}")
```

然后在 `parse_recipes` 入口调用它，即可离线审查页面结构，调整选择器。

## 五、回退方案

如需临时关闭自动更新功能，有两种方式：

1. **快速关闭**：在 `user_config.yaml` 中新增字段 `auto_update_recipes: false`，`main.py` 中用条件判断跳过。
2. **彻底关闭**：删除 `daily_fetcher.py`，`main.py` 中的 try-import 会静默设置 `_HAS_FETCHER = False`，不影响运行。

推荐方案 1，因为方案 2 需要修改代码。
