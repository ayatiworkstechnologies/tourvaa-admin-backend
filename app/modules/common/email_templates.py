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
