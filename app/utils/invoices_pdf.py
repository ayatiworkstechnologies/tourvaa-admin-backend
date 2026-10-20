"""
Invoice PDF generation.
Uses reportlab if available; falls back to a plain-text PDF stub
so the server starts even without reportlab installed.
"""

import logging
from html import escape
from pathlib import Path

from app.utils.pdf_fallback import write_text_pdf

logger = logging.getLogger(__name__)

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER

    REPORTLAB_AVAILABLE = True

    # These are only ever used inside the reportlab-rendered PDF path below,
    # but must be defined inside this try block (not at module level) since
    # they depend on `colors`, which doesn't exist when reportlab isn't
    # installed -- see itinerary_pdf.py for the same pattern.
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
except ImportError as exc:
    REPORTLAB_AVAILABLE = False
    REPORTLAB_IMPORT_ERROR = exc
    logger.warning(
        "Invoice PDF rendering is unavailable because a ReportLab dependency failed "
        "to import (%s: %s); invoice output will use the plain-text fallback.",
        type(exc).__name__,
        exc,
    )


def _plain_text_pdf(path: Path, data: dict) -> None:
    """Write a readable, standards-valid PDF if ReportLab is unavailable."""
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
    write_text_pdf(path, lines)


def _money(inv: dict, value) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        amount = 0.0
    return f"{inv.get('currency', '')} {amount:,.2f}".strip()


