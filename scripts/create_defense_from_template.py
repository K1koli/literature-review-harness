from __future__ import annotations

import os
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.util import Inches, Pt


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = Path(os.environ.get("DEFENSE_TEMPLATE", ROOT / "templates" / "defense_template.pptx"))
OUTPUT = ROOT / "output" / "defense_template_version.pptx"

# Keep the user's template pages; remove irrelevant single-paper result pages.
SELECTED_SLIDES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 27, 28]

NAV_MAP = {
    "基本信息": "项目概述",
    "研究背景": "证据工具",
    "研究思路": "Skill系统",
    "研究结果": "写作返修",
    "结论讨论": "图片导出",
    "创新启发": "总结展望",
    "结论与讨论": "图片与导出",
    "创新与启发": "总结与展望",
}

BLUE = "1D4A8F"
DARK = "1F2937"
MUTED = "4B5563"
LIGHT = "EAF2FF"
PALE = "F5F8FC"


def remove_slide(prs: Presentation, idx: int) -> None:
    r_id = prs.slides._sldIdLst[idx].rId
    prs.part.drop_rel(r_id)
    del prs.slides._sldIdLst[idx]


def remove_shape(shape) -> None:
    shape.element.getparent().remove(shape.element)


def set_text(shape, text: str, size: float = 18, bold: bool = False, color: str = DARK) -> None:
    if not hasattr(shape, "text_frame"):
        return
    tf = shape.text_frame
    tf.clear()
    tf.word_wrap = True
    for idx, line in enumerate(text.split("\n")):
        p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
        p.text = line
        p.font.name = "Microsoft YaHei"
        p.font.size = Pt(size)
        p.font.bold = bold
        p.font.color.rgb = RGBColor.from_string(color)
        p.space_after = Pt(5)


def add_text(slide, text: str, x: float, y: float, w: float, h: float, size: float = 18, bold: bool = False, color: str = DARK):
    shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    set_text(shape, text, size=size, bold=bold, color=color)
    return shape


def add_panel(slide, title: str, body: str, x: float, y: float, w: float, h: float, title_size: float = 19, body_size: float = 17):
    # Use simple filled text panel only; no decorative vector diagrams.
    rect = slide.shapes.add_shape(1, Inches(x), Inches(y), Inches(w), Inches(h))
    rect.fill.solid()
    rect.fill.fore_color.rgb = RGBColor.from_string(PALE)
    rect.line.color.rgb = RGBColor.from_string("D7E2F2")
    add_text(slide, title, x + 0.18, y + 0.16, w - 0.36, 0.32, size=title_size, bold=True, color=BLUE)
    add_text(slide, body, x + 0.18, y + 0.62, w - 0.36, h - 0.78, size=body_size, color=DARK)


def replace_text(shape, mapping: dict[str, str]) -> None:
    if not hasattr(shape, "text_frame"):
        return
    current = shape.text
    new = current
    for old, value in mapping.items():
        new = new.replace(old, value)
    if new != current:
        set_text(shape, new, size=13 if len(new) < 10 else 12, bold=len(new) < 10)


def replace_exact(slide, old: str, new: str, size: float = 18, bold: bool = False, color: str = DARK) -> None:
    for shape in slide.shapes:
        if hasattr(shape, "text_frame") and shape.text.strip() == old:
            set_text(shape, new, size=size, bold=bold, color=color)


def replace_contains(slide, needle: str, new: str, size: float = 18, bold: bool = False, color: str = DARK) -> None:
    for shape in slide.shapes:
        if hasattr(shape, "text_frame") and needle in shape.text:
            set_text(shape, new, size=size, bold=bold, color=color)


def apply_nav(prs: Presentation) -> None:
    for slide in prs.slides:
        for shape in slide.shapes:
            replace_text(shape, NAV_MAP)


def clean_media(slide) -> None:
    for shape in list(slide.shapes):
        if shape.shape_type in {MSO_SHAPE_TYPE.PICTURE, MSO_SHAPE_TYPE.CHART, MSO_SHAPE_TYPE.GROUP}:
            x = shape.left / 914400
            y = shape.top / 914400
            if x > 1.8 or y > 0.8:
                remove_shape(shape)


def clear_content_area(slide) -> None:
    for shape in list(slide.shapes):
        x = shape.left / 914400
        y = shape.top / 914400
        # Preserve left navigation and top section title.
        if x > 1.85 and y > 0.82:
            remove_shape(shape)


