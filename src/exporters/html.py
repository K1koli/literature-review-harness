from __future__ import annotations

import html
import re
from pathlib import Path

from ..validation.citations import EVIDENCE_ID_RE


def export_html(markdown_path: Path, output_path: Path, *, title: str = "Literature Survey") -> None:
    markdown = markdown_path.read_text(encoding="utf-8")
    body = _markdown_to_html(markdown)
    output_path.write_text(_page(title, body), encoding="utf-8")


def _markdown_to_html(markdown: str) -> str:
    lines = markdown.splitlines()
    html_lines: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    ordered_items: list[str] = []
    table_rows: list[list[str]] = []
    in_figure = False

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            html_lines.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph = []

    def flush_list() -> None:
        nonlocal list_items
        if list_items:
            html_lines.append("<ul>")
            html_lines.extend(f"<li>{_inline(item)}</li>" for item in list_items)
            html_lines.append("</ul>")
            list_items = []

    def flush_ordered_list() -> None:
        nonlocal ordered_items
        if ordered_items:
            html_lines.append("<ol>")
            html_lines.extend(f"<li>{_inline(item)}</li>" for item in ordered_items)
            html_lines.append("</ol>")
            ordered_items = []

    def flush_table() -> None:
        nonlocal table_rows
        if not table_rows:
            return
        if len(table_rows) >= 2 and all(_is_separator_cell(cell) for cell in table_rows[1]):
            header = table_rows[0]
            body_rows = table_rows[2:]
        else:
            header = []
            body_rows = table_rows
        html_lines.append("<table>")
        if header:
            html_lines.append("<thead><tr>")
            html_lines.extend(f"<th>{_inline(cell)}</th>" for cell in header)
            html_lines.append("</tr></thead>")
        if body_rows:
            html_lines.append("<tbody>")
            for row in body_rows:
                html_lines.append("<tr>")
                html_lines.extend(f"<td>{_inline(cell)}</td>" for cell in row)
                html_lines.append("</tr>")
            html_lines.append("</tbody>")
        html_lines.append("</table>")
        table_rows = []

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            flush_paragraph()
            flush_list()
            flush_ordered_list()
            flush_table()
            continue
        if line.startswith("<figure"):
            flush_paragraph()
            flush_list()
            flush_ordered_list()
            flush_table()
            in_figure = True
            html_lines.append(line)
            continue
        if line.startswith("</figure"):
            flush_paragraph()
            flush_list()
            flush_ordered_list()
            flush_table()
            in_figure = False
            html_lines.append(line)
            continue
        if line.startswith("<figcaption"):
            flush_paragraph()
            flush_list()
            flush_ordered_list()
            flush_table()
            html_lines.append(_inline_raw_html(line))
            continue
        if _is_table_line(line):
            flush_paragraph()
            flush_list()
            flush_ordered_list()
            table_rows.append(_parse_table_row(line))
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            flush_list()
            flush_ordered_list()
            flush_table()
            level = len(heading.group(1))
            html_lines.append(f"<h{level}>{_inline(heading.group(2).strip())}</h{level}>")
            continue
        if line.strip() == "---":
            flush_paragraph()
            flush_list()
            flush_ordered_list()
            flush_table()
            html_lines.append("<hr/>")
            continue
        image = re.match(r"^!\[(.*?)\]\((.*?)\)$", line.strip())
        if image:
            flush_paragraph()
            flush_list()
            flush_ordered_list()
            flush_table()
            alt = html.escape(image.group(1))
            src = html.escape(image.group(2))
            html_lines.append(f'<img src="{src}" alt="{alt}" loading="lazy"/>')
            continue
        if line.startswith("- "):
            flush_paragraph()
            flush_ordered_list()
            flush_table()
            list_items.append(line[2:].strip())
            continue
        ordered = re.match(r"^\d+\.\s+(.+)$", line)
        if ordered:
            flush_paragraph()
            flush_list()
            flush_table()
            ordered_items.append(ordered.group(1).strip())
            continue
        paragraph.append(line.strip())

    flush_paragraph()
    flush_list()
    flush_ordered_list()
    flush_table()
    return "\n".join(html_lines)


def _inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = EVIDENCE_ID_RE.sub(lambda m: f'<code class="evidence-id">{m.group(0)}</code>', escaped)
    return escaped


def _inline_raw_html(text: str) -> str:
    text = re.sub(r"<strong>(.*?)</strong>", lambda m: f"<strong>{html.escape(m.group(1))}</strong>", text)
    return EVIDENCE_ID_RE.sub(lambda m: f'<code class="evidence-id">{m.group(0)}</code>', text)


def _is_table_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def _parse_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator_cell(cell: str) -> bool:
    return bool(re.fullmatch(r":?-{3,}:?", cell.strip()))


def _page(title: str, body: str) -> str:
    escaped_title = html.escape(title)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{escaped_title}</title>
  <style>
    :root {{
      --ink: #172033;
      --muted: #5d6b7a;
      --line: #d8e1ea;
      --accent: #173b68;
      --paper: #ffffff;
      --soft: #f5f8fb;
    }}
    body {{
      margin: 0;
      background: #edf2f7;
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
      line-height: 1.65;
    }}
    main {{
      max-width: 980px;
      margin: 40px auto;
      padding: 56px 68px;
      background: var(--paper);
      box-shadow: 0 18px 60px rgba(23, 32, 51, .10);
      border: 1px solid var(--line);
    }}
    h1 {{
      font-size: 38px;
      line-height: 1.15;
      margin: 0 0 28px;
      color: #0d2442;
      letter-spacing: 0;
    }}
    h2 {{
      font-size: 25px;
      margin-top: 42px;
      padding-top: 20px;
      border-top: 1px solid var(--line);
      color: var(--accent);
      letter-spacing: 0;
    }}
    h3 {{
      font-size: 19px;
      margin-top: 30px;
      color: #22304a;
      letter-spacing: 0;
    }}
    p, li {{
      font-size: 16px;
    }}
    hr {{
      border: 0;
      border-top: 1px solid var(--line);
      margin: 32px 0;
    }}
    figure {{
      margin: 24px 0 34px;
      padding: 18px;
      background: var(--soft);
      border: 1px solid var(--line);
    }}
    figure img {{
      display: block;
      width: 100%;
      height: auto;
      background: #fff;
      border: 1px solid #e2e8f0;
    }}
    figcaption {{
      margin-top: 12px;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.5;
    }}
    code.evidence-id {{
      padding: 2px 5px;
      border-radius: 5px;
      background: #eef5ff;
      color: #174a86;
      font-size: .88em;
      white-space: nowrap;
    }}
    ul {{
      padding-left: 24px;
    }}
    ol {{
      padding-left: 24px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 22px 0 30px;
      font-size: 14px;
    }}
    th, td {{
      border: 1px solid var(--line);
      padding: 10px 12px;
      vertical-align: top;
    }}
    th {{
      background: #f2f6fb;
      color: #173b68;
      text-align: left;
    }}
    @media (max-width: 760px) {{
      main {{
        margin: 0;
        padding: 28px 22px;
        box-shadow: none;
      }}
      h1 {{ font-size: 30px; }}
    }}
  </style>
</head>
<body>
<main>
{body}
</main>
</body>
</html>
"""
