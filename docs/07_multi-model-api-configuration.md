# 07 · 多模型 API 配置指南

系统对大模型的依赖被隔离在 `homeshift/llm/` 一层接口后面，
**换模型不需要改 Agent 一行代码**。

---

## 1. 三分钟接上 DeepSeek

```bash
# 1) 设置密钥（去 https://platform.deepseek.com/api_keys 申请）
export DEEPSEEK_API_KEY=sk-xxxxxxxx           # macOS / Linux
$env:DEEPSEEK_API_KEY="sk-xxxxxxxx"           # Windows PowerShell

# 2) 在项目根目录建 config.json
echo '{"llm": {"provider": "deepseek"}}' > config.json

# 3) 先测连通性，再跑正式任务
python -m homeshift llm-test
python -m homeshift diagnose
```

`llm-test` 会发一条最小请求，验证三件事：密钥有效、网络可达、
**模型能否正确发起工具调用**。第三点最关键 —— 不支持 function calling 的模型
无法驱动本项目的 Agent 循环。

---

## 2. 关于 DeepSeek 模型名的重要提醒

**`deepseek-chat` 和 `deepseek-reasoner` 已于 2026-07-24 15:59 UTC 正式下线。**

网上绝大多数教程还在用这两个名字，照抄会直接拿到 HTTP 400 / 404。
现行模型名：

| 模型 | 特点 | 建议 |
| --- | --- | --- |
| `deepseek-v4-pro` | 强推理，适合多轮工具调用 | **本项目默认，推荐** |
| `deepseek-v4-flash` | 快且便宜 | 反复调试时用，省钱 |

两个 base_url 都可以：
- OpenAI 格式：`https://api.deepseek.com`（本项目走这个）
- Anthropic 格式：`https://api.deepseek.com/anthropic`

本项目默认还会传 `thinking: {"type": "enabled"}` 与 `reasoning_effort: "high"`，
想关掉可在 config.json 里覆盖 `llm.extra_body`。

---

## 3. 全部可用提供方

```bash
python -m homeshift providers      # 带密钥就绪状态
```

| provider | 服务 | 默认模型 | 环境变量 |
| --- | --- | --- | --- |
| `mock` | 离线剧本 | — | 无需 |
| `anthropic` | Claude | `claude-sonnet-4-6` | `ANTHROPIC_API_KEY` |
| `deepseek` | DeepSeek | `deepseek-v4-pro` | `DEEPSEEK_API_KEY` |
| `openai` | OpenAI | `gpt-4.1` | `OPENAI_API_KEY` |
| `qwen` | 阿里通义千问 | `qwen-plus` | `DASHSCOPE_API_KEY` |
| `kimi` | 月之暗面 | `moonshot-v1-32k` | `MOONSHOT_API_KEY` |
| `zhipu` | 智谱 GLM | `glm-4-plus` | `ZHIPU_API_KEY` |
| `siliconflow` | 硅基流动 | `deepseek-ai/DeepSeek-V3` | `SILICONFLOW_API_KEY` |
| `openrouter` | OpenRouter 聚合 | `anthropic/claude-sonnet-4.5` | `OPENROUTER_API_KEY` |
| `ollama` | 本地模型 | `qwen2.5:14b` | 无需 |
| `custom` | 任意兼容网关 | 自填 | `LLM_API_KEY` |

`provider: "auto"`（默认）会按顺序探测已设置的密钥，
一个都没有就自动降级为 `mock`，保证演示永远跑得起来。

---

## 4. 完整配置示例

`config.json` 放在项目根目录，只写你要改的字段即可：

```json
{
  "llm": {
    "provider": "deepseek",
    "model": "deepseek-v4-pro",
    "max_tokens": 8000,
    "max_tool_rounds": 16,
    "temperature": null,
    "timeout_seconds": 180,
    "max_retries": 3,
    "extra_body": {}
  }
}
```

| 字段 | 说明 |
| --- | --- |
| `provider` | 见上表；`auto` 自动探测 |
| `model` | 留空则用该 provider 的默认模型 |
| `base_url` | 留空用默认；中转/代理/内网网关填这里 |
| `max_tool_rounds` | 单回合最大工具轮数，**防失控护栏** |
| `temperature` | `null` 用服务端默认；工具调用建议低温 |
| `extra_body` | 直接透传给服务端的额外字段 |

