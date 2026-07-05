from __future__ import annotations

import html
import re
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any


def write_review_pdf(
    *,
    markdown: str,
    summary: dict[str, Any],
    check_report: dict[str, Any],
    topic: str,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _write_reportlab_pdf(
            markdown=markdown,
            summary=summary,
            check_report=check_report,
            topic=topic,
            output_path=output_path,
        )
    except Exception:
        _write_basic_pdf(markdown=markdown, topic=topic, output_path=output_path)


def write_pdf_page_previews(pdf_path: Path, output_dir: Path, *, max_pages: int = 8) -> list[Path]:
    """Render PDF pages to PNG files for browsers that cannot embed PDFs."""

    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm or not pdf_path.exists():
        return []
    output_dir.mkdir(parents=True, exist_ok=True)
    for old_page in output_dir.glob("page-*.png"):
        old_page.unlink()
    prefix = output_dir / "page"
    try:
        subprocess.run(
            [
                pdftoppm,
                "-png",
                "-r",
                "144",
                "-f",
                "1",
                "-l",
                str(max(1, max_pages)),
                str(pdf_path),
                str(prefix),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []
    return sorted(output_dir.glob("page-*.png"))


def _write_reportlab_pdf(
    *,
    markdown: str,
    summary: dict[str, Any],
    check_report: dict[str, Any],
    topic: str,
    output_path: Path,
) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        base_font = "STSong-Light"
    except Exception:
        base_font = "Helvetica"

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            parent=styles["Title"],
            fontName=base_font,
            fontSize=22,
            leading=28,
            textColor=colors.HexColor("#102033"),
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportMeta",
            parent=styles["BodyText"],
            fontName=base_font,
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#5f6f83"),
            spaceAfter=8,
        )
    )
    for name in ["Normal", "BodyText", "Heading1", "Heading2", "Heading3", "Bullet"]:
        styles[name].fontName = base_font
    styles["Normal"].leading = 14
    styles["BodyText"].leading = 14
    styles["Heading1"].fontSize = 18
    styles["Heading1"].leading = 22
    styles["Heading2"].fontSize = 14
    styles["Heading2"].leading = 18
    styles["Heading3"].fontSize = 12
    styles["Heading3"].leading = 16

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"{topic} literature review",
    )

    story: list[Any] = [
        Paragraph(f"Literature Review Harness Demo: {_escape(topic)}", styles["ReportTitle"]),
        Paragraph(
            "Evidence-grounded survey export. Substantive claims in the Markdown are checked against stable evidence ids.",
            styles["ReportMeta"],
        ),
        _MetricTable(summary, check_report, base_font),
        Spacer(1, 8),
        _HarnessPipeline(summary),
        Spacer(1, 10),
        _YearBars(summary),
        PageBreak(),
    ]
    story.extend(_markdown_flowables(markdown, styles))
    doc.build(story)


class _MetricTable:
    def __new__(cls, summary: dict[str, Any], check_report: dict[str, Any], font_name: str):
        from reportlab.lib import colors
        from reportlab.platypus import Table, TableStyle

        rows = [
            ["Papers", summary.get("paper_count", 0), "Evidence", summary.get("evidence_count", 0)],
            ["Cited evidence", summary.get("cited_evidence_count", 0), "Citation check", check_report.get("status", "not_run")],
        ]
        table = Table(rows, colWidths=[92, 70, 104, 90])
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), font_name),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#203040")),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f4f7fb")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d7e0ea")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d7e0ea")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        return table


class _BaseDemoFlowable:
    _fixedWidth = 0
    _fixedHeight = 0

    def wrapOn(self, canvas: Any, availWidth: float, availHeight: float) -> tuple[float, float]:
        self.canv = canvas
        return self.wrap(availWidth, availHeight)

    def getKeepWithNext(self) -> bool:
        return False

    def identity(self, maxLen: int | None = None) -> str:
        return self.__class__.__name__


class _HarnessPipeline(_BaseDemoFlowable):
    def __init__(self, summary: dict[str, Any]):
        self.summary = summary

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
        self.width = availWidth
        self.height = 78
        return availWidth, self.height

    def drawOn(self, canvas: Any, x: float, y: float, _sW: float = 0) -> None:
        canvas.saveState()
        canvas.translate(x, y)
        labels = ["Topic", "Skill routing", "Evidence KB", "Grounded writing", "Citation check", "Exports"]
        count = len(labels)
        gap = 8
        box_w = (self.width - gap * (count - 1)) / count
        for index, label in enumerate(labels):
            left = index * (box_w + gap)
            canvas.setFillColorRGB(0.94, 0.97, 1.0)
            canvas.setStrokeColorRGB(0.66, 0.74, 0.83)
            canvas.roundRect(left, 22, box_w, 34, 5, stroke=1, fill=1)
            canvas.setFillColorRGB(0.10, 0.18, 0.27)
            canvas.setFont("Helvetica", 7.5)
            canvas.drawCentredString(left + box_w / 2, 37, label)
            if index < count - 1:
                canvas.setStrokeColorRGB(0.45, 0.56, 0.70)
                canvas.line(left + box_w + 1, 39, left + box_w + gap - 1, 39)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColorRGB(0.38, 0.45, 0.52)
        canvas.drawString(
            0,
            5,
            f"Retrieved {self.summary.get('paper_count', 0)} papers and "
            f"{self.summary.get('evidence_count', 0)} evidence records; "
            f"cited {self.summary.get('cited_evidence_count', 0)} evidence ids.",
        )
        canvas.restoreState()


