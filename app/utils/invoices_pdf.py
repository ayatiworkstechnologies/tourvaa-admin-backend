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
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT

    REPORTLAB_AVAILABLE = True

    # ReportLab color constants
    NAVY_HEADER = colors.HexColor("#0B263D")
    TEAL_BRAND = colors.HexColor("#07566A")
    ACCENT_TEAL = colors.HexColor("#159C96")
    RED_ACCENT = colors.HexColor("#C62828")
    INK = colors.HexColor("#1F2937")
    MUTED = colors.HexColor("#4B5563")
    LIGHT_MUTED = colors.HexColor("#6B7280")
    LINE = colors.HexColor("#CBD5E1")
    LIGHT_BG = colors.HexColor("#F8FAFC")
    BADGE_BG = colors.HexColor("#F1F5F9")
    TOTAL_BG = colors.HexColor("#EBF3F8")
    DUE_FG = colors.HexColor("#B3261E")
except ImportError as exc:
    REPORTLAB_AVAILABLE = False
    REPORTLAB_IMPORT_ERROR = exc
    logger.warning(
        "Invoice PDF rendering is unavailable because a ReportLab dependency failed "
        "to import (%s: %s); invoice output will use the plain-text fallback.",
        type(exc).__name__,
        exc,
    )


def _money(inv: dict, value) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        amount = 0.0
    curr = inv.get("currency") or ""
    return f"{curr} {amount:,.2f}".strip()


def _plain_text_pdf(path: Path, data: dict) -> None:
    """Write a readable, standards-valid plain text PDF if ReportLab is unavailable."""
    inv = data
    doc_label = str(inv.get("document_label") or "INVOICE")
    doc_num = str(inv.get("invoice_number") or "-")
    doc_date = str(inv.get("invoice_date") or "-")
    currency = inv.get("currency", "")

    lines = [
        "=" * 64,
        f"TOURVAA - {doc_label}: {doc_num}",
        f"Issued: {doc_date}",
        "=" * 64,
        "",
        "FROM:",
        f"  {inv.get('tourvaa_legal_business_name') or 'Tourvaa Ltd'}",
        f"  {inv.get('tourvaa_business_address') or '-'}",
        f"  {inv.get('tourvaa_email') or 'support@tourvaa.com'} | {inv.get('tourvaa_website') or 'www.tourvaa.com'}",
    ]
    if inv.get("tourvaa_gst_number"):
        lines.append(f"  GST No.: {inv['tourvaa_gst_number']}")

    lines.append("")
    recipient_label = "RECEIVED FROM:" if inv.get("is_full_receipt") else "BILL TO:"
    lines.append(recipient_label)
    if inv.get("is_agent") and inv.get("recipient_business_name"):
        lines.append(f"  {inv['recipient_business_name']}")
        if inv.get("recipient_contact_name"):
            lines.append(f"  Attn: {inv['recipient_contact_name']}")
    else:
        lines.append(f"  {inv.get('customer_name') or inv.get('recipient_contact_name') or '-'}")
    if inv.get("recipient_address"):
        lines.append(f"  {inv['recipient_address']}")
    if inv.get("recipient_email"):
        lines.append(f"  {inv['recipient_email']}")
    if inv.get("recipient_phone"):
        lines.append(f"  {inv['recipient_phone']}")

    lines += [
        "",
        "-" * 64,
        "BOOKING DETAILS",
        "-" * 64,
        f"Booking Reference: {inv.get('booking_code', '-')}",
        f"Tour:              {inv.get('tour_name', '-')}",
        f"Travel Date:       {inv.get('travel_date', '-')}",
        f"Travellers:        {inv.get('adult_count', 0)} adults, {inv.get('child_count', 0)} children",
    ]
    if inv.get("lead_traveller"):
        lines.append(f"Lead traveller:    {inv['lead_traveller']}")
    if inv.get("pickup"):
        lines.append(f"Start / Pickup:    {inv['pickup']}")

    lines += [
        "",
        "-" * 64,
        f"{'PRICE SUMMARY - Description':<40} {'Qty':<10} {'Amount':>12}",
        "-" * 64,
    ]
    for item in inv.get("items", []):
        desc = str(item.get("description", ""))[:38]
        qty = str(item.get("quantity", ""))[:9]
        amt = _money(inv, item.get("total_price", 0))
        lines.append(f"{desc:<40} {qty:<10} {amt:>12}")
    booking_total = inv.get("booking_total") or inv.get("total_amount") or 0
    lines.append(f"{'TOTAL BOOKING AMOUNT':<50} {_money(inv, booking_total):>12}")

    lines += [
        "",
        "-" * 64,
        "PAYMENT SUMMARY",
        "-" * 64,
    ]
    paid_to_date = inv.get("cumulative_paid") if inv.get("cumulative_paid") is not None else inv.get("amount_paid")
    amount_due = inv.get("amount_due") or 0
    lines.append(f"{'Amount paid to date:':<40} {_money(inv, paid_to_date):>22}")
    lines.append(f"{'BALANCE DUE:':<40} {_money(inv, amount_due):>22}")
    try:
        due_val = float(amount_due)
    except Exception:
        due_val = 0.0
    if due_val > 0 and inv.get("balance_due_date"):
        lines.append(f"{'Payment Due Date:':<40} {str(inv['balance_due_date']):>22}")

    if inv.get("payment_date") or inv.get("payment_method") or inv.get("transaction_id"):
        lines += [
            "",
            f"Payment Date:   {str(inv.get('payment_date') or '-')[:10]}",
            f"Payment Method: {inv.get('payment_method') or '-'}",
            f"Transaction ID: {inv.get('transaction_id') or '-'}",
        ]

    b_status = str(inv.get("booking_status") or "-").replace("_", " ").title()
    p_status = str(inv.get("payment_status") or ("Paid in Full" if due_val <= 0 else "Outstanding")).replace("_", " ").title()
    lines += [
        "",
        f"Booking status: {b_status} | Payment status: {p_status}",
    ]

    lines += [
        "",
        "-" * 64,
        "IMPORTANT BOOKING INFORMATION",
        "-" * 64,
        f"Terms and Conditions: {inv.get('terms_url') or '-'}",
        f"Cancellation policy:  {inv.get('cancellation_policy') or '-'}",
        f"Queries:              {inv.get('tourvaa_email') or inv.get('support_email') or 'support@tourvaa.com'}",
    ]
    if due_val > 0 and inv.get("payment_link"):
        lines.append(f"Payment Link:         {inv['payment_link']}")

    lines += [
        "=" * 64,
        "Thank you for choosing Tourvaa.",
    ]
    write_text_pdf(path, lines)


