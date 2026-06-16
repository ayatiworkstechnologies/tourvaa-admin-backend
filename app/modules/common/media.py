from urllib.parse import urlparse

from app.config import get_storage_root


def existing_storage_path(value: str | None):
    if not value:
        return ""

    parsed = urlparse(value)
    path = parsed.path if parsed.scheme else value

    if not path.startswith("/storage/"):
        return value

    relative = path.removeprefix("/storage/")
    if (get_storage_root() / relative).exists():
        return value

    return ""
