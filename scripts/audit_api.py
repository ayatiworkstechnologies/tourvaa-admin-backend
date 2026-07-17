"""Audit the complete FastAPI contract without authenticating or mutating real rows."""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.api import router as api_router
from app.config import settings
from app.main import app


HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
MISSING_ID = "999999999"
MISSING_TEXT = "__api_audit_missing__"


def _declared_operations():
    groups = [
        ("/api", router)
        for router in (
            *api_router.CORE_ROUTERS,
            *api_router.PARTNER_AND_CUSTOMER_ROUTERS,
            *api_router.CONTENT_AND_TOUR_ROUTERS,
            *api_router.OPERATIONS_ROUTERS,
        )
    ]
    groups.extend(("/api/admin", router) for router in api_router.ADMIN_ALIAS_ROUTERS)
    groups.append(("/api/public", api_router.public_router))

    declared = defaultdict(list)
    for base, router in groups:
        for route in router.routes:
            for method in route.methods:
                path = f"{base}{router.prefix}{route.path}"
                declared[(method.lower(), path)].append(route.name)
    return declared


def _sample_request(path: str, operation: dict) -> tuple[str, dict]:
    params = operation.get("parameters", [])
    path_params = {
        item["name"]: item.get("schema", {})
        for item in params
        if item.get("in") == "path"
    }

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        schema = path_params.get(name, {})
        return MISSING_ID if schema.get("type") == "integer" else MISSING_TEXT

    url = re.sub(r"\{([^}]+)\}", replace, path)
    query = {}
    for item in params:
        if item.get("in") != "query" or not item.get("required"):
            continue
        schema = item.get("schema", {})
        query[item["name"]] = 1 if schema.get("type") in {"integer", "number"} else MISSING_TEXT

    kwargs: dict = {"params": query, "follow_redirects": False}
    content = operation.get("requestBody", {}).get("content", {})
    if "application/json" in content:
        kwargs["json"] = {}
    return url, kwargs


def _shadowed_static_routes(paths: dict) -> list[tuple[str, str, str]]:
    ordered = list(paths.items())
    problems = []
    for later_index, (static_path, static_item) in enumerate(ordered):
        static_parts = static_path.strip("/").split("/")
        if any(part.startswith("{") for part in static_parts):
            continue
        for dynamic_path, dynamic_item in ordered[:later_index]:
            dynamic_parts = dynamic_path.strip("/").split("/")
            if not any(part.startswith("{") for part in dynamic_parts):
                continue
            if len(dynamic_parts) != len(static_parts):
                continue
            matches = all(
                dynamic.startswith("{") or dynamic == static
                for dynamic, static in zip(dynamic_parts, static_parts)
            )
            if not matches:
                continue
            for method in HTTP_METHODS & dynamic_item.keys() & static_item.keys():
                problems.append((method.upper(), dynamic_path, static_path))
    return problems


def main(authenticated_reads: bool = False) -> int:
    schema = app.openapi()
    paths = schema["paths"]
    operations = [
        (method, path, operation)
        for path, item in paths.items()
        for method, operation in item.items()
        if method in HTTP_METHODS
    ]

    duplicates = {
        key: names
        for key, names in _declared_operations().items()
        if len(names) > 1
    }
    shadowed = _shadowed_static_routes(paths)

    failures = []
    client = TestClient(app, raise_server_exceptions=False)
    for method, path, operation in operations:
        url, kwargs = _sample_request(path, operation)
        response = client.request(method.upper(), url, **kwargs)
        if response.status_code >= 500:
            failures.append((method.upper(), path, response.status_code, response.text[:200]))

    authenticated_failures = []
    if authenticated_reads:
        login = client.post(
            "/api/auth/login",
            json={
                "email": settings.SUPER_ADMIN_EMAIL,
                "password": settings.SUPER_ADMIN_PASSWORD,
            },
        )
        if login.status_code != 200:
            authenticated_failures.append(
                ("POST", "/api/auth/login", login.status_code, login.text[:200])
            )
        else:
            body = login.json()
            token = body.get("data", {}).get("access_token") or body.get("access_token")
            headers = {"Authorization": f"Bearer {token}"}
            for method, path, operation in operations:
                if method != "get":
                    continue
                url, kwargs = _sample_request(path, operation)
                response = client.get(url, headers=headers, **kwargs)
                if response.status_code >= 500:
                    authenticated_failures.append(
                        ("GET", path, response.status_code, response.text[:200])
                    )

    print(f"OpenAPI paths: {len(paths)}")
    print(f"API operations: {len(operations)}")
    print(f"Duplicate declarations: {len(duplicates)}")
    print(f"Shadowed static routes: {len(shadowed)}")
    print(f"Unauthenticated 5xx responses: {len(failures)}")
    if authenticated_reads:
        print(f"Authenticated GET 5xx responses: {len(authenticated_failures)}")

    for key, names in duplicates.items():
        print(f"DUPLICATE {key}: {names}")
    for method, dynamic, static in shadowed:
        print(f"SHADOW {method} {dynamic} precedes {static}")
    for method, path, status, body in failures:
        print(f"FAIL {method} {path}: {status} {body}")
    for method, path, status, body in authenticated_failures:
        print(f"AUTH FAIL {method} {path}: {status} {body}")

    return 1 if duplicates or shadowed or failures or authenticated_failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--authenticated-reads",
        action="store_true",
        help="Also smoke-test every GET route with the configured super-admin account.",
    )
    args = parser.parse_args()
    raise SystemExit(main(authenticated_reads=args.authenticated_reads))
