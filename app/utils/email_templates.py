import html as _html
import os
import re


def esc(value) -> str:
    """Escape a value for safe interpolation into HTML email bodies."""
    return _html.escape(str(value)) if value is not None else ""


def base_email(title: str, intro: str, body: str, button_text: str | None = None, button_url: str | None = None):
    """Render the shared, email-client-safe wrapper used by transactional mail."""
    safe_title = esc(title)
    preheader = re.sub(r"<[^>]+>", " ", f"{title}. {intro}")
    preheader = re.sub(r"\s+", " ", _html.unescape(preheader)).strip()[:140]
    frontend_url = (os.getenv("FRONTEND_URL") or "https://tourvaa.vercel.app").rstrip("/")
    hero_url = f"{frontend_url}/images/hero-1.jpg"
    support_email = os.getenv("SMTP_REPLY_TO") or os.getenv("SMTP_FROM_EMAIL") or "support@tourvaa.com"
    button = ""

    if button_text and button_url:
        button = f"""
        <tr>
          <td style="padding:30px 0 8px;">
            <table role="presentation" cellspacing="0" cellpadding="0">
              <tr>
                <td bgcolor="#159C96" style="border-radius:12px;">
                  <a href="{esc(button_url)}" style="display:inline-block;border:1px solid #159C96;border-radius:12px;color:#ffffff;text-decoration:none;font-weight:800;font-size:16px;line-height:22px;padding:15px 28px;">
                    {esc(button_text)}&nbsp;&nbsp;&rarr;
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:12px 0 0;color:#778594;font-size:12px;line-height:19px;">
            If the button does not work, copy and paste this link into your browser:<br />
            <a href="{esc(button_url)}" style="color:#087E79;word-break:break-all;">{esc(button_url)}</a>
          </td>
        </tr>
        """

    return f"""
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <meta name="x-apple-disable-message-reformatting" />
        <title>{safe_title}</title>
        <style>
          @media only screen and (max-width:620px) {{
            .email-shell {{ width:100% !important; }}
            .mobile-pad {{ padding-left:22px !important; padding-right:22px !important; }}
            .brand-name {{ font-size:30px !important; }}
            .brand-promise {{ font-size:17px !important; line-height:21px !important; }}
            .hero-image {{ height:175px !important; }}
            .benefit-label {{ font-size:10px !important; line-height:14px !important; }}
          }}
        </style>
      </head>
      <body style="margin:0;background:#F2FAFC;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;color:#102A43;">
        <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">{esc(preheader)}</div>
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#F2FAFC;padding:18px 0;">
          <tr>
            <td bgcolor="#ffffff" align="center" style="background:#ffffff;">
              <table role="presentation" width="760" cellspacing="0" cellpadding="0" class="email-shell" style="width:100%;max-width:760px;background:#ffffff;">
                <tr>
                  <td class="mobile-pad" style="padding:27px 38px 23px;color:#0B263D;">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                      <tr>
                        <td valign="middle">
                          <div class="brand-name" style="font-size:38px;line-height:40px;font-weight:900;letter-spacing:-1.8px;color:#07566A;">Tour<span style="color:#21A99E;">vaa</span></div>
                          <div style="margin-top:7px;font-size:9px;line-height:13px;font-weight:800;letter-spacing:3px;color:#17364A;">EXPLORE &middot; TRAVEL &middot; BELONG</div>
                        </td>
                        <td align="right" valign="middle" class="brand-promise" style="font-size:21px;line-height:25px;font-weight:600;font-style:italic;color:#07566A;">Your Journey<br />Our Passion</td>
                      </tr>
                    </table>
                  </td>
                </tr>
                <tr>
                  <td style="font-size:0;line-height:0;">
                    <img class="hero-image" src="{esc(hero_url)}" width="760" alt="Discover memorable journeys with Tourvaa" style="display:block;width:100%;max-width:760px;height:230px;object-fit:cover;border:0;" />
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td align="center">
              <table role="presentation" width="760" cellspacing="0" cellpadding="0" class="email-shell" style="width:100%;max-width:760px;background:#ffffff;">
                <tr>
                  <td class="mobile-pad" style="padding:38px 46px 34px;">
                    <h1 style="margin:0 0 20px;font-size:28px;line-height:36px;font-weight:800;letter-spacing:-0.4px;color:#0B263D;">{intro}</h1>
                    <p style="margin:0 0 17px;font-size:19px;line-height:27px;font-weight:700;color:#17364A;">{safe_title}</p>
                    <div style="font-size:15px;line-height:25px;color:#263D50;">{body}</div>
                    <table role="presentation" cellspacing="0" cellpadding="0">{button}</table>
                  </td>
                </tr>
                <tr>
                  <td class="mobile-pad" style="padding:0 38px 36px;">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-top:1px solid #CDE5E9;">
                      <tr>
                        <td width="25%" align="center" valign="top" style="padding:24px 5px 4px;color:#0B263D;">
                          <div style="font-size:26px;line-height:30px;font-weight:900;color:#159C96;">&#9650;</div>
                          <div class="benefit-label" style="margin-top:7px;font-size:12px;line-height:17px;font-weight:800;">Handpicked<br />Destinations</div>
                        </td>
                        <td width="25%" align="center" valign="top" style="padding:24px 5px 4px;border-left:1px solid #CDE5E9;color:#0B263D;">
                          <div style="font-size:24px;line-height:30px;font-weight:900;color:#159C96;">&#9679;&#9679;</div>
                          <div class="benefit-label" style="margin-top:7px;font-size:12px;line-height:17px;font-weight:800;">Personalized<br />Travel Plans</div>
                        </td>
                        <td width="25%" align="center" valign="top" style="padding:24px 5px 4px;border-left:1px solid #CDE5E9;color:#0B263D;">
                          <div style="font-size:27px;line-height:30px;font-weight:900;color:#07566A;">&#10003;</div>
                          <div class="benefit-label" style="margin-top:7px;font-size:12px;line-height:17px;font-weight:800;">Safe &amp; Reliable<br />Travel</div>
                        </td>
                        <td width="25%" align="center" valign="top" style="padding:24px 5px 4px;border-left:1px solid #CDE5E9;color:#0B263D;">
                          <div style="font-size:19px;line-height:30px;font-weight:900;color:#07566A;">24/7</div>
                          <div class="benefit-label" style="margin-top:7px;font-size:12px;line-height:17px;font-weight:800;">Dedicated<br />Support</div>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td bgcolor="#E7F6F5" align="center" style="background:#E7F6F5;border-top:1px solid #C9E8E6;">
              <table role="presentation" width="760" cellspacing="0" cellpadding="0" class="email-shell" style="width:100%;max-width:760px;">
                <tr>
                  <td style="padding:26px 28px 14px;">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                      <tr>
                        <td valign="top">
                          <div style="font-size:28px;line-height:31px;font-weight:900;letter-spacing:-1px;color:#07566A;">Tour<span style="color:#21A99E;">vaa</span></div>
                          <div style="margin-top:5px;font-size:8px;line-height:12px;font-weight:800;letter-spacing:2px;color:#17364A;">EXPLORE &middot; TRAVEL &middot; BELONG</div>
                        </td>
                        <td align="right" valign="top" style="font-size:12px;line-height:20px;color:#486581;">
                          <a href="mailto:{esc(support_email)}" style="color:#086A78;text-decoration:none;font-weight:700;">{esc(support_email)}</a><br />
                          <a href="{esc(frontend_url)}" style="color:#486581;text-decoration:none;">Visit Tourvaa online</a>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
                <tr>
                  <td style="padding:0 28px 24px;">
                    <p style="margin:0;font-size:11px;line-height:18px;color:#6B8292;">
                      This service message relates to your Tourvaa account, booking, or travel activity. If you did not expect it, you can safely ignore it.
                    </p>
                    <p style="margin:7px 0 0;font-size:11px;line-height:18px;color:#8297A5;">&copy; Tourvaa &middot; Explore &middot; Travel &middot; Belong</p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """


