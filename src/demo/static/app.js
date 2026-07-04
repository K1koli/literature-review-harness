const els = {
  form: document.getElementById("reviewForm"),
  topic: document.getElementById("topicInput"),
  runButton: document.getElementById("runButton"),
  sampleButton: document.getElementById("sampleButton"),
  statusDot: document.getElementById("statusDot"),
  statusText: document.getElementById("statusText"),
  tracePanel: document.getElementById("tracePanel"),
  traceSummary: document.getElementById("traceSummary"),
  traceLog: document.getElementById("traceLog"),
  visualSummary: document.getElementById("visualSummary"),
  pipeline: document.getElementById("pipeline"),
  timelineBars: document.getElementById("timelineBars"),
  sourceBars: document.getElementById("sourceBars"),
  markdownView: document.getElementById("markdownView"),
  pdfView: document.getElementById("pdfView"),
  pdfObject: document.getElementById("pdfObject"),
  evidenceFocus: document.getElementById("evidenceFocus"),
  paperCount: document.getElementById("paperCount"),
  evidenceCount: document.getElementById("evidenceCount"),
  citedCount: document.getElementById("citedCount"),
  citationStatus: document.getElementById("citationStatus"),
  downloadMd: document.getElementById("downloadMd"),
  downloadHtml: document.getElementById("downloadHtml"),
  downloadTex: document.getElementById("downloadTex"),
  downloadPdf: document.getElementById("downloadPdf"),
  downloadEvidence: document.getElementById("downloadEvidence"),
};

let activeSource = null;
let activeRunId = "";
let currentPayload = null;

els.form.addEventListener("submit", (event) => {
  event.preventDefault();
  startRun("/api/reviews");
});

els.sampleButton.addEventListener("click", () => {
  startRun("/api/reviews/sample");
});

document.querySelectorAll(".tab-btn").forEach((button) => {
  button.addEventListener("click", () => setTab(button.dataset.tab));
});

els.markdownView.addEventListener("click", (event) => {
  const chip = event.target.closest(".evidence-chip");
  if (!chip) return;
  showEvidence(chip.dataset.eid);
  document.querySelectorAll(".evidence-chip.active").forEach((item) => item.classList.remove("active"));
  chip.classList.add("active");
});

async function startRun(endpoint) {
  const topic = els.topic.value.trim();
  if (!topic) {
    setStatus("error", "Topic is required");
    return;
  }
  resetRun();
  setStatus("running", endpoint.endsWith("sample") ? "Loading sample" : "Running harness");
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic }),
  });
  const data = await response.json();
  if (!response.ok) {
    setStatus("error", data.error || "Request failed");
    return;
  }
  activeRunId = data.run_id;
  subscribeToRun(activeRunId);
}

function subscribeToRun(runId) {
  if (activeSource) activeSource.close();
  activeSource = new EventSource(`/api/reviews/${runId}/events`);
  activeSource.onmessage = (message) => {
    const event = JSON.parse(message.data);
    appendTrace(event);
    if (event.type === "artifacts_ready") {
      setStatus("done", "Ready");
      activeSource.close();
      setTimeout(() => {
        els.tracePanel.open = false;
      }, 700);
      loadRun(runId);
    }
    if (event.type === "run_failed" || event.type === "config_error") {
      setStatus("error", event.message || "Run failed");
      activeSource.close();
      loadRun(runId);
    }
  };
  activeSource.onerror = () => {
    if (!activeRunId) return;
    setStatus("error", "Event stream closed");
  };
}

async function loadRun(runId) {
  const response = await fetch(`/api/reviews/${runId}`);
  const payload = await response.json();
  currentPayload = payload;
  renderMetrics(payload.summary || {});
  renderDownloads(payload.downloads || {});
  if (payload.markdown) {
    els.markdownView.innerHTML = renderMarkdown(payload.markdown);
    renderVisuals(payload.summary || {});
    els.visualSummary.hidden = false;
  }
  if (payload.downloads?.pdf_preview) {
    els.pdfObject.data = payload.downloads.pdf_preview;
  }
}

function resetRun() {
  if (activeSource) activeSource.close();
  activeSource = null;
  activeRunId = "";
  currentPayload = null;
  els.traceLog.innerHTML = "";
  els.traceSummary.textContent = "Starting";
  els.tracePanel.open = true;
  els.visualSummary.hidden = true;
  els.markdownView.innerHTML = `<div class="empty-state"><strong>Running</strong><span>Harness events will appear above.</span></div>`;
  els.pdfObject.removeAttribute("data");
  renderMetrics({});
  renderDownloads({});
  setTab("markdown");
  els.evidenceFocus.innerHTML = `<p class="panel-label">Evidence focus</p><p class="muted">Select an evidence id in the article.</p>`;
}

