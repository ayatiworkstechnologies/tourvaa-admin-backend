"""
Day-wise itinerary PDF generation.
Uses ReportLab if available and otherwise generates a small, standards-valid
text PDF. The fallback must still be a real PDF: a text file with a .pdf
extension cannot be opened by browser PDF viewers.
"""

import logging
from html import escape
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    REPORTLAB_AVAILABLE = True
except ImportError as exc:
    REPORTLAB_AVAILABLE = False
    REPORTLAB_IMPORT_ERROR = exc
    logger.warning(
        "Itinerary PDF rendering is unavailable because a ReportLab dependency failed "
        "to import (%s: %s); itinerary output will use the plain-text fallback.",
        type(exc).__name__,
        exc,
    )


def _plain_text_pdf(path: Path, data: dict) -> None:
    """Write a dependency-free, standards-valid PDF fallback.

    This deliberately keeps the layout simple, but the output begins with a
    PDF header and has a valid cross-reference table so browser viewers and
    downloaded PDF readers can open it.
    """
    lines = [
        "=" * 60,
        f"ITINERARY: {data['tour_name']}",
        f"Booking: {data['booking_code']}",
        "=" * 60,
        f"Traveller: {data.get('customer_name', '-')}",
        f"Travel Date: {data.get('tour_date', '-')}",
        "",
    ]
    if data.get("highlights"):
        lines += ["TOUR HIGHLIGHTS", "-" * 60]
        for highlight in data["highlights"]:
            lines.append(f"* {highlight['title']}")
            if highlight.get("description"):
                lines.append(f"  {highlight['description']}")
        lines.append("")
    for day in data.get("days", []):
        lines += [
            "-" * 60,
            f"Day {day['day']}: {day['title']}",
            f"Location: {day.get('location') or '-'}",
            (day.get("description") or "").strip(),
            f"Meals: {day.get('meals') or '-'}   Transport: {day.get('transport') or '-'}",
        ]
    lines += ["", "=" * 60, "Thank you for booking with Tourvaa.", f"For queries contact {data.get('support_email') or 'support@tourvaa.com'} | {data.get('website') or 'www.tourvaa.com'}"]
    def _escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    # Helvetica is one of PDF's built-in fonts. Limit line length so basic
    # viewers do not need a layout engine to show a readable document.
    wrapped: list[str] = []
    for line in lines:
        text = str(line or "")
        if not text:
            wrapped.append("")
            continue
        while len(text) > 92:
            split_at = text.rfind(" ", 0, 93)
            split_at = split_at if split_at > 0 else 92
            wrapped.append(text[:split_at])
            text = text[split_at:].lstrip()
        wrapped.append(text)

    pages = [wrapped[index:index + 48] for index in range(0, len(wrapped), 48)] or [[""]]
    objects: list[bytes] = []
    # Object 1 is the catalog and object 2 is filled in after page objects
    # are numbered. Every page gets a content and page object.
    page_object_numbers: list[int] = []
    content_object_numbers: list[int] = []
    for index in range(len(pages)):
        content_object_numbers.append(4 + index * 2)
        page_object_numbers.append(5 + index * 2)
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{number} 0 R" for number in page_object_numbers)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("ascii"))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for page, content_number in zip(pages, content_object_numbers):
        commands = ["BT", "/F1 10 Tf", "50 790 Td", "14 TL"]
        for line in page:
            commands.append(f"({_escape(line)}) Tj")
            commands.append("T*")
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1", "replace")
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_number} 0 R >>".encode("ascii"))

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode("ascii"))
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
    path.write_bytes(bytes(output))


def _reportlab_pdf(path: Path, data: dict) -> None:
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Heading1"], fontSize=20, textColor=colors.HexColor("#1a365d"))
    center_style = ParagraphStyle("center", parent=styles["Normal"], alignment=TA_CENTER)

    story = [
        Paragraph("TOURVAA", title_style),
        Paragraph(f"<b>ITINERARY</b> - {data['tour_name']}", styles["Heading2"]),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#2d6a4f")),
        Spacer(1, 0.3 * cm),
    ]

    meta = [
        ["Booking Code:", data["booking_code"], "Travel Date:", data.get("tour_date", "-")],
        ["Traveller:", data.get("customer_name", "-"), "", ""],
    ]
    meta_table = Table(meta, colWidths=[3.5 * cm, 7 * cm, 3.5 * cm, 4 * cm])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("SPAN", (1, 1), (3, 1)),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.5 * cm))

    if data.get("highlights"):
        story.append(Paragraph("Tour Highlights", styles["Heading2"]))
        for highlight in data["highlights"]:
            story.append(Paragraph(f"&bull; <b>{highlight['title']}</b>", styles["Normal"]))
            if highlight.get("description"):
                story.append(Paragraph(highlight["description"], styles["Normal"]))
        story.append(Spacer(1, 0.4 * cm))

    for day in data.get("days", []):
        story.append(Paragraph(f"Day {day['day']}: {day['title']}", styles["Heading3"]))
        details = " | ".join(filter(None, [
            day.get("location") and f"Location: {day['location']}",
            day.get("meals") and f"Meals: {day['meals']}",
            day.get("transport") and f"Transport: {day['transport']}",
        ]))
        if details:
            story.append(Paragraph(details, styles["Normal"]))
        if day.get("description"):
            story.append(Spacer(1, 0.1 * cm))
            story.append(Paragraph(day["description"], styles["Normal"]))
        story.append(Spacer(1, 0.4 * cm))

    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.gray))
    story.append(Spacer(1, 0.2 * cm))
    support_email = escape(str(data.get("support_email") or "support@tourvaa.com"))
    website = escape(str(data.get("website") or "www.tourvaa.com"))
    story.append(Paragraph(f"Thank you for booking with <b>Tourvaa</b>. For queries contact {support_email} &nbsp;|&nbsp; {website}", center_style))

    doc.build(story)


def generate_pdf(output_path: Path, itinerary_data: dict) -> None:
    """
    Generate an itinerary PDF at `output_path`.
    `itinerary_data` must contain: booking_code, tour_name, customer_name,
    tour_date, days=[{day, title, location, description, meals, transport}]
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if REPORTLAB_AVAILABLE:
        try:
            _reportlab_pdf(output_path, itinerary_data)
            return
        except Exception as exc:
            logger.error("reportlab itinerary PDF generation failed: %s", exc)

    _plain_text_pdf(output_path, itinerary_data)