def _reportlab_pdf(path: Path, data: dict) -> None:
    inv = data

    # 1. Resolve document classification & labels according to the 4 approved template types:
    is_agent = bool(inv.get("is_agent"))
    is_booking_invoice = bool(inv.get("is_booking_invoice"))
    is_deposit_document = bool(inv.get("is_deposit_document"))
    is_full_receipt = bool(inv.get("is_full_receipt"))

    # Fallback derivation if flags were omitted
    doc_label = str(inv.get("document_label") or "")
    if not is_booking_invoice and not is_deposit_document and not is_full_receipt:
        if "AGENT BOOKING" in doc_label or "agent_reservation" in doc_label.lower():
            is_booking_invoice = True
            is_agent = True
        elif "DEPOSIT" in doc_label or "deposit" in doc_label.lower():
            is_deposit_document = True
        elif "RECEIPT" in doc_label or "receipt" in doc_label.lower():
            is_full_receipt = True
            if "AGENT" in doc_label:
                is_agent = True
        else:
            try:
                amt_due = float(inv.get("amount_due") or 0)
                if amt_due <= 0:
                    is_full_receipt = True
                else:
                    is_deposit_document = True
            except Exception:
                pass

    if inv.get("document_title"):
        doc_title = str(inv["document_title"])
        doc_subtitle = ""
        doc_number_label = str(inv.get("doc_number_label") or ("Receipt No." if is_full_receipt else "Invoice No."))
        recipient_heading = str(inv.get("recipient_heading") or ("RECEIVED FROM" if is_full_receipt else "BILL TO"))
    elif is_booking_invoice:
        doc_title = "BOOKING INVOICE"
        doc_subtitle = ""
        doc_number_label = "Invoice No."
        recipient_heading = "BILL TO"
    elif is_deposit_document:
        doc_title = "BOOKING INVOICE & PAYMENT RECEIPT"
        doc_subtitle = ""
        doc_number_label = "Document No."
        recipient_heading = "BILL TO"
    elif is_full_receipt:
        doc_title = "PAYMENT RECEIPT"
        doc_subtitle = ""
        doc_number_label = "Receipt No."
        recipient_heading = "RECEIVED FROM"
    else:
        doc_title = inv.get("document_label") or "INVOICE"
        doc_subtitle = ""
        doc_number_label = "Invoice No."
        recipient_heading = "BILL TO"

    try:
        balance_due_val = float(inv.get("amount_due") or 0)
    except Exception:
        balance_due_val = 0.0
    is_paid = balance_due_val <= 0

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=1.2 * cm,
        leftMargin=1.2 * cm,
        topMargin=1.0 * cm,
        bottomMargin=1.0 * cm,
    )
    styles = getSampleStyleSheet()

    # Typography styles
    brand_title_style = ParagraphStyle(
        "brand_title",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        textColor=NAVY_HEADER,
        alignment=TA_RIGHT,
        leading=22,
    )
    doc_header_title_style = ParagraphStyle(
        "doc_header_title",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        textColor=NAVY_HEADER,
        leading=16,
    )
    doc_header_meta_style = ParagraphStyle(
        "doc_header_meta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.8,
        textColor=MUTED,
        leading=10.5,
    )
    section_heading_style = ParagraphStyle(
        "sec_head",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        textColor=NAVY_HEADER,
        leading=12,
    )
    box_header_style = ParagraphStyle(
        "box_head",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        textColor=colors.white,
        leading=10.5,
    )
    body_style = ParagraphStyle(
        "body_norm",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        textColor=INK,
        leading=9.8,
    )
    body_bold_style = ParagraphStyle(
        "body_b",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.8,
        textColor=INK,
        leading=10,
    )
    th_style = ParagraphStyle(
        "th_norm",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.8,
        textColor=colors.white,
        leading=9.5,
    )
    th_right_style = ParagraphStyle(
        "th_r",
        parent=th_style,
        alignment=TA_RIGHT,
    )
    td_right_style = ParagraphStyle(
        "td_r",
        parent=body_style,
        alignment=TA_RIGHT,
    )
    td_center_style = ParagraphStyle(
        "td_c",
        parent=body_style,
        alignment=TA_CENTER,
    )
    center_footer_style = ParagraphStyle(
        "foot_center",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7,
        textColor=LIGHT_MUTED,
        alignment=TA_CENTER,
        leading=8.8,
    )

    story = []

    # -------------------------------------------------------------
    # HEADER: Top Left Title & Subtitle + Top Right Brand Logo
    # -------------------------------------------------------------
    logo_url = inv.get("invoice_logo_url")
    logo_flowable = None
    if logo_url:
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
                    max_w = 4.5 * cm
                    scale = min(max_w / w, max_h / h)
                    logo_flowable = RLImage(io.BytesIO(img_bytes), width=w * scale, height=h * scale)
        except Exception as img_err:
            logger.warning("Could not load invoice logo from %s: %s", logo_url, img_err)

    title_html = f"<b>{doc_title}</b>"
    if doc_subtitle:
        title_html += f' <font color="#C62828"><i>{doc_subtitle}</i></font>'

    header_left = [
        Paragraph(title_html, doc_header_title_style),
        Spacer(1, 0.12 * cm),
        Paragraph(
            f"{doc_number_label} {escape(str(inv.get('invoice_number') or ''))} &nbsp;|&nbsp; Issued {escape(str(inv.get('invoice_date') or ''))}",
            doc_header_meta_style,
        ),
    ]

    header_right = []
    if logo_flowable:
        header_right.append(logo_flowable)
    else:
        brand_name = escape(str(inv.get("invoice_brand_name") or "TOURVAA")).upper()
        header_right.append(Paragraph(f"<b>{brand_name}</b>", brand_title_style))

    header_table = Table([[header_left, header_right]], colWidths=[12.2 * cm, 6.0 * cm])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.25 * cm))

    # -------------------------------------------------------------
    # FROM & BILL TO / RECEIVED FROM PANELS
    # Rule 1: Agent recipient is always Agent business, never lead traveller.
    # Rule 8: Hide optional rows when data is unavailable; do not print empty labels.
    # -------------------------------------------------------------
    tourvaa_name = inv.get("tourvaa_legal_business_name") or inv.get("invoice_brand_name") or "Tourvaa Ltd"
    tourvaa_addr = inv.get("tourvaa_business_address") or "Level 1, 123 Queen Street, Auckland 1010, New Zealand"
    tourvaa_email = inv.get("tourvaa_email") or inv.get("support_email") or "support@tourvaa.com"
    tourvaa_web = inv.get("tourvaa_website") or inv.get("website") or "www.tourvaa.com"
    tourvaa_gst = inv.get("tourvaa_gst_number")

    from_paragraphs = [
        Paragraph(f"<b>{escape(str(tourvaa_name))}</b>", body_bold_style),
        Paragraph(escape(str(tourvaa_addr)).replace("\n", "<br/>"), body_style),
        Paragraph(f"{escape(str(tourvaa_email))} &nbsp;|&nbsp; {escape(str(tourvaa_web))}", body_style),
    ]
    if tourvaa_gst:
        from_paragraphs.append(Paragraph(f"GST No.: {escape(str(tourvaa_gst))}", body_style))

    to_paragraphs = []
    if inv.get("recipient_business_name"):
        biz_name = inv.get("recipient_business_name")
        to_paragraphs.append(Paragraph(f"<b>{escape(str(biz_name))}</b>", body_bold_style))
        if inv.get("recipient_contact_name") and inv.get("recipient_contact_name") != biz_name:
            to_paragraphs.append(Paragraph(f"Attn: {escape(str(inv['recipient_contact_name']))}", body_style))
    else:
        # Registered customer or individual
        cust_name = inv.get("customer_name") or inv.get("recipient_contact_name") or "Customer"
        to_paragraphs.append(Paragraph(f"<b>{escape(str(cust_name))}</b>", body_bold_style))

    if inv.get("recipient_address"):
        to_paragraphs.append(Paragraph(escape(str(inv["recipient_address"])).replace("\n", "<br/>"), body_style))
    if inv.get("recipient_email"):
        to_paragraphs.append(Paragraph(escape(str(inv["recipient_email"])), body_style))
    if inv.get("recipient_phone"):
        to_paragraphs.append(Paragraph(escape(str(inv["recipient_phone"])), body_style))

    from_card = Table([[Paragraph("FROM", box_header_style)], [from_paragraphs]], colWidths=[8.9 * cm])
    from_card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), NAVY_HEADER),
        ("BACKGROUND", (0, 1), (0, 1), LIGHT_BG),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("TOPPADDING", (0, 0), (0, 0), 3.5),
        ("BOTTOMPADDING", (0, 0), (0, 0), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 1), (0, 1), 5),
        ("BOTTOMPADDING", (0, 1), (0, 1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))

    to_card = Table([[Paragraph(recipient_heading, box_header_style)], [to_paragraphs]], colWidths=[8.9 * cm])
    to_card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), NAVY_HEADER),
        ("BACKGROUND", (0, 1), (0, 1), LIGHT_BG),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("TOPPADDING", (0, 0), (0, 0), 3.5),
        ("BOTTOMPADDING", (0, 0), (0, 0), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 1), (0, 1), 5),
        ("BOTTOMPADDING", (0, 1), (0, 1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))

    panels_table = Table([[from_card, "", to_card]], colWidths=[8.9 * cm, 0.4 * cm, 8.9 * cm])
    panels_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(panels_table)
    story.append(Spacer(1, 0.25 * cm))

    # -------------------------------------------------------------
    # BOOKING DETAILS
    # -------------------------------------------------------------
    story.append(Paragraph("BOOKING DETAILS", section_heading_style))
    story.append(Spacer(1, 0.08 * cm))

    adults = inv.get("adult_count") or 0
    children = inv.get("child_count") or 0
    travellers_text = f"{adults} adults, {children} children" if (adults or children) else (inv.get("traveller_names") or "-")

    booking_headers = [
        Paragraph("Booking Reference", th_style),
        Paragraph("Tour", th_style),
        Paragraph("Travel Date", th_style),
        Paragraph("Travellers", th_style),
    ]
    booking_values = [
        Paragraph(escape(str(inv.get("booking_code") or "-")), body_style),
        Paragraph(escape(str(inv.get("tour_name") or "-")), body_style),
        Paragraph(escape(str(inv.get("travel_date") or "-")), body_style),
        Paragraph(escape(travellers_text), body_style),
    ]
    booking_table = Table([booking_headers, booking_values], colWidths=[4.2 * cm, 6.0 * cm, 3.8 * cm, 4.2 * cm])
    booking_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY_HEADER),
        ("BACKGROUND", (0, 1), (-1, 1), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(booking_table)

    # Rule 8: Hide optional rows when data is unavailable
    extra_details = []
    if inv.get("lead_traveller"):
        extra_details.append(f"<b>Lead traveller:</b> {escape(str(inv['lead_traveller']))}")
    if inv.get("pickup"):
        extra_details.append(f"<b>Start / Pickup:</b> {escape(str(inv['pickup']))}")
    if extra_details:
        story.append(Spacer(1, 0.08 * cm))
        story.append(Paragraph(" &nbsp;&nbsp;&nbsp;&nbsp; ".join(extra_details), body_style))

    story.append(Spacer(1, 0.25 * cm))

    # -------------------------------------------------------------
    # PRICE SUMMARY
    # Rule 12: Configure tax display according to Tourvaa registration.
    # Rule 13: Never expose supplier net payable, Tourvaa margin or internal commission.
    # -------------------------------------------------------------
    story.append(Paragraph("PRICE SUMMARY", section_heading_style))
    story.append(Spacer(1, 0.08 * cm))

    price_headers = [
        Paragraph("Description", th_style),
        Paragraph("Quantity", th_style),
        Paragraph("Amount", th_right_style),
    ]
    price_rows = [price_headers]

    # Render items
    items = inv.get("items") or []
    if not items:
        # Default single tour price item
        tour_price_val = inv.get("tour_price") or inv.get("subtotal_amount") or inv.get("total_amount") or 0
        items = [{
            "description": "Total Tour Price",
            "quantity": f"{adults + children} travellers" if (adults + children) > 0 else "1",
            "total_price": tour_price_val,
        }]

    for item in items:
        desc = escape(str(item.get("description") or ""))
        qty = str(item.get("quantity") or "")
        tot = item.get("total_price")

        # Tax is included in the booking total but its rate and amount are
        # intentionally not disclosed on customer-facing documents.
        if "Including Tax" in desc or "Tax" in desc and "Included" in qty:
            qty_p = Paragraph(escape(qty), body_style)
            amt_p = Paragraph("", td_right_style)
        elif "Discount" in desc:
            qty_p = Paragraph(escape(qty), td_center_style)
            try:
                amt_num = float(tot)
                disc_str = f"− {_money(inv, abs(amt_num))}"
            except Exception:
                disc_str = f"− {_money(inv, tot)}"
            amt_p = Paragraph(disc_str, td_right_style)
        else:
            qty_p = Paragraph(escape(qty), body_style)
            amt_p = Paragraph(_money(inv, tot), td_right_style)

        price_rows.append([
            Paragraph(desc, body_style),
            qty_p,
            amt_p,
        ])

    booking_total_val = inv.get("booking_total") or inv.get("total_amount") or 0
    total_booking_row = [
        Paragraph("<b>TOTAL BOOKING AMOUNT</b>", ParagraphStyle("tot_lbl", parent=body_bold_style, textColor=NAVY_HEADER)),
        "",
        Paragraph(f"<b>{_money(inv, booking_total_val)}</b>", ParagraphStyle("tot_val", parent=td_right_style, fontName="Helvetica-Bold", textColor=NAVY_HEADER)),
    ]
    price_rows.append(total_booking_row)

    price_table = Table(price_rows, colWidths=[10.4 * cm, 4.0 * cm, 3.8 * cm])
    price_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY_HEADER),
        ("BACKGROUND", (0, 1), (-1, -2), colors.white),
        ("BACKGROUND", (0, -1), (-1, -1), TOTAL_BG),
        ("GRID", (0, 0), (-1, -2), 0.5, LINE),
        ("SPAN", (0, -1), (1, -1)),
        ("BOX", (0, -1), (-1, -1), 0.5, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(price_table)
    story.append(Spacer(1, 0.25 * cm))

    # -------------------------------------------------------------
    # PAYMENT SUMMARY / PAYMENT RECEIPT SUMMARY
    # Page 1 (Agent Reserves): Payment line | Amount / date
    # Page 2 & 5 (Full Receipts): Description | Amount + Payment details table
    # Page 3 (Deposit): Payment line | Amount / date + Deposit details table
    # Rule 9: Hide payment due date when the outstanding balance is zero.
    # -------------------------------------------------------------
    summary_title = "PAYMENT RECEIPT SUMMARY" if is_full_receipt else "PAYMENT SUMMARY"
    story.append(Paragraph(summary_title, section_heading_style))
    story.append(Spacer(1, 0.08 * cm))

    paid_to_date = inv.get("cumulative_paid") if inv.get("cumulative_paid") is not None else inv.get("amount_paid")

    if is_booking_invoice:
        # Page 1: Agent reservation invoice
        summary_table_rows = [
            [Paragraph("Payment line", th_style), Paragraph("Amount / date", th_right_style)],
            [Paragraph("Amount paid to date", body_style), Paragraph(_money(inv, paid_to_date), td_right_style)],
            [Paragraph("<b>BALANCE DUE</b>", body_bold_style), Paragraph(f"<b>{_money(inv, balance_due_val)}</b>", ParagraphStyle("bal_due", parent=td_right_style, fontName="Helvetica-Bold", textColor=DUE_FG if balance_due_val > 0 else NAVY_HEADER))],
        ]
        if balance_due_val > 0 and inv.get("balance_due_date"):
            summary_table_rows.append([
                Paragraph("PAYMENT DUE DATE", body_bold_style),
                Paragraph(escape(str(inv["balance_due_date"])), td_right_style),
            ])
        p_table = Table(summary_table_rows, colWidths=[12.6 * cm, 5.6 * cm])
        p_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY_HEADER),
            ("BACKGROUND", (0, 1), (-1, -1), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(p_table)

    elif is_full_receipt:
        # Pages 2 & 5: Full Payment Receipt
        receipt_table_rows = [
            [Paragraph("Description", th_style), Paragraph("Amount", th_right_style)],
            [Paragraph("Total booking amount", body_style), Paragraph(_money(inv, booking_total_val), td_right_style)],
            [Paragraph("Payment received", body_style), Paragraph(_money(inv, paid_to_date), td_right_style)],
            [Paragraph("<b>OUTSTANDING BALANCE</b>", body_bold_style), Paragraph(f"<b>{inv.get('currency', '')} 0.00</b>", ParagraphStyle("zero_bal", parent=td_right_style, fontName="Helvetica-Bold", textColor=NAVY_HEADER))],
        ]
        r_table = Table(receipt_table_rows, colWidths=[12.6 * cm, 5.6 * cm])
        r_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY_HEADER),
            ("BACKGROUND", (0, 1), (-1, -1), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(r_table)
        story.append(Spacer(1, 0.15 * cm))

        # Payment details table
        p_date_raw = inv.get("payment_date") or inv.get("invoice_date") or "-"
        p_date = str(p_date_raw)[:10]
        p_method = inv.get("payment_method") or "Credit / Debit Card"
        tx_id = inv.get("transaction_id") or "-"

        p_details_rows = [
            [Paragraph("Payment date", th_style), Paragraph("Payment method", th_style), Paragraph("Transaction ID", th_style)],
            [Paragraph(escape(p_date), body_style), Paragraph(escape(p_method), body_style), Paragraph(escape(tx_id), body_style)],
        ]
        p_details_table = Table(p_details_rows, colWidths=[6.0 * cm, 6.0 * cm, 6.2 * cm])
        p_details_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY_HEADER),
            ("BACKGROUND", (0, 1), (-1, 1), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(p_details_table)

    else:
        # Page 3: Customer Deposit Invoice & Receipt
        deposit_table_rows = [
            [Paragraph("Payment line", th_style), Paragraph("Amount / date", th_right_style)],
            [Paragraph("Deposit / payment received", body_style), Paragraph(_money(inv, paid_to_date), td_right_style)],
            [Paragraph("<b>BALANCE DUE</b>", body_bold_style), Paragraph(f"<b>{_money(inv, balance_due_val)}</b>", ParagraphStyle("dep_bal", parent=td_right_style, fontName="Helvetica-Bold", textColor=DUE_FG if balance_due_val > 0 else NAVY_HEADER))],
        ]
        if balance_due_val > 0 and inv.get("balance_due_date"):
            deposit_table_rows.append([
                Paragraph("BALANCE DUE DATE", body_bold_style),
                Paragraph(escape(str(inv["balance_due_date"])), td_right_style),
            ])
        d_table = Table(deposit_table_rows, colWidths=[12.6 * cm, 5.6 * cm])
        d_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY_HEADER),
            ("BACKGROUND", (0, 1), (-1, -1), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(d_table)
        story.append(Spacer(1, 0.15 * cm))

        # Deposit payment details table
        p_date_raw = inv.get("payment_date") or inv.get("invoice_date") or "-"
        p_date = str(p_date_raw)[:10]
        p_method = inv.get("payment_method") or "Credit / Debit Card"
        tx_id = inv.get("transaction_id") or "-"

        deposit_details_rows = [
            [Paragraph("Deposit payment date", th_style), Paragraph("Payment method", th_style), Paragraph("Transaction ID", th_style)],
            [Paragraph(escape(p_date), body_style), Paragraph(escape(p_method), body_style), Paragraph(escape(tx_id), body_style)],
        ]
        deposit_details_table = Table(deposit_details_rows, colWidths=[6.0 * cm, 6.0 * cm, 6.2 * cm])
        deposit_details_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY_HEADER),
            ("BACKGROUND", (0, 1), (-1, 1), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(deposit_details_table)

    story.append(Spacer(1, 0.18 * cm))

    # Notes & Booking/Payment Status
    due_date_str = escape(str(inv.get("balance_due_date") or "the stated due date"))
    if is_booking_invoice:
        summary_note = (
            f"Your booking has been reserved. Full payment of {_money(inv, balance_due_val)} "
            f"is due by {due_date_str}. Please ensure payment is received by the due date. "
            "Any consequences of late or non-payment are subject to the applicable Tourvaa terms and booking conditions."
        )
        status_line = "<b>Booking status:</b> Booking Confirmed &nbsp;|&nbsp; <b>Payment status:</b> Outstanding"
    elif is_full_receipt:
        if is_agent:
            summary_note = "Payment has been received in full for this booking. Thank you for booking through Tourvaa."
            status_line = "<b>Booking status:</b> Booking Confirmed &nbsp;|&nbsp; <b>Payment status:</b> Paid in Full"
        else:
            summary_note = "Payment has been received in full for this booking. Thank you for choosing Tourvaa."
            b_st = escape(str(inv.get("booking_status") or "Booking Confirmed").replace("_", " ").title())
            status_line = f"<b>Booking status:</b> {b_st} &nbsp;|&nbsp; <b>Payment status:</b> Paid in Full"
    else:
        summary_note = (
            f"Your payment of {_money(inv, paid_to_date)} has been received. The remaining balance of "
            f"{_money(inv, balance_due_val)} must be paid by {due_date_str}."
        )
        b_st = escape(str(inv.get("booking_status") or "Booking Confirmed").replace("_", " ").title())
        p_st = escape(str(inv.get("payment_status") or "Deposit Received").replace("_", " ").title())
        status_line = f"<b>Booking status:</b> {b_st} &nbsp;|&nbsp; <b>Payment status:</b> {p_st}"

    story.append(Paragraph(summary_note, body_style))
    story.append(Spacer(1, 0.08 * cm))
    story.append(Paragraph(status_line, body_style))
    story.append(Spacer(1, 0.18 * cm))



    # -------------------------------------------------------------
    # IMPORTANT BOOKING INFORMATION
    # Rule 10: Clickable terms link in PDF
    # Rule 11: Cancellation terms as at time of booking
    # -------------------------------------------------------------
    story.append(Paragraph("IMPORTANT BOOKING INFORMATION", section_heading_style))
    story.append(Spacer(1, 0.08 * cm))

    terms_url = inv.get("terms_url") or f"https://{tourvaa_web.strip('/')}/terms"
    terms_link_html = f'<link href="{escape(terms_url, quote=True)}"><font color="#07566A"><u>{escape(terms_url)}</u></font></link>'
    story.append(Paragraph(f"Tourvaa General Terms and Conditions: {terms_link_html}", body_style))

    tour_name_safe = escape(str(inv.get("tour_name") or "this tour"))
    cancel_policy_safe = escape(str(inv.get("cancellation_policy") or "Cancellation terms as recorded at booking."))
    story.append(Paragraph(f"Cancellation policy for {tour_name_safe}: {cancel_policy_safe}", body_style))

    story.append(Paragraph(f'For booking or payment queries, contact <font color="#07566A">{escape(tourvaa_email)}</font>.', body_style))

    if is_booking_invoice:
        closing_disclaimer = "This invoice reflects the booking and payment information available at the issue date. Please retain it for your records."
    elif is_deposit_document:
        closing_disclaimer = "This document records the payment received to date and the remaining balance as at the issue date."
    else:
        closing_disclaimer = "This receipt confirms payment received; it does not by itself confirm supplier acceptance if the booking status above is not confirmed."

    story.append(Paragraph(closing_disclaimer, body_style))

    if is_full_receipt and not is_agent:
        story.append(Paragraph("<i>Please note:</i> Please check your pickup and itinerary details carefully before travel.", body_style))

    story.append(Spacer(1, 0.25 * cm))

    # -------------------------------------------------------------
    # FOOTER: Payment Link (Page 6 rule 3) & Support Contact
    # -------------------------------------------------------------
    story.append(HRFlowable(width="100%", thickness=0.5, color=LINE))
    story.append(Spacer(1, 0.15 * cm))

    payment_link = inv.get("payment_link")
    if balance_due_val > 0 and payment_link:
        pay_html = f'<b>Pay Balance Online:</b> <link href="{escape(payment_link, quote=True)}"><font color="#07566A"><u>{escape(payment_link)}</u></font></link>'
        story.append(Paragraph(pay_html, center_footer_style))
        story.append(Spacer(1, 0.1 * cm))

    story.append(Paragraph(f"For booking or payment queries, contact {escape(tourvaa_email)} &nbsp;|&nbsp; {escape(tourvaa_web)}", center_footer_style))
    story.append(Paragraph(escape(str(inv.get("invoice_footer_legal") or "This document is generated by Tourvaa and reflects the financial status as of the issue date.")), center_footer_style))

    doc.build(story)


def generate_pdf(output_path: Path, invoice_data: dict) -> None:
    """
    Generate an invoice PDF at `output_path`.
    `invoice_data` contains all snapshot & calculated invoice fields.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if REPORTLAB_AVAILABLE:
        try:
            _reportlab_pdf(output_path, invoice_data)
            return
        except Exception as exc:
            logger.error("reportlab PDF generation failed: %s", exc)

    # Fallback to plain-text PDF
    _plain_text_pdf(output_path, invoice_data)
