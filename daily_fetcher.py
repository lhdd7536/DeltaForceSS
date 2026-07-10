"""
每日从 orzice.com/v/rb 抓取今日特勤处制造推荐，
更新 user_config.yaml 中的制造队列。

使用 Playwright 加载页面（Vue SPA），提取渲染后的物品名。
"""

import re
from datetime import date
from rapidfuzz import fuzz
import os
from utils import read_with_encoding_fallback

# ============================================================
# Playwright 按需导入
# ============================================================

try:
    from playwright.sync_api import sync_playwright
    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False

# ============================================================
# 配置常量
# ============================================================

ORZICE_URL = "https://orzice.com/v/rb"
CACHE_FILE = "data/last_update_date.txt"

# 四大台在页面中对应的 HTML 标识关键词
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
    os.makedirs("data", exist_ok=True)
    return "data"


def should_update_today() -> bool:
    cache_file = os.path.join(_get_cache_dir(), "last_update_date.txt")
    if not os.path.exists(cache_file):
        return True
    saved = read_with_encoding_fallback(cache_file).strip()
    return saved != str(date.today())


def mark_updated_today():
    cache_file = os.path.join(_get_cache_dir(), "last_update_date.txt")
    with open(cache_file, "w", encoding="utf-8") as f:
        f.write(str(date.today()))


# ============================================================
# Playwright 页面加载
# ============================================================

def fetch_page_html(url: str = ORZICE_URL) -> str | None:
    """
    使用 Playwright 加载 orzice.com/v/rb，
    等待 Vue 渲染完成，返回完整 HTML。
    失败时返回 None。
    """
    if not _HAS_PLAYWRIGHT:
        print("[daily_fetcher] Playwright 未安装，跳过自动更新")
        print("[daily_fetcher] 安装方式: pip install playwright && python -m playwright install chromium")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                channel="chrome",
                headless=True,
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
            )
            page = context.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)

            # 等待 Vue 渲染的物品列表出现
            page.wait_for_selector(".list-item-title", timeout=15000)
            page.wait_for_timeout(2000)  # 额外等待确保渲染完成

            html = page.content()
            browser.close()
            return html
    except Exception as e:
        print(f"[daily_fetcher] Playwright 加载页面失败: {e}")
        return None


# ============================================================
# HTML 解析 — 针对 orzice.com 渲染后的 DOM 结构
# ============================================================

def parse_recipes(html: str) -> dict[str, list[str]]:
    """
    从 orzice.com 渲染后的 HTML 中提取四大台的推荐物品名称。

    页面结构（Vue 渲染后）:
        <div class="box">
            <h1 class="orzice-list-title">技术中心</h1>
            <div class="list">
                <div class="list-item">
                    <div class="list-item-title">M249轻机枪</div>
                    ...
                </div>
                ...
            </div>
        </div>

    返回:
    {
        "tech":    ["SVD狙击步枪", "QCQ171冲锋枪", ...],
        "work":    ["4.6x30mm AP SX", ...],
        "medical": ["战地医疗箱", ...],
        "armor":   ["精英防弹背心", ...],
    }
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    recipes: dict[str, list[str]] = {dep: [] for dep in DEPARTMENT_KEYWORDS}

    boxes = soup.select(".box")
    for box in boxes:
        title_el = box.select_one(".orzice-list-title")
        if not title_el:
            continue
        dept_name = title_el.get_text(strip=True)

        # 匹配部门
        dep_key = None
        for key, keyword in DEPARTMENT_KEYWORDS.items():
            if keyword in dept_name:
                dep_key = key
                break
        if dep_key is None:
            continue

        # 提取该部门下的物品名
        items = box.select(".list-item-title")
        for item in items:
            name = item.get_text(strip=True)
            if name and len(name) >= 2:
                recipes[dep_key].append(name)

    return recipes


# ============================================================
# 物品名匹配 — 与 config.yaml 对齐
# ============================================================

def load_config_departments(config_path: str = "config.yaml") -> dict[str, set[str]]:
    import yaml
    cfg = yaml.safe_load(read_with_encoding_fallback(config_path))

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
    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedSeq

    user_config_path = "user_config.yaml"

    yaml_loader = YAML()
    yaml_loader.indent(mapping=2, sequence=4, offset=2)
    yaml_loader.preserve_quotes = True
    yaml_loader.width = 120

    user_cfg = yaml_loader.load(read_with_encoding_fallback(user_config_path))

    changed = False
    for dep, item_name in recipes.items():
        if item_name is None:
            continue
        if dep == "tech":
            print(f"[daily_fetcher] tech: 跳过网站推荐，使用配置中的默认制造")
            continue
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

def _do_fetch_and_update() -> bool:
    """
    执行抓取、解析、匹配、写入的完整流程（不检查日期）。
    成功返回 True，失败返回 False。
    """
    print("[daily_fetcher] 正在获取今日特勤处制造推荐...")
    html = fetch_page_html()
    if html is None:
        print("[daily_fetcher] 跳过本次更新")
        return False

    site_recipes = parse_recipes(html)
    total = sum(len(v) for v in site_recipes.values())
    if total == 0:
        print("[daily_fetcher] 未解析到任何推荐物品，跳过更新")
        return False

    for dep, items in site_recipes.items():
        print(f"[daily_fetcher] {dep}: {items}")

    config_items = load_config_departments()
    matched = match_site_to_config(site_recipes, config_items)

    if not any(matched.values()):
        print("[daily_fetcher] 没有任何部门匹配到可制造的物品，跳过更新")
        return False

    update_user_config(matched)
    mark_updated_today()
    print("[daily_fetcher] 今日配方更新完成")
    return True


def maybe_update_recipes():
    """
    供 main.py 调用的入口（自动模式）。
    检查今天是否已更新，如未更新则执行抓取。
    """
    if not should_update_today():
        print("[daily_fetcher] 今天已更新，跳过")
        return
    _do_fetch_and_update()


def force_update_recipes():
    """
    供 GUI 手动更新调用。
    忽略日期检查，强制拉取最新推荐并更新配方（技术中心除外）。
    """
    print("[daily_fetcher] 手动强制更新...")
    _do_fetch_and_update()


# ============================================================
# 独立测试入口
# ============================================================

if __name__ == "__main__":
    maybe_update_recipes()
