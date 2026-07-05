# Literature Review Harness 答辩文档

本文档用于项目答辩、技术讲解和评审问答准备。内容以当前代码实现为准，重点说明本项目为什么是一个真正的学术综述生成 Harness，而不是一次性 prompt 写作脚本。

## 1. 项目概述

### 1.1 一句话介绍

本项目是一个面向学术综述生成的 evidence-grounded agent harness。系统围绕 Sciverse 文献检索、可选 MinerU 全文解析、运行时 Evidence KB、渐进式 Skill 系统、多智能体审查、引用校验、图片生成和多格式导出，形成一条可审计、可返修、可复现的综述生成链路。

更简洁地说：

> 我们不是让模型直接写 survey，而是让模型在 Harness 的约束下先找证据、再组织知识结构、再写作、再审查、再导出。

### 1.2 项目目标

赛题要求构建一个论文综述 Harness，能够：

- 阅读学术论文。
- 整理和分类论文。
- 总结领域关键论文。
- 梳理领域发展脉络。
- 给出未来研究方向。
- 保证没有幻觉引用。
- 避免缺乏事实证据的幻觉描述。
- 以 World Models 为题生成图文并茂的综述。
- 推荐使用 Sciverse 科学文献库 API 和 MinerU 文档解析 API。

本项目的目标不是只完成 World Models 这一个题目，而是实现一个可复用的 Survey Harness。World Models 是默认展示题目，Harness 可以替换成其他主题运行。

## 2. 为什么需要 Harness

直接让大模型写综述通常会有几个问题：

- 模型可能编造论文、作者、年份、结论。
- 检索结果和正文引用之间没有可追踪关系。
- 输出经常像论文摘要拼接，而不是有组织的 survey。
- 引用格式混乱，可能出现不存在的 citation。
- 图片生成和正文证据脱节。
- 如果草稿质量不好，缺少系统化返修机制。

本项目把综述生成拆成多个可控制环节：

```text
检索论文
  -> 构建 Evidence KB
  -> 读取证据和上下文
  -> Skill 发现与加载
  -> 生成 timeline / citation map / outline
  -> 补读证据
  -> 写完整 survey
  -> 多智能体审查
  -> 引用校验
  -> 返修
  -> 图片生成
  -> Markdown / HTML / LaTeX 导出
```

这样做的核心好处是：每一步都有输入、输出、状态和审计文件，评审可以追溯最终综述中每个引用来自哪里。

## 3. 总体架构

### 3.1 主链路

当前主入口是 `main.py`。完整运行过程如下：

```text
python main.py "World Models in deep reinforcement learning"
  |
  v
Config.from_env()
  |
  v
初始化 LLMClient / LiteratureKB / ToolRegistry / SkillManager
  |
  v
AgentLoop.run(user_message)
  |
  v
LLM 根据 system prompt 和 tool schema 自主调用工具
  |
  +-- build_literature_kb
  +-- list_evidence / read_evidence / search_literature / read_context
  +-- list_parsed_papers / read_parsed_paper / search_parsed_paper
  +-- skills_list_index / skills_route_for_phase / skills_load_for_phase / skills_unload
  +-- prepare_survey_context
  |
  v
LLM 输出完整 Markdown survey
  |
  v
MultiAgentReviewer 三路并行审查
  |
  v
CitationVerifier 机械引用校验
  |
  v
必要时进入返修，最多 3 轮
  |
  v
保存 survey.md / evidence_pack.json / check_report.json / skill_trace.json
  |
  v
图片生成后处理
  |
  v
导出 HTML / LaTeX / run package
```

### 3.2 目录结构

```text
literature-review-harness/
├── main.py
├── configs/
│   ├── config.example.toml
│   └── skills.toml
├── skills/
│   ├── research-framing/
│   ├── survey-writing/
│   ├── citation-grounding/
│   ├── agent-research-skills/
│   ├── engineering-figure-agent/
│   └── ...
├── src/
│   ├── agent/
│   │   ├── context.py
│   │   └── loop.py
│   ├── exporters/
│   │   ├── html.py
│   │   └── latex.py
│   ├── images/
│   │   ├── generator.py
│   │   ├── pipeline.py
│   │   ├── planner.py
│   │   └── vector.py
│   ├── llm/
│   │   └── client.py
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
│   │   └── survey_context.py
│   ├── utils/
│   │   ├── config.py
│   │   └── runs.py
│   └── validation/
│       ├── citations.py
│       └── multi_agent.py
├── tests/
└── output/
    └── runs/YYYYMMDD-HHMM-topic/
```