def _reportlab_pdf(path: Path, data: dict) -> None:
    inv = data
    primary_hex = str(inv.get("invoice_primary_color") or "#07566A")
    header_hex = str(inv.get("invoice_header_color") or "#0B263D")
    accent_hex = str(inv.get("invoice_accent_color") or "#159C96")
    try:
        brand_color = colors.HexColor(primary_hex)
    except Exception:
        brand_color = colors.HexColor("#07566A")
    try:
        brand_dark_color = colors.HexColor(header_hex)
    except Exception:
        brand_dark_color = colors.HexColor("#0B263D")
    try:
        accent_color = colors.HexColor(accent_hex)
    except Exception:
        accent_color = colors.HexColor("#159C96")

    panel_color = colors.HexColor("#F2FAFC")
    row_alt_color = colors.HexColor("#F8FCFD")
    line_color = colors.HexColor("#E2E8F0")

    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=1.8 * cm, leftMargin=1.8 * cm, topMargin=1.6 * cm, bottomMargin=1.6 * cm)
    styles = getSampleStyleSheet()
    brand_style = ParagraphStyle("brand", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=22, textColor=brand_dark_color, leading=26)
    tagline_style = ParagraphStyle("tagline", parent=styles["Normal"], fontSize=8.5, textColor=MUTED, leading=11)
    invoice_title_style = ParagraphStyle("invtitle", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=16, textColor=INK, alignment=TA_RIGHT, leading=19)
    invoice_meta_style = ParagraphStyle("invmeta", parent=styles["Normal"], fontSize=9.5, textColor=MUTED, alignment=TA_RIGHT, leading=13)
    section_label_style = ParagraphStyle("seclabel", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8.5, textColor=brand_color, leading=11)
    body_style = ParagraphStyle("body", parent=styles["Normal"], fontSize=9.5, textColor=INK, leading=14)
    body_bold_style = ParagraphStyle("bodyb", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9.5, textColor=INK, leading=14)
    center_style = ParagraphStyle("center", parent=styles["Normal"], fontSize=8.5, textColor=MUTED, alignment=TA_CENTER, leading=12)
    item_desc_style = ParagraphStyle("itemdesc", parent=styles["Normal"], fontSize=9, textColor=INK, leading=12)

    is_paid = float(inv.get("amount_due") or 0) <= 0
    status_bg, status_fg = (PAID_BG, PAID_FG) if is_paid else (DUE_BG, DUE_FG)
    status_label = "PAID" if is_paid else inv["status"].upper()

    story = []

    # ---- Header: brand block (left) + invoice title block (right) ----
    logo_url = inv.get("invoice_logo_url")
    header_layout = inv.get("invoice_header_layout") or "both"
    logo_flowable = None

    if logo_url and header_layout in ("logo", "both"):
        try:
            import io
            import urllib.request
            from PIL import Image as PILImage

            img_bytes = None
            if str(logo_url).startswith("http://") or str(logo_url).startswith("https://"):
                req = urllib.request.Request(str(logo_url), headers={"User-Agent": "Tourvaa-Invoice-Generator/1.0"})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    img_bytes = resp.read()
            elif Path(str(logo_url)).is_file():
                img_bytes = Path(str(logo_url)).read_bytes()

            if img_bytes:
                pil_img = PILImage.open(io.BytesIO(img_bytes))
                w, h = pil_img.size
                if w > 0 and h > 0:
                    max_h = 1.3 * cm
                    max_w = 4.8 * cm
                    scale = min(max_w / w, max_h / h)
                    logo_flowable = RLImage(io.BytesIO(img_bytes), width=w * scale, height=h * scale)
        except Exception as img_err:
            logger.warning("Could not load invoice logo from %s: %s", logo_url, img_err)

    header_left = []
    if logo_flowable:
        if header_layout == "both":
            brand_p = Paragraph(escape(str(inv.get("invoice_brand_name") or "Tourvaa")).upper(), brand_style)
            logo_table = Table([[logo_flowable, brand_p]], colWidths=[None, None])
            logo_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
            header_left.append(logo_table)
        else:
            header_left.append(logo_flowable)
    else:
        header_left.append(Paragraph(escape(str(inv.get("invoice_brand_name") or "Tourvaa")).upper(), brand_style))

    header_left.append(Spacer(1, 0.1 * cm))
    header_left.append(Paragraph(escape(str(inv.get("invoice_brand_tagline") or "Curated journeys, effortlessly booked.")), tagline_style))
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
    story.append(HRFlowable(width="100%", thickness=1.5, color=brand_color))
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
        Paragraph(
            f"Invoice Currency: {inv.get('currency', 'USD')} ({escape(str(inv.get('currency_symbol') or inv.get('currency', 'USD')))})",
            body_style,
        ),
    ]
    panels = Table([[billed_to, trip_details]], colWidths=[8.6 * cm, 8.6 * cm])
    panels.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), panel_color),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 12),
        ("LEFTPADDING", (1, 0), (1, 0), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LINEBEFORE", (1, 0), (1, 0), 0.75, line_color),
    ]))
    story.append(panels)
    story.append(Spacer(1, 0.6 * cm))

    # ---- Line items ----
    header_row = [
        Paragraph("#", ParagraphStyle("th", parent=body_style, textColor=colors.white, fontName="Helvetica-Bold")),
        Paragraph(str(inv.get("invoice_column_description") or "Description"), ParagraphStyle("th", parent=body_style, textColor=colors.white, fontName="Helvetica-Bold")),
        Paragraph(str(inv.get("invoice_column_quantity") or "Qty"), ParagraphStyle("thr", parent=body_style, textColor=colors.white, fontName="Helvetica-Bold", alignment=TA_RIGHT)),
        Paragraph(str(inv.get("invoice_column_unit_price") or "Unit Price"), ParagraphStyle("thr", parent=body_style, textColor=colors.white, fontName="Helvetica-Bold", alignment=TA_RIGHT)),
        Paragraph(str(inv.get("invoice_column_tax") or "Tax"), ParagraphStyle("thr", parent=body_style, textColor=colors.white, fontName="Helvetica-Bold", alignment=TA_RIGHT)),
        Paragraph(str(inv.get("invoice_column_total") or "Total"), ParagraphStyle("thr", parent=body_style, textColor=colors.white, fontName="Helvetica-Bold", alignment=TA_RIGHT)),
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
        ("BACKGROUND", (0, 0), (-1, 0), brand_dark_color),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, row_alt_color]),
        ("LINEBELOW", (0, 0), (-1, 0), 0, colors.white),
        ("LINEBELOW", (0, 1), (-1, -2), 0.5, line_color),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, line_color),
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
        [str(inv.get("invoice_label_amount_due") or "Amount Due"), _money(inv, inv["amount_due"])],
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
        ("BACKGROUND", (0, 2), (-1, 2), panel_color),
        ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
        ("FONTSIZE", (0, 2), (-1, 2), 11),
        ("TEXTCOLOR", (0, 2), (-1, 2), brand_dark_color),
        ("TOPPADDING", (0, 2), (-1, 2), 7),
        ("BOTTOMPADDING", (0, 2), (-1, 2), 7),
        ("LEFTPADDING", (0, 2), (0, 2), 8),
        ("RIGHTPADDING", (1, 2), (1, 2), 8),
        # Amount due emphasis
        ("TEXTCOLOR", (0, 4), (-1, 4), (DUE_FG if not is_paid else INK)),
        ("FONTNAME", (0, 4), (-1, 4), "Helvetica-Bold"),
        # Rules
        ("LINEABOVE", (0, 2), (-1, 2), 0.75, brand_color),
        ("LINEBELOW", (0, 2), (-1, 2), 0.75, brand_color),
        ("LINEBELOW", (0, -1), (-1, -1), 0.75, line_color),
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
    story.append(HRFlowable(width="100%", thickness=0.5, color=line_color))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(escape(str(inv.get("invoice_footer_thanks") or "Thank you for booking with Tourvaa.")), center_style))
    support_email = escape(str(data.get("support_email") or "support@tourvaa.com"))
    website = escape(str(data.get("website") or "www.tourvaa.com"))
    story.append(Paragraph(f"For queries contact {support_email} &nbsp;|&nbsp; {website}", center_style))
    story.append(Spacer(1, 0.15 * cm))
    story.append(Paragraph(escape(str(inv.get("invoice_footer_legal") or "This is a system-generated invoice and does not require a signature.")), center_style))

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
