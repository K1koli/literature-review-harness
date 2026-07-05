const pptxgen = require("pptxgenjs");

const pptx = new pptxgen();
pptx.author = "Literature Review Harness Team";
pptx.company = "SurveyHarness";
pptx.subject = "Defense deck generated with PPT Master-inspired workflow";
pptx.title = "Literature Review Harness 答辩";
pptx.lang = "zh-CN";
pptx.defineLayout({ name: "CUSTOM_WIDE", width: 13.333, height: 7.5 });
pptx.layout = "CUSTOM_WIDE";
pptx.margin = 0;
pptx.theme = {
  headFontFace: "Songti SC",
  bodyFontFace: "Microsoft YaHei",
  lang: "zh-CN",
};

const W = 13.333;
const H = 7.5;
const FONT_TITLE = "Songti SC";
const FONT_BODY = "Microsoft YaHei";
const FONT_EN = "Aptos";
const C = {
  paper: "FCFCFA",
  white: "FFFFFF",
  ink: "111827",
  body: "1F2937",
  muted: "586174",
  line: "D1D5DB",
  faint: "F3F4F6",
  navy: "14213D",
  blue: "1F4E79",
  teal: "0F766E",
  red: "8B1E1E",
  gold: "9A6B21",
};

function bg(slide) {
  slide.background = { color: C.paper };
  slide.addShape(pptx.ShapeType.rect, {
    x: 0, y: 0, w: W, h: H,
    fill: { color: C.paper }, line: { color: C.paper },
  });
}

function footer(slide, n) {
  slide.addShape(pptx.ShapeType.line, {
    x: 0.75, y: 6.92, w: 11.82, h: 0,
    line: { color: C.line, width: 0.7 },
  });
  slide.addText("Literature Review Harness", {
    x: 0.78, y: 7.08, w: 4.4, h: 0.2,
    fontFace: FONT_EN, fontSize: 9.5, color: C.muted, margin: 0,
  });
  slide.addText(String(n).padStart(2, "0"), {
    x: 12.02, y: 7.07, w: 0.55, h: 0.2,
    fontFace: FONT_EN, fontSize: 9.5, color: C.muted, align: "right", margin: 0,
  });
}

function title(slide, text, sub, n) {
  bg(slide);
  slide.addText(text, {
    x: 0.72, y: 0.38, w: 10.9, h: 0.56,
    fontFace: FONT_TITLE, fontSize: 36, bold: true, color: C.ink, margin: 0,
  });
  if (sub) {
    slide.addText(sub, {
      x: 0.75, y: 1.08, w: 11.2, h: 0.28,
      fontFace: FONT_BODY, fontSize: 15.5, color: C.muted, margin: 0,
    });
  }
  slide.addShape(pptx.ShapeType.line, {
    x: 0.75, y: 1.52, w: 11.85, h: 0,
    line: { color: C.navy, width: 1.1 },
  });
  footer(slide, n);
}

function t(slide, text, x, y, w, h, opt = {}) {
  slide.addText(text, {
    x, y, w, h,
    fontFace: opt.font || FONT_BODY,
    fontSize: opt.size || 16,
    bold: opt.bold || false,
    color: opt.color || C.body,
    margin: opt.margin ?? 0.03,
    valign: opt.valign || "top",
    align: opt.align || "left",
    breakLine: false,
  });
}

function box(slide, x, y, w, h, head, body, opt = {}) {
  slide.addShape(pptx.ShapeType.rect, {
    x, y, w, h,
    fill: { color: opt.fill || C.white },
    line: { color: opt.line || C.line, width: 0.8 },
  });
  slide.addShape(pptx.ShapeType.rect, {
    x, y, w: 0.08, h,
    fill: { color: opt.accent || C.navy },
    line: { color: opt.accent || C.navy },
  });
  t(slide, head, x + 0.24, y + 0.18, w - 0.42, 0.32, {
    size: opt.headSize || 18,
    bold: true,
    color: opt.accent || C.navy,
  });
  t(slide, body, x + 0.24, y + 0.68, w - 0.42, h - 0.82, {
    size: opt.bodySize || 15.2,
    color: C.body,
  });
}

