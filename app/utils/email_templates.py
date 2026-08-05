import html as _html


def esc(value) -> str:
    """Escape a value for safe interpolation into HTML email bodies."""
    return _html.escape(str(value)) if value is not None else ""


def base_email(title: str, intro: str, body: str, button_text: str | None = None, button_url: str | None = None):
    button = ""

    if button_text and button_url:
        button = f"""
        <tr>
          <td style="padding:28px 0 8px;">
            <a href="{button_url}" style="display:inline-block;background:linear-gradient(135deg,#43A9F6,#2F9FE9);color:#ffffff;text-decoration:none;font-weight:700;font-size:14px;padding:14px 28px;border-radius:12px;box-shadow:0 4px 14px rgba(67,169,246,0.35);">
              {button_text}
            </a>
          </td>
        </tr>
        <tr>
          <td style="padding:10px 0 0;color:#8B93A1;font-size:12px;line-height:19px;">
            If the button does not work, copy and paste this link into your browser:<br />
            <a href="{button_url}" style="color:#2F9FE9;word-break:break-all;">{button_url}</a>
          </td>
        </tr>
        """

    return f"""
    <!doctype html>
    <html>
      <body style="margin:0;background:#F0F4F9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;color:#121826;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#F0F4F9;padding:40px 16px;">
          <tr>
            <td align="center">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;background:#ffffff;border-radius:20px;overflow:hidden;box-shadow:0 2px 16px rgba(16,24,40,0.08);">
                <tr>
                  <td style="background:linear-gradient(135deg,#101828,#1D2939);padding:36px 36px 32px;color:#ffffff;">
                    <table role="presentation" cellspacing="0" cellpadding="0">
                      <tr>
                        <td style="width:36px;height:36px;background:linear-gradient(135deg,#43A9F6,#2F9FE9);border-radius:10px;text-align:center;vertical-align:middle;font-size:16px;font-weight:800;color:#ffffff;">T</td>
                        <td style="padding-left:10px;font-size:15px;font-weight:700;letter-spacing:0.2px;color:#ffffff;">Tourvaa</td>
                      </tr>
                    </table>
                    <h1 style="margin:22px 0 0;font-size:24px;line-height:32px;font-weight:700;">{title}</h1>
                  </td>
                </tr>
                <tr>
                  <td style="padding:36px;">
                    <p style="margin:0 0 16px;font-size:16px;line-height:26px;color:#344054;">{intro}</p>
                    <div style="font-size:14px;line-height:24px;color:#475467;">{body}</div>
                    <table role="presentation" cellspacing="0" cellpadding="0">{button}</table>
                  </td>
                </tr>
                <tr>
                  <td style="padding:20px 36px 28px;border-top:1px solid #EEF2F6;">
                    <p style="margin:0;font-size:12px;line-height:20px;color:#98A2B3;">
                      This message was sent by <strong style="color:#667085;">Tourvaa</strong>. If you did not expect this email, you can safely ignore it.
                    </p>
                    <p style="margin:8px 0 0;font-size:12px;line-height:20px;color:#C0C6D1;">
                      &copy; Tourvaa. All rights reserved.
                    </p>
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
    output = content

    for key, value in values.items():
        output = output.replace("{{" + key + "}}", esc(value) if value else "")

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


def booking_confirmation_email(name: str, booking_code: str, tour_name: str, tour_date: str, adults: int | str, currency: str, total: str | float, login_url: str):
    summary = _summary_card(_booking_rows(booking_code, tour_name, tour_date, adults, currency, total))
    return base_email(
        "Booking received",
        f"Hi {esc(name)},",
        (
            f"Thank you for booking with Tourvaa! {status_badge('Pending confirmation', 'warning')}<br /><br />"
            f"{summary}<br />"
            "We will notify you as soon as your booking is confirmed by the supplier."
        ),
        "View booking",
        login_url,
    )


def booking_confirmed_email(name: str, booking_code: str, tour_name: str, tour_date: str, adults: int | str, currency: str, total: str | float, login_url: str):
    summary = _summary_card(_booking_rows(booking_code, tour_name, tour_date, adults, currency, total))
    return base_email(
        "Booking confirmed",
        f"Hi {esc(name)},",
        (
            f"Great news! Your Tourvaa booking has been confirmed by the supplier. {status_badge('Confirmed', 'success')}<br /><br />"
            f"{summary}<br />"
            "Get ready for your trip! You can view your full booking details using the button below."
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
        "Booking declined by supplier",
        f"Hi {esc(name)},",
        (
            f"Unfortunately your booking <strong>{esc(booking_code)}</strong> for <strong>{esc(tour_name)}</strong> was declined by the supplier.<br /><br />"
            f"Reason: {esc(reason) or 'Declined by supplier'}<br /><br />"
            "Any authorized payment has been released. Please browse other available tours or contact our support team."
            f"{similar_html}"
        ),
        "Browse tours",
        login_url,
    )


def booking_status_update_email(name: str, booking_code: str, tour_name: str, new_status: str, reason: str, login_url: str):
    readable_status = esc(new_status.replace('_', ' ').title())
    return base_email(
        f"Booking update: {readable_status}",
        f"Hi {esc(name)},",
        (
            f"Your booking <strong>{esc(booking_code)}</strong> for <strong>{esc(tour_name)}</strong> status has been updated.<br /><br />"
            f"New status: <strong>{readable_status}</strong><br />"
            + (f"Reason: {esc(reason)}<br />" if reason else "")
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


def admin_booking_event_email(event_title: str, detail: str, booking_code: str, tour_name: str, admin_url: str):
    """Generic admin notifier shared by every booking-lifecycle event (supplier
    accept/decline/cancel/start/complete/postpone, cancellation requests) so we
    don't hand-write a near-identical template per event."""
    summary = _summary_card([("Booking ID", esc(booking_code)), ("Tour", esc(tour_name))])
    return base_email(
        event_title,
        "Hi team,",
        f"{esc(detail)}<br /><br />{summary}",
        "View booking",
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


def payment_received_email(name: str, booking_code: str, tour_name: str, currency: str, amount: str | float, login_url: str):
    return base_email(
        "Payment received",
        f"Hi {esc(name)},",
        (
            f"We have received your payment for booking <strong>{esc(booking_code)}</strong>.<br /><br />"
            f"Tour: <strong>{esc(tour_name)}</strong><br />"
            f"Amount paid: <strong>{esc(currency)} {esc(amount)}</strong><br /><br />"
            "Your payment has been captured. You can view your invoice in the customer portal."
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


def supplier_commission_requested_email(supplier_name: str, markup_type: str, markup_value):
    return base_email(
        "Supplier commission request pending approval",
        "Hi team,",
        (
            f"Supplier <strong>{esc(supplier_name)}</strong> requested a commission/markup change.<br /><br />"
            f"Type: <strong>{esc(markup_type)}</strong><br />"
            f"Value: <strong>{esc(markup_value)}</strong><br /><br />"
            "Please review this request in the admin supplier detail page."
        ),
    )


def supplier_commission_approved_email(supplier_name: str, markup_type: str, markup_value, login_url: str):
    return base_email(
        "Your commission request is approved",
        f"Hi {esc(supplier_name)},",
        (
            "Your commission request has been approved.<br /><br />"
            f"Type: <strong>{esc(markup_type)}</strong><br />"
            f"Value: <strong>{esc(markup_value)}</strong><br /><br />"
            "You can continue using your supplier portal."
        ),
        "View supplier portal",
        login_url,
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
