---
name: survey-writing
description: Write a coherent evidence-grounded academic survey from a LiteratureKB.
roles: ["survey_writing"]
triggers: ["write survey", "literature review", "academic survey"]
max_chars: 5000
---

# Survey Writing Skill

Use this skill when drafting the final Markdown survey.

## Required Shape

1. Abstract or overview.
2. Introduction and scope.
3. Conceptual or technical organization of the literature.
4. Comparative synthesis across papers.
5. Open problems and future directions.
6. References listing only cited evidence/papers.

## Writing Rules

- Write synthesis paragraphs, not one bullet per paper.
- Every substantive paragraph must cite evidence ids such as `[P001-E01]`.
- Do not expose tool logs, raw Sciverse offsets, or hidden reasoning.
- Do not force internal labels like taxonomy/timeline/matrix into prose unless they improve readability.
- Future directions must follow from evidence gaps, limitations, or observed disagreements.

## Quality Bar

The output should read like a survey article, not a retrieval report.