function row(slide, y, cells, widths, opt = {}) {
  const x = opt.x || 0.82;
  const w = opt.w || 11.68;
  const h = opt.h || 0.66;
  let cx = x;
  cells.forEach((cell, i) => {
    const cw = w * widths[i];
    slide.addShape(pptx.ShapeType.rect, {
      x: cx, y, w: cw, h,
      fill: { color: opt.header ? C.faint : (i === 0 ? "F8FAFC" : C.white) },
      line: { color: C.line, width: 0.55 },
    });
    t(slide, cell, cx + 0.12, y + 0.14, cw - 0.24, h - 0.16, {
      size: opt.size || 13.6,
      bold: opt.header || i === 0,
      color: i === 0 ? C.ink : C.body,
      valign: "mid",
    });
    cx += cw;
  });
}

function emphasis(slide, text, y) {
  slide.addShape(pptx.ShapeType.rect, {
    x: 0.98, y, w: 11.35, h: 0.72,
    fill: { color: C.faint },
    line: { color: C.line, width: 0.7 },
  });
  t(slide, text, 1.25, y + 0.2, 10.85, 0.22, {
    size: 18,
    bold: true,
    color: C.navy,
    align: "center",
    valign: "mid",
  });
}

function slide01() {
  const s = pptx.addSlide();
  bg(s);
  s.addShape(pptx.ShapeType.line, {
    x: 0.72, y: 0.58, w: 11.9, h: 0,
    line: { color: C.navy, width: 2.0 },
  });
  t(s, "Literature Review Harness", 0.88, 1.28, 11.3, 0.68, {
    font: FONT_TITLE, size: 42, bold: true, color: C.ink,
  });
  t(s, "面向学术综述生成的 Evidence-Grounded Agent Harness", 0.9, 2.18, 10.9, 0.42, {
    size: 22, bold: true, color: C.navy,
  });
  t(s, "Sciverse / MinerU · Skill System · Multi-Agent Review · Citation Verifier · HTML / LaTeX / Figures", 0.92, 2.82, 11.2, 0.32, {
    font: FONT_EN, size: 15.5, color: C.muted,
  });
  emphasis(s, "答辩核心：把综述生成从一次性 prompt，改造成可检索、可审计、可返修的工程链路。", 4.15);
  t(s, "World Models Survey Demo", 0.92, 6.28, 5.2, 0.26, {
    font: FONT_EN, size: 14, color: C.muted,
  });
}

function slide02() {
  const s = pptx.addSlide();
  title(s, "一、赛题理解", "评价重点不是“能写一篇文章”，而是“能稳定写出可信综述”。", 2);
  box(s, 0.82, 1.95, 5.55, 1.75, "任务目标", "阅读学术论文，整理分类，总结关键论文，梳理发展脉络，给出未来研究方向，并生成图文并茂的综述。", { accent: C.navy, bodySize: 15.8 });
  box(s, 6.85, 1.95, 5.55, 1.75, "可靠性约束", "无幻觉引用；无缺乏事实证据的描述；引用必须能回到真实论文和证据片段。", { accent: C.red, bodySize: 15.8 });
  box(s, 0.82, 4.25, 11.58, 1.45, "我们的判断", "如果只靠长 prompt，很难保证引用、结构、返修和可复查。因此必须实现一个真正的 harness：让模型在工具、证据、skill 和 verifier 的约束下工作。", { accent: C.teal, headSize: 18, bodySize: 16.2 });
}

