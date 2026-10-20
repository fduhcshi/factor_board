"""获取因子看板内容，打印列表并保存完整 JSON（仅使用标准库）。"""

import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def get_json(endpoint, params=None):
    url = "https://www.joinquant.com/factorlib/index/" + endpoint
    if params:
        url += "?" + urlencode(params)
    request = Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.joinquant.com/view/factorlib/list",
    })
    with urlopen(request, timeout=30) as response:
        result = json.load(response)
    if result.get("code") != "00000":
        raise ValueError(f"{endpoint} 返回错误：{result.get('msg', result.get('code'))}")
    return result["data"]


def main():
    try:
        settings = get_json("getSetting")
        categories = get_json("getFctCategoryList")
        params = {"categoryId": "0"}  # 全部分类，其余条件使用网站默认值。
        for key in ("universeType", "timeRange", "commisionFee", "skipPaused"):
            params[key] = settings[key]["default"]
        factors = get_json("getList", params)
        factors.sort(key=lambda row: row.get("ic_mean") is None)
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError) as exc:
        print(f"获取失败：{exc}")
        return 1

    output = Path(__file__).with_name("joinquant_factors.json")
    output.write_text(json.dumps({
        "params": params, "settings": settings,
        "categories": categories, "factors": factors,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("因子看板")
    for key, label in (("universeType", "股票池"), ("timeRange", "回测周期"),
                       ("commisionFee", "手续费及滑点"), ("skipPaused", "过滤涨停及停牌股")):
        value = settings[key]["list"][params[key]]
        print(f"{label}：{value[0] if isinstance(value, list) else value}")
    print("分类：" + "、".join(item["intro"] for item in categories))
    print(f"\n共 {len(factors)} 个因子\n因子名称\t英文名\tIC均值\tIR值")
    for row in factors:
        print(f"{row['intro']}\t{row['name']}\t{row.get('ic_mean')}\t{row.get('ir')}")
    print(f"\n完整数据（含计算说明、收益率及换手率等）：{output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
