---
name: citation-grounding
description: Keep all literature-review claims grounded in known evidence ids.
roles: ["citation_grounding"]
triggers: ["citation", "grounding", "anti hallucination"]
max_chars: 4000
---

# Citation Grounding Skill

Use this skill whenever writing or revising evidence-backed prose.

## Rules

1. Use only evidence ids that exist in the current LiteratureKB.
2. Cite evidence ids inline with the claim they support, e.g. `[P001-E01]`.
3. Do not cite raw `doc_id`, offsets, URLs, or API traces in final prose.
4. If evidence is insufficient, say so explicitly instead of filling the gap.
5. The References section must list only papers that were cited by evidence id.

## Revision Checklist

- Remove unknown evidence ids.
- Add citations to long substantive paragraphs.
- Remove claims about authors, datasets, metrics, or dates unless supported by evidence.
- Keep audit details in `evidence_pack.json`, not in the reader-facing survey.
