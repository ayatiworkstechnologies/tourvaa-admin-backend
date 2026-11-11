"""Safely diagnose the active SMTP transport.

By default this checks only connectivity. Pass --send-to an address to send a
real test email using the configured backend transport.
"""

import argparse
import socket

from app.utils.mailer import _effective_smtp_config, send_email


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send-to", help="Send a real test email to this address.")
    args = parser.parse_args()
    config = _effective_smtp_config()
    print(f"Target: {config.host}:{config.port}; SSL={config.use_ssl}; STARTTLS={config.use_starttls}")
    try:
        with socket.create_connection((config.host, config.port), timeout=config.timeout_seconds):
            print("TCP connectivity: OK")
    except OSError as error:
        print(f"TCP connectivity: FAILED ({error})")
        return 1

    if args.send_to:
        send_email(
            args.send_to,
            "Tourvaa SMTP delivery test",
            "<p>This is a Tourvaa SMTP delivery test.</p>",
            template_key="smtp_test",
            entity_type="system",
        )
        print(f"SMTP accepted the test email for {args.send_to}.")
    else:
        print("No email sent. Use --send-to you@example.com to send a test.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