class _YearBars(_BaseDemoFlowable):
    def __init__(self, summary: dict[str, Any]):
        self.rows = [row for row in summary.get("year_counts", []) if row.get("label") != "Unknown"][-14:]

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
        self.width = availWidth
        self.height = 105 if self.rows else 14
        return availWidth, self.height

    def drawOn(self, canvas: Any, x: float, y: float, _sW: float = 0) -> None:
        if not self.rows:
            return
        canvas.saveState()
        canvas.translate(x, y)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColorRGB(0.10, 0.18, 0.27)
        canvas.drawString(0, 90, "Evidence Timeline")
        max_count = max(int(row.get("count") or 0) for row in self.rows) or 1
        gap = 4
        bar_w = max(10, (self.width - gap * (len(self.rows) - 1)) / len(self.rows))
        for index, row in enumerate(self.rows):
            count = int(row.get("count") or 0)
            height = 52 * count / max_count
            left = index * (bar_w + gap)
            canvas.setFillColorRGB(0.22, 0.50, 0.76)
            canvas.rect(left, 24, bar_w, height, stroke=0, fill=1)
            canvas.setFillColorRGB(0.34, 0.40, 0.48)
            canvas.setFont("Helvetica", 6)
            canvas.drawCentredString(left + bar_w / 2, 13, str(row.get("label"))[-4:])
        canvas.restoreState()


def _markdown_flowables(markdown: str, styles: dict[str, Any]) -> list[Any]:
    from reportlab.platypus import Paragraph, Preformatted, Spacer

    flowables: list[Any] = []
    paragraph: list[str] = []
    in_code = False
    code_lines: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph:
            return
        flowables.append(Paragraph(_inline_markup(" ".join(paragraph)), styles["BodyText"]))
        flowables.append(Spacer(1, 5))
        paragraph.clear()

    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.startswith("```"):
            if in_code:
                flowables.append(Preformatted("\n".join(code_lines), styles["Code"]))
                code_lines.clear()
                in_code = False
            else:
                flush_paragraph()
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not line.strip():
            flush_paragraph()
            continue
        heading = re.match(r"^(#{1,4})\s+(.*)$", line)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            style_name = "Heading1" if level == 1 else "Heading2" if level == 2 else "Heading3"
            flowables.append(Paragraph(_inline_markup(heading.group(2)), styles[style_name]))
            continue
        bullet = re.match(r"^[-*]\s+(.*)$", line)
        numbered = re.match(r"^\d+\.\s+(.*)$", line)
        if bullet or numbered:
            flush_paragraph()
            flowables.append(Paragraph(_inline_markup((bullet or numbered).group(1)), styles["Bullet"], bulletText="•"))
            continue
        if line.startswith("|"):
            flush_paragraph()
            continue
        paragraph.append(line.strip())
    flush_paragraph()
    return flowables


def _inline_markup(text: str) -> str:
    safe = _escape(text)
    safe = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)
    safe = re.sub(
        r"\b(P\d{2,4}-E\d{2,3})\b",
        r'<font color="#1f6feb">\1</font>',
        safe,
    )
    return safe


def _escape(text: Any) -> str:
    return html.escape(str(text), quote=False)


def _write_basic_pdf(*, markdown: str, topic: str, output_path: Path) -> None:
    lines = [f"Literature Review Harness Demo: {topic}", ""]
    lines.extend(_plain_markdown_lines(markdown))
    pages = [lines[index : index + 48] for index in range(0, len(lines), 48)] or [[]]
    objects: list[bytes] = []

    def add_object(payload: bytes) -> int:
        objects.append(payload)
        return len(objects)

    font_id = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids: list[int] = []
    content_ids: list[int] = []
    for page in pages:
        commands = ["BT /F1 10 Tf 54 790 Td 13 TL"]
        for line in page:
            commands.append(f"({_pdf_escape(line)}) Tj T*")
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1", "replace")
        content_ids.append(add_object(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"))
        page_ids.append(0)

    pages_id_placeholder = len(objects) + len(pages) + 1
    for index, content_id in enumerate(content_ids):
        page_ids[index] = add_object(
            (
                f"<< /Type /Page /Parent {pages_id_placeholder} 0 R "
                f"/MediaBox [0 0 595 842] /Resources << /Font << /F1 {font_id} 0 R >> >> "
                f"/Contents {content_id} 0 R >>"
            ).encode("latin-1")
        )
    pages_id = add_object(
        (
            f"<< /Type /Pages /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] "
            f"/Count {len(page_ids)} >>"
        ).encode("latin-1")
    )
    catalog_id = add_object(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("latin-1"))

    chunks = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets = [0]
    for index, payload in enumerate(objects, start=1):
        offsets.append(sum(len(chunk) for chunk in chunks))
        chunks.append(f"{index} 0 obj\n".encode("latin-1") + payload + b"\nendobj\n")
    xref_offset = sum(len(chunk) for chunk in chunks)
    chunks.append(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin-1"))
    for offset in offsets[1:]:
        chunks.append(f"{offset:010d} 00000 n \n".encode("latin-1"))
    chunks.append(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("latin-1")
    )
    output_path.write_bytes(b"".join(chunks))


def _plain_markdown_lines(markdown: str) -> list[str]:
    lines: list[str] = []
    for raw in markdown.splitlines():
        text = re.sub(r"^#{1,6}\s*", "", raw.strip())
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"`(.+?)`", r"\1", text)
        if not text:
            lines.append("")
            continue
        lines.extend(textwrap.wrap(text, width=88) or [""])
    return lines


def _pdf_escape(text: str) -> str:
    clean = text.encode("latin-1", "replace").decode("latin-1")
    return clean.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