def set_section_title(slide, title: str) -> None:
    for shape in slide.shapes:
        x = shape.left / 914400
        y = shape.top / 914400
        if hasattr(shape, "text_frame") and x > 2.0 and y < 0.8 and shape.text.strip():
            set_text(shape, title, size=21, bold=True, color=DARK)
            return
    add_text(slide, title, 2.45, 0.18, 7.5, 0.45, size=21, bold=True)


def make_body_slide(slide, title: str, panels: list[tuple[str, str]]) -> None:
    clean_media(slide)
    clear_content_area(slide)
    set_section_title(slide, title)
    if len(panels) == 1:
        add_panel(slide, panels[0][0], panels[0][1], 2.35, 1.32, 10.2, 4.95, title_size=21, body_size=19)
    elif len(panels) == 2:
        add_panel(slide, panels[0][0], panels[0][1], 2.35, 1.32, 4.95, 4.95, title_size=20.5, body_size=17.8)
        add_panel(slide, panels[1][0], panels[1][1], 7.55, 1.32, 4.95, 4.95, title_size=20.5, body_size=17.8)
    else:
        add_panel(slide, panels[0][0], panels[0][1], 2.25, 1.20, 3.28, 5.15, body_size=15.5)
        add_panel(slide, panels[1][0], panels[1][1], 5.82, 1.20, 3.28, 5.15, body_size=15.5)
        add_panel(slide, panels[2][0], panels[2][1], 9.38, 1.20, 3.28, 5.15, body_size=15.5)


def fill_cover(slide) -> None:
    replacements = {
        "Developmental hematopoietic stem cell variation explains clonal hematopoiesis later in life": "Literature Review Harness",
        "发育性造血干细胞变异解释了生命后期的克隆造血": "面向学术综述生成的 Evidence-Grounded Agent Harness",
        "课题小组：组会文献汇报": "赛题答辩：学术论文综述生成 Harness",
        "汇报人：XXX": "汇报人：SurveyHarness Team",
        "汇报日期：20XX.XX.XX": "汇报日期：2026.07.05",
    }
    for shape in slide.shapes:
        if not hasattr(shape, "text_frame"):
            continue
        text = shape.text.strip()
        if text == "Developmental hematopoietic stem cell variation explains clonal hematopoiesis later in life":
            set_text(shape, replacements[text], size=29, bold=True)
            shape.top = Inches(1.72)
        elif text == "发育性造血干细胞变异解释了生命后期的克隆造血":
            set_text(shape, replacements[text], size=18, bold=True)
            shape.top = Inches(2.75)
        elif text == "课题小组：组会文献汇报":
            set_text(shape, replacements[text], size=17, bold=True)
            shape.top = Inches(3.42)
        elif text == "汇报人：XXX":
            set_text(shape, replacements[text], size=11, color="FFFFFF")
        elif text == "汇报日期：20XX.XX.XX":
            set_text(shape, replacements[text], size=11, color="FFFFFF")


def fill_contents(slide) -> None:
    mapping = {
        "基本信息": "项目概述",
        "研究背景": "证据工具",
        "研究思路": "Skill系统",
        "研究结果": "写作返修",
        "结论与讨论": "图片与导出",
        "创新与启发": "总结与展望",
    }
    for shape in slide.shapes:
        if hasattr(shape, "text_frame") and shape.text.strip() in mapping:
            set_text(shape, mapping[shape.text.strip()], size=18, bold=True)


def fill_project_info(slide) -> None:
    clean_media(slide)
    clear_content_area(slide)
    set_section_title(slide, "1 项目概述")
    add_panel(
        slide,
        "项目定位",
        "面向学术论文综述生成的 agent harness。\n\n不是一次性 prompt 写作，而是围绕检索、证据、结构、写作、审查、引用校验和导出形成完整流程。",
        2.35, 1.15, 4.85, 5.25, body_size=17,
    )
    add_panel(
        slide,
        "核心能力",
        "Sciverse 召回论文片段。\nMinerU 按需补读全文。\nEvidence KB 绑定事实来源。\nSkill 系统注入写作协议。\nMulti-Agent Review 推动返修。\nCitationVerifier 检查引用。",
        7.48, 1.15, 5.05, 5.25, body_size=16.3,
    )


