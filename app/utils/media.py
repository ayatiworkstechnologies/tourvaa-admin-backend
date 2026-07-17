from urllib.parse import urlparse

from app.config import get_storage_root


def detect_image_type(content: bytes) -> str | None:
    """Return the supported image type identified from its file signature."""
    if content.startswith(b"\xff\xd8\xff"):
        return "jpeg"

    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"

    if (
        len(content) >= 12
        and content.startswith(b"RIFF")
        and content[8:12] == b"WEBP"
    ):
        return "webp"

    return None


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