## 4. 核心模块说明

### 4.1 AgentLoop

文件：`src/agent/loop.py`

`AgentLoop` 是项目的核心控制器，负责：

- 构造 LLM 请求。
- 暴露工具 schema。
- 解析 tool calls。
- 执行工具。
- 支持多工具并行调用。
- 将工具结果写回上下文。
- 在模型输出正文后运行 stop conditions。
- 触发返修。
- 控制最大迭代和最大返修轮数。

当前返修预算：

```text
max_revision_rounds = 3
```

设计原因：

- 返修太少，质量可能不够。
- 返修太多，小模型容易越写越长、越修越散。
- 3 轮是比较稳妥的折中：初稿后最多修 3 次，如果仍不通过，就返回最新草稿并保留 audit report。

返修逻辑：

```text
LLM 输出草稿
  -> reviewer / verifier 不通过
  -> 注入反馈
  -> LLM 修订
  -> 最多 3 轮
  -> 仍失败则返回当前最新草稿
```

### 4.2 ContextBuilder

文件：`src/agent/context.py`

`ContextBuilder` 负责构建 system prompt，约束模型必须按 Harness 流程行动。核心规则包括：

- 先构建 KB，再写作。
- 使用 Sciverse snippets 和 context。
- 如果 snippets 不够，使用 MinerU parsed-paper 工具。
- 写作前必须演示 Skill 系统的渐进式加载。
- 调用 `prepare_survey_context` 获得 timeline、citation map 和 LLM outline。
- 每个实质性段落必须引用 evidence id。
- 最终引用只能使用 `P001-E01` 这样的 evidence id，不能使用 raw doc_id 或 offset。

### 4.3 LLMClient

文件：`src/llm/client.py`

这是一个 OpenAI-compatible Chat Completions 客户端，当前用于调用 Intern-S2-Preview：

- 支持 tools。
- 自动解析 tool calls。
- 支持普通 chat completion。
- 可以用于主 AgentLoop、Survey Context 内部结构设计、多智能体审查。

## 5. Evidence KB 设计

### 5.1 为什么需要 Evidence KB

综述生成最重要的问题是证据可追溯。本项目没有让模型直接引用论文，而是先把论文和证据统一写入 `LiteratureKB`。

Evidence KB 解决三个问题：

- 给每条证据生成稳定 id。
- 记录证据来源、论文、年份、doc_id、offset、score。
- 让 CitationVerifier 可以机械检查最终正文引用是否真实存在。

### 5.2 数据模型

文件：`src/state/kb.py`

核心数据结构：

```python
PaperRecord:
  paper_id
  title
  year
  venue
  doi
  authors
  doc_id
  parse_url
  mineru
  evidence_ids

EvidenceRecord:
  evidence_id
  paper_id
  title
  text
  source
  doc_id
  offset
  score
  year

ParsedDocument:
  paper_id
  title
  text
  source
  metadata
```

Evidence id 形如：

```text
P001-E01
P001-E02
P002-E01
```

其中：

- `P001` 是论文 id。
- `E01` 是这篇论文下的证据编号。

### 5.3 去重与合并

`LiteratureKB.upsert_paper()` 会根据以下稳定 key 合并论文：

- DOI
- doc_id
- normalized title

这样可以减少 Sciverse semantic search 和 meta search 返回重复论文造成的污染。

## 6. Sciverse 与 MinerU

### 6.1 Sciverse 调用

文件：`src/tools/literature_kb.py`

主要工具：

| 工具 | 功能 |
|---|---|
| `build_literature_kb` | 调用 Sciverse semantic/meta search，构建 Evidence KB |
| `search_literature` | 后续追加检索，把新结果写回 KB |
| `list_evidence` | 列出当前 evidence |
| `read_evidence` | 读取指定 evidence |
| `read_context` | 根据 Sciverse doc_id/offset 读取更大上下文，并写回 KB |

Sciverse 的定位：

- 快速给出候选论文、片段、metadata。
- 为 agent 提供初始 evidence。
- 在返修和 evidence gap 阶段补充检索。

### 6.2 MinerU 调用

文件：`src/tools/mineru.py`

MinerU 是可选增强，不是硬依赖。原因是：

- 全文解析耗时较长。
- 部分论文没有可解析 URL。
- 比赛 demo 需要可控运行时间。

当前策略：

