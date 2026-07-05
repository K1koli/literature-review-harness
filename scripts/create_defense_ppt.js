const pptxgen = require("pptxgenjs");

const pptx = new pptxgen();
pptx.author = "Literature Review Harness Team";
pptx.company = "SurveyHarness";
pptx.subject = "Evidence-grounded academic survey generation harness";
pptx.title = "Literature Review Harness 答辩";
pptx.lang = "zh-CN";
pptx.theme = {
  headFontFace: "Microsoft YaHei",
  bodyFontFace: "Microsoft YaHei",
  lang: "zh-CN",
};
pptx.defineLayout({ name: "CUSTOM_WIDE", width: 13.333, height: 7.5 });
pptx.layout = "CUSTOM_WIDE";
pptx.margin = 0;

const W = 13.333;
const H = 7.5;
const FONT_CN = "Microsoft YaHei";
const FONT_EN = "Aptos";
const C = {
  bg: "FBFCFE",
  panel: "FFFFFF",
  ink: "152033",
  body: "263142",
  muted: "5F6B7A",
  line: "D5DCE7",
  faint: "EEF3F8",
  teal: "0E766F",
  tealSoft: "DDF2EF",
  blue: "1E4E8C",
  blueSoft: "E6EEF8",
  amber: "B7791F",
  amberSoft: "F6EAD0",
  red: "A6423B",
  redSoft: "F4DEDC",
};

function addFooter(slide, n) {
  slide.addText("Literature Review Harness", {
    x: 0.62, y: 7.08, w: 4.2, h: 0.22,
    fontFace: FONT_EN, fontSize: 9.5, color: C.muted, margin: 0,
  });
  slide.addText(String(n).padStart(2, "0"), {
    x: 12.15, y: 7.06, w: 0.55, h: 0.22,
    fontFace: FONT_EN, fontSize: 10, color: C.muted, align: "right", margin: 0,
  });
}

function title(slide, text, subtitle, n) {
  slide.background = { color: C.bg };
  slide.addText(text, {
    x: 0.62, y: 0.36, w: 8.6, h: 0.5,
    fontFace: FONT_CN, fontSize: 30, bold: true, color: C.ink, margin: 0,
  });
  if (subtitle) {
    slide.addText(subtitle, {
      x: 0.64, y: 0.94, w: 9.6, h: 0.26,
      fontFace: FONT_CN, fontSize: 13.2, color: C.muted, margin: 0,
    });
  }
  slide.addShape(pptx.ShapeType.line, {
    x: 0.62, y: 1.28, w: 12.1, h: 0,
    line: { color: C.line, width: 1.0 },
  });
  addFooter(slide, n);
}

function textBox(slide, text, x, y, w, h, opts = {}) {
  slide.addText(text, {
    x, y, w, h,
    fontFace: opts.fontFace || FONT_CN,
    fontSize: opts.size || 14,
    bold: opts.bold || false,
    color: opts.color || C.body,
    valign: opts.valign || "top",
    align: opts.align || "left",
    margin: opts.margin ?? 0.03,
    breakLine: false,
  });
}

function card(slide, x, y, w, h, head, body, opts = {}) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h, rectRadius: 0.05,
    fill: { color: opts.fill || C.panel },
    line: { color: opts.line || C.line, width: 0.8 },
  });
  slide.addShape(pptx.ShapeType.rect, {
    x, y, w: 0.08, h,
    fill: { color: opts.accent || C.teal },
    line: { color: opts.accent || C.teal },
  });
  textBox(slide, head, x + 0.22, y + 0.16, w - 0.38, 0.3, {
    size: opts.headSize || 15.5,
    bold: true,
    color: opts.headColor || C.ink,
  });
  textBox(slide, body, x + 0.22, y + 0.58, w - 0.38, h - 0.72, {
    size: opts.bodySize || 12.5,
    color: opts.bodyColor || C.body,
  });
}