SLIDE_CONTENT = [
    (
        "2.1 赛题目标与评价重点",
        [
            ("赛题目标", "输入：一个学术主题。\n过程：阅读论文、分类整理、总结关键论文、梳理发展脉络。\n输出：图文并茂的综述，包含未来研究方向。"),
            ("评价重点", "不是只生成 World Models 这一篇。\n更重要的是：Harness 可复用、可审计、可返修。\n底线：减少幻觉引用和无证据描述。"),
        ],
    ),
    (
        "2.2 为什么不能直接让模型写？",
        [
            ("直接生成的风险", "引用可能被编造：论文、作者、年份都可能不存在。\n证据不可追踪：正文不知道来自哪个检索片段。\n结构弱：容易变成摘要拼接。"),
            ("Harness 的必要性", "把任务拆成可检查步骤：检索、建库、读证据、规划、写作、审查、校验、导出。\n每一步都有输入、输出和审计文件。"),
        ],
    ),
    (
        "3 主流程：从主题到运行包",
        [
            ("AgentLoop", "接收用户主题。\n构造 system prompt 和 tool schema。\n模型通过 tool calls 调用检索、证据读取、skill、survey context。"),
            ("状态产物", "正文：survey.md / html / tex。\n证据：evidence_pack.json。\n质量：check_report.json。\n过程：skill_trace 和 figure_plan。"),
        ],
    ),
    (
        "4.1 Sciverse：先获得论文片段",
        [
            ("调用目标", "Sciverse 负责广度召回。\n输入：topic / query。\n输出：论文片段、元数据、URL、score、doc_id。\n优点：快，适合建初始证据池。"),
            ("在链路中的作用", "候选论文进入 Evidence KB。\n片段变成 EvidenceRecord。\n后续 outline、写作、引用校验都从这里拿材料。"),
        ],
    ),
    (
        "4.2 MinerU：关键论文全文补读",
        [
            ("为什么需要 MinerU", "Sciverse 片段适合召回，但关键论断需要上下文。\nMinerU 将 PDF 解析为可搜索全文。\n它用于补读方法、实验、限制和结论细节。"),
            ("调用策略", "不是每篇都强制解析。\n当 outline 或 reviewer 提出 evidence needs 时再补读。\n这样控制 35B 模型的上下文负担。"),
        ],
    ),
    (
        "4.3 Evidence KB 与 Citation Map",
        [
            ("Evidence KB", "PaperRecord：论文级信息。\nEvidenceRecord：片段级证据。\nParsedDocument：MinerU 全文。\n每条证据有稳定 ID，如 P001-E01。"),
            ("Citation Map", "正文引用必须指向真实 evidence id。\n未知 ID 会被 verifier 拦截。\nReferences 只列正文实际使用过的论文。"),
        ],
    ),
    (
        "5.1 Tool Registry：可控工具层",
        [
            ("暴露的工具", "检索：build_literature_kb / search_literature。\n证据：list_evidence / read_evidence。\n全文：list_parsed_papers / read_parsed_paper。\n规划：prepare_survey_context。"),
            ("边界控制", "工具结果结构化返回。\n长文本会截断。\n失败写入状态，不直接崩溃。\n返修时仍可继续读取 evidence 或 parsed paper。"),
        ],
    ),
    (
        "5.2 Survey Context：证据到结构",
        [
            ("确定性压缩", "从 KB 生成 coverage、timeline、citation map、available evidence ids。\n这些部分可复现、可检查，避免结构规划完全靠模型记忆。"),
            ("LLM 规划", "LLM 基于证据生成 recommended outline、section plan、selected papers、evidence needs。\n代码再清洗非法 paper id。"),
        ],
    ),
    (
        "6.1 Skill System：渐进式披露",
        [
            ("发现与路由", "SkillManager 扫描 skills/。\nlist_index 只暴露 name、description、phase、roles。\n模型先发现，再决定是否加载，避免上下文爆炸。"),
            ("加载与卸载", "route_for_phase 选择少量 skill。\nload_for_phase 注入当前阶段 SKILL.md。\nunload 清理 active skill，并写入 skill_trace。"),
        ],
    ),
    (
        "6.2 Writing Skill：不是替代主流程",
        [
            ("我们的取舍", "不把写作完全交给外部 skill。\nAgentLoop 保留基础写作能力。\n如果没有合适 skill，系统仍能完成主流程。"),
            ("Skill 的角色", "writing skill：综述写作规范。\ncitation skill：引用约束。\narxiv/export skill：格式和导出协议。\n它们是策略层，不替代 harness。"),
        ],
    ),
    (
        "7.1 写作阶段：整体草稿生成",
        [
            ("为什么不分块写", "分块写全文容易造成段落割裂。\n当前采用整体草稿生成。\n再通过 reviewer 和 verifier 做结构化返修。"),
            ("模型看到什么", "Evidence KB 摘要。\noutline 和 section plan。\n写作 skill 指令。\n补读结果。\n引用规则和禁止项。"),
        ],
    ),
    (
        "7.2 Multi-Agent Review：三路审查",
        [
            ("并行审查", "内容质量 reviewer：是否像 survey。\n引用准确 reviewer：证据是否足够。\n结构完整 reviewer：章节是否完整。\n三者并行返回 JSON。"),
            ("返修机制", "任一 reviewer 不通过：\n把 issues 和 suggestions 合并成 Multi-Agent Review Results。\n注入消息历史，进入下一轮修复。"),
        ],
    ),
    (
        "7.3 CitationVerifier：机械引用校验",
        [
            ("检查什么", "未知 evidence id。\n长段落无引用。\nraw doc_id / offset 泄漏。\nReferences 与正文引用不一致。"),
            ("为什么重要", "Reviewer 判断学术质量。\nCitationVerifier 守住可判定底线。\n让“无幻觉引用”从口头承诺变成程序检查。"),
        ],
    ),
    (
        "8.1 图片生成与多格式导出",
        [
            ("图片生成", "Figure planner 根据章节和 evidence ids 判断是否需要图。\n图不作为事实来源，只表达结构。\nAPI 失败时使用 SVG fallback。"),
            ("导出格式", "正文：Markdown / HTML / LaTeX。\n证据：evidence_pack。\n质量：check_report。\n过程：skill_trace、figure_plan、figures。"),
        ],
    ),
    (
        "8.2 当前验证与运行结果",
        [
            ("验证内容", "测试覆盖 skill system、tool registry、multi-agent review、citation verifier、image planner、exporter。\n重点验证机制，而不是只验证一次输出。"),
            ("答辩展示", "survey.html：看正文。\nevidence_pack：看证据。\ncheck_report：看引用校验。\nskill_trace：看 skill 调用。"),
        ],
    ),
    (
        "9 局限与下一步",
        [
            ("当前局限", "长综述质量仍受模型能力影响。\nSciverse 检索质量决定材料上限。\nMinerU 解析依赖 URL 和时间预算。\nLaTeX 仍是基础导出。"),
            ("下一步", "加入 Memory 系统。\n强化 ranking / dedup / bibliography formatter。\n把 reviewer feedback 转成 patch plan。\n接入正式 arXiv 模板。"),
        ],
    ),
]