- 配置中可开启或关闭。
- 开启时优先解析 `parse_url` 可用的论文。
- 支持快模式，只解析前 1-12 页。
- 支持超时后降级，不阻塞主链路。

相关工具：

| 工具 | 功能 |
|---|---|
| `list_parsed_papers` | 查看哪些论文已有 MinerU 解析全文 |
| `read_parsed_paper` | 读取某篇论文解析文本片段，并写回 citeable evidence |
| `search_parsed_paper` | 在解析全文中搜索关键词，并写回 citeable evidence |

### 6.3 Sciverse 和 MinerU 的分工

```text
Sciverse:
  - 检索论文
  - 返回片段、doc_id、metadata
  - 适合快速构建 KB

MinerU:
  - 解析论文全文
  - 适合关键论文深读
  - 适合补充方法细节、实验设置、限制讨论
```

因此本项目不是把所有论文全文塞进上下文，而是：

```text
先用 Sciverse 建证据层
再按需要用 MinerU parsed tools 补读关键论文
```

这对 35B 级模型尤其重要，可以避免上下文爆炸。

## 7. Survey Context 与 Outline 设计

### 7.1 为什么不硬编码 outline

早期版本曾经用规则生成 taxonomy、timeline、matrix、agenda 等结构。但实践中发现：规则结构容易把噪声论文也组织进正文，甚至会产生看起来完整但学术判断不足的 outline。

当前实现做了简化：

文件：`src/tools/survey_context.py`

确定性部分只保留：

- `coverage`
- `timeline`
- `citation_map`

高阶学术判断交给 LLM：

- `recommended_outline`
- `survey_design`
- `selected_papers`
- `low_relevance_papers`
- `evidence_needs`
- `writing_plan`

### 7.2 当前流程

```text
prepare_survey_context
  -> 从 KB 生成 coverage / timeline / citation_map
  -> 调用 LLM 设计 outline
  -> 清洗 LLM 输出
  -> 返回 recommended_outline 和 evidence_needs
```

如果 LLM 没有成功生成 outline，系统不会用硬编码模板伪装成功，而是返回：

```json
{
  "outline_status": "llm_returned_no_outline"
}
```

如果成功：

```json
{
  "outline_status": "generated_by_llm",
  "recommended_outline": [...],
  "survey_design": {
    "evidence_needs": [...],
    "writing_plan": "..."
  }
}
```

### 7.3 输出清洗

LLM 输出会经过清洗：

- 只允许 evidence gap 推荐 Harness 内部工具。
- 过滤不存在的 paper id。
- 支持 `recommended_outline / outline / sections / section_plan` 等别名。
- 把 dict 形式 section 转成干净的 `"Section: purpose"` 字符串。

允许的补读工具白名单：

```text
search_literature
read_context
list_parsed_papers
read_parsed_paper
search_parsed_paper
```

## 8. Skill 系统

### 8.1 赛题要求

赛题提出，如果实现 Skill 系统，需要考虑：

- 如何渐进性披露，避免上下文过载。
- 多个 Skill 如何统一管理。
- Skill 如何被模型发现和加载。
- Skill 内容如何注入上下文。
- Skill 如何卸载。

本项目实现了上述完整链路。

### 8.2 Skill 系统模块

目录：`src/skill_system/`

| 文件 | 作用 |
|---|---|
| `manager.py` | 发现、加载、卸载 skill；读取资源；控制脚本权限 |
| `router.py` | 根据 phase 和 roles 从 metadata 中选择 skill |
| `tools.py` | 把 Skill 系统暴露成 Agent 可调用工具 |
| `trace.py` | 记录 skill 发现、路由、加载、卸载审计 |

### 8.3 渐进性披露

Skill 系统不是启动时把所有 skill 全部塞进 prompt，而是分阶段：

```text
skills_list_index
  -> 只列 metadata，不加载全文

skills_route_for_phase
  -> 根据 phase/roles 选择候选 skill

skills_load_for_phase
  -> 只加载当前阶段需要的 SKILL.md 和 always-load 资源

skills_read_resource
  -> 按需读取 references/templates/scripts

skills_unload
  -> 当前阶段结束后卸载 active skill
```

这满足 progressive disclosure：发现阶段便宜，加载阶段受控，资源按需读取。

### 8.4 当前可用 Skill

当前 smoke test 发现 9 个 skill：

- `research-framing`
- `survey-writing`
- `citation-grounding`
- `engineering-figure-agent`
- `paper-writing`
- `agent-literature-review`
- `agent-survey-generation`
- `agent-related-work-writing`
- `agent-figure-generation`