function callout(slide, text, x, y, w, h, fill = C.blueSoft, color = C.blue) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h, rectRadius: 0.06,
    fill: { color: fill },
    line: { color: fill },
  });
  textBox(slide, text, x + 0.25, y + 0.18, w - 0.5, h - 0.28, {
    size: 17, bold: true, color, align: "center", valign: "mid",
  });
}

function row(slide, x, y, w, cells, widths, opts = {}) {
  let cx = x;
  cells.forEach((cell, i) => {
    const cw = w * widths[i];
    slide.addShape(pptx.ShapeType.rect, {
      x: cx, y, w: cw, h: opts.h || 0.58,
      fill: { color: opts.fill || (i === 0 ? C.faint : C.panel) },
      line: { color: C.line, width: 0.6 },
    });
    textBox(slide, cell, cx + 0.1, y + 0.13, cw - 0.2, (opts.h || 0.58) - 0.18, {
      size: opts.size || 11.5,
      bold: opts.boldFirst && i === 0,
      color: i === 0 ? C.ink : C.body,
      valign: "mid",
    });
    cx += cw;
  });
}

function pipeline(slide, items, y) {
  const x = 0.72;
  const gap = 0.14;
  const w = (11.9 - gap * (items.length - 1)) / items.length;
  items.forEach((item, i) => {
    slide.addShape(pptx.ShapeType.roundRect, {
      x: x + i * (w + gap), y, w, h: 0.86, rectRadius: 0.04,
      fill: { color: i % 2 === 0 ? C.blueSoft : C.tealSoft },
      line: { color: i % 2 === 0 ? C.blue : C.teal, width: 0.8 },
    });
    textBox(slide, item, x + i * (w + gap) + 0.08, y + 0.23, w - 0.16, 0.24, {
      size: 11.2, bold: true, color: C.ink, align: "center", valign: "mid",
    });
  });
}

function addSlide01() {
  const slide = pptx.addSlide();
  slide.background = { color: C.bg };
  slide.addShape(pptx.ShapeType.rect, {
    x: 0, y: 0, w: W, h: 0.18,
    fill: { color: C.teal },
    line: { color: C.teal },
  });
  textBox(slide, "Literature Review Harness", 0.75, 1.08, 10.8, 0.62, {
    fontFace: FONT_EN, size: 36, bold: true, color: C.ink,
  });
  textBox(slide, "面向学术综述生成的 Evidence-Grounded Agent Harness", 0.78, 1.88, 10.5, 0.38, {
    size: 20, bold: true, color: C.teal,
  });
  textBox(slide, "Sciverse / MinerU · Skill System · Multi-Agent Review · Citation Verifier · HTML/LaTeX/Figures", 0.8, 2.48, 11.2, 0.36, {
    fontFace: FONT_EN, size: 14.5, color: C.muted,
  });
  callout(slide, "答辩主张：不是让模型“一次性写文章”，而是把综述生成拆成可检索、可审计、可返修的工程流程。", 0.9, 3.45, 11.4, 1.25, C.blueSoft, C.blue);
  pipeline(slide, ["Retrieve", "Ground", "Plan", "Write", "Review", "Export"], 5.35);
  textBox(slide, "World Models Survey Demo / 代码与运行包均可复查", 0.8, 6.55, 8.2, 0.28, {
    size: 12.5, color: C.muted,
  });
}

function addSlide02() {
  const slide = pptx.addSlide();
  title(slide, "赛题理解与核心挑战", "好的综述不是论文摘要堆叠，而是有证据支撑的知识组织", 2);
  card(slide, 0.75, 1.65, 5.75, 1.15, "赛题要求", "阅读论文、整理分类、总结关键论文、梳理发展脉络、提出未来方向，并输出图文并茂综述。", { accent: C.blue, bodySize: 13.2 });
  card(slide, 6.83, 1.65, 5.75, 1.15, "可靠性要求", "不能有幻觉引用，不能写缺乏事实证据的描述；必须能追踪每个论断来源。", { accent: C.red, bodySize: 13.2 });
  row(slide, 0.95, 3.42, 11.45, ["风险", "直接让 LLM 生成，容易出现不存在论文、弱结构、上下文溢出、不可返修。"], [0.18, 0.82], { h: 0.7, size: 13.2, boldFirst: true });
  row(slide, 0.95, 4.28, 11.45, ["解法", "Harness 先构建 Evidence KB，再通过工具调用、Skill 指令、审查与校验生成最终综述。"], [0.18, 0.82], { h: 0.7, size: 13.2, boldFirst: true });
  row(slide, 0.95, 5.14, 11.45, ["目标", "让输出像一篇规范综述，同时保留证据包、审查报告、运行 trace，方便答辩和复查。"], [0.18, 0.82], { h: 0.7, size: 13.2, boldFirst: true });
}