def fill_innovation(slide) -> None:
    clean_media(slide)
    clear_content_area(slide)
    set_section_title(slide, "10 创新与启发")
    add_panel(
        slide,
        "创新点",
        "Evidence-first：先构建证据再写正文。\nAgentic：模型通过工具完成长程任务。\nSkill-aware：按阶段发现、加载、卸载 skill。\nVerified：多智能体审查 + 机械引用校验。",
        2.35, 1.25, 4.95, 4.95, body_size=16.5,
    )
    add_panel(
        slide,
        "启发",
        "好的综述生成系统不应只是 prompt，而应是可追踪的工程链路。\n\n质量问题要落到可定位模块：检索、证据、结构、写作、返修、引用和导出。",
        7.55, 1.25, 4.95, 4.95, body_size=16.5,
    )


def fill_closing(slide) -> None:
    replace_contains(slide, "汇报完毕", "汇报完毕，敬请老师同学批评指正！", size=28, bold=True, color="FFFFFF")
    replace_contains(slide, "20XX年XX大学XX学院专业", "Literature Review Harness · Evidence-grounded Survey Generation", size=13, color="FFFFFF")
    replace_contains(slide, "汇报人：XXX", "汇报人：SurveyHarness Team", size=12)
    replace_contains(slide, "汇报日期：20XX.XX.XX", "汇报日期：2026.07.05", size=12)


def main() -> None:
    prs = Presentation(TEMPLATE)
    for idx in reversed(range(len(prs.slides))):
        if idx not in SELECTED_SLIDES:
            remove_slide(prs, idx)

    apply_nav(prs)
    fill_cover(prs.slides[0])
    fill_contents(prs.slides[1])
    fill_project_info(prs.slides[2])

    slides = list(prs.slides)
    for slide, (title, panels) in zip(slides[3:-2], SLIDE_CONTENT):
        make_body_slide(slide, title, panels)

    # Convert the final two template pages into summary pages.
    fill_innovation(slides[-2])
    fill_closing(slides[-1])

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()
