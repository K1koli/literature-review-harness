# Literature Review Harness

基于 Intern-S2、Sciverse 和可选 MinerU 的 agentic 文献综述 Harness。默认主链路由 AgentLoop 完整负责：检索、构建 evidence KB、按需加载 Skill、构造写作上下文、直接生成最终综述，并通过多智能体审查和引用校验进行返修。

## 核心设计

```
用户输入主题
  -> ContextBuilder 组装 system prompt + 工具 schema
  -> LLM 调用 Intern-S2 tool calling
  -> LLM 先调用 build_literature_kb
  -> Sciverse semantic/meta 检索并生成 evidence records
  -> MinerU 以快模式尝试解析可访问全文
  -> LLM 通过 list_evidence/read_evidence/read_context 补 Sciverse 证据
  -> 必要时用 list_parsed_papers/read_parsed_paper/search_parsed_paper 读取 MinerU 解析原文
  -> LLM 按当前需求使用 skill tools 发现、加载、读取、卸载 Skill
  -> LLM 调用 prepare_survey_context 形成 timeline/citation map，并由 LLM 生成 outline
  -> LLM 在 AgentLoop 内直接输出完整 Markdown 综述
  -> MultiAgentReviewer 三路并行审查内容质量、引用准确性、结构完整性
  -> CitationVerifier 硬校验最终 Markdown 引用
  -> 可选 OpenAI 图片生成后处理
  -> 输出 output/runs/YYYYMMDD-HHMM-topic/ 运行包
```

Evidence id 形如 `P001-E01`。最终综述中的实质性段落必须引用这些 id，例如 `[P001-E01]`，不能自由编造论文、作者、结论，也不能再使用旧的 `[doc_id, offset]` 作为最终引用格式。

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env
```

编辑 `.env`：

```bash
INTERN_API_BASE=https://chat.intern-ai.org.cn/api/v1
INTERN_API_KEY=sk-xxx
SCIVERSE_API_TOKEN=sv-xxx

# 可选。缺失时自动退化为 Sciverse-only。
MINERU_API_TOKEN=xxx
MINERU_ENABLED=true
MINERU_TIMEOUT=600
MINERU_BATCH_SIZE=1
MINERU_FAST=true

