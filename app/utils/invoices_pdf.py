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
        f"{'Balance Due Date':<40} {inv.get('balance_due_date') or 'Fully paid':>8}",
        "=" * 60,
        "Thank you for booking with Tourvaa.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


BRAND = colors.HexColor("#1b5e46")
BRAND_DARK = colors.HexColor("#0f3d2c")
INK = colors.HexColor("#1f2937")
MUTED = colors.HexColor("#6b7280")
LINE = colors.HexColor("#e2e8e5")
ROW_ALT = colors.HexColor("#f4f8f6")
PANEL = colors.HexColor("#f0f5f2")
PAID_BG = colors.HexColor("#e6f4ea")
PAID_FG = colors.HexColor("#1e7a3d")
DUE_BG = colors.HexColor("#fdecea")
DUE_FG = colors.HexColor("#b3261e")


def _money(inv: dict, value) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        amount = 0.0
    return f"{inv.get('currency', '')} {amount:,.2f}".strip()


def _reportlab_pdf(path: Path, data: dict) -> None:
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=1.8 * cm, leftMargin=1.8 * cm, topMargin=1.6 * cm, bottomMargin=1.6 * cm)
    styles = getSampleStyleSheet()
    brand_style = ParagraphStyle("brand", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=22, textColor=BRAND_DARK, leading=26)
    tagline_style = ParagraphStyle("tagline", parent=styles["Normal"], fontSize=8.5, textColor=MUTED, leading=11)
    invoice_title_style = ParagraphStyle("invtitle", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=16, textColor=INK, alignment=TA_RIGHT, leading=19)
    invoice_meta_style = ParagraphStyle("invmeta", parent=styles["Normal"], fontSize=9.5, textColor=MUTED, alignment=TA_RIGHT, leading=13)
    section_label_style = ParagraphStyle("seclabel", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8.5, textColor=BRAND, leading=11)
    body_style = ParagraphStyle("body", parent=styles["Normal"], fontSize=9.5, textColor=INK, leading=14)
    body_bold_style = ParagraphStyle("bodyb", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9.5, textColor=INK, leading=14)
    center_style = ParagraphStyle("center", parent=styles["Normal"], fontSize=8.5, textColor=MUTED, alignment=TA_CENTER, leading=12)
    item_desc_style = ParagraphStyle("itemdesc", parent=styles["Normal"], fontSize=9, textColor=INK, leading=12)

    inv = data
    is_paid = float(inv.get("amount_due") or 0) <= 0
    status_bg, status_fg = (PAID_BG, PAID_FG) if is_paid else (DUE_BG, DUE_FG)
    status_label = "PAID" if is_paid else inv["status"].upper()

    story = []

    # ---- Header: brand block (left) + invoice title block (right) ----
    header_left = [
        Paragraph("TOURVAA", brand_style),
        Spacer(1, 0.1 * cm),
        Paragraph("Curated journeys, effortlessly booked.", tagline_style),
    ]
    header_right = [
        Paragraph("INVOICE", invoice_title_style),
        Spacer(1, 0.15 * cm),
        Paragraph(f"#{inv['invoice_number']}", invoice_meta_style),
        Paragraph(f"Date: {inv['invoice_date']}", invoice_meta_style),
    ]
    header_table = Table([[header_left, header_right]], colWidths=[10.4 * cm, 6.8 * cm])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.35 * cm))
    story.append(HRFlowable(width="100%", thickness=1.4, color=BRAND))
    story.append(Spacer(1, 0.5 * cm))

    # ---- Status badge + booking code row ----
    badge_table = Table([[f"  {status_label}  "]], colWidths=[None])
    badge_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), status_bg),
        ("TEXTCOLOR", (0, 0), (-1, -1), status_fg),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))
    booking_para = Paragraph(f"<b>Booking Code:</b> {inv['booking_code']}", body_style)
    status_row = Table([[badge_table, booking_para]], colWidths=[4 * cm, 13.2 * cm])
    status_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(status_row)
    story.append(Spacer(1, 0.5 * cm))

    # ---- Billed To / Trip details panels ----
    billed_to = [
        Paragraph("BILLED TO", section_label_style),
        Spacer(1, 0.15 * cm),
        Paragraph(inv["customer_name"], body_bold_style),
        Paragraph(f"Traveller(s): {inv.get('traveller_names', '-')}", body_style),
    ]
    trip_details = [
        Paragraph("TRIP DETAILS", section_label_style),
        Spacer(1, 0.15 * cm),
        Paragraph(inv.get("tour_name", "-"), body_bold_style),
        Paragraph(f"Payment Method: {inv.get('payment_method', '-')}", body_style),
    ]
    panels = Table([[billed_to, trip_details]], colWidths=[8.6 * cm, 8.6 * cm])
    panels.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PANEL),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 12),
        ("LEFTPADDING", (1, 0), (1, 0), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LINEBEFORE", (1, 0), (1, 0), 0.75, LINE),
    ]))
    story.append(panels)
    story.append(Spacer(1, 0.6 * cm))

    # ---- Line items ----
    header_row = [
        Paragraph("#", ParagraphStyle("th", parent=body_style, textColor=colors.white, fontName="Helvetica-Bold")),
        Paragraph("Description", ParagraphStyle("th", parent=body_style, textColor=colors.white, fontName="Helvetica-Bold")),
        Paragraph("Qty", ParagraphStyle("thr", parent=body_style, textColor=colors.white, fontName="Helvetica-Bold", alignment=TA_RIGHT)),
        Paragraph("Unit Price", ParagraphStyle("thr", parent=body_style, textColor=colors.white, fontName="Helvetica-Bold", alignment=TA_RIGHT)),
        Paragraph("Tax", ParagraphStyle("thr", parent=body_style, textColor=colors.white, fontName="Helvetica-Bold", alignment=TA_RIGHT)),
        Paragraph("Total", ParagraphStyle("thr", parent=body_style, textColor=colors.white, fontName="Helvetica-Bold", alignment=TA_RIGHT)),
    ]
    table_data = [header_row]
    amt_right = ParagraphStyle("amtr", parent=item_desc_style, alignment=TA_RIGHT)
    for i, item in enumerate(inv.get("items", []), 1):
        table_data.append([
            Paragraph(str(i), item_desc_style),
            Paragraph(item["description"], item_desc_style),
            Paragraph(str(item["quantity"]), amt_right),
            Paragraph(_money(inv, item["unit_price"]), amt_right),
            Paragraph(_money(inv, item["tax_amount"]), amt_right),
            Paragraph(_money(inv, item["total_price"]), amt_right),
        ])

    items_table = Table(table_data, colWidths=[0.8 * cm, 7.2 * cm, 1.4 * cm, 2.8 * cm, 2.4 * cm, 2.6 * cm], repeatRows=1)
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_DARK),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
        ("LINEBELOW", (0, 0), (-1, 0), 0, colors.white),
        ("LINEBELOW", (0, 1), (-1, -2), 0.5, LINE),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, LINE),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (0, -1), 10),
        ("LEFTPADDING", (1, 0), (1, -1), 8),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 0.5 * cm))

    # ---- Totals ----
    gst_rate = inv.get("gst_rate", "0.18")
    try:
        gst_pct = f"{float(gst_rate) * 100:.0f}%"
    except (TypeError, ValueError):
        gst_pct = str(gst_rate)

    totals_rows = [
        ["Subtotal", _money(inv, inv["subtotal_amount"])],
        [f"Tax / GST ({gst_pct})", _money(inv, inv["gst_amount"])],
        ["Total", _money(inv, inv["total_amount"])],
        ["Amount Paid", _money(inv, inv["amount_paid"])],
        ["Amount Due", _money(inv, inv["amount_due"])],
        ["Balance Due Date", inv.get("balance_due_date") or "Fully paid"],
    ]
    totals_table = Table(totals_rows, colWidths=[5.4 * cm, 4.0 * cm])
    totals_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        # Total row emphasis
        ("BACKGROUND", (0, 2), (-1, 2), PANEL),
        ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
        ("FONTSIZE", (0, 2), (-1, 2), 11),
        ("TEXTCOLOR", (0, 2), (-1, 2), BRAND_DARK),
        ("TOPPADDING", (0, 2), (-1, 2), 7),
        ("BOTTOMPADDING", (0, 2), (-1, 2), 7),
        ("LEFTPADDING", (0, 2), (0, 2), 8),
        ("RIGHTPADDING", (1, 2), (1, 2), 8),
        # Amount due emphasis
        ("TEXTCOLOR", (0, 4), (-1, 4), (DUE_FG if not is_paid else INK)),
        ("FONTNAME", (0, 4), (-1, 4), "Helvetica-Bold"),
        # Rules
        ("LINEABOVE", (0, 2), (-1, 2), 0.75, BRAND),
        ("LINEBELOW", (0, 2), (-1, 2), 0.75, BRAND),
        ("LINEBELOW", (0, -1), (-1, -1), 0.75, LINE),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    totals_wrapper = Table([["", totals_table]], colWidths=[7.8 * cm, 9.4 * cm])
    totals_wrapper.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(totals_wrapper)
    story.append(Spacer(1, 1 * cm))

    # ---- Footer ----
    story.append(HRFlowable(width="100%", thickness=0.5, color=LINE))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Thank you for booking with <b>Tourvaa</b>.", center_style))
    story.append(Paragraph("For queries contact support@tourvaa.com &nbsp;|&nbsp; www.tourvaa.com", center_style))
    story.append(Spacer(1, 0.15 * cm))
    story.append(Paragraph("This is a system-generated invoice and does not require a signature.", center_style))

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