def apply_template_values(content: str, values: dict):
    required = set(re.findall(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}", content or ""))
    missing = sorted(required.difference(values))
    if missing:
        raise ValueError(f"Email template is missing required values: {', '.join(missing)}")
    output = content

    for key, value in values.items():
        output = output.replace("{{" + key + "}}", "" if value is None else esc(value))

    return output


def render_database_email(db, key: str, values: dict, fallback_subject: str, fallback_html: str):
    from app.models.email_templates import EmailTemplate

    template = (
        db.query(EmailTemplate)
        .filter(EmailTemplate.key == key)
        .filter(EmailTemplate.is_active == True)
        .first()
    )

    if not template:
        return fallback_subject, fallback_html

    subject = apply_template_values(template.subject, values)
    body = apply_template_values(template.body, values)

    if "<html" in body.lower() or "<table" in body.lower():
        return subject, body

    html = base_email(
        subject,
        f"Hi {esc(values.get('name', 'there'))},",
        body.replace("\n", "<br />"),
        values.get("button_text"),
        values.get("button_url"),
    )

    return subject, html


def pending_approval_email(name: str):
    return base_email(
        "Registration received",
        f"Hi {esc(name)},",
        "Your Tourvaa account has been created and is waiting for admin approval. We will email you when your account is approved.",
    )


def approved_email(name: str, login_url: str):
    return base_email(
        "Your account is approved",
        f"Hi {esc(name)},",
        "Your Tourvaa account has been approved. You can now sign in and access the modules assigned to your role.",
        "Login to Tourvaa",
        login_url,
    )


def user_created_email(name: str, email: str, set_password_url: str):
    return base_email(
        "Your Tourvaa account is ready",
        f"Hi {esc(name)},",
        (
            "An administrator created a Tourvaa account for you.<br /><br />"
            f"<strong>Email:</strong> {esc(email)}<br /><br />"
            "For security, no password was set for you - use the button below to create your own password before signing in. This link expires in 30 minutes."
        ),
        "Set your password",
        set_password_url,
    )


def password_reset_email(name: str, reset_url: str):
    return base_email(
        "Reset your password",
        f"Hi {esc(name)},",
        "We received a request to reset your Tourvaa password. This link expires in 30 minutes.",
        "Reset Password",
        reset_url,
    )


def password_changed_email(name: str, login_url: str):
    return base_email(
        "Password changed",
        f"Hi {esc(name)},",
        "Your Tourvaa password was changed successfully. You can now sign in with your new password.",
        "Login to Tourvaa",
        login_url,
    )


def email_verification_email(name: str, verification_url: str):
    return base_email(
        "Verify your email and create your password",
        f"Hi {esc(name)},",
        (
            "Thanks for registering with Tourvaa.<br /><br />"
            "Use the secure button below to verify your email and create your password. "
            "After password creation, your account will be active and ready to sign in.<br /><br />"
            "<strong>For your security:</strong> this single-use link expires in 24 hours."
        ),
        "Verify Email & Create Password",
        verification_url,
    )


def otp_login_email(name: str, code: str):
    return base_email(
        "Your Tourvaa verification code",
        f"Hi {esc(name)},",
        (
            "Use the code below to continue your booking. It expires in 10 minutes - "
            "if you didn't request this, you can safely ignore this email.<br /><br />"
            f"<div style=\"margin:18px 0;font-size:32px;font-weight:800;letter-spacing:8px;color:#123024;\">{esc(code)}</div>"
        ),
    )


def registration_password_created_email(name: str, login_url: str):
    return base_email(
        "Your Tourvaa password is ready",
        f"Hi {esc(name)},",
        "Your email has been verified and your password has been created. You can now sign in to your Tourvaa account.",
        "Login to Tourvaa",
        login_url,
    )


def status_badge(label: str, tone: str = "info") -> str:
    """A small colored pill used to draw the eye to a booking/order status."""
    palette = {
        "info": ("#EFF8FF", "#175CD3"),
        "success": ("#ECFDF3", "#027A48"),
        "warning": ("#FFFAEB", "#B54708"),
        "danger": ("#FEF3F2", "#B42318"),
    }
    background, text = palette.get(tone, palette["info"])
    return (
        f'<span style="display:inline-block;background:{background};color:{text};'
        f'font-size:12px;font-weight:700;letter-spacing:0.2px;padding:4px 12px;border-radius:999px;">{esc(label)}</span>'
    )


def _summary_card(rows: list[tuple[str, str]]) -> str:
    """Bordered label/value card used across booking and order emails so every
    transactional email shares the same at-a-glance summary layout."""
    body = "".join(
        f'<tr><td style="padding:6px 0;color:#667085;font-size:13px;">{label}</td>'
        f'<td style="padding:6px 0;font-weight:700;color:#101828;font-size:13px;text-align:right;">{value}</td></tr>'
        for label, value in rows
    )
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>'
        '<td style="background:#F8FAFC;border:1px solid #EAECF0;border-radius:12px;padding:16px 20px;">'
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0">{body}</table>'
        "</td></tr></table>"
    )


