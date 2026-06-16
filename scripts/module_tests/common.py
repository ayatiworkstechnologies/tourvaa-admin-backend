from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


class CheckError(RuntimeError):
    pass


@dataclass(frozen=True)
class Step:
    name: str
    method: str
    path: str
    expected: tuple[int, ...] = (200,)
    body: dict[str, Any] | Callable[["Runner"], dict[str, Any]] | None = None
    save_id_as: str | None = None
    needs_id: str | None = None


def unique(prefix: str) -> str:
    return f"{prefix} {int(time.time() * 1000)}"


def extract_id(payload: dict[str, Any]) -> int | None:
    data = payload.get("data")
    if isinstance(data, dict):
        value = data.get("id")
        if isinstance(value, int):
            return value
    rows = payload.get("data")
    if isinstance(rows, list) and rows:
        value = rows[0].get("id") if isinstance(rows[0], dict) else None
        if isinstance(value, int):
            return value
    return None


class Runner:
    def __init__(self, base_url: str, token: str | None, write: bool):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.write = write
        self.ids: dict[str, int] = {}
        self.failures: list[str] = []

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                status = response.status
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as exc:
            raise CheckError(f"Cannot reach {url}: {exc.reason}") from exc

        if status not in expected:
            raise CheckError(f"{method} {path} expected {expected}, got {status}: {raw[:500]}")

        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CheckError(f"{method} {path} returned non-JSON response: {raw[:500]}") from exc

    def run_steps(self, module: str, steps: list[Step]) -> None:
        print(f"\n== {module} ==")
        for step in steps:
            if step.needs_id and step.needs_id not in self.ids:
                print(f"SKIP {step.name} (missing {step.needs_id})")
                continue

            path = step.path
            if step.needs_id:
                path = path.format(id=self.ids[step.needs_id])

            if step.method != "GET" and not self.write:
                print(f"SKIP {step.name} (use --write)")
                continue

            body = step.body(self) if callable(step.body) else step.body
            try:
                payload = self.request(step.method, path, body, step.expected)
                saved_id = extract_id(payload)
                if step.save_id_as and saved_id:
                    self.ids[step.save_id_as] = saved_id
                print(f"PASS {step.name}")
            except Exception as exc:
                message = f"FAIL {step.name}: {exc}"
                self.failures.append(f"{module}: {message}")
                print(message)


def first_id_from_list(runner: Runner, path: str) -> int | None:
    payload = runner.request("GET", path)
    data = payload.get("data")
    if isinstance(data, list) and data:
        value = data[0].get("id")
        return value if isinstance(value, int) else None
    return None