写作阶段路由结果：

```text
survey-writing
agent-survey-generation
agent-related-work-writing
```

这些 skill 会作为写作协议使用，而不是事实来源。事实来源只能来自 Evidence KB。

### 8.5 Skill 安全策略

第三方 skill 可能包含脚本或 prompt injection，因此默认：

- 允许读取 `SKILL.md`。
- 允许读取 markdown resources。
- 默认不执行 scripts。
- 只有 `allow_scripts=true` 的 skill 才能运行脚本。
- skill 路径必须位于项目 `skills/` 目录内，外部路径会被忽略。

### 8.6 Skill Trace

每次运行会输出：

```text
output/runs/YYYYMMDD-HHMM-topic/skill_trace.json
```

其中记录：

- 发现了哪些 skill。
- 路由选择了哪些 skill。
- 加载了哪些 skill。
- 注入了多少字符。
- 读取了哪些资源。
- 何时卸载。

这使得答辩时可以证明 skill 不是写在 README 里的概念，而是运行时可审计的 Harness 行为。

## 9. 写作生成流程

当前写作不是单独外部 pipeline 默认执行，而是在 AgentLoop 内完成。这样设计是为了让模型能在同一上下文里：

- 看到检索证据。
- 看到 skill 指令。
- 看到 outline。
- 看到 evidence needs。
- 决定是否补读。
- 直接写完整 survey。
- 接受 reviewer 和 verifier 的反馈进行返修。

写作阶段大致是：

```text
Evidence KB ready
  -> Skill 写作协议加载
  -> prepare_survey_context 生成 outline
  -> evidence_needs 驱动补读
  -> LLM 生成完整 Markdown survey
  -> MultiAgentReviewer 审查
  -> CitationVerifier 校验
  -> 最多 3 轮返修
```

输出必须满足：

- Markdown 格式。
- 包含 Abstract、Introduction、主体章节、Future Directions、Conclusion、References。
- 每个实质性段落引用 evidence id。
- References 只列正文引用过的论文。
- 不暴露工具日志、doc_id、offset、隐藏推理。

## 10. 多智能体审查

文件：`src/validation/multi_agent.py`

`MultiAgentReviewer` 是一个 stop condition。它在 LLM 输出草稿后触发，三个 reviewer 并行调用：

```text
content_quality
citation_accuracy
structure_completeness
```

### 10.1 三个 reviewer 的职责

#### Content Quality Reviewer

检查：

- 是否有清晰 scope。
- 是否是 synthesis，而不是论文罗列。
- 是否解释方法族、tradeoff、限制。
- 是否有 evidence-grounded research agenda。

#### Citation Accuracy Reviewer

检查：

- 段落是否有 evidence id。
- 引用是否分布合理。
- 表格是否有来源。
- 是否出现 raw doc_id、offset、伪 citation。

#### Structure Completeness Reviewer

检查：

- 是否有 Abstract、Introduction、taxonomy/framework、comparison、limitations、conclusion、references。
- 章节是否平衡。
- abstract 是否总结观点。
- conclusion 是否有综合，而不是重复引言。

### 10.2 聚合方式

每个 reviewer 返回：

```json
{
  "passed": true,
  "issues": [],
  "suggestions": []
}
```

如果任意 reviewer 不通过，Harness 会聚合成：

```text
## Multi-Agent Review Results
Issues Found
Suggested Fixes
```

然后注入下一轮 AgentLoop，让主模型修订。

### 10.3 返修预算

为了避免无休止返修，当前 AgentLoop 设置：

```text
max_revision_rounds = 3
```

如果 3 轮后仍不通过，系统返回最新草稿，同时保留 `check_report.json` 和 reviewer feedback，供人工继续审查。

## 11. CitationVerifier

文件：`src/validation/citations.py`

`CitationVerifier` 是机械校验器，不依赖 LLM。

它检查：

- 所有 evidence id 是否存在于 KB。
- 长段落是否缺少 evidence id。
- 是否出现模型错误响应。
- References 区域不会被误判为正文段落。
- Markdown 表格、figure markup 会被跳过，避免误报。

这层是防幻觉引用的关键。

### 11.1 为什么需要机械校验

LLM reviewer 可以判断内容质量，但它本身也可能漏判。因此引用层必须有确定性校验：

```text
如果正文引用 [P999-E99]
  -> KB 中不存在
  -> CitationVerifier fail
```

