from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def existing_sample_is_ready(sample_dir: Path) -> bool:
    survey_path = sample_dir / "survey.md"
    check_path = sample_dir / "check_report.json"
    if not survey_path.exists() or not check_path.exists():
        return False
    markdown = survey_path.read_text(encoding="utf-8")
    try:
        report = json.loads(check_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return len(markdown) > 1200 and report.get("status") == "pass"


def write_fallback_sample(*, topic: str, evidence_pack_path: Path, output_dir: Path) -> None:
    evidence_pack = json.loads(evidence_pack_path.read_text(encoding="utf-8"))
    evidence = [item for item in evidence_pack.get("evidence", []) if isinstance(item, dict)]
    papers = [item for item in evidence_pack.get("papers", []) if isinstance(item, dict)]
    cited = _pick_cited_evidence(evidence)
    if not cited:
        raise ValueError("Sample evidence_pack.json does not contain evidence records.")

    output_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(exist_ok=True)
    _write_harness_svg(figures_dir / "sample_harness_flow.svg")

    markdown = _sample_markdown(topic=topic, papers=papers, evidence=evidence, cited=cited)
    (output_dir / "survey.md").write_text(markdown, encoding="utf-8")
    (output_dir / "evidence_pack.json").write_text(
        json.dumps(evidence_pack, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "check_report.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "errors": [],
                "warnings": [
                    {
                        "issue": "demo_sample",
                        "message": "Deterministic sample generated from the local evidence pack for UI demonstration.",
                    }
                ],
                "cited_evidence_ids": [item["evidence_id"] for item in cited],
                "available_evidence_count": len(evidence),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (output_dir / "skill_trace.json").write_text(
        json.dumps(
            [
                {"phase": "literature_review", "action": "route", "skill_names": ["survey-writing", "citation-grounding"]},
                {"phase": "literature_review", "action": "load", "skill_names": ["survey-writing", "citation-grounding"]},
                {"phase": "literature_review", "action": "unload", "skill_names": ["survey-writing", "citation-grounding"]},
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (output_dir / "figure_plan.json").write_text(
        json.dumps(
            [
                {
                    "figure_id": "F001",
                    "title": "Evidence-grounded harness flow",
                    "filename": "sample_harness_flow.svg",
                    "render_mode": "svg",
                    "source_evidence_ids": [item["evidence_id"] for item in cited[:3]],
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _pick_cited_evidence(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    preferred_terms = [
        "world model",
        "model-based",
        "reinforcement",
        "planning",
        "multimodality",
        "environment",
        "robot",
        "control",
    ]
    scored = []
    for item in evidence:
        text = f"{item.get('title') or ''} {item.get('text') or ''}".lower()
        score = sum(text.count(term) for term in preferred_terms)
        if item.get("evidence_id"):
            scored.append((score, str(item.get("year") or ""), str(item.get("evidence_id")), item))
    ranked = [item for _, _, _, item in sorted(scored, key=lambda row: (-row[0], row[1], row[2]))]
    return ranked[:8] or [item for item in evidence[:8] if item.get("evidence_id")]


def _sample_markdown(
    *,
    topic: str,
    papers: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    cited: list[dict[str, Any]],
) -> str:
    while len(cited) < 8:
        cited.append(cited[-1])
    ids = [item["evidence_id"] for item in cited]
    count_sentence = (
        f"本 demo 使用本地 evidence pack 中的 {len(papers)} 篇论文记录和 {len(evidence)} 条 evidence record。"
    )
    bibliography = "\n".join(_reference_row(item) for item in cited)
    return f"""# {topic}：Evidence-Grounded Literature Review Demo

## Abstract

This sample review demonstrates the harness output format rather than claiming to be the final field survey. {count_sentence} The cited evidence shows that the phrase "world model" is used across model-based reinforcement learning, multimodal representation, planning, control, and deployment contexts, so a reliable survey must first separate scope and evidence strength before synthesis [{ids[0]}] [{ids[1]}].

<figure id="F001">

![Evidence-grounded harness flow](figures/sample_harness_flow.svg)

<figcaption><strong>F001. Evidence-grounded harness flow.</strong> The demo keeps retrieval, evidence indexing, writing, citation checking, and export as separate auditable stages. Sources: {", ".join(ids[:3])}.</figcaption>

</figure>

## 1. Scope and Taxonomy

The local evidence pack suggests that a World Models review should not treat every retrieved item as equally central. Some records are directly about learned environment or latent models for decision making, while others use world-model language in adjacent systems settings; the harness therefore makes relevance filtering a first-class step before drafting [{ids[0]}] [{ids[2]}]. A practical taxonomy for this demo separates representation learning, predictive dynamics, planning/control, multimodal grounding, and deployment-oriented uses, while keeping every paragraph tied to explicit evidence ids [{ids[1]}] [{ids[3]}].

## 2. Development Trajectory

The retrieved evidence supports a development story that moves from model-based reinforcement learning and object-centric control toward broader multimodal and system-level uses. In a full live run, `prepare_survey_context` turns this evidence into a timeline and citation map before the writer drafts the article, reducing the chance that the final prose overweights a single retrieval cluster [{ids[2]}] [{ids[4]}].

## 3. Method Families

A cautious synthesis should compare world models by what they learn, what downstream decision process consumes the learned state, and how the learned model is validated. The sample evidence points to predictive or latent representations, object-based implementations, and task-level control/offloading variants; those claims remain narrow here because the UI sample deliberately avoids inventing details not present in the local pack [{ids[1]}] [{ids[3]}] [{ids[5]}].

## 4. Harness Engineering Notes

The harness separates factual evidence from writing protocol. Sciverse and optional MinerU populate `evidence_pack.json`; skill tools may guide structure or citation discipline but are not allowed to introduce facts; `CitationVerifier` checks that final citations resolve to known evidence ids; and the demo exposes the event stream so viewers can inspect the loop instead of only seeing the final article [{ids[0]}] [{ids[6]}].

## 5. Future Directions

A live World Models survey should use the same evidence contract to identify open questions: stronger benchmarks for learned dynamics, clearer multimodal grounding tests, better long-horizon evaluation, and tighter connections between learned representations and deployed decision systems. These are presented as directions for follow-up retrieval and verification rather than as unsupported conclusions [{ids[4]}] [{ids[6]}] [{ids[7]}].

## References

{bibliography}
"""


def _write_harness_svg(path: Path) -> None:
    labels = ["Topic", "Evidence KB", "Survey Context", "Grounded Draft", "Citation Check", "MD / PDF"]
    boxes = []
    for index, label in enumerate(labels):
        x = 50 + index * 238
        boxes.append(
            f'<rect x="{x}" y="170" width="180" height="86" rx="10" fill="#ffffff" stroke="#c9d6e3"/>'
            f'<text x="{x + 90}" y="221" text-anchor="middle" font-size="22" font-weight="700" fill="#16233a">{label}</text>'
        )
        if index < len(labels) - 1:
            x2 = x + 180
            boxes.append(
                f'<path d="M{x2 + 10} 213 H{x2 + 48}" stroke="#6b8199" stroke-width="4" marker-end="url(#arrow)"/>'
            )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1536" height="520" viewBox="0 0 1536 520" role="img" aria-label="Evidence-grounded harness flow">
  <defs>
    <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L0,6 L9,3 z" fill="#6b8199"/>
    </marker>
  </defs>
  <rect width="1536" height="520" fill="#f6f8fb"/>
  <text x="768" y="92" text-anchor="middle" font-size="36" font-weight="800" fill="#102033">Literature Review Harness</text>
  <text x="768" y="132" text-anchor="middle" font-size="19" fill="#5f6f83">visible loop, evidence contract, independent checking, downloadable artifacts</text>
  {"".join(boxes)}
  <text x="768" y="350" text-anchor="middle" font-size="20" fill="#334155">Every substantive claim in the live review must cite stable evidence ids such as P001-E01.</text>
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def _reference_row(item: dict[str, Any]) -> str:
    year = f" ({item.get('year')})" if item.get("year") else ""
    return f"- {item.get('evidence_id')}: {item.get('title') or 'Untitled'}{year}."
