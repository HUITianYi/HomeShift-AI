"""真实数据集注册表。

每个数据集声明：从哪下、什么格式、怎么映射到本项目的六大用电类别、
以及它所在的地区（决定电价、碳因子、气候假设与天气坐标）。

为什么要有 category_map：
真实公开数据集的分电器口径各不相同（有的按房间分表，有的按回路分表），
不可能和本项目的类别一一对应。这里显式写出映射关系与它的已知污染
（比如 UCI 的 2 号分表把冰箱和洗衣机混在一起），
评估负载分解精度时会如实反映出来，而不是假装完美对齐。

新增数据集只需在 DATASETS 里加一项 + 在 loaders.py 里加一个解析函数。
"""

from __future__ import annotations

DATASETS: dict[str, dict] = {

    # =====================================================================
    "uci": {
        "id": "uci",
        "title": "UCI Individual Household Electric Power Consumption",
        "short": "UCI 家庭用电（法国，含 3 路分表真值）",
        "loader": "load_uci",
        # 主链接 + 镜像：任一可用即可。下载器会依次尝试。
        "urls": [
            "https://archive.ics.uci.edu/static/public/235/individual+household+electric+power+consumption.zip",
            "https://d396qusza40orc.cloudfront.net/exdata%2Fdata%2Fhousehold_power_consumption.zip",
        ],
        "archive_name": "uci_household_power.zip",
        "member": "household_power_consumption.txt",
        "approx_size_mb": 20,
        "raw_resolution_minutes": 1,
        "license": "CC BY 4.0",
        "citation": (
            "Hebrail, G. & Berard, A. (2012). Individual Household Electric Power "
            "Consumption [Dataset]. UCI Machine Learning Repository. "
            "https://doi.org/10.24432/C58K54"
        ),
        "period": "2006-12 ~ 2010-11",
        # 该住户所在地：法国 Sceaux（巴黎南郊），用于拉取匹配的真实气温
        "region": {
            "code": "fr",
            "name": "Sceaux, France",
            "currency": "EUR",
            "currency_symbol": "€",
            "timezone": "Europe/Paris",
            "latitude": 48.7786,
            "longitude": 2.2906,
            "climate": "temperate",
        },
        # 法国居民电价（EDF 蓝色关税基础档，示意值，答辩时应注明口径）
        "tariff": {
            "plan": "regulated",
            "regulated_rate_per_kwh": 0.2516,
            "gst_rate": 0.20,
            "source_note": "法国 EDF Tarif Bleu 基础档示意值（含 TVA 前），实际以 EDF 公布为准",
        },
        # 法国电网碳因子远低于新加坡（核电为主）
        "carbon": {
            "grid_emission_factor_kg_per_kwh": 0.056,
            "source_note": "法国电网排放因子（核电占比高），示意值",
        },
        # 分表 -> 本项目类别 的映射
        "category_map": {
            "sub_metering_1": "other",
            "sub_metering_2": "laundry",
            "sub_metering_3": "water_heater",
            "unmetered": "other",
        },
        "truth_notes": [
            "sub_metering_1 = 厨房（洗碗机/烤箱/微波炉）-> 归入 other",
            "sub_metering_2 = 洗衣房（洗衣机/烘干机/冰箱/照明）-> 归入 laundry，"
            "但其中混有冰箱负载，因此 fridge 类别没有独立真值",
            "sub_metering_3 = 电热水器 + 空调 -> 归入 water_heater，"
            "法国家庭空调使用极少，绝大部分是热水器",
            "unmetered = 总量减三路分表 -> 归入 other（照明/电视/其他插座）",
        ],
        "recommended_for": "验证负载分解算法（唯一自带分表真值的免密钥公开数据集）",
    },

    # =====================================================================
    "spgroup": {
        "id": "spgroup",
        "title": "SP Group / 自有智能电表导出",
        "short": "你自己家的电表数据（新加坡 SP Utilities 导出 CSV）",
        "loader": "load_generic_csv",
        "urls": [],                  # 无法自动下载，需用户手工导出
        "manual": True,
        "manual_hint": (
            "在 SP Utilities App 中：Usage -> Electricity -> 选择时间范围 -> "
            "Download/Email CSV；把拿到的 CSV 放到 data/raw/ 目录下，然后运行：\n"
            "  python fetch_real_data.py --dataset spgroup --file data/raw/你的文件.csv"
        ),
        "raw_resolution_minutes": 30,
        "license": "用户自有数据",
        "citation": "用户本人的电表账户导出",
        "region": {
            "code": "sg",
            "name": "Singapore",
            "currency": "SGD",
            "currency_symbol": "S$",
            "timezone": "Asia/Singapore",
            "latitude": 1.3521,
            "longitude": 103.8198,
            "climate": "tropical",
        },
        "category_map": {},
        "truth_notes": ["真实家庭只有总表，没有分电器真值 —— 这正是负载分解要解决的问题"],
        "recommended_for": "最贴近产品真实场景（新加坡 HDB 家庭 + 半小时总表）",
    },

    # =====================================================================
    "csv": {
        "id": "csv",
        "title": "通用 CSV 导入",
        "short": "任意含时间戳与用电量两列的 CSV",
        "loader": "load_generic_csv",
        "urls": [],
        "manual": True,
        "manual_hint": (
            "任何包含【时间戳】与【用电量或功率】两列的 CSV 都可以导入：\n"
            "  python fetch_real_data.py --dataset csv --file 路径.csv "
            "--time-col 时间列名 --value-col 用电列名 --value-unit kwh|kw|wh|w"
        ),
        "raw_resolution_minutes": None,
        "license": "取决于来源",
        "citation": "用户提供",
        "region": None,              # 沿用当前 config
        "category_map": {},
        "truth_notes": [],
        "recommended_for": "接入 Ausgrid / Low Carbon London / 学校提供的任意数据集",
    },
}


def get_dataset(name: str) -> dict:
    if name not in DATASETS:
        raise KeyError(
            f"未知数据集 '{name}'。可选：{'、'.join(DATASETS)}"
        )
    return DATASETS[name]


def list_datasets() -> list[dict]:
    return list(DATASETS.values())
