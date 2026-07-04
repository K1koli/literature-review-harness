# Literature Review Harness

基于 Intern-S2-Preview API 和 Sciverse 文献检索的 **Agentic Harness**，LLM 自主决策文献检索、研读、写作，输出带真实引用的文献综述。

## 核心设计

区别于普通脚本，本 Harness 实现的是 **Agent Loop**（LLM 驱动的工具调用循环）：

```
用户输入主题
  → ContextBuilder 组装 system prompt + 工具 schema
  → LLM 调用（Intern-S2-Preview，带 tools 参数）
  → LLM 自主决定调用 search_literature / read_context
  → 执行工具 → 结果回传 → LLM 再决策
  → 循环直到 LLM 认为证据充分 → 输出综述
```

三阶段流程由 LLM **自主驱动**（非硬编码流水线）：文献检索 → 文献研读 → 综述写作。

## 快速开始

```bash
# 1. 安装依赖
pip install httpx python-dotenv

# 2. 配置 API Key
cp .env.example .env
# 编辑 .env，填入：
#   INTERN_API_BASE=https://chat.intern-ai.org.cn/api/v1
#   INTERN_API_KEY=sk-xxx
#   SCIVERSE_API_TOKEN=sci_xxx

# 3. 运行
python main.py "World Models in deep reinforcement learning"
```

输出：`output/survey.md`

## 项目结构

```
literature-review-harness/
├── main.py                        # 入口：组装组件 + 运行 Agent Loop
├── .env.example                   # API Key 配置模板
├── requirements.txt               # httpx, python-dotenv
└── src/
    ├── agent/
    │   ├── loop.py                # AgentLoop：LLM ↔ tools 循环核心
    │   └── context.py             # ContextBuilder：messages 组装 + hook 预留
    ├── tools/
    │   ├── registry.py            # ToolRegistry：工具注册/执行/schema 导出
    │   └── sciverse_tools.py      # search_literature + read_context
    ├── llm/
    │   └── client.py              # LLMClient：OpenAI 兼容 tool-calling
    └── utils/
        └── config.py              # Config：环境变量加载
```

## 组件说明

### AgentLoop（`src/agent/loop.py`）

核心循环逻辑：
- LLM 返回 `tool_calls` → 逐个执行 → 结果回传 → 继续循环
- LLM 返回纯文本（无 tool_calls） → 检查 stop_conditions → 输出最终结果
- `max_iters=15` 硬限制防止无限循环

### ToolRegistry（`src/tools/registry.py`）

- `Tool` Protocol：`name` / `description` / `parameters`(JSON Schema) / `execute()`
- `register(tool)` 注册工具
- `export_schemas()` 导出为 OpenAI function-calling 格式
- `add_hook()` 注册执行后钩子

### ContextBuilder（`src/agent/context.py`）

- 组装 system prompt（含综述写作规范 + 防幻觉要求）
- 管理 messages 列表
- 预留 `pre_llm_hooks`（Skills/Memory 注入点）
- 预留 `post_tool_hooks`（工具结果截断/转换点）

### 工具列表

| 工具 | 功能 | API |
|------|------|-----|
| `search_literature` | 语义检索论文 | Sciverse `/agentic-search` |
| `read_context` | 读取论文全文上下文 | Sciverse `/content` |

## 扩展预留

所有扩展点已预留 hook 接口，新增功能无需修改核心循环：

| 要加的功能 | 接入方式 |
|-----------|---------|
| Skill 系统 | `ContextBuilder.add_pre_llm_hook()` 注入 skill prompt |
| Memory 系统 | `ContextBuilder.add_pre_llm_hook()` 注入记忆摘要 |
| 上下文截断 | `ContextBuilder.add_post_tool_hook()` 截断过长工具结果 |
| 幻觉检测 | `AgentLoop.add_post_llm_hook()` 检查每轮 LLM 输出 |
| 引用验证 | `AgentLoop.add_stop_condition()` 未通过审查则继续循环 |
| 新工具 | `ToolRegistry.register(MyNewTool)` |

## 防幻觉机制

当前通过 system prompt 强制要求：
- 每个论点标注来源 `[doc_id, offset]`
- 严禁编造未在检索结果中出现的论文信息
- 证据不足时明确说明而非编造

后续计划：添加 `TextCitationVerifier` 进行文本级引用扫描验证。
