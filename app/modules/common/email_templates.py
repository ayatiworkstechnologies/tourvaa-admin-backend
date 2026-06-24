def base_email(title: str, intro: str, body: str, button_text: str | None = None, button_url: str | None = None):
    button = ""

    if button_text and button_url:
        button = f"""
        <tr>
          <td style="padding:24px 0 8px;">
            <a href="{button_url}" style="display:inline-block;background:#43A9F6;color:#ffffff;text-decoration:none;font-weight:700;padding:13px 20px;border-radius:10px;">
              {button_text}
            </a>
          </td>
        </tr>
        <tr>
          <td style="padding:8px 0 0;color:#667085;font-size:13px;line-height:20px;">
            If the button does not work, open this link:<br />
            <a href="{button_url}" style="color:#238DD7;word-break:break-all;">{button_url}</a>
          </td>
        </tr>
        """

    return f"""
    <!doctype html>
    <html>
      <body style="margin:0;background:#F7F9FC;font-family:Arial,Helvetica,sans-serif;color:#121826;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#F7F9FC;padding:32px 16px;">
          <tr>
            <td align="center">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:620px;background:#ffffff;border:1px solid #E7EAF0;border-radius:18px;overflow:hidden;">
                <tr>
                  <td style="background:#101828;padding:28px 32px;color:#ffffff;">
                    <div style="font-size:14px;font-weight:700;color:#7DD3FC;">Tourvaa</div>
                    <h1 style="margin:10px 0 0;font-size:26px;line-height:34px;">{title}</h1>
                  </td>
                </tr>
                <tr>
                  <td style="padding:32px;">
                    <p style="margin:0 0 16px;font-size:16px;line-height:26px;color:#344054;">{intro}</p>
                    <div style="font-size:14px;line-height:24px;color:#667085;">{body}</div>
                    <table role="presentation" cellspacing="0" cellpadding="0">{button}</table>
                    <p style="margin:28px 0 0;font-size:12px;line-height:20px;color:#98A2B3;">
                      This message was sent by Tourvaa. If you did not request this email, you can ignore it.
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
        output = output.replace("{{" + key + "}}", str(value or ""))

    return output


def render_database_email(db, key: str, values: dict, fallback_subject: str, fallback_html: str):
    from app.modules.email_templates.models import EmailTemplate

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
        f"Hi {values.get('name', 'there')},",
        body.replace("\n", "<br />"),
        values.get("button_text"),
        values.get("button_url"),
    )

    return subject, html


def pending_approval_email(name: str):
    return base_email(
        "Registration received",
        f"Hi {name},",
        "Your Tourvaa account has been created and is waiting for admin approval. We will email you when your account is approved.",
    )


def approved_email(name: str, login_url: str):
    return base_email(
        "Your account is approved",
        f"Hi {name},",
        "Your Tourvaa account has been approved. You can now sign in and access the modules assigned to your role.",
        "Login to Tourvaa",
        login_url,
    )


def user_created_email(name: str, email: str, password: str, login_url: str):
    return base_email(
        "Your Tourvaa account is ready",
        f"Hi {name},",
        (
            "An administrator created your Tourvaa account.<br /><br />"
            f"<strong>Email:</strong> {email}<br />"
            f"<strong>Temporary password:</strong> {password}<br /><br />"
            "Please sign in and change your password after your first login."
        ),
        "Login to Tourvaa",
        login_url,
    )


def password_reset_email(name: str, reset_url: str):
    return base_email(
        "Reset your password",
        f"Hi {name},",
        "We received a request to reset your Tourvaa password. This link expires in 30 minutes.",
        "Reset Password",
        reset_url,
    )


def password_changed_email(name: str, login_url: str):
    return base_email(
        "Password changed",
        f"Hi {name},",
        "Your Tourvaa password was changed successfully. You can now sign in with your new password.",
        "Login to Tourvaa",
        login_url,
    )


def email_verification_email(name: str, verification_url: str):
    return base_email(
        "Verify your email",
        f"Hi {name},",
        "Please verify your email address to complete your Tourvaa account setup. This link expires in 24 hours.",
        "Verify Email",
        verification_url,
    )


def _booking_summary_rows(booking_code: str, tour_name: str, tour_date: str, adults: int | str, currency: str, total: str | float) -> str:
    rows = [
        ("Booking ID", booking_code),
        ("Tour", tour_name),
        ("Date", tour_date or "—"),
        ("Adults", str(adults)),
        ("Total", f"{currency} {total}"),
    ]
    return "".join(
        f'<tr><td style="padding:4px 12px 4px 0;color:#667085;">{label}</td>'
        f'<td style="padding:4px 0;font-weight:700;color:#101828;">{value}</td></tr>'
        for label, value in rows
    )


def booking_confirmation_email(name: str, booking_code: str, tour_name: str, tour_date: str, adults: int | str, currency: str, total: str | float, login_url: str):
    summary = _booking_summary_rows(booking_code, tour_name, tour_date, adults, currency, total)
    return base_email(
        "Booking received",
        f"Hi {name},",
        (
            "Thank you for booking with Tourvaa! Your booking is received and pending confirmation.<br /><br />"
            f'<table role="presentation" cellspacing="0" cellpadding="0" style="width:100%;">{summary}</table><br />'
            "We will notify you as soon as your booking is confirmed by the supplier."
        ),
        "View booking",
        login_url,
    )


def booking_confirmed_email(name: str, booking_code: str, tour_name: str, tour_date: str, adults: int | str, currency: str, total: str | float, login_url: str):
    summary = _booking_summary_rows(booking_code, tour_name, tour_date, adults, currency, total)
    return base_email(
        "Booking confirmed",
        f"Hi {name},",
        (
            "Great news! Your Tourvaa booking has been confirmed by the supplier.<br /><br />"
            f'<table role="presentation" cellspacing="0" cellpadding="0" style="width:100%;">{summary}</table><br />'
            "Get ready for your trip! You can view your full booking details using the button below."
        ),
        "View booking",
        login_url,
    )


def booking_cancelled_email(name: str, booking_code: str, tour_name: str, reason: str, login_url: str):
    return base_email(
        "Booking cancelled",
        f"Hi {name},",
        (
            f"Your booking <strong>{booking_code}</strong> for <strong>{tour_name}</strong> has been cancelled.<br /><br />"
            f"Reason: {reason or 'Cancelled'}<br /><br />"
            "If you have any questions, please contact our support team."
        ),
        "View bookings",
        login_url,
    )


def booking_declined_email(name: str, booking_code: str, tour_name: str, reason: str, login_url: str):
    return base_email(
        "Booking declined by supplier",
        f"Hi {name},",
        (
            f"Unfortunately your booking <strong>{booking_code}</strong> for <strong>{tour_name}</strong> was declined by the supplier.<br /><br />"
            f"Reason: {reason or 'Declined by supplier'}<br /><br />"
            "Any authorized payment has been released. Please browse other available tours or contact our support team."
        ),
        "Browse tours",
        login_url,
    )


def booking_status_update_email(name: str, booking_code: str, tour_name: str, new_status: str, reason: str, login_url: str):
    return base_email(
        f"Booking update: {new_status.replace('_', ' ').title()}",
        f"Hi {name},",
        (
            f"Your booking <strong>{booking_code}</strong> for <strong>{tour_name}</strong> status has been updated.<br /><br />"
            f"New status: <strong>{new_status.replace('_', ' ').title()}</strong><br />"
            + (f"Reason: {reason}<br />" if reason else "")
        ),
        "View booking",
        login_url,
    )


def supplier_booking_assigned_email(supplier_name: str, booking_code: str, tour_name: str, tour_date: str, customer_name: str, adults: int | str, currency: str, total: str | float, portal_url: str):
    return base_email(
        "New booking assigned to you",
        f"Hi {supplier_name},",
        (
            f"A new booking has been assigned to you on Tourvaa and is awaiting your acceptance.<br /><br />"
            f'<table role="presentation" cellspacing="0" cellpadding="0" style="width:100%;">'
            + "".join(
                f'<tr><td style="padding:4px 12px 4px 0;color:#667085;">{label}</td>'
                f'<td style="padding:4px 0;font-weight:700;color:#101828;">{value}</td></tr>'
                for label, value in [
                    ("Booking ID", booking_code),
                    ("Tour", tour_name),
                    ("Date", tour_date or "—"),
                    ("Customer", customer_name),
                    ("Adults", str(adults)),
                    ("Total", f"{currency} {total}"),
                ]
            )
            + "</table><br />"
            "Please log in to your supplier portal to accept or decline this booking."
        ),
        "View booking",
        portal_url,
    )


def payment_received_email(name: str, booking_code: str, tour_name: str, currency: str, amount: str | float, login_url: str):
    return base_email(
        "Payment received",
        f"Hi {name},",
        (
            f"We have received your payment for booking <strong>{booking_code}</strong>.<br /><br />"
            f"Tour: <strong>{tour_name}</strong><br />"
            f"Amount paid: <strong>{currency} {amount}</strong><br /><br />"
            "Your payment has been captured. You can view your invoice in the customer portal."
        ),
        "View booking",
        login_url,
    )