def _booking_rows(booking_code: str, tour_name: str, tour_date: str, adults: int | str, currency: str, total: str | float, extra: list[tuple[str, str]] | None = None) -> list[tuple[str, str]]:
    rows = [
        ("Booking ID", esc(booking_code)),
        ("Tour", esc(tour_name)),
        ("Date", esc(tour_date) or "-"),
    ]
    rows.extend(extra or [])
    rows.append(("Adults", esc(adults)))
    rows.append(("Total", f"{esc(currency)} {esc(total)}"))
    return rows


def booking_confirmation_email(name: str, booking_code: str, tour_name: str, tour_date: str, adults: int | str, currency: str, total: str | float, login_url: str, payment_summary: str = ""):
    summary = _summary_card(_booking_rows(booking_code, tour_name, tour_date, adults, currency, total))
    return base_email(
        "Booking received",
        f"Hi {esc(name)},",
        (
            f"Thank you for booking with Tourvaa! {status_badge('Pending confirmation', 'warning')}<br /><br />"
            f"{summary}<br />"
            + (f"<strong>Payment summary</strong><br />{esc(payment_summary).replace(chr(10), '<br />')}<br /><br />" if payment_summary else "")
            + "We will notify you as soon as your booking is confirmed."
        ),
        "View booking",
        login_url,
    )


