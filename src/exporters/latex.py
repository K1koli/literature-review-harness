from __future__ import annotations

import re
from pathlib import Path


def export_latex(markdown_path: Path, output_path: Path, *, title: str = "Literature Survey") -> None:
    markdown = markdown_path.read_text(encoding="utf-8")
    output_path.write_text(_latex_page(title, _markdown_to_latex(markdown)), encoding="utf-8")


def _markdown_to_latex(markdown: str) -> str:
    lines = markdown.splitlines()
    out: list[str] = []
    in_figure = False
    pending_image: tuple[str, str] | None = None
    for raw in lines:
        line = raw.strip()
        if not line:
            out.append("")
            continue
        if line.startswith("<figure"):
            in_figure = True
            pending_image = None
            continue
        if line.startswith("</figure"):
            in_figure = False
            pending_image = None
            continue
        image = re.match(r"^!\[(.*?)\]\((.*?)\)$", line)
        if image:
            pending_image = (image.group(1), image.group(2))
            continue
        if line.startswith("<figcaption") and pending_image:
            caption = re.sub(r"<.*?>", "", line)
            alt, src = pending_image
            if src.lower().endswith((".png", ".jpg", ".jpeg", ".pdf")):
                out.extend(
                    [
                        "\\begin{figure}[t]",
                        "\\centering",
                        f"\\includegraphics[width=0.95\\linewidth]{{{_escape_path(src)}}}",
                        f"\\caption{{{_escape(caption)}}}",
                        "\\end{figure}",
                    ]
                )
            else:
                out.append(f"\\noindent\\textbf{{{_escape(alt)}.}} {_escape(caption)}")
            pending_image = None
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            level = len(heading.group(1))
            text = _escape(heading.group(2))
            if level == 1:
                out.append(f"\\section*{{{text}}}")
            elif level == 2:
                out.append(f"\\section{{{text}}}")
            elif level == 3:
                out.append(f"\\subsection{{{text}}}")
            else:
                out.append(f"\\paragraph{{{text}}}")
            continue
        if line == "---":
            continue
        if line.startswith("- "):
            out.append(f"\\noindent\\textbullet\\ {_escape(line[2:])}\\\\")
            continue
        if not in_figure:
            out.append(_escape(line))
    return "\n".join(out)


def _latex_page(title: str, body: str) -> str:
    return f"""\\documentclass[11pt]{{article}}
\\usepackage[margin=1in]{{geometry}}
\\usepackage{{graphicx}}
\\usepackage{{hyperref}}
\\usepackage{{microtype}}
\\title{{{_escape(title)}}}
\\date{{}}
\\begin{{document}}
\\maketitle

{body}

\\end{{document}}
"""


def _escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", text)
    return text


def _escape_path(path: str) -> str:
    return path.replace(" ", "\\ ")