function addSlide03() {
  const slide = pptx.addSlide();
  title(slide, "总体架构", "AgentLoop 负责主流程，Skill 是可发现、可加载、可卸载的策略层", 3);
  pipeline(slide, ["Topic", "Sciverse", "MinerU", "Evidence KB", "Skill Router", "Survey Context", "Draft", "Verify"], 1.65);
  card(slide, 0.78, 3.0, 3.8, 2.15, "输入与检索", "用户给出主题。\nSciverse 返回论文片段和元数据。\nMinerU 可选补读全文解析。", { accent: C.blue, bodySize: 13 });
  card(slide, 4.78, 3.0, 3.8, 2.15, "结构与写作", "Evidence KB 统一证据。\nLLM 生成 outline / section plan。\n写作 Skill 注入阶段规范。", { accent: C.teal, bodySize: 13 });
  card(slide, 8.78, 3.0, 3.8, 2.15, "审查与导出", "三路 reviewer 提反馈。\nCitationVerifier 机械校验。\n输出 md/html/tex/figures。", { accent: C.amber, bodySize: 13 });
  callout(slide, "关键变化：把“写一篇综述”变成“有状态、有工具、有证据、有返修”的工作流。", 1.0, 5.75, 11.3, 0.78, C.tealSoft, C.teal);
}

function addSlide04() {
  const slide = pptx.addSlide();
  title(slide, "证据层设计：Sciverse + MinerU + LiteratureKB", "先建立可信材料，再进入写作", 4);
  card(slide, 0.8, 1.55, 3.6, 2.45, "Sciverse", "快速检索相关论文。\n返回 snippets、url、metadata、score。\n适合作为综述初始证据池。", { accent: C.blue });
  card(slide, 4.86, 1.55, 3.6, 2.45, "MinerU", "对关键论文补读全文。\n解析 PDF 为可搜索文本。\n失败不阻断主流程。", { accent: C.teal });
  card(slide, 8.92, 1.55, 3.6, 2.45, "LiteratureKB", "统一 PaperRecord、EvidenceRecord、ParsedDocument。\n生成稳定 paper_id / evidence_id。", { accent: C.amber });
  row(slide, 0.95, 4.75, 11.45, ["引用粒度", "正文引用的不是“模型记忆”，而是 KB 中真实存在的 evidence id，例如 P001-E01。"], [0.22, 0.78], { h: 0.72, size: 13.4, boldFirst: true });
  row(slide, 0.95, 5.63, 11.45, ["补读策略", "Sciverse 片段不足时，Agent 可调用 parsed paper 工具读取 MinerU 原文解析文件。"], [0.22, 0.78], { h: 0.72, size: 13.4, boldFirst: true });
}