def booking_confirmed_email(name: str, booking_code: str, tour_name: str, tour_date: str, adults: int | str, currency: str, total: str | float, login_url: str, cancellation_policy: str = "See your booking for the applicable policy.", payment_summary: str = ""):
    summary = _summary_card(_booking_rows(booking_code, tour_name, tour_date, adults, currency, total))
    return base_email(
        "Booking confirmed",
        f"Hi {esc(name)},",
        (
            f"Great news! Your Tourvaa booking is now confirmed. {status_badge('Confirmed', 'success')}<br /><br />"
            f"{summary}<br />"
            + (f"<strong>Payment summary</strong><br />{esc(payment_summary).replace(chr(10), '<br />')}<br /><br />" if payment_summary else "")
            + f"Cancellation &amp; refund policy: {esc(cancellation_policy)}<br /><br />"
            + "Get ready for your trip! You can view your full booking details using the button below."
        ),
        "View booking",
        login_url,
    )


def booking_cancelled_email(name: str, booking_code: str, tour_name: str, reason: str, login_url: str):
    return base_email(
        "Booking cancelled",
        f"Hi {esc(name)},",
        (
            f"Your booking <strong>{esc(booking_code)}</strong> for <strong>{esc(tour_name)}</strong> has been cancelled.<br /><br />"
            f"Reason: {esc(reason) or 'Cancelled'}<br /><br />"
            "If you have any questions, please contact our support team."
        ),
        "View bookings",
        login_url,
    )


def booking_declined_email(name: str, booking_code: str, tour_name: str, reason: str, login_url: str, similar_tours: list[dict] | None = None):
    similar_html = ""
    if similar_tours:
        rows = "".join(
            f'<li style="margin:6px 0;"><a href="{esc(t["url"])}" style="color:#2F9FE9;text-decoration:none;font-weight:600;">{esc(t["title"])}</a></li>'
            for t in similar_tours
        )
        similar_html = f'<br /><br /><strong>You might also like:</strong><ul style="margin:8px 0 0;padding-left:20px;">{rows}</ul>'
    return base_email(
        "Booking request could not be confirmed",
        f"Hi {esc(name)},",
        (
            f"Unfortunately, your booking request <strong>{esc(booking_code)}</strong> for <strong>{esc(tour_name)}</strong> could not be confirmed.<br /><br />"
            f"Reason: {esc(reason) or 'No further details were provided'}<br /><br />"
            "Any authorized payment has been released. Please browse other available tours or contact our support team."
            f"{similar_html}"
        ),
        "Browse tours",
        login_url,
    )


