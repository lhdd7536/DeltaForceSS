"""daily_fetcher 解析/匹配纯函数测试（不访问网络）"""
from core.daily_fetcher import parse_recipes, match_site_to_config, load_config_departments

SAMPLE_HTML = """
<html><body>
<div class="box"><h1 class="orzice-list-title">技术中心</h1><div class="list">
<div class="list-item"><div class="list-item-title">M249轻机枪</div></div>
<div class="list-item"><div class="list-item-title">AKM突击步枪</div></div>
</div></div>
<div class="box"><h1 class="orzice-list-title">工作台</h1><div class="list">
<div class="list-item"><div class="list-item-title">5.45x39mm BS</div></div>
</div></div>
<div class="box"><h1 class="orzice-list-title">制药台</h1><div class="list">
<div class="list-item"><div class="list-item-title">精密头盔维修包</div></div>
</div></div>
<div class="box"><h1 class="orzice-list-title">防具台</h1><div class="list">
<div class="list-item"><div class="list-item-title">精英防弹背心</div></div>
</div></div>
</body></html>
"""


def test_parse_recipes():
    r = parse_recipes(SAMPLE_HTML)
    assert r["tech"] == ["M249轻机枪", "AKM突击步枪"]
    assert r["work"] == ["5.45x39mm BS"]
    assert r["medical"] == ["精密头盔维修包"]
    assert r["armor"] == ["精英防弹背心"]


def test_parse_recipes_empty():
    assert parse_recipes("<html></html>") == {
        "tech": [], "work": [], "medical": [], "armor": [],
    }


def test_match_site_to_config():
    site = {
        "tech": ["M249轻机枪"],
        "work": ["5.45x39mm BS"],
        "medical": ["未知物品"],
        "armor": [],
    }
    known = {
        "tech": {"M249轻机枪", "AKM突击步枪"},
        "work": {"5.45x39mm BS", "7.62x54R BT"},
        "medical": {"精密头盔维修包"},
        "armor": {"精英防弹背心"},
    }
    m = match_site_to_config(site, known, threshold=60)
    assert m["tech"] == "M249轻机枪"
    assert m["work"] == "5.45x39mm BS"
    assert m["medical"] is None   # 未知物品匹配分数低于阈值
    assert m["armor"] is None     # 无候选


def test_load_config_departments(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        "departments:\n"
        "  tech:\n"
        "    枪:\n"
        "      - M249轻机枪\n"
        "      - AKM突击步枪\n",
        encoding="utf-8",
    )
    d = load_config_departments(str(cfg))
    assert d["tech"] == {"M249轻机枪", "AKM突击步枪"}