function addSlide05() {
  const slide = pptx.addSlide();
  title(slide, "工具层：让模型在边界内自主工作", "工具暴露能力，Harness 管理状态和安全边界", 5);
  row(slide, 0.82, 1.55, 11.7, ["工具类别", "代表工具", "作用"], [0.22, 0.34, 0.44], { h: 0.58, size: 12.6, boldFirst: true, fill: C.blueSoft });
  const rows = [
    ["证据构建", "build_literature_kb / search_literature", "检索、去重、构造初始证据库"],
    ["证据读取", "list_evidence / read_evidence", "让模型按 evidence id 精读材料"],
    ["全文补读", "list_parsed_papers / read_parsed_paper", "需要更细事实时读取 MinerU 解析文本"],
    ["结构规划", "prepare_survey_context", "基于 KB 生成 outline、timeline、evidence needs"],
    ["Skill 系统", "skills_route / load / resource / unload", "按阶段加载写作协议并记录 trace"],
  ];
  rows.forEach((r, i) => row(slide, 0.82, 2.18 + i * 0.72, 11.7, r, [0.22, 0.34, 0.44], { h: 0.62, size: 11.4, boldFirst: true }));
  callout(slide, "模型不是无约束生成：它必须通过工具读材料、建上下文、再写作。", 1.18, 6.05, 10.95, 0.58, C.tealSoft, C.teal);
}

function addSlide06() {
  const slide = pptx.addSlide();
  title(slide, "Survey Context：从证据到写作计划", "不是硬编码大纲，而是让 LLM 基于证据做学术组织", 6);
  card(slide, 0.78, 1.55, 3.75, 2.45, "确定性压缩", "coverage\npaper timeline\ncitation map\navailable evidence ids", { accent: C.blue, bodySize: 14 });
  card(slide, 4.78, 1.55, 3.75, 2.45, "LLM 判断", "recommended outline\nsection plan\nselected papers\nevidence needs", { accent: C.teal, bodySize: 14 });
  card(slide, 8.78, 1.55, 3.75, 2.45, "清洗与约束", "过滤非法 paper id\n不伪造模板\n保留 evidence 缺口\n供下一步补读", { accent: C.amber, bodySize: 14 });
  row(slide, 0.95, 4.88, 11.45, ["为什么需要这一步", "综述的逻辑、技术谱系、时间脉络和研究议程应来自证据组织，而不是固定模板。"], [0.24, 0.76], { h: 0.74, size: 13.3, boldFirst: true });
  row(slide, 0.95, 5.78, 11.45, ["输出给写作", "AgentLoop 在最终写作时同时看到 KB 摘要、outline、section plan、skill 指令和补读结果。"], [0.24, 0.76], { h: 0.74, size: 13.3, boldFirst: true });
}

function addSlide07() {
  const slide = pptx.addSlide();
  title(slide, "Skill System：渐进式披露", "满足赛题对 skill 管理、发现、注入、卸载的要求", 7);
  row(slide, 0.86, 1.52, 11.6, ["能力", "实现方式", "价值"], [0.2, 0.45, 0.35], { h: 0.58, size: 12.6, boldFirst: true, fill: C.tealSoft });
  const data = [
    ["统一管理", "SkillManager 扫描 skills/ 下的 SKILL.md 与 metadata", "外部 skill 可直接加入目录"],
    ["模型发现", "list_index 只返回短描述、phase、roles", "节省上下文窗口"],
    ["按需加载", "route_for_phase + load_for_phase", "只加载当前阶段需要内容"],
    ["资源与脚本", "read_resource / run_script 带路径边界", "可用但可控"],
    ["卸载与审计", "unload + skill_trace.json", "防上下文污染，可复查"],
  ];
  data.forEach((r, i) => row(slide, 0.86, 2.15 + i * 0.73, 11.6, r, [0.2, 0.45, 0.35], { h: 0.63, size: 11.2, boldFirst: true }));
  callout(slide, "Skill 不是替代 Harness，而是每个阶段可插拔的操作协议。", 1.25, 6.05, 10.8, 0.58, C.blueSoft, C.blue);
}