def booking_status_update_email(name: str, booking_code: str, tour_name: str, new_status: str, reason: str, login_url: str, payment_summary: str = ""):
    readable_status = esc(new_status.replace('_', ' ').title())
    return base_email(
        f"Booking update: {readable_status}",
        f"Hi {esc(name)},",
        (
            f"Your booking <strong>{esc(booking_code)}</strong> for <strong>{esc(tour_name)}</strong> status has been updated.<br /><br />"
            f"New status: <strong>{readable_status}</strong><br />"
            + (f"Reason: {esc(reason)}<br />" if reason else "")
            + (f"<br /><strong>Payment summary</strong><br />{esc(payment_summary).replace(chr(10), '<br />')}" if payment_summary else "")
        ),
        "View booking",
        login_url,
    )


def supplier_booking_assigned_email(supplier_name: str, booking_code: str, tour_name: str, tour_date: str, customer_name: str, adults: int | str, currency: str, total: str | float, portal_url: str):
    summary = _summary_card(_booking_rows(booking_code, tour_name, tour_date, adults, currency, total, extra=[("Customer", esc(customer_name))]))
    return base_email(
        "New booking assigned to you",
        f"Hi {esc(supplier_name)},",
        (
            f"A new booking has been assigned to you on Tourvaa and is awaiting your acceptance. {status_badge('Action required', 'warning')}<br /><br />"
            f"{summary}<br />"
            "Please log in to your supplier portal to accept or decline this booking."
        ),
        "View booking",
        portal_url,
    )


def booking_reminder_email(name: str, booking_code: str, tour_name: str, tour_date: str, login_url: str):
    return base_email(
        "Your tour is coming up",
        f"Hi {esc(name)},",
        (
            f"A reminder that your booking <strong>{esc(booking_code)}</strong> for "
            f"<strong>{esc(tour_name)}</strong> is scheduled for <strong>{esc(tour_date)}</strong>.<br /><br />"
            "Please review the booking details and contact Tourvaa if you need help."
        ),
        "View booking",
        login_url,
    )


def review_request_email(name: str, booking_code: str, tour_name: str, login_url: str):
    return base_email(
        "How was your tour?",
        f"Hi {esc(name)},",
        (
            f"Your tour <strong>{esc(tour_name)}</strong> is complete. We'd love to hear about your experience "
            f"with booking <strong>{esc(booking_code)}</strong>.<br /><br />"
            "Your feedback helps other travellers make informed choices."
        ),
        "Leave a review",
        login_url,
    )


def supplier_booking_confirmed_email(supplier_name: str, booking_code: str, tour_name: str, tour_date: str, customer_name: str, adults: int | str, currency: str, total: str | float, portal_url: str, cancellation_policy: str = "See the booking for the applicable policy."):
    summary = _summary_card(_booking_rows(booking_code, tour_name, tour_date, adults, currency, total, extra=[("Customer", esc(customer_name))]))
    return base_email(
        "Booking confirmed",
        f"Hi {esc(supplier_name)},",
        (
            f"The booking you accepted is now confirmed. {status_badge('Confirmed', 'success')}<br /><br />"
            f"{summary}<br />"
            f"Cancellation &amp; refund policy: {esc(cancellation_policy)}<br /><br />"
            "You can review the booking details and prepare for the tour in your supplier portal."
        ),
        "View booking",
        portal_url,
    )


def new_booking_admin_email(booking_code: str, tour_name: str, tour_date: str, customer_name: str, supplier_name: str, adults: int | str, currency: str, total: str | float, admin_url: str):
    summary = _summary_card(_booking_rows(
        booking_code, tour_name, tour_date, adults, currency, total,
        extra=[("Customer", esc(customer_name)), ("Supplier", esc(supplier_name) or "Unassigned")],
    ))
    return base_email(
        "New booking created",
        "Hi team,",
        (
            f"A customer just created a new booking on Tourvaa. {status_badge('New order', 'info')}<br /><br />"
            f"{summary}<br />"
            "Let the assigned supplier know if they haven't accepted it yet, or reassign the booking from the admin panel."
        ),
        "View booking",
        admin_url,
    )


