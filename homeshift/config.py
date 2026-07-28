"""全局配置。

所有可调参数集中在 DEFAULTS 中；项目根目录放置 config.json 可覆盖任意字段
（深度合并）。敏感信息（API 密钥）永远只从环境变量读取，不写入配置文件。

配置优先级：环境变量(仅密钥) > config.json > DEFAULTS
"""

from __future__ import annotations

import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULTS: dict = {
    "data_dir": "data",

    "llm": {
        # provider 可选值见 llm/registry.py 的 PROVIDERS：
        #   auto | mock | anthropic | deepseek | openai | qwen | kimi | zhipu
        #   | siliconflow | openrouter | ollama | custom
        # auto = 按 AUTO_ORDER 探测已设置的 API 密钥，都没有则降级为 mock。
        "provider": "auto",
        # 留空则使用该 provider 的默认模型（见 registry.py）
        "model": None,
        # 留空则使用该 provider 的默认地址；自定义中转/网关时填这里
        "base_url": None,
        "max_tokens": 8000,
        # 单次任务允许的最大工具调用轮数（防失控护栏之一）
        "max_tool_rounds": 16,
        # None = 用服务端默认；工具调用场景建议低温或不设
        "temperature": None,
        "timeout_seconds": 180,
        "max_retries": 3,
        # 传给服务端的额外字段（如 DeepSeek 的 thinking / reasoning_effort）
        "extra_body": {},
    },

    # ------------------------------------------------------------------
    # 场景与地区：决定电价、碳因子、负载分解所用的作息与气候假设
    # ------------------------------------------------------------------
    "region": {
        # sg = 新加坡（热带，全年制冷）；其他真实数据集会在导入时自动改写这里
        "code": "sg",
        "name": "Singapore",
        "currency": "SGD",
        "currency_symbol": "S$",
        "timezone": "Asia/Singapore",
        "latitude": 1.3521,
        "longitude": 103.8198,
        # tropical = 只有制冷需求；temperate = 冬季有采暖、夏季有制冷
        "climate": "tropical",
    },

    "tariff": {
        # regulated: 受管制固定费率；tou: 分时电价
        "plan": "regulated",
        # 单位 元/kWh（币种见 region.currency），不含消费税。
        # 新加坡 SP Group 受管制电价随季度调整，以官网公布为准；
        # 真实电价接口见 connectors/tariff_api.py。
        "regulated_rate_per_kwh": 0.2988,
        "tou": {
            "peak_rate_per_kwh": 0.3420,
            "offpeak_rate_per_kwh": 0.2210,
            "peak_start_hour": 9,
            "peak_end_hour": 23,
        },
        "gst_rate": 0.09,
        "source_note": "新加坡 SP Group 受管制电价（示意值），实际以官网季度公布为准",
    },

    "carbon": {
        # 新加坡电网平均运行排放因子（EMA 公布口径约 0.412 kgCO2e/kWh）
        "grid_emission_factor_kg_per_kwh": 0.412,
        "source_note": "Singapore EMA Grid Emission Factor",
    },

    # ------------------------------------------------------------------
    # 负载分解的作息锚点（不同家庭/地区可覆盖）
    # ------------------------------------------------------------------
    "disaggregation": {
        # 白天无人在家的时段（用于取基线负载），24 小时制
        "away_start_hour": 9,
        "away_end_hour": 16,
        # 夜间制冷时段
        "night_start_hour": 22,
        "night_end_hour": 7.5,
        # 制冷度时的基准温度
        "cdh_base_c": 26.0,
        # 冰箱 : 待机 的基线拆分比例
        "fridge_share_of_baseline": 0.58,
    },

    "datagen": {
        # 合成数据生成器参数（仅演示用；真实数据见 realdata/）
        "seed": 42,
        "days": 56,
        "default_adherence": 0.85,
    },

    # ------------------------------------------------------------------
    # 真实数据源
    # ------------------------------------------------------------------
    "realdata": {
        # 默认数据集，见 realdata/sources.py
        "dataset": "uci",
        "cache_dir": "data/raw",
        # 从数据集中截取多少天作为演示窗口（太长会让 LLM 上下文过大）
        "window_days": 63,
        # 天气数据来源：openmeteo（全球历史，免密钥）| datagovsg（新加坡实时）| none
        "weather_source": "openmeteo",
        "download_timeout_seconds": 600,
    },

    # ------------------------------------------------------------------
    # 给可视化网站的导出
    # ------------------------------------------------------------------
    "export": {
        "out_dir": "data/web",
        "schema_version": "1.0",
        # 同时导出 .js（window.HOMESHIFT_DATA=...），便于纯静态页面直接引用
        "emit_js": True,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(root: Path | None = None) -> dict:
    """加载配置：DEFAULTS + 可选的 config.json 覆盖。"""
    root = Path(root) if root else PROJECT_ROOT
    cfg = DEFAULTS
    user_cfg_path = root / "config.json"
    if user_cfg_path.exists():
        with open(user_cfg_path, "r", encoding="utf-8") as f:
            try:
                user_cfg = json.load(f)
            except json.JSONDecodeError as exc:
                raise SystemExit(
                    f"config.json 格式错误（第 {exc.lineno} 行）：{exc.msg}\n"
                    "常见原因：多了一个逗号，或用了中文引号。"
                ) from exc
        cfg = _deep_merge(cfg, user_cfg)
    return cfg


def save_config_patch(patch: dict, root: Path | None = None) -> Path:
    """把一部分配置写回 config.json（保留用户已有的其他字段）。

    真实数据导入后需要改写 region / tariff 等，用这个函数持久化。
    """
    root = Path(root) if root else PROJECT_ROOT
    path = root / "config.json"
    existing: dict = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            existing = json.load(f)
    merged = _deep_merge(existing, patch)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    return path


def resolve_provider(cfg: dict) -> str:
    """兼容旧接口：返回最终生效的 provider 名称。"""
    from .llm.registry import resolve_llm_settings

    return resolve_llm_settings(cfg)["provider"]