function setStatus(kind, text) {
  els.statusDot.className = `status-dot ${kind === "done" ? "done" : kind === "error" ? "error" : kind === "running" ? "running" : "idle"}`;
  els.statusText.textContent = text;
  const busy = kind === "running";
  els.runButton.disabled = busy;
  els.sampleButton.disabled = busy;
}

function appendTrace(event) {
  const li = document.createElement("li");
  li.innerHTML = formatTraceEvent(event);
  els.traceLog.appendChild(li);
  els.traceLog.scrollTop = els.traceLog.scrollHeight;
  const count = els.traceLog.children.length;
  els.traceSummary.textContent = event.type === "artifacts_ready" ? `${count} events, complete` : `${count} events`;
}

function formatTraceEvent(event) {
  const type = event.type;
  if (type === "tool_call_started") {
    return `<strong>Tool</strong> ${escapeHtml(event.name)} <code>${escapeHtml(JSON.stringify(event.arguments || {}))}</code>`;
  }
  if (type === "tool_call_finished") {
    return `<strong>Tool result</strong> ${escapeHtml(event.name)} <code>${escapeHtml(shorten(event.result_preview || "", 300))}</code>`;
  }
  if (type === "llm_response" && event.mode === "tool_calls") {
    return `<strong>LLM</strong> requested ${event.tool_call_count || 0} tool call(s): <code>${escapeHtml((event.tool_names || []).join(", "))}</code>`;
  }
  if (type === "llm_response" && event.mode === "final_content") {
    return `<strong>LLM</strong> produced final Markdown (${event.content_chars || 0} chars)`;
  }
  if (type === "stop_condition") {
    const status = event.passed ? "passed" : "failed";
    return `<strong>${escapeHtml(event.name || "Verifier")}</strong> ${status} <code>${escapeHtml(JSON.stringify(event.report || {}))}</code>`;
  }
  if (type === "artifacts_ready") {
    return `<strong>Artifacts ready</strong> ${escapeHtml(JSON.stringify(event.summary || {}))}`;
  }
  if (type === "config_error" || type === "run_failed") {
    return `<strong>Run failed</strong> ${escapeHtml(event.message || "")}`;
  }
  const message = event.message || event.task_preview || event.topic || event.mode || "";
  return `<strong>${escapeHtml(titleCase(type))}</strong> ${escapeHtml(shorten(String(message), 220))}`;
}

function renderMetrics(summary) {
  els.paperCount.textContent = summary.paper_count ?? 0;
  els.evidenceCount.textContent = summary.evidence_count ?? 0;
  els.citedCount.textContent = summary.cited_evidence_count ?? 0;
  els.citationStatus.textContent = summary.citation_status || "-";
}

function renderDownloads(downloads) {
  setLink(els.downloadMd, downloads.markdown);
  setLink(els.downloadHtml, downloads.html);
  setLink(els.downloadTex, downloads.latex);
  setLink(els.downloadPdf, downloads.pdf);
  setLink(els.downloadEvidence, downloads.evidence);
}

function setLink(link, href) {
  if (href) {
    link.href = href;
    link.classList.remove("disabled");
  } else {
    link.href = "#";
    link.classList.add("disabled");
  }
}

function renderVisuals(summary) {
  const steps = [
    ["Topic", "User-scoped prompt"],
    ["Skills", (summary.skill_trace || []).length ? `${summary.skill_trace.length} trace events` : "progressive context"],
    ["Evidence KB", `${summary.paper_count || 0} papers`],
    ["Grounding", `${summary.evidence_count || 0} evidence records`],
    ["Verifier", summary.citation_status || "not_run"],
    ["Exports", "Markdown + PDF"],
  ];
  els.pipeline.innerHTML = steps
    .map(([label, value]) => `<div class="pipeline-step"><strong>${escapeHtml(label)}</strong><small>${escapeHtml(value)}</small></div>`)
    .join("");

  const years = (summary.year_counts || []).filter((row) => row.label !== "Unknown").slice(-16);
  const maxYear = Math.max(1, ...years.map((row) => row.count || 0));
  els.timelineBars.innerHTML = years
    .map((row) => {
      const height = Math.max(6, Math.round(((row.count || 0) / maxYear) * 92));
      return `<div class="timeline-bar" title="${escapeHtml(row.label)}: ${row.count}"><span style="height:${height}px"></span><small>${escapeHtml(String(row.label).slice(-4))}</small></div>`;
    })
    .join("");

  const sources = (summary.source_counts || []).slice(0, 8);
  const maxSource = Math.max(1, ...sources.map((row) => row.count || 0));
  els.sourceBars.innerHTML = sources
    .map((row) => {
      const width = Math.round(((row.count || 0) / maxSource) * 100);
      return `<div class="source-row"><span title="${escapeHtml(row.label)}">${escapeHtml(row.label)}</span><div class="source-track"><div class="source-fill" style="width:${width}%"></div></div><strong>${row.count}</strong></div>`;
    })
    .join("");
}

