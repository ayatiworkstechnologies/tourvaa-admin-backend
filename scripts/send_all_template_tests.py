"""Send a sample rendering of every active email template to one address."""

import argparse

from app.database import SessionLocal
from app.services.email_templates import get_templates, preview_template
from app.utils.mailer import try_send_email


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("recipient")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        templates = [template for template in get_templates(db) if template.is_active]
        results: list[tuple[str, bool]] = []

        for template in templates:
            preview = preview_template(db, template.id)
            sent = try_send_email(
                args.recipient,
                preview["subject"],
                preview["html"],
                template_key=f"test:{template.key}",
            )
            results.append((template.key, sent))
            print(f"{'SENT' if sent else 'FAILED'} {template.key}", flush=True)

        failed = [key for key, sent in results if not sent]
        print(f"TOTAL={len(results)} SENT={len(results) - len(failed)} FAILED={len(failed)}")
        if failed:
            print(f"FAILED_KEYS={','.join(failed)}")
        return 1 if failed else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
