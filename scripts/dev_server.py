"""Run the Tourvaa API in development with scoped auto-reload."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-reload", action="store_true")
    args = parser.parse_args()

    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=not args.no_reload,
        reload_dirs=[
            str(BACKEND_ROOT / "app"),
            str(BACKEND_ROOT / "alembic"),
        ],
        reload_excludes=[
            ".git/*",
            ".pytest_cache/*",
            "__pycache__/*",
            "backups/*",
            "scripts/*",
            "tests/*",
            "venv/*",
            "*.log",
            "*.pyc",
            "*.sql",
        ],
    )


if __name__ == "__main__":
    main()