function slide03() {
  const s = pptx.addSlide();
  title(s, "二、系统总览", "主流程由 AgentLoop 串联，所有关键步骤都有状态产物。", 3);
  row(s, 1.92, ["阶段", "输入", "输出"], [0.22, 0.39, 0.39], { header: true, size: 14.5 });
  const data = [
    ["检索", "用户主题、Sciverse API", "论文片段、元数据、候选论文"],
    ["证据", "候选论文、MinerU 可选全文", "PaperRecord、EvidenceRecord、ParsedDocument"],
    ["规划", "Evidence KB、Skill 指令", "outline、timeline、citation map、evidence needs"],
    ["生成", "证据、计划、补读结果", "完整 Markdown survey"],
    ["校验", "草稿、KB、review prompts", "review feedback、citation report、返修稿"],
    ["导出", "最终 survey、figure plan", "HTML、LaTeX、图片、运行包"],
  ];
  data.forEach((r, i) => row(s, 2.58 + i * 0.6, r, [0.22, 0.39, 0.39], { size: 13.2, h: 0.55 }));
}

function slide04() {
  const s = pptx.addSlide();
  title(s, "三、证据层：先有 Evidence，再有正文", "Sciverse 负责广度，MinerU 负责关键论文深度。", 4);
  box(s, 0.82, 1.9, 3.65, 2.6, "Sciverse", "返回论文片段、论文 URL、元数据和相关性分数。\n用于快速构造候选论文池。", { accent: C.blue, bodySize: 16.2 });
  box(s, 4.85, 1.9, 3.65, 2.6, "MinerU", "按需解析关键论文全文。\n当片段不足以支撑重要论断时，Agent 可补读原文解析文本。", { accent: C.teal, bodySize: 16.2 });
  box(s, 8.88, 1.9, 3.65, 2.6, "LiteratureKB", "统一保存 paper、evidence、parsed document。\n生成稳定 ID：P001-E01。", { accent: C.gold, bodySize: 16.2 });
  emphasis(s, "正文引用的最小单位是 evidence id，而不是模型记忆。", 5.35);
}

function slide05() {
  const s = pptx.addSlide();
  title(s, "四、工具调用设计", "模型可以自主调用工具，但不能绕过 Harness 边界。", 5);
  row(s, 1.88, ["工具类型", "代表工具", "功能"], [0.24, 0.34, 0.42], { header: true, size: 14.5 });
  const data = [
    ["证据构建", "build_literature_kb / search_literature", "检索、去重、构建初始 KB"],
    ["证据读取", "list_evidence / read_evidence", "按 evidence id 精读材料"],
    ["全文补读", "list_parsed_papers / read_parsed_paper", "从 MinerU 解析文件补事实"],
    ["上下文规划", "prepare_survey_context", "生成 outline、timeline、evidence needs"],
    ["Skill 系统", "skills_route / load / unload", "按阶段加载协议并记录 trace"],
  ];
  data.forEach((r, i) => row(s, 2.55 + i * 0.68, r, [0.24, 0.34, 0.42], { size: 13.4, h: 0.61 }));
  emphasis(s, "工具层的价值：让模型读材料、建上下文、再写作，而不是凭空写作。", 6.1);
}

function slide06() {
  const s = pptx.addSlide();
  title(s, "五、Survey Context", "不是硬编码综述结构，而是让 LLM 基于证据做学术组织。", 6);
  box(s, 0.82, 1.95, 5.55, 2.0, "确定性部分", "coverage、timeline、citation map、available evidence ids。\n它们来自 KB，可复现、可检查。", { accent: C.navy, bodySize: 16.1 });
  box(s, 6.85, 1.95, 5.55, 2.0, "LLM 判断部分", "recommended outline、section plan、selected papers、evidence needs。\n它负责技术谱系和篇章逻辑。", { accent: C.teal, bodySize: 16.1 });
  box(s, 0.82, 4.45, 11.58, 1.35, "清洗边界", "LLM 可以规划结构，但输出会被清洗：过滤非法 paper id，不伪造模板，不隐藏证据缺口。", { accent: C.red, headSize: 18, bodySize: 16.2 });
}