```text
如果某个长段落没有任何 Pxxx-Exx
  -> CitationVerifier fail
```

这保证最终 survey 至少满足 evidence id 层面的可审计性。

## 12. 图片生成

### 12.1 图片生成定位

图片生成是后处理，不参与 citation verifier，也不阻塞正文生成。

原因：

- 图片 API 可能失败。
- 视觉表达不应该成为事实来源。
- 正文证据仍然由 evidence id 支撑。

### 12.2 图片流程

文件：

- `src/images/planner.py`
- `src/images/generator.py`
- `src/images/pipeline.py`
- `src/images/vector.py`

流程：

```text
读取最终 survey.md
  -> 解析 Markdown section
  -> 找到带 evidence id 的章节
  -> 根据章节类型规划少量 figures
  -> raster 图调用 OpenAI-compatible Images API
  -> 表格/矩阵类图优先本地 SVG
  -> 失败时 SVG fallback
  -> 插入对应章节
  -> 保存 figure_plan.json / figure_manifest.json
```

### 12.3 图的类型

当前 planner 支持：

- conceptual overview
- method taxonomy
- comparison matrix
- research agenda

规划策略非常保守：

- 最多 3 张图。
- 只给已经有 evidence id 的章节插图。
- 图 caption 记录 source evidence ids。
- 图片 prompt 不要求写论文题名、作者、DOI、citation id、数字结果。

这样避免图片 hallucination 成为事实依据。

### 12.4 OpenAI / 第三方兼容

图片 API 配置：

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

如果使用第三方兼容 OpenAI 的服务，只需要改：

```toml
base_url = "https://your-provider/v1"
endpoint_path = "/images/generations"
```

## 13. 导出与运行包

### 13.1 输出目录

每次运行会创建：

```text
output/runs/YYYYMMDD-HHMM-topic/
├── survey.md
├── survey.html
├── survey.tex
├── evidence_pack.json
├── check_report.json
├── skill_trace.json
├── figure_plan.json
└── figures/
```

同时为了兼容旧脚本，会同步：

```text
output/survey.md
output/survey.html
output/survey.tex
output/evidence_pack.json
output/check_report.json
output/skill_trace.json
output/figure_plan.json
output/latest_run.json
```

### 13.2 Markdown

`survey.md` 是主产物。它是审查、图片插入和导出的基础。

### 13.3 HTML

文件：`src/exporters/html.py`

特点：

- 科研风格页面。
- Evidence id 高亮。
- 支持 figure markup。
- 适合答辩展示。

### 13.4 LaTeX

文件：`src/exporters/latex.py`

当前是基础 LaTeX 导出：

- 支持 heading 映射。
- 支持 figure 图片。
- 支持基本 escape。

注意：当前不是完整 arXiv conference template，只是基础 `.tex` 导出。后续可以接入 `latex-arxiv` skill 或模板导出模块。

## 14. 配置系统

文件：`src/utils/config.py`

配置来源：

- `configs/config.toml`
- `.env`
- 环境变量

关键配置：

```toml
[llm]
base_url_env = "INTERN_API_BASE"
api_key_env = "INTERN_API_KEY"
model = "intern-s2-preview"

[sciverse]
token_env = "SCIVERSE_API_TOKEN"

[mineru]
token_env = "MINERU_API_TOKEN"

[runtime]
skip_mineru = false
timeout_seconds = 600

[image_generation]
enabled = false
api_key_env = "OPENAI_API_KEY"
base_url = "https://api.openai.com/v1"
endpoint_path = "/images/generations"
model = "gpt-image-1"
```

答辩时不要展示真实 key。只展示 `.env.example` 或 `config.example.toml`。

## 15. 测试与验证

### 15.1 单元测试

当前测试覆盖：

- Evidence KB 合并和 evidence id 生成。
- MinerU 超时降级。
- MinerU parsed-paper 工具。
- CitationVerifier。
- MultiAgentReviewer 三路聚合。
- Skill system 发现、路由、加载、卸载。
- Image generation planner / fallback。
- Run output path。
- AgentLoop 返修预算。

运行：

```bash
python3 -m unittest discover -s tests
```

当前验证结果：

```text
Ran 30 tests
OK
```

编译检查：

```bash
python3 -m py_compile main.py $(find src -name '*.py')
```

当前验证结果：通过。

### 15.2 已验证的关键链路

已经验证过的模块级链路：

```text
Sciverse build KB
  -> list/read evidence
  -> read_context 补读
```

