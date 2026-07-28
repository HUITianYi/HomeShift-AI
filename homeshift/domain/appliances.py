"""电器档案：典型新加坡 HDB 4 房式家庭的主要用电设备。

数据生成器、负载分解和节能模拟共享这份档案。
分类依据教授提纲引用的 NEA 结论：空调、冰箱、照明、热水器和洗衣机
约占典型新加坡家庭用电的 80%。
"""

# 具体电器（数据生成器使用的粒度）
APPLIANCES: dict[str, dict] = {
    "aircon_master": {"label": "主卧空调", "category": "aircon"},
    "aircon_kids": {"label": "次卧空调", "category": "aircon"},
    "aircon_living": {"label": "客厅空调（周末）", "category": "aircon"},
    "water_heater": {"label": "储水式热水器", "category": "water_heater"},
    "fridge": {"label": "冰箱", "category": "fridge"},
    "washing_machine": {"label": "洗衣机", "category": "laundry"},
    "lighting": {"label": "照明", "category": "other"},
    "tv_media": {"label": "电视/娱乐设备", "category": "other"},
    "kitchen": {"label": "厨房电器", "category": "other"},
    "fans": {"label": "风扇", "category": "other"},
    "standby": {"label": "待机负载/路由器", "category": "standby"},
}

# 负载分解输出的类别（智能体“看得到”的粒度）
CATEGORY_LABELS: dict[str, str] = {
    "aircon": "空调",
    "water_heater": "热水器",
    "fridge": "冰箱",
    "laundry": "洗衣",
    "standby": "待机负载",
    "other": "照明/厨房/娱乐等",
}


def category_of(appliance_key: str) -> str:
    return APPLIANCES.get(appliance_key, {}).get("category", "other")