function showEvidence(evidenceId) {
  const evidence = currentPayload?.summary?.cited_evidence || [];
  const item = evidence.find((row) => row.evidence_id === evidenceId);
  if (!item) {
    els.evidenceFocus.innerHTML = `<p class="panel-label">Evidence focus</p><span class="evidence-tag">${escapeHtml(evidenceId)}</span><p class="muted">Evidence text is not in the current cited set.</p>`;
    return;
  }
  els.evidenceFocus.innerHTML = `
    <p class="panel-label">Evidence focus</p>
    <span class="evidence-tag">${escapeHtml(item.evidence_id)}</span>
    <h3>${escapeHtml(item.title || "Untitled")}</h3>
    <p class="muted">${escapeHtml([item.year, item.source].filter(Boolean).join(" · "))}</p>
    <p>${escapeHtml(item.text || "")}</p>
  `;
}

function setTab(name) {
  document.querySelectorAll(".tab-btn").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === name);
  });
  els.markdownView.hidden = name !== "markdown";
  els.pdfView.hidden = name !== "pdf";
}

function renderMarkdown(markdown) {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const out = [];
  let paragraph = [];
  let list = null;
  let table = [];
  let inCode = false;
  let code = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    out.push(`<p>${inline(paragraph.join(" "))}</p>`);
    paragraph = [];
  };
  const flushList = () => {
    if (!list) return;
    out.push(`<${list.type}>${list.items.map((item) => `<li>${inline(item)}</li>`).join("")}</${list.type}>`);
    list = null;
  };
  const flushTable = () => {
    if (!table.length) return;
    const rows = table
      .map((line) => line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim()))
      .filter((cells) => !cells.every((cell) => /^:?-{3,}:?$/.test(cell)));
    if (rows.length) {
      const [head, ...body] = rows;
      out.push(`<table><thead><tr>${head.map((cell) => `<th>${inline(cell)}</th>`).join("")}</tr></thead><tbody>${body.map((row) => `<tr>${row.map((cell) => `<td>${inline(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table>`);
    }
    table = [];
  };
  const flushAll = () => {
    flushParagraph();
    flushList();
    flushTable();
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    if (line.startsWith("```")) {
      flushAll();
      if (inCode) {
        out.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
        code = [];
        inCode = false;
      } else {
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      code.push(line);
      continue;
    }
    if (!line.trim()) {
      flushAll();
      continue;
    }
    if (line.startsWith("|")) {
      flushParagraph();
      flushList();
      table.push(line);
      continue;
    }
    flushTable();
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      flushParagraph();
      flushList();
      const level = Math.min(4, heading[1].length);
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
      continue;
    }
    const ordered = line.match(/^\d+\.\s+(.*)$/);
    const unordered = line.match(/^[-*]\s+(.*)$/);
    if (ordered || unordered) {
      flushParagraph();
      const type = ordered ? "ol" : "ul";
      if (!list || list.type !== type) flushList();
      if (!list) list = { type, items: [] };
      list.items.push((ordered || unordered)[1]);
      continue;
    }
    if (line.startsWith(">")) {
      flushAll();
      out.push(`<blockquote>${inline(line.replace(/^>\s?/, ""))}</blockquote>`);
      continue;
    }
    paragraph.push(line.trim());
  }
  flushAll();
  return out.join("\n");
}

function inline(text) {
  let safe = escapeHtml(text);
  safe = safe.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  safe = safe.replace(/`(.+?)`/g, "<code>$1</code>");
  safe = safe.replace(/\b(P\d{2,4}-E\d{2,3})\b/g, '<button type="button" class="evidence-chip" data-eid="$1">$1</button>');
  return safe;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function shorten(value, max) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length > max ? `${text.slice(0, max)}...` : text;
}

function titleCase(value) {
  return String(value || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}