```text
prepare_survey_context
  -> LLM 生成 outline
  -> evidence_needs
```

```text
outline
  -> 补读
  -> section_plan
```

```text
draft
  -> MultiAgentReviewer
  -> CitationVerifier
  -> revision loop
```

```text
SkillManager
  -> discover 9 skills
  -> route write phase
  -> load 3 writing skills
  -> unload
```

## 16. 当前运行状态与注意事项

### 16.1 当前已经稳定的部分

- 工具注册正常。
- Sciverse 检索和 evidence 写入正常。
- `prepare_survey_context` 能生成 LLM outline。
- Skill manager 能发现和加载 skill。
- 多智能体审查能触发。
- CitationVerifier 能机械校验 evidence id。
- 返修预算已限制为 3，避免 loop 长时间不结束。
- 图片生成模块具备 OpenAI-compatible API 和 SVG fallback。
- 输出包结构清晰。

### 16.2 仍需注意的部分

1. 完整链路耗时较长  
   因为包含 Sciverse 检索、主模型多轮调用、`prepare_survey_context` 内部 LLM 调用、3 路 reviewer、图片生成。

2. 小模型返修可能越写越长  
   已通过 `max_revision_rounds=3` 控制，但仍需要在答辩 demo 中设置合理的 `MAX_ITERATIONS` 和 reviewer timeout。

3. MinerU 当前可选  
   默认可关闭以保证 demo 稳定。打开后可以展示全文补读能力，但运行时间更长。

4. LaTeX 导出是基础版  
   当前能生成 `.tex`，但不是完整 arXiv template。可以作为后续增强点。

## 17. 与赛题要求对应关系

| 赛题要求 | 本项目实现 |
|---|---|
| 阅读学术论文 | Sciverse snippets + 可选 MinerU parsed text |
| 整理和分类论文 | Evidence KB + LLM outline + writing plan |
| 总结关键论文 | `selected_papers`、正文 synthesis、References |
| 梳理发展脉络 | `timeline` + survey sections |
| 给出未来研究方向 | outline 和正文中的 Open Problems / Research Agenda |
| 无幻觉引用 | evidence id + CitationVerifier |
| 无事实幻觉描述 | 每个实质性段落必须引用 KB evidence |
| 使用 Sciverse | `build_literature_kb`、`search_literature`、`read_context` |
| 使用 MinerU | `run_mineru_for_kb`、parsed-paper tools |
| 图文并茂 | section-aware figure planner + image API + SVG fallback |
| Skill 系统 | metadata discovery、routing、loading、resource reading、unload、trace |
| 返修能力 | MultiAgentReviewer + CitationVerifier + revision budget |
| 多格式输出 | Markdown / HTML / LaTeX / evidence audit |

## 18. 答辩展示建议

### 18.1 演示顺序

建议按这个顺序讲：

1. 展示 `README.md` 的核心流程图。
2. 展示 `main.py` 主链路。
3. 展示 `src/state/kb.py` 的 evidence id 数据结构。
4. 展示 `src/tools/literature_kb.py` 的 Sciverse 工具。
5. 展示 `src/tools/mineru.py` 的可选全文解析。
6. 展示 `src/tools/survey_context.py` 的 LLM outline 生成。
7. 展示 `src/skill_system/` 的渐进式 Skill 系统。
8. 展示 `src/validation/` 的多智能体审查和引用校验。
9. 展示 `src/images/` 的图片生成后处理。
10. 展示 `output/runs/...` 的最终运行包。

### 18.2 推荐 Demo 命令

```bash
python3 -m unittest discover -s tests
```

```bash
python3 main.py "World Models in deep reinforcement learning"
```

如果现场网络或图片 API 不稳定，可以关闭图片：

```bash
IMAGE_GENERATION_ENABLED=false python3 main.py "World Models in deep reinforcement learning"
```

如果想加快 demo，可以关闭 MinerU：

```bash
MINERU_ENABLED=false python3 main.py "World Models in deep reinforcement learning"
```

### 18.3 展示输出

优先展示：

- `output/latest_run.json`
- `output/runs/.../survey.html`
- `output/runs/.../evidence_pack.json`
- `output/runs/.../check_report.json`
- `output/runs/.../skill_trace.json`
- `output/runs/.../figure_plan.json`

这些文件最能体现 Harness，而不是单纯一篇生成文本。

## 19. 答辩口径：我们的创新点

### 19.1 Evidence-first，而不是 prompt-first