function slide07() {
  const s = pptx.addSlide();
  title(s, "六、Skill System", "渐进式披露：只在需要时加载必要 skill。", 7);
  row(s, 1.88, ["要求", "系统实现", "意义"], [0.22, 0.48, 0.3], { header: true, size: 14.5 });
  const data = [
    ["统一管理", "扫描 skills/ 下 SKILL.md 与 metadata", "外部 skill 可插拔"],
    ["模型发现", "只暴露 name、description、phase、roles", "节省上下文"],
    ["按需加载", "route_for_phase + load_for_phase", "减少噪声"],
    ["资源脚本", "read_resource / run_script 带路径边界", "可用但可控"],
    ["卸载审计", "unload + skill_trace.json", "防污染，可复查"],
  ];
  data.forEach((r, i) => row(s, 2.55 + i * 0.68, r, [0.22, 0.48, 0.3], { size: 13.2, h: 0.61 }));
  emphasis(s, "Skill 不是替代主流程，而是 AgentLoop 各阶段的可插拔策略层。", 6.1);
}

function slide08() {
  const s = pptx.addSlide();
  title(s, "七、写作与返修", "整体草稿生成，随后用多智能体审查推动修订。", 8);
  box(s, 0.82, 1.9, 5.55, 2.2, "写作方式", "保留 AgentLoop 主流程。\n模型在看到证据、outline、section plan、skill 指令和补读结果后，生成完整 survey。", { accent: C.navy, bodySize: 16 });
  box(s, 6.85, 1.9, 5.55, 2.2, "为什么不分块写全文", "分块写作容易造成段落割裂。\n当前采用整体写作 + reviewer 反馈 + citation verifier 的返修策略。", { accent: C.teal, bodySize: 16 });
  row(s, 4.65, ["返修触发", "LLM 输出草稿后，三路 reviewer 并行检查内容质量、引用准确性、结构完整性。"], [0.23, 0.77], { size: 14.2, h: 0.72 });
  row(s, 5.55, ["返修方式", "任一 reviewer 不通过，就把 issues 和 suggestions 注入消息历史，进入下一轮修复。"], [0.23, 0.77], { size: 14.2, h: 0.72 });
}

function slide09() {
  const s = pptx.addSlide();
  title(s, "八、引用校验", "LLM 判断负责质量，确定性规则负责底线。", 9);
  row(s, 1.88, ["检查项", "规则", "失败处理"], [0.25, 0.48, 0.27], { header: true, size: 14.5 });
  const data = [
    ["未知 evidence id", "正文引用必须存在于 Evidence KB", "要求替换或删除"],
    ["长段落无引用", "实质性段落必须带证据", "要求补 citation 或弱化表述"],
    ["工具日志污染", "doc_id、offset、raw evidence id 不应泄漏为正文噪声", "要求清洗"],
    ["References", "只列正文实际引用过的论文", "重建参考文献"],
  ];
  data.forEach((r, i) => row(s, 2.65 + i * 0.78, r, [0.25, 0.48, 0.27], { size: 13.7, h: 0.7 }));
  emphasis(s, "CitationVerifier 的目标：让“没有幻觉引用”变成可执行检查，而不是口头承诺。", 6.1);
}

function slide10() {
  const s = pptx.addSlide();
  title(s, "九、图片与导出", "图文并茂，但图片不是事实来源。", 10);
  box(s, 0.82, 1.88, 3.7, 2.15, "Figure Planner", "根据 survey 章节和 evidence ids 判断是否需要图。\n控制图片数量。", { accent: C.navy, bodySize: 15.8 });
  box(s, 4.82, 1.88, 3.7, 2.15, "Image Generator", "OpenAI-compatible API。\n支持第三方 base_url、model、size、quality。", { accent: C.teal, bodySize: 15.8 });
  box(s, 8.82, 1.88, 3.7, 2.15, "SVG Fallback", "时间线、矩阵等结构图可用简洁 SVG。\nAPI 失败不阻断正文。", { accent: C.gold, bodySize: 15.8 });
  row(s, 4.85, ["输出包", "survey.md、survey.html、survey.tex、evidence_pack.json、check_report.json、skill_trace.json、figure_plan.json、figures/"], [0.2, 0.8], { size: 14, h: 0.86 });
  emphasis(s, "图片服务于结构表达，事实仍由正文 evidence id 支撑。", 6.02);
}