function addSlide08() {
  const slide = pptx.addSlide();
  title(slide, "AgentLoop 中的写作流程", "保留基础 pipeline，同时让 skill 成为策略层", 8);
  pipeline(slide, ["检索", "读证据", "建上下文", "加载写作 Skill", "生成完整草稿", "审查返修"], 1.55);
  card(slide, 0.82, 2.95, 5.55, 2.05, "为什么不完全依赖 Skill", "如果外部 skill 不适配综述任务，Harness 仍要能完成基础写作。\n因此保留稳定的 AgentLoop 主流程。", { accent: C.blue, bodySize: 13.1 });
  card(slide, 6.92, 2.95, 5.55, 2.05, "为什么不分块写全文", "分节生成容易造成段落割裂。\n当前采用整体草稿 + 结构反馈 + 返修机制。", { accent: C.teal, bodySize: 13.1 });
  row(slide, 1.0, 5.68, 11.3, ["最终设计", "写作发生在 AgentLoop 内；Skill 负责注入规范、模板、审查标准或辅助脚本。"], [0.22, 0.78], { h: 0.72, size: 13.2, boldFirst: true });
}

function addSlide09() {
  const slide = pptx.addSlide();
  title(slide, "返修机制：Multi-Agent Review", "让模型输出后继续被三个专门 reviewer 检查", 9);
  card(slide, 0.8, 1.45, 3.7, 2.15, "内容质量 Reviewer", "检查是否像 survey：\n有 synthesis、comparison、limitations、future agenda。", { accent: C.blue, bodySize: 12.7 });
  card(slide, 4.82, 1.45, 3.7, 2.15, "引用准确 Reviewer", "检查段落是否有证据。\n避免 doc_id、offset、工具日志进入正文。", { accent: C.red, bodySize: 12.7 });
  card(slide, 8.84, 1.45, 3.7, 2.15, "结构完整 Reviewer", "检查 abstract、main sections、comparison、references 是否完整。", { accent: C.teal, bodySize: 12.7 });
  row(slide, 0.95, 4.35, 11.45, ["触发方式", "LLM 输出草稿后，asyncio.gather 并行调用 3 个审查 prompt，返回 JSON {passed, issues, suggestions}。"], [0.23, 0.77], { h: 0.72, size: 12.8, boldFirst: true });
  row(slide, 0.95, 5.25, 11.45, ["返修方式", "任一 reviewer 不通过，就把 Multi-Agent Review Results 注入消息历史，进入下一轮 LLM 修复。"], [0.23, 0.77], { h: 0.72, size: 12.8, boldFirst: true });
}

function addSlide10() {
  const slide = pptx.addSlide();
  title(slide, "Citation Verifier：机械校验引用", "用确定性规则兜底，减少幻觉引用", 10);
  row(slide, 0.9, 1.55, 11.5, ["检查项", "规则", "失败后处理"], [0.24, 0.44, 0.32], { h: 0.58, size: 12.5, boldFirst: true, fill: C.redSoft });
  const data = [
    ["未知 evidence id", "正文引用必须存在于 KB", "要求模型替换或删除"],
    ["缺少证据", "长段落不能无 citation", "要求补 citation 或弱化表述"],
    ["污染信息", "禁止 doc_id、offset、tool log 进入正文", "要求清洗正文"],
    ["References", "只列正文实际使用过的论文", "重建 references"],
  ];
  data.forEach((r, i) => row(slide, 0.9, 2.2 + i * 0.78, 11.5, r, [0.24, 0.44, 0.32], { h: 0.66, size: 11.8, boldFirst: true }));
  callout(slide, "LLM reviewer 负责学术质量；CitationVerifier 负责可判定的引用事实。", 1.25, 5.95, 10.8, 0.62, C.amberSoft, C.amber);
}