普通做法是先写 prompt。本项目先构建 evidence KB，再让模型写。

### 19.2 Citation-grounded

最终正文必须引用 `P001-E01` 这种 evidence id。每条 id 都能在 `evidence_pack.json` 里查到。

### 19.3 Skill progressive disclosure

Skill 不是全部塞进 prompt，而是：

```text
metadata discovery
  -> route
  -> load
  -> read resource
  -> unload
```

这满足赛题对 Skill 系统的设计要求。

### 19.4 Multi-agent review

不是只生成一次，而是用 3 个 reviewer 从不同角度审查：

- 内容质量。
- 引用准确性。
- 结构完整性。

### 19.5 Deterministic verifier

除了 LLM reviewer，还有机械 CitationVerifier，确保 unknown evidence id 和缺 citation 的段落被拦截。

### 19.6 Section-aware figures

图片不是随便生成，而是根据最终 survey 的章节和 evidence ids 规划，并插入对应章节。

### 19.7 Run package

每次运行形成独立包，包含正文、HTML、LaTeX、证据、审查、skill trace、图片计划。这使得结果可复查、可分享、可答辩。

## 20. 常见评委问题与回答

### Q1：你们如何保证没有幻觉引用？

回答：

我们不让模型自由编引用。系统先构建 Evidence KB，每条证据都有稳定 evidence id，例如 `P001-E01`。最终正文只能引用这些 evidence id。生成后 `CitationVerifier` 会检查正文中出现的 evidence id 是否存在于 KB，并检查长段落是否缺少 evidence id。未知 id 或缺引用都会触发返修。

### Q2：如果 Sciverse 检索结果不准怎么办？

回答：

Sciverse 返回的是候选证据，不直接等于最终正文。Agent 会通过 `list_evidence/read_evidence/read_context` 检查证据，`prepare_survey_context` 会生成 `low_relevance_papers` 和 `evidence_needs`，后续可以通过 `search_literature` 或 MinerU parsed-paper 工具补读。最终也会经过 reviewer 和 citation verifier。

### Q3：MinerU 是不是必须成功？

回答：

不是。MinerU 是增强源，不是硬依赖。Sciverse 构建基础 evidence，MinerU 用于关键论文全文补读。如果 MinerU 缺 key、超时或没有 parseable URL，系统会记录状态并降级为 Sciverse-only，不阻塞生成。

### Q4：Skill 系统真的起作用了吗？

回答：

是。Skill 系统被注册为工具，Agent 可以调用 `skills_list_index`、`skills_route_for_phase`、`skills_load_for_phase`、`skills_read_resource`、`skills_unload`。运行后会生成 `skill_trace.json`，记录发现、路由、加载、资源读取和卸载过程。我们也有单元测试覆盖 Skill discovery、routing、loading、unloading。

### Q5：为什么不把所有 skill 一次性加载？

回答：

因为上下文窗口有限，而且第三方 skill 可能很长。我们采用 progressive disclosure：先只读取 metadata，根据当前 phase 选择少量 skill，再加载必要内容。这样节省 token，也降低 prompt injection 风险。

### Q6：多智能体 reviewer 会不会让系统跑不完？

回答：

早期确实可能反复返修。现在 AgentLoop 增加了 `max_revision_rounds=3`。如果 3 轮后仍不通过，系统返回最新草稿，并保留 reviewer feedback 和 check report。这样避免无限循环，同时保留人工审查信息。

### Q7：图片生成如何保证不胡编？

回答：

图片不是事实来源，只是表达层。Figure planner 只给已有 evidence id 的章节插图，caption 会标注 source evidence ids。图片 prompt 明确禁止写论文题名、作者、DOI、citation id、数字 benchmark。事实仍由正文 evidence id 支撑。

### Q8：为什么 `prepare_survey_context` 不直接硬编码 taxonomy？

回答：

硬编码 taxonomy 容易把噪声论文组织进去，产生看似完整但学术判断不足的结构。当前做法是确定性生成 timeline 和 citation map，高阶 outline 由 LLM 基于 evidence pack 生成，并经过输出清洗。这更适合不同主题的 survey。

### Q9：这个系统和普通 RAG 有什么区别？

回答：

普通 RAG 通常是检索后回答。本项目是长程 Harness：有状态 KB、工具循环、Skill 系统、多智能体审查、引用校验、返修预算、图片后处理和运行包导出。它不仅回答问题，而是执行完整的 survey production workflow。

### Q10：最终论文质量不够怎么办？