function slide11() {
  const s = pptx.addSlide();
  title(s, "十、验证与赛题映射", "每个赛题要求都有对应模块和审计产物。", 11);
  row(s, 1.82, ["赛题要求", "系统对应能力"], [0.34, 0.66], { header: true, size: 14.5 });
  const data = [
    ["阅读论文", "Sciverse 片段检索 + MinerU 全文解析"],
    ["整理分类与关键论文", "Evidence KB + LLM outline / section plan"],
    ["梳理发展脉络", "timeline、citation map、survey context"],
    ["未来研究方向", "写作 prompt 与 reviewer 强制检查 research agenda"],
    ["无幻觉引用", "evidence id + CitationVerifier + check_report"],
    ["Skill 系统", "发现、路由、加载、资源读取、脚本执行、卸载、trace"],
  ];
  data.forEach((r, i) => row(s, 2.46 + i * 0.62, r, [0.34, 0.66], { size: 13.5, h: 0.56 }));
}

function slide12() {
  const s = pptx.addSlide();
  title(s, "十一、局限与下一步", "当前系统已经把质量问题拆解到可定位环节。", 12);
  box(s, 0.82, 1.9, 5.55, 3.25, "当前局限", "长综述质量仍受模型能力影响。\n检索质量依赖 Sciverse 返回结果。\nMinerU 全文解析依赖 URL 和时间预算。\nLaTeX 目前是基础导出。", { accent: C.red, bodySize: 16.2 });
  box(s, 6.85, 1.9, 5.55, 3.25, "下一步", "Memory 记录长期偏好和失败经验。\n强化 ranking / dedup / bibliography formatter。\nReviewer 输出结构化 patch plan。\n接入 arXiv / conference 模板。", { accent: C.teal, bodySize: 16.2 });
  emphasis(s, "核心价值：问题不再隐藏在一次生成里，而是落在可审计、可替换、可优化的 Harness 环节。", 5.9);
}

function slide13() {
  const s = pptx.addSlide();
  bg(s);
  s.addShape(pptx.ShapeType.line, {
    x: 0.72, y: 0.58, w: 11.9, h: 0,
    line: { color: C.navy, width: 2 },
  });
  t(s, "总结", 0.88, 1.0, 3.2, 0.62, {
    font: FONT_TITLE, size: 42, bold: true, color: C.ink,
  });
  emphasis(s, "我们把学术综述生成从 prompt 工程推进到 evidence-grounded agent harness。", 2.05);
  row(s, 3.35, ["Evidence-first", "先构建证据，再组织结构，再写作。"], [0.3, 0.7], { size: 15, h: 0.7 });
  row(s, 4.15, ["Skill-aware", "Skill 渐进式加载，避免上下文污染。"], [0.3, 0.7], { size: 15, h: 0.7 });
  row(s, 4.95, ["Verified", "多智能体审查 + CitationVerifier 共同把关。"], [0.3, 0.7], { size: 15, h: 0.7 });
  t(s, "Q&A", 10.8, 6.35, 1.6, 0.38, {
    font: FONT_EN, size: 28, bold: true, color: C.navy, align: "right",
  });
}

[
  slide01, slide02, slide03, slide04, slide05, slide06, slide07,
  slide08, slide09, slide10, slide11, slide12, slide13,
].forEach((fn) => fn());

for (let i = 0; i < pptx._slides.length; i += 1) {
  pptx._slides[i].addNotes(`Slide ${i + 1}: PPT Master-inspired version. 讲解时保持慢节奏，重点解释本页对应的模块、输入输出和审计产物。`);
}

pptx.writeFile({ fileName: "output/defense_presentation_ppt_master.pptx" });
