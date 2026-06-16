"""Run module-based backend API checks.

The actual module checks live in backend/scripts/module_tests/*.py.
This file is only the CLI runner.
"""

from __future__ import annotations

import argparse
import os
import sys

from module_tests import MODULES
from module_tests.common import CheckError, Runner


BASE_URL = os.getenv("TOURVAA_API_URL", "http://127.0.0.1:8000/api").rstrip("/")
ADMIN_EMAIL = os.getenv("TOURVAA_TEST_EMAIL", "admin@tourvaa.com")
ADMIN_PASSWORD = os.getenv("TOURVAA_TEST_PASSWORD", "Admin@123")


def login(base_url: str) -> str:
    runner = Runner(base_url, None, write=False)
    payload = runner.request(
        "POST",
        "/auth/login",
        {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "client_type": "web"},
    )
    token = payload.get("data", {}).get("access_token")
    if not token:
        raise CheckError("Login succeeded but no access_token was returned")
    return token


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run module-based Tourvaa backend API checks.")
    parser.add_argument(
        "modules",
        nargs="*",
        help=f"Modules to run. Available: {', '.join(MODULES)}. Default: all.",
    )
    parser.add_argument("--base-url", default=BASE_URL, help="API base URL, default from TOURVAA_API_URL or localhost.")
    parser.add_argument("--write", action="store_true", help="Run create/update/action checks. Default only runs GET checks.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected = args.modules or list(MODULES)
    unknown = [module for module in selected if module not in MODULES]
    if unknown:
        print(f"Unknown module(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    try:
        token = login(args.base_url.rstrip("/"))
    except Exception as exc:
        print(f"Login failed: {exc}", file=sys.stderr)
        return 1

    runner = Runner(args.base_url.rstrip("/"), token, args.write)
    for module in selected:
        runner.run_steps(module, MODULES[module])

    if runner.failures:
        print("\nFailures:")
        for failure in runner.failures:
            print(f"- {failure}")
        return 1

    print("\nAll selected module checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
