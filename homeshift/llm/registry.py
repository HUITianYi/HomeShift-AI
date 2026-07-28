"""LLM 提供方注册表：一处配置，处处可用。

设计目标：让"换一个模型"变成改一个字符串的事。

三类提供方：
1. anthropic      —— Claude 原生 Messages API（tool-use 原生格式）
2. openai_compat  —— 所有兼容 OpenAI /chat/completions 的服务
                     （DeepSeek / OpenAI / 通义千问 / Kimi / 智谱 / OpenRouter /
                      SiliconFlow / 本地 Ollama / vLLM ...）
3. mock           —— 离线剧本，零依赖零成本

每个预设声明：kind（走哪套协议）、base_url、默认模型、读哪个环境变量拿密钥。
用户只需在 config.json 写 {"llm": {"provider": "deepseek"}} 并设置对应环境变量。

注意（2026-07 核实）：DeepSeek 的 `deepseek-chat` / `deepseek-reasoner` 两个旧
模型名已于 2026-07-24 15:59 UTC 下线，现行模型名为 `deepseek-v4-pro`（强推理，
适合本项目的多轮工具调用）与 `deepseek-v4-flash`（便宜快速）。
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# 预设表
# ---------------------------------------------------------------------------
# kind:          "anthropic" | "openai_compat" | "mock"
# base_url:      API 根地址（openai_compat 会自动补 /chat/completions）
# default_model: 不指定 llm.model 时使用
# key_env:       从哪个环境变量读密钥（第一个存在的生效）
# tool_support:  该服务是否支持 function calling（不支持则无法跑 Agent 循环）
# notes:         给用户看的说明

PROVIDERS: dict[str, dict] = {
    # ---------- 离线 ----------
    "mock": {
        "kind": "mock",
        "label": "离线 Mock（剧本驱动，零依赖零成本）",
        "base_url": None,
        "default_model": "-",
        "key_env": [],
        "tool_support": True,
        "notes": "工具循环与全部数值计算真实，仅'下一步调哪个工具'由剧本决定。",
    },

    # ---------- Anthropic 原生 ----------
    "anthropic": {
        "kind": "anthropic",
        "label": "Anthropic Claude（原生 Messages API）",
        "base_url": "https://api.anthropic.com",
        "default_model": "claude-sonnet-4-6",
        "key_env": ["ANTHROPIC_API_KEY"],
        "tool_support": True,
        "notes": "需要 pip install anthropic，或本项目内置的零依赖 HTTP 回退实现。",
    },

    # ---------- OpenAI 兼容 ----------
    "deepseek": {
        "kind": "openai_compat",
        "label": "DeepSeek（深度求索）",
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-v4-pro",
        "key_env": ["DEEPSEEK_API_KEY"],
        "tool_support": True,
        "extra_body": {"thinking": {"type": "enabled"}, "reasoning_effort": "high"},
        "notes": (
            "国内可直连、价格低。可选模型：deepseek-v4-pro（强推理，推荐）/ "
            "deepseek-v4-flash（快且便宜）。旧名 deepseek-chat、deepseek-reasoner "
            "已于 2026-07-24 下线，勿再使用。"
        ),
    },
    "openai": {
        "kind": "openai_compat",
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4.1",
        "key_env": ["OPENAI_API_KEY"],
        "tool_support": True,
        "notes": "标准 OpenAI 接口。",
    },
    "qwen": {
        "kind": "openai_compat",
        "label": "阿里通义千问（DashScope 兼容模式）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
        "key_env": ["DASHSCOPE_API_KEY", "QWEN_API_KEY"],
        "tool_support": True,
        "notes": "国内可直连；qwen-max 推理更强，qwen-plus 性价比高。",
    },
    "kimi": {
        "kind": "openai_compat",
        "label": "月之暗面 Kimi（Moonshot）",
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "moonshot-v1-32k",
        "key_env": ["MOONSHOT_API_KEY", "KIMI_API_KEY"],
        "tool_support": True,
        "notes": "长上下文友好。",
    },
    "zhipu": {
        "kind": "openai_compat",
        "label": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-4-plus",
        "key_env": ["ZHIPU_API_KEY", "GLM_API_KEY"],
        "tool_support": True,
        "notes": "国内可直连。",
    },
    "siliconflow": {
        "kind": "openai_compat",
        "label": "硅基流动 SiliconFlow（多模型聚合）",
        "base_url": "https://api.siliconflow.cn/v1",
        "default_model": "deepseek-ai/DeepSeek-V3",
        "key_env": ["SILICONFLOW_API_KEY"],
        "tool_support": True,
        "notes": "一个 key 调多家开源模型，注意模型名要带组织前缀。",
    },
    "openrouter": {
        "kind": "openai_compat",
        "label": "OpenRouter（多模型聚合）",
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "anthropic/claude-sonnet-4.5",
        "key_env": ["OPENROUTER_API_KEY"],
        "tool_support": True,
        "notes": "一个 key 调几乎所有模型，适合答辩时现场对比。",
    },
    "ollama": {
        "kind": "openai_compat",
        "label": "本地 Ollama（离线、免费、不上传数据）",
        "base_url": "http://localhost:11434/v1",
        "default_model": "qwen2.5:14b",
        "key_env": ["OLLAMA_API_KEY"],
        "api_key_optional": True,
        "tool_support": True,
        "notes": (
            "先 `ollama serve` 并 `ollama pull qwen2.5:14b`。"
            "小于 7B 的模型往往不能稳定地做多轮工具调用，建议 14B 起。"
        ),
    },
    "custom": {
        "kind": "openai_compat",
        "label": "自定义 OpenAI 兼容端点",
        "base_url": None,          # 必须由 config.json 的 llm.base_url 提供
        "default_model": None,     # 必须由 config.json 的 llm.model 提供
        "key_env": ["LLM_API_KEY"],
        "api_key_optional": True,
        "tool_support": True,
        "notes": "用于 vLLM / one-api / 公司内网网关等，需自行填 base_url 与 model。",
    },
}

# 自动探测顺序：谁的密钥先就绪就用谁（provider = "auto" 时）
AUTO_ORDER = ["anthropic", "deepseek", "openai", "qwen", "kimi", "zhipu",
              "siliconflow", "openrouter"]


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------

class ProviderError(RuntimeError):
    """提供方配置错误（缺密钥、缺 base_url、未知名称等）。"""


def get_preset(name: str) -> dict:
    if name not in PROVIDERS:
        available = "、".join(PROVIDERS)
        raise ProviderError(f"未知的 LLM 提供方 '{name}'。可选：{available}")
    return PROVIDERS[name]


def find_api_key(preset: dict) -> str | None:
    """按 key_env 顺序找第一个非空环境变量。"""
    for env_name in preset.get("key_env", []):
        value = os.environ.get(env_name)
        if value:
            return value.strip()
    return None


def resolve_llm_settings(config: dict) -> dict:
    """把 config + 环境变量解析成一份完整、可直接用于建客户端的设置。

    返回 {provider, kind, model, base_url, api_key, max_tokens,
          max_tool_rounds, temperature, extra_body, label, reason}
    reason 说明"为什么最终选了这个 provider"，便于 status 命令展示与排错。
    """
    llm_cfg = config.get("llm", {})
    requested = llm_cfg.get("provider", "auto")
    reason = ""

    if requested == "auto":
        chosen = None
        for candidate in AUTO_ORDER:
            if find_api_key(PROVIDERS[candidate]):
                chosen = candidate
                reason = f"auto 探测到 {PROVIDERS[candidate]['key_env'][0]}，使用 {candidate}"
                break
        if chosen is None:
            chosen = "mock"
            reason = "auto 未探测到任何 API 密钥，降级为离线 Mock 模式"
    else:
        chosen = requested
        reason = f"config.json 显式指定 provider={chosen}"

    preset = get_preset(chosen)
    kind = preset["kind"]

    # 模型：config 显式 > 预设默认
    model = llm_cfg.get("model") or preset.get("default_model")
    # base_url：config 显式 > 预设默认 > 环境变量（自定义端点）
    base_url = llm_cfg.get("base_url") or preset.get("base_url") or os.environ.get("LLM_BASE_URL")

    api_key = find_api_key(preset)
    # 允许把密钥直接写进环境变量 LLM_API_KEY 作为兜底
    if not api_key and kind != "mock":
        api_key = os.environ.get("LLM_API_KEY")

    settings = {
        "provider": chosen,
        "kind": kind,
        "label": preset["label"],
        "model": model,
        "base_url": base_url,
        "api_key": api_key,
        "max_tokens": llm_cfg.get("max_tokens", 8000),
        "max_tool_rounds": llm_cfg.get("max_tool_rounds", 16),
        "temperature": llm_cfg.get("temperature"),
        "timeout": llm_cfg.get("timeout_seconds", 180),
        "max_retries": llm_cfg.get("max_retries", 3),
        "extra_body": {**preset.get("extra_body", {}), **llm_cfg.get("extra_body", {})},
        "reason": reason,
    }
    return settings


def validate_settings(settings: dict) -> None:
    """在真正发请求前做一次友好的前置校验，避免看不懂的 HTTP 报错。"""
    kind = settings["kind"]
    if kind == "mock":
        return
    preset = get_preset(settings["provider"])

    if not settings.get("model"):
        raise ProviderError(
            f"provider={settings['provider']} 没有默认模型，"
            '请在 config.json 里填写 {"llm": {"model": "..."}}'
        )
    if kind == "openai_compat" and not settings.get("base_url"):
        raise ProviderError(
            f"provider={settings['provider']} 缺少 base_url，"
            '请在 config.json 里填写 {"llm": {"base_url": "https://..."}}'
        )
    if not settings.get("api_key") and not preset.get("api_key_optional"):
        envs = " 或 ".join(preset.get("key_env", [])) or "LLM_API_KEY"
        raise ProviderError(
            f"未找到 {settings['provider']} 的 API 密钥。请先设置环境变量 {envs}：\n"
            f"  macOS/Linux:  export {(preset.get('key_env') or ['LLM_API_KEY'])[0]}=sk-xxxx\n"
            f"  Windows PowerShell:  $env:{(preset.get('key_env') or ['LLM_API_KEY'])[0]}=\"sk-xxxx\""
        )


def describe_providers() -> list[dict]:
    """给 `python -m homeshift providers` 命令用的清单（含密钥就绪状态）。"""
    out = []
    for name, preset in PROVIDERS.items():
        out.append({
            "name": name,
            "label": preset["label"],
            "kind": preset["kind"],
            "default_model": preset.get("default_model"),
            "base_url": preset.get("base_url"),
            "key_env": preset.get("key_env", []),
            "key_ready": bool(find_api_key(preset)) or preset["kind"] == "mock"
                         or bool(preset.get("api_key_optional")),
            "notes": preset.get("notes", ""),
        })
    return out