回答：

Harness 的价值是把质量问题定位到具体环节：是检索不足、证据不足、outline 不好、写作不够、引用失败，还是审查不通过。每个环节都有可审计文件和工具，可以针对性改进，而不是盲目改 prompt。

## 21. 当前局限与未来工作

### 21.1 当前局限

- 小模型在长文返修时可能倾向于扩写而非精准修改。
- MinerU 全文解析耗时较长，现场 demo 建议关闭或低 batch。
- LaTeX 导出目前是基础格式，不是完整 arXiv template。
- 图片生成依赖外部 API，网络失败时会降级 SVG。
- 论文筛选仍依赖模型判断，未来可以加入更强的 ranking 和 dedup 策略。

### 21.2 未来工作

- 加入 Memory 系统，记录多轮使用偏好、领域经验和失败教训。
- 将 reviewer feedback 结构化为 patch plan，减少无目的扩写。
- 加入更强的 citation map 和 bibliography formatter。
- 接入 arXiv / conference LaTeX 模板。
- 增强 MinerU 的全文检索和分段摘要。
- 引入 sub-agent 并行完成 evidence gap search。
- 加入 UI 展示 evidence graph、skill trace 和 run report。

## 22. 推荐答辩总结

可以用下面这段作为结尾：

> 我们的项目核心不是让模型“一次性写一篇综述”，而是构建一个可审计、可返修、可扩展的 Survey Harness。它先通过 Sciverse 和可选 MinerU 构建 evidence KB，再通过 Skill 系统加载写作规范，通过 LLM 生成 outline 和 evidence needs，通过多智能体 reviewer 和 CitationVerifier 约束最终输出，最后生成包含正文、证据包、审查报告、skill trace 和图文导出的完整运行包。这个设计把综述生成从 prompt 工程推进到了 Harness 工程。

## 23. 答辩时最值得展示的代码点

1. `src/state/kb.py`：Evidence KB 和 stable evidence id。
2. `src/tools/literature_kb.py`：Sciverse 检索和 evidence 写入。
3. `src/tools/mineru.py`：可选全文解析和降级策略。
4. `src/tools/survey_context.py`：LLM outline 与 evidence needs。
5. `src/skill_system/manager.py`：progressive disclosure loader。
6. `src/skill_system/tools.py`：Skill 系统工具化。
7. `src/validation/multi_agent.py`：3 路 reviewer。
8. `src/validation/citations.py`：机械引用校验。
9. `src/images/pipeline.py`：章节级图片生成与 fallback。
10. `src/utils/runs.py`：运行包输出。

## 24. 最小可复现实验

### 24.1 环境准备

```bash
pip install -r requirements.txt
cp .env.example .env
```

填写：

```bash
INTERN_API_BASE=...
INTERN_API_KEY=...
SCIVERSE_API_TOKEN=...
```

可选：

```bash
MINERU_API_TOKEN=...
OPENAI_API_KEY=...
```

### 24.2 测试

```bash
python3 -m unittest discover -s tests
python3 -m py_compile main.py $(find src -name '*.py')
```

### 24.3 运行

```bash
python3 main.py "World Models in deep reinforcement learning"
```

### 24.4 查看结果

```bash
cat output/latest_run.json
```

打开：

```text
output/runs/.../survey.html
output/runs/.../evidence_pack.json
output/runs/.../check_report.json
output/runs/.../skill_trace.json
```

## 25. 一页版答辩提纲

```text
1. 问题：普通 LLM 写 survey 容易幻觉引用、结构弱、不可审计。
2. 目标：构建 evidence-grounded Survey Harness。
3. 证据层：Sciverse 检索 + 可选 MinerU 全文解析 + LiteratureKB。
4. Agent 层：AgentLoop + ToolRegistry + Intern-S2 tool calling。
5. Skill 层：metadata discovery -> route -> load -> resource -> unload -> trace。
6. 结构层：prepare_survey_context 生成 timeline/citation map，LLM 生成 outline 和 evidence needs。
7. 写作层：AgentLoop 内完整写作，所有实质性段落引用 evidence id。
8. 质量层：三路 MultiAgentReviewer + CitationVerifier + 3 轮返修预算。
9. 图文层：section-aware figure planner + OpenAI image adapter + SVG fallback。
10. 输出层：Markdown / HTML / LaTeX / evidence pack / check report / skill trace / figure plan。
11. 创新：不是 prompt，而是可审计、可返修、可扩展的 Harness。
```