# 可选。默认关闭，开启后会在当前 run 的 figures/ 生成综述配图。
IMAGE_GENERATION_ENABLED=false
OPENAI_API_KEY=sk-xxx
OPENAI_IMAGE_MODEL=gpt-image-1
OPENAI_IMAGE_SIZE=1536x1024
OPENAI_IMAGE_QUALITY=low
```

运行原命令仍可用：

```bash
python main.py "World Models in deep reinforcement learning"
```

输出文件：

- `output/runs/YYYYMMDD-HHMM-topic/survey.md`：最终 Markdown 综述
- `output/runs/YYYYMMDD-HHMM-topic/survey.html`：科研风格 HTML 展示版
- `output/runs/YYYYMMDD-HHMM-topic/survey.tex`：基础 LaTeX 导出版
- `output/runs/YYYYMMDD-HHMM-topic/evidence_pack.json`：论文、evidence、MinerU 状态审计包
- `output/runs/YYYYMMDD-HHMM-topic/check_report.json`：引用校验报告
- `output/runs/YYYYMMDD-HHMM-topic/skill_trace.json`：Skill 路由和加载审计
- `output/runs/YYYYMMDD-HHMM-topic/figure_plan.json`：章节级图片计划
- `output/runs/YYYYMMDD-HHMM-topic/figures/`：图片和 SVG 图
- `output/latest_run.json`：最近一次运行的路径索引

为兼容旧脚本，最近一次运行也会同步到 `output/survey.md`、`output/survey.html`、`output/survey.tex` 等顶层副本。

## 工具列表

| 工具 | 功能 |
|------|------|
| `build_literature_kb` | 构建 Sciverse evidence KB，并按配置尝试 MinerU |
| `list_evidence` | 列出当前 KB 中的 evidence ids |
| `read_evidence` | 按 evidence id 读取完整证据文本 |
| `search_literature` | 追加 Sciverse semantic 检索结果为 evidence |
| `read_context` | 读取 Sciverse 上下文并包装成 evidence |
| `list_parsed_papers` | 列出已有 MinerU 解析全文的论文 |
| `read_parsed_paper` | 按 paper_id/offset 读取 MinerU 解析原文片段，并写回 citeable evidence |
| `search_parsed_paper` | 在 MinerU 解析原文中检索关键词，并把命中片段写回 citeable evidence |
| `prepare_survey_context` | 从当前 KB 构造 timeline/citation map，并调用 LLM 生成 outline、evidence needs 和 writing plan |
| `skills_list_index` | 只列出 skill metadata，不加载全文 |
| `skills_route_for_phase` | 按当前阶段或需求从 metadata 选择候选 skill |
| `skills_load_for_phase` | 加载当前需要的 skill 指令全文 |
| `skills_resource_index` | 列出 skill 内 references/templates/assets/scripts |
| `skills_read_resource` | 按需读取 skill 内资源 |
| `skills_run_script` | 仅在 skill 显式允许时运行 scripts |
| `skills_unload` | 清理当前 active skill |

## 图片生成

图片生成是可选后处理，不进入 citation verifier，也不会阻断正文生成。开启方式：

```toml
[image_generation]
enabled = true
api_key_env = "OPENAI_API_KEY"
base_url = "https://api.openai.com/v1"
endpoint_path = "/images/generations"
model = "gpt-image-1"
size = "1536x1024"
quality = "low"
count = 1
timeout_seconds = 180
```

设计原则：

- prompt 来自最终 `survey.md` 和 Evidence KB 的论文元数据
- 图片只做概念图、时间线、方法图等表达层内容
- 不要求图片写精确论文题名、作者、DOI 或 citation id
- factual claims 仍然只由正文中的 evidence id 支撑

## MinerU 策略

MinerU 是增强源，不是硬依赖。默认配置面向综述快模式：

- `pipeline` 模型
- 关闭 table/formula
- 只取 `1-12` 页
- `MINERU_BATCH_SIZE=1`，即一篇论文一个 batch
- `MINERU_TIMEOUT=600`，10 分钟内没完成就标记 `skipped`
- 超时 reason 为 `MinerU timeout; using Sciverse evidence`

只要 Sciverse evidence 已经存在，MinerU 失败、缺 key、超时都不会阻塞综述生成。

## 防幻觉机制

- 所有工具返回稳定 `evidence_id`
- system prompt 要求最终正文只引用 evidence id
- `CitationVerifier` 会拒绝未知 evidence id
- 长实质性段落没有 evidence id 时会触发继续修订
- `evidence_pack.json` 保留所有可审计证据和 MinerU 状态

## 项目结构

```
literature-review-harness/
├── main.py
├── src/
│   ├── agent/
│   │   ├── context.py
│   │   └── loop.py
│   ├── llm/
│   │   └── client.py
│   ├── images/
│   │   ├── generator.py
│   │   ├── pipeline.py
│   │   ├── planner.py
│   │   └── vector.py
│   ├── skill_system/
│   │   ├── manager.py
│   │   ├── router.py
│   │   ├── tools.py
│   │   └── trace.py
│   ├── state/
│   │   └── kb.py
│   ├── tools/
│   │   ├── literature_kb.py
│   │   ├── mineru.py
│   │   ├── registry.py
│   │   ├── sciverse_tools.py
│   │   └── survey_context.py
│   ├── utils/
│   │   └── config.py
│   ├── validation/
│   │   ├── citations.py
│   │   └── multi_agent.py
└── tests/
    ├── test_evidence_kb.py
    ├── test_skill_system.py
    ├── test_image_generation.py
    └── test_multi_agent_review.py
```

## 测试

```bash
python -m unittest discover -s tests
python -m py_compile main.py $(find src -name '*.py')
```