**密钥永远不写进 config.json**，只从环境变量读 —— 避免误提交到 Git。

---

## 5. 本地模型（不联网、不花钱、数据不出本机）

```bash
ollama serve
ollama pull qwen2.5:14b
echo '{"llm": {"provider": "ollama"}}' > config.json
python -m homeshift llm-test
```

**经验提醒**：小于 7B 的模型通常无法稳定完成多轮工具调用
（会忘记调工具、或吐出非法 JSON 参数）。建议 14B 起。
如果 `llm-test` 显示"模型没有发起工具调用"，就是这个原因。

---

## 6. 技术实现：格式是怎么翻译的

项目的 Agent 循环按 Anthropic Messages API 的内容块格式工作
（`text` / `tool_use` / `tool_result`），而多数服务走 OpenAI 的
`/chat/completions` 格式。`llm/openai_compat.py` 做双向翻译：

| 概念 | Anthropic | OpenAI |
| --- | --- | --- |
| 工具定义 | `{name, description, input_schema}` | `{type:"function", function:{name, description, parameters}}` |
| 模型要调工具 | content 里的 `{type:"tool_use", id, name, input}` | `message.tool_calls[].function.arguments`（JSON 字符串） |
| 工具返回结果 | `{role:"user", content:[{type:"tool_result", tool_use_id}]}` | 多条 `{role:"tool", tool_call_id, content}` |
| 停止原因 | `stop_reason: "tool_use"` | `finish_reason: "tool_calls"` |

几个容易踩的坑，本项目都已处理：

1. **顺序约束**：OpenAI 要求 `role="tool"` 必须紧跟在包含对应 `tool_call_id` 的
   assistant 消息后面。翻译时保持原时间顺序即可满足。
2. **thinking 块**：Claude 会返回 `thinking` 内容块，其他模型不认识，
   回传会报错 —— 翻译时会过滤掉。
3. **非法 JSON 参数**：小模型经常把 `arguments` 写成非法 JSON。
   直接 `json.loads` 会让整个 Agent 崩溃；这里会兜底成
   `{"_malformed_arguments": ...}` 交还给模型自己纠正。
4. **finish_reason 不一致**：有些服务带着 `tool_calls` 却返回
   `finish_reason: "stop"`，会导致循环提前结束。这里会自动纠正。

实现只用标准库 `urllib`，不依赖 `openai` SDK —— 保住项目"零必装依赖"的特点，
同时自己实现了指数退避重试（429/5xx 自动重试）。

---

## 7. 排错对照表

| 报错 | 原因 | 怎么办 |
| --- | --- | --- |
| `HTTP 401` | 密钥无效或环境变量没生效 | 重开终端；`echo $DEEPSEEK_API_KEY` 确认 |
| `HTTP 402` | 余额不足 | 充值 |
| `HTTP 404` + 模型名 | **模型名已下线**或写错 | 见第 2 节；`providers` 查默认模型 |
| `HTTP 404` + 路径 | base_url 多写/少写了 `/v1` | 本项目会自动补 `/chat/completions`，别自己再加 |
| `HTTP 422` | 该服务不支持 `tools` | 换支持 function calling 的模型 |
| `HTTP 429` | 限流 | 已自动重试 3 次；仍失败就等一会 |
| `无法连接` | 网络/代理/Ollama 没启动 | 设 `HTTPS_PROXY`；或 `ollama serve` |
| `返回的不是合法 JSON` | base_url 指向了网页而非 API | 检查 base_url |
| `模型没有发起工具调用` | 模型能力不足或不支持 tools | 换更大的模型 |

所有错误信息都已翻译成中文并附带排查建议，不会只丢一个堆栈给你。

---

## 8. 答辩可能会问

> **为什么要做这个抽象层？直接调一个 API 不就行了？**

三个理由，都可以现场演示：

1. **可演示性**：评审电脑没有密钥、没有网络时，`mock` 模式仍能跑完整个
   Agent 闭环，所有数字照样真实（因为数字来自工具，不来自模型）。
2. **可比较性**：同一套提示词与工具，换 `provider` 就能对比不同模型的
   工具调用能力 —— 这本身就是一个有价值的实验。
3. **成本与合规**：调试时用便宜模型或本地模型，正式演示用强模型；
   涉及家庭用电这类隐私数据时，`ollama` 让数据完全不出本机。