function addSlide11() {
  const slide = pptx.addSlide();
  title(slide, "图片生成模块", "图根据章节和证据规划，不把图片当事实来源", 11);
  card(slide, 0.8, 1.52, 3.65, 2.35, "Figure Planner", "读取 survey.md。\n识别适合图示的章节。\n根据 evidence ids 生成 figure_plan。", { accent: C.blue, bodySize: 13 });
  card(slide, 4.86, 1.52, 3.65, 2.35, "Image Generator", "OpenAI-compatible API。\n支持第三方 base_url。\n可配置 model、size、quality。", { accent: C.teal, bodySize: 13 });
  card(slide, 8.92, 1.52, 3.65, 2.35, "Vector Fallback", "时间线、矩阵等结构图优先 SVG。\nAPI 失败不会阻断主链路。", { accent: C.amber, bodySize: 13 });
  row(slide, 0.95, 4.75, 11.45, ["控制原则", "图不宜过多；默认根据章节必要性规划，最多少量关键图，并在 caption 中保留 evidence ids。"], [0.22, 0.78], { h: 0.72, size: 13, boldFirst: true });
  row(slide, 0.95, 5.63, 11.45, ["适合图型", "技术谱系、论文时间线、方法比较矩阵、贡献关系图；避免无信息装饰图。"], [0.22, 0.78], { h: 0.72, size: 13, boldFirst: true });
}

function addSlide12() {
  const slide = pptx.addSlide();
  title(slide, "输出组织：一次运行就是一个可复查包", "不是只导出 Markdown", 12);
  row(slide, 0.9, 1.45, 11.5, ["文件", "内容", "答辩价值"], [0.3, 0.36, 0.34], { h: 0.58, size: 12.5, boldFirst: true, fill: C.blueSoft });
  const data = [
    ["survey.md / html / tex", "综述正文与展示格式", "可直接展示或继续排版"],
    ["evidence_pack.json", "论文、证据、解析文档", "证明材料来源"],
    ["check_report.json", "引用校验结果", "说明无幻觉引用策略"],
    ["skill_trace.json", "Skill 发现、加载、卸载记录", "展示 skill system"],
    ["figure_plan.json / figures", "图片计划和图像资产", "图文并茂输出"],
  ];
  data.forEach((r, i) => row(slide, 0.9, 2.08 + i * 0.72, 11.5, r, [0.3, 0.36, 0.34], { h: 0.62, size: 11.5, boldFirst: true }));
  callout(slide, "output/runs/YYYYMMDD-HHMM-topic/ 保存一次完整运行。", 1.35, 6.1, 10.6, 0.54, C.tealSoft, C.teal);
}

function addSlide13() {
  const slide = pptx.addSlide();
  title(slide, "当前验证结果", "验证重点是链路通不通、机制是否生效", 13);
  card(slide, 0.82, 1.55, 3.6, 2.2, "单元测试", "Skill system、reviewer、tool registry、image pipeline 等核心模块已有测试覆盖。", { accent: C.blue, bodySize: 13.3 });
  card(slide, 4.86, 1.55, 3.6, 2.2, "完整链路", "能完成检索、KB 构建、outline、写作、review、引用校验和导出。", { accent: C.teal, bodySize: 13.3 });
  card(slide, 8.9, 1.55, 3.6, 2.2, "可观测性", "输出 evidence_pack、check_report、skill_trace、figure_plan，便于复查。", { accent: C.amber, bodySize: 13.3 });
  row(slide, 0.95, 4.65, 11.45, ["答辩展示方式", "可以从输出 HTML 看最终论文，从 JSON 看证据，从 skill_trace 看 skill 调用，从 check_report 看引用检查。"], [0.24, 0.76], { h: 0.8, size: 13, boldFirst: true });
  row(slide, 0.95, 5.62, 11.45, ["风险控制", "API 失败、MinerU 超时、图片失败都不会直接毁掉主链路，而是降级或写入报告。"], [0.24, 0.76], { h: 0.8, size: 13, boldFirst: true });
}

function addSlide14() {
  const slide = pptx.addSlide();
  title(slide, "赛题要求映射", "逐项对应，不只做演示效果", 14);
  row(slide, 0.86, 1.45, 11.6, ["赛题要求", "系统实现"], [0.34, 0.66], { h: 0.6, size: 13, boldFirst: true, fill: C.tealSoft });
  const data = [
    ["阅读学术论文", "Sciverse 片段检索 + MinerU 全文解析工具"],
    ["整理分类与关键论文", "Evidence KB + LLM outline / section plan"],
    ["梳理发展脉络", "timeline、citation map、survey context"],
    ["未来研究方向", "写作 prompt 与 reviewer 强制检查 research agenda"],
    ["无幻觉引用", "evidence id 引用 + CitationVerifier"],
    ["图文并茂", "figure planner + image generator + SVG fallback"],
    ["Skill 系统", "发现、路由、加载、资源读取、脚本执行、卸载、trace"],
  ];
  data.forEach((r, i) => row(slide, 0.86, 2.08 + i * 0.56, 11.6, r, [0.34, 0.66], { h: 0.5, size: 11.4, boldFirst: true }));
}

