"""
Invoice PDF generation.
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
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER

    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.warning("reportlab not installed - invoice PDFs will be plain text. Run: pip install reportlab")


def _plain_text_pdf(path: Path, data: dict) -> None:
    """Minimal fallback: write a readable text file with .pdf extension."""
    inv = data
    lines = [
        "=" * 60,
        f"INVOICE: {inv['invoice_number']}",
        "=" * 60,
        f"Booking:   {inv['booking_code']}",
        f"Customer:  {inv['customer_name']}",
        f"Tour:      {inv.get('tour_name', '-')}",
        f"Traveller(s): {inv.get('traveller_names', '-')}",
        f"Payment Method: {inv.get('payment_method', '-')}",
        f"Date:      {inv['invoice_date']}",
        "",
        "-" * 60,
        f"{'Description':<40} {'Amount':>10}",
        "-" * 60,
    ]
    for item in inv.get("items", []):
        lines.append(f"{item['description'][:40]:<40} {inv['currency']} {item['total_price']:>8}")
    lines += [
        "-" * 60,
        f"{'Subtotal':<40} {inv['currency']} {inv['subtotal_amount']:>8}",
        f"{'Tax / GST':<40} {inv['currency']} {inv['gst_amount']:>8}",
        f"{'TOTAL':<40} {inv['currency']} {inv['total_amount']:>8}",
        f"{'Amount Paid':<40} {inv['currency']} {inv['amount_paid']:>8}",
        f"{'Amount Due':<40} {inv['currency']} {inv['amount_due']:>8}",
        "=" * 60,
        "Thank you for booking with Tourvaa.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _reportlab_pdf(path: Path, data: dict) -> None:
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Heading1"], fontSize=20, textColor=colors.HexColor("#1a365d"))
    right_style = ParagraphStyle("right", parent=styles["Normal"], alignment=TA_RIGHT)
    center_style = ParagraphStyle("center", parent=styles["Normal"], alignment=TA_CENTER)

    inv = data
    story = []

    # Header
    story.append(Paragraph("TOURVAA", title_style))
    story.append(Paragraph(f"<b>INVOICE</b>  #{inv['invoice_number']}", styles["Heading2"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#2d6a4f")))
    story.append(Spacer(1, 0.3 * cm))

    # Meta table
    meta = [
        ["Invoice Date:", inv["invoice_date"], "Booking Code:", inv["booking_code"]],
        ["Customer:", inv["customer_name"], "Status:", inv["status"].upper()],
        ["Tour:", inv.get("tour_name", "-"), "Payment Method:", inv.get("payment_method", "-")],
        ["Traveller(s):", inv.get("traveller_names", "-"), "", ""],
    ]
    meta_table = Table(meta, colWidths=[3.5 * cm, 7 * cm, 3.5 * cm, 4 * cm])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("SPAN", (1, 3), (3, 3)),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.5 * cm))

    # Line items
    table_data = [["#", "Description", "Qty", "Unit Price", "Tax", "Total"]]
    for i, item in enumerate(inv.get("items", []), 1):
        table_data.append([
            str(i),
            item["description"],
            str(item["quantity"]),
            f"{inv['currency']} {item['unit_price']}",
            f"{inv['currency']} {item['tax_amount']}",
            f"{inv['currency']} {item['total_price']}",
        ])

    items_table = Table(table_data, colWidths=[0.8 * cm, 8.2 * cm, 1.5 * cm, 3 * cm, 2.5 * cm, 3 * cm])
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d6a4f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4f8")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 0.5 * cm))

    # Totals
    totals_data = [
        ["Subtotal", f"{inv['currency']} {inv['subtotal_amount']}"],
        ["Tax / GST", f"{inv['currency']} {inv['gst_amount']}"],
        ["Total", f"{inv['currency']} {inv['total_amount']}"],
        ["Amount Paid", f"{inv['currency']} {inv['amount_paid']}"],
        ["Amount Due", f"{inv['currency']} {inv['amount_due']}"],
    ]
    totals_table = Table(totals_data, colWidths=[14 * cm, 5 * cm])
    totals_table.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#2d6a4f")),
        ("LINEABOVE", (0, 2), (-1, 2), 0.5, colors.HexColor("#cccccc")),
    ]))
    story.append(totals_table)
    story.append(Spacer(1, 1 * cm))

    # Footer
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.gray))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("Thank you for booking with <b>Tourvaa</b>. For queries contact support@tourvaa.com", center_style))

    doc.build(story)


def generate_pdf(output_path: Path, invoice_data: dict) -> None:
    """
    Generate an invoice PDF at `output_path`.
    `invoice_data` must contain: invoice_number, booking_code, customer_name,
    tour_name, traveller_names, payment_method, invoice_date, status, currency,
    subtotal_amount, gst_amount, total_amount, amount_paid, amount_due,
    items=[{description, quantity, unit_price, tax_amount, total_price}]
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if REPORTLAB_AVAILABLE:
        try:
            _reportlab_pdf(output_path, invoice_data)
            return
        except Exception as exc:
            logger.error("reportlab PDF generation failed: %s", exc)

    # Fallback
    _plain_text_pdf(output_path, invoice_data)