def admin_booking_event_email(event_title: str, detail: str, booking_code: str, tour_name: str, admin_url: str, cancellation_policy: str = "See the booking for the applicable policy."):
    """Generic admin notifier shared by every booking-lifecycle event (supplier
    accept/decline/cancel/start/complete/postpone, cancellation requests) so we
    don't hand-write a near-identical template per event."""
    summary = _summary_card([("Booking ID", esc(booking_code)), ("Tour", esc(tour_name))])
    return base_email(
        event_title,
        "Hi team,",
        f"{esc(detail)}<br /><br />{summary}<br />Cancellation &amp; refund policy: {esc(cancellation_policy)}",
        "View booking",
        admin_url,
    )


def bank_detail_edit_requested_admin_email(partner_type: str, partner_name: str, admin_url: str):
    """Admin alert for a protected payout-detail edit request.

    Bank credentials are deliberately never included in notification emails.
    Admins must open the authenticated portal to review and unlock the edit.
    """
    role = (partner_type or "partner").title()
    summary = _summary_card([("Account type", esc(role)), ("Account", esc(partner_name) or "Unknown")])
    return base_email(
        "Bank-detail edit requested",
        "Hi team,",
        (
            f"A {esc(role).lower()} has requested a one-time edit to their payout bank details. "
            "No bank credentials are included in this email.<br /><br />"
            f"{summary}<br />Review the request in the authenticated admin portal before unlocking the account."
        ),
        "Review request",
        admin_url,
    )


def booking_cancelled_supplier_email(supplier_name: str, booking_code: str, tour_name: str, reason: str, portal_url: str):
    return base_email(
        "Booking cancelled",
        f"Hi {esc(supplier_name)},",
        (
            f"Booking <strong>{esc(booking_code)}</strong> for <strong>{esc(tour_name)}</strong> has been cancelled and is no longer on your schedule.<br /><br />"
            f"Reason: {esc(reason) or 'Cancelled'}<br /><br />"
            "No further action is needed from you for this booking."
        ),
        "View supplier portal",
        portal_url,
    )


def refund_processed_email(name: str, booking_code: str, tour_name: str, currency: str, amount: str | float, login_url: str):
    return base_email(
        "Refund processed",
        f"Hi {esc(name)},",
        (
            f"We have processed a refund for booking <strong>{esc(booking_code)}</strong>.<br /><br />"
            f"Tour: <strong>{esc(tour_name)}</strong><br />"
            f"Refund amount: <strong>{esc(currency)} {esc(amount)}</strong><br /><br />"
            "The refund should reflect in your original payment method within a few business days."
        ),
        "View booking",
        login_url,
    )


def cancellation_requested_email(name: str, booking_code: str, tour_name: str, refund_amount: str | float, currency: str, login_url: str):
    return base_email(
        "Cancellation request received",
        f"Hi {esc(name)},",
        (
            f"We received your cancellation request for booking <strong>{esc(booking_code)}</strong> ({esc(tour_name)}). "
            f"{status_badge('Under review', 'warning')}<br /><br />"
            f"Estimated refund: <strong>{esc(currency)} {esc(refund_amount)}</strong><br /><br />"
            "Our team will review this shortly and notify you once it's approved."
        ),
        "View booking",
        login_url,
    )


def cancellation_approved_email(name: str, booking_code: str, tour_name: str, refund_amount: str | float, currency: str, login_url: str):
    return base_email(
        "Cancellation approved",
        f"Hi {esc(name)},",
        (
            f"Your cancellation request for booking <strong>{esc(booking_code)}</strong> ({esc(tour_name)}) has been approved. "
            f"{status_badge('Approved', 'success')}<br /><br />"
            f"Refund amount: <strong>{esc(currency)} {esc(refund_amount)}</strong><br /><br />"
            "We'll email you again once the refund has been processed."
        ),
        "View booking",
        login_url,
    )


