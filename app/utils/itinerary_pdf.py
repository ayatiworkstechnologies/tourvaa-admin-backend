"""
Day-wise itinerary PDF generation.
Uses reportlab if available; falls back to a plain-text PDF stub
so the server starts even without reportlab installed.
"""

import logging
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
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.warning("reportlab not installed - itinerary PDFs will be plain text. Run: pip install reportlab")


def _plain_text_pdf(path: Path, data: dict) -> None:
    """Minimal fallback: write a readable text file with .pdf extension."""
    lines = [
        "=" * 60,
        f"ITINERARY: {data['tour_name']}",
        f"Booking: {data['booking_code']}",
        "=" * 60,
        f"Traveller: {data.get('customer_name', '-')}",
        f"Travel Date: {data.get('tour_date', '-')}",
        "",
    ]
    for day in data.get("days", []):
        lines += [
            "-" * 60,
            f"Day {day['day']}: {day['title']}",
            f"Location: {day.get('location') or '-'}",
            (day.get("description") or "").strip(),
            f"Meals: {day.get('meals') or '-'}   Transport: {day.get('transport') or '-'}",
        ]
    lines += ["", "=" * 60, "Thank you for booking with Tourvaa."]
    path.write_text("\n".join(lines), encoding="utf-8")


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
    story.append(Paragraph("Thank you for booking with <b>Tourvaa</b>. For queries contact support@tourvaa.com", center_style))

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