function addSlide15() {
  const slide = pptx.addSlide();
  title(slide, "局限与下一步", "诚实说明当前边界，也说明为什么架构可继续扩展", 15);
  card(slide, 0.82, 1.55, 5.55, 3.35, "当前局限", "长综述的篇章质量仍受模型能力影响。\n检索质量依赖 Sciverse 返回结果。\nMinerU 解析需要 URL 和时间预算。\nLaTeX 目前是基础导出，不是完整会议模板。", { accent: C.red, bodySize: 13.2 });
  card(slide, 6.92, 1.55, 5.55, 3.35, "下一步优化", "Memory 记录长期偏好和失败经验。\n更强 paper ranking 与 bibliography formatter。\nReviewer 输出转成 patch plan。\n接入 arXiv / conference LaTeX 模板。", { accent: C.teal, bodySize: 13.2 });
  callout(slide, "重要的是：问题不再隐藏在一次生成里，而是落到可定位、可替换、可优化的 Harness 环节。", 1.0, 5.65, 11.35, 0.8, C.blueSoft, C.blue);
}

function addSlide16() {
  const slide = pptx.addSlide();
  slide.background = { color: C.bg };
  slide.addShape(pptx.ShapeType.rect, {
    x: 0, y: 0, w: W, h: 0.18,
    fill: { color: C.teal },
    line: { color: C.teal },
  });
  textBox(slide, "总结", 0.85, 0.85, 3.2, 0.62, {
    size: 34, bold: true, color: C.ink,
  });
  callout(slide, "我们把学术综述生成从“写作 prompt”推进到“Evidence-grounded Agent Harness”。", 0.92, 1.75, 11.5, 0.92, C.tealSoft, C.teal);
  row(slide, 1.0, 3.18, 11.3, ["Evidence-first", "所有实质论断尽量落到 evidence id，输出 evidence_pack。"], [0.28, 0.72], { h: 0.68, size: 13.2, boldFirst: true });
  row(slide, 1.0, 4.0, 11.3, ["Agentic", "模型通过工具完成检索、阅读、规划、补读和写作。"], [0.28, 0.72], { h: 0.68, size: 13.2, boldFirst: true });
  row(slide, 1.0, 4.82, 11.3, ["Skill-aware", "Skill 渐进式加载，不把所有说明一次塞进上下文。"], [0.28, 0.72], { h: 0.68, size: 13.2, boldFirst: true });
  row(slide, 1.0, 5.64, 11.3, ["Verified", "Multi-agent review 与 CitationVerifier 共同构成质量门禁。"], [0.28, 0.72], { h: 0.68, size: 13.2, boldFirst: true });
  textBox(slide, "Q&A", 10.7, 6.68, 1.65, 0.35, { fontFace: FONT_EN, size: 24, bold: true, color: C.blue, align: "right" });
}

[
  addSlide01, addSlide02, addSlide03, addSlide04,
  addSlide05, addSlide06, addSlide07, addSlide08,
  addSlide09, addSlide10, addSlide11, addSlide12,
  addSlide13, addSlide14, addSlide15, addSlide16,
].forEach((fn) => fn());

for (let i = 0; i < pptx._slides.length; i += 1) {
  const slide = pptx._slides[i];
  slide.addNotes(`Slide ${i + 1}: 答辩时围绕 docs/DEFENSE.md 展开，重点讲清该页对应的设计动机、代码模块和可审计产物。`);
}

pptx.writeFile({ fileName: "output/defense_presentation.pptx" });