def cancellation_rejected_email(name: str, booking_code: str, tour_name: str, reason: str, login_url: str):
    return base_email(
        "Cancellation request rejected",
        f"Hi {esc(name)},",
        (
            f"Your cancellation request for booking <strong>{esc(booking_code)}</strong> ({esc(tour_name)}) was not approved. "
            f"{status_badge('Rejected', 'danger')}<br /><br />"
            f"Reason: {esc(reason) or 'Not specified'}<br /><br />"
            "Your booking remains active. Contact our support team if you have questions."
        ),
        "View booking",
        login_url,
    )


def payment_received_email(name: str, booking_code: str, tour_name: str, currency: str, amount: str | float, login_url: str, payment_summary: str = ""):
    return base_email(
        "Payment received",
        f"Hi {esc(name)},",
        (
            f"We have received your payment for booking <strong>{esc(booking_code)}</strong>.<br /><br />"
            f"Tour: <strong>{esc(tour_name)}</strong><br />"
            f"Amount paid: <strong>{esc(currency)} {esc(amount)}</strong><br /><br />"
            + (f"<strong>{esc(payment_summary)}</strong><br /><br />" if payment_summary else "")
            + "Your payment has been captured. You can view your invoice in the customer portal."
        ),
        "View booking",
        login_url,
    )


# supplier lifecycle
def supplier_rejected_email(supplier_name: str, reason: str):
    return base_email(
        "Supplier profile rejected",
        f"Hi {esc(supplier_name)},",
        (
            "Your Tourvaa supplier profile was not approved.<br /><br />"
            f"Reason: {esc(reason) or 'Not specified'}<br /><br />"
            "Please review the feedback and contact our support team if you have questions."
        ),
    )


def supplier_changes_requested_email(supplier_name: str, requirements: str, login_url: str):
    return base_email(
        "Updates required on your supplier profile",
        f"Hi {esc(supplier_name)},",
        (
            "Our team reviewed your supplier profile and requires a few updates before it can be approved.<br /><br />"
            f"<strong>Required changes:</strong> {esc(requirements) or 'See supplier portal for details'}<br /><br />"
            "Please make the requested updates in your supplier portal and resubmit for review."
        ),
        "Update profile",
        login_url,
    )


def supplier_submitted_verification_email(supplier_name: str):
    return base_email(
        "Supplier submitted for review",
        "Hi team,",
        f"Supplier <strong>{esc(supplier_name)}</strong> has submitted their profile for admin review. Please review it in the admin supplier detail page.",
    )


def supplier_registered_email(supplier_name: str):
    return base_email(
        "New supplier registration",
        "Hi team,",
        f"Supplier <strong>{esc(supplier_name)}</strong> has registered and is awaiting email verification and profile submission.",
    )


# agent lifecycle
def agent_submitted_verification_email(agent_name: str):
    return base_email(
        "Agent submitted for review",
        "Hi team,",
        f"Agent <strong>{esc(agent_name)}</strong> has submitted their profile for admin review. Please review it in the admin agent detail page.",
    )


def agent_changes_requested_email(agent_name: str, requirements: str, login_url: str):
    return base_email(
        "Updates required on your agent profile",
        f"Hi {esc(agent_name)},",
        (
            "Our team reviewed your agent profile and requires a few updates before it can be approved.<br /><br />"
            f"<strong>Required changes:</strong> {esc(requirements) or 'See agent portal for details'}<br /><br />"
            "Please make the requested updates in your agent portal and resubmit for review."
        ),
        "Update profile",
        login_url,
    )


def agent_approved_email(agent_name: str, login_url: str):
    return base_email(
        "Your agent profile is approved",
        f"Hi {esc(agent_name)},",
        "Congratulations! Your Tourvaa agent profile has been approved. You can now manage bookings from the agent portal.",
        "Go to agent portal",
        login_url,
    )


def agent_rejected_email(agent_name: str, reason: str):
    return base_email(
        "Your agent profile was rejected",
        f"Hi {esc(agent_name)},",
        (
            "Your Tourvaa agent profile was not approved.<br /><br />"
            f"Reason: {esc(reason) or 'Not specified'}<br /><br />"
            "Please review the feedback and contact our support team if you have questions."
        ),
    )
