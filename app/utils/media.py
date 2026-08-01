from pathlib import Path
from urllib.parse import urlparse

from app.config import get_storage_root, get_private_docs_root


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

    # AVIF uses the ISO Base Media File Format. Require an AVIF major or
    # compatible brand inside the declared ftyp box instead of trusting the
    # browser-provided MIME type or filename.
    if len(content) >= 16 and content[4:8] == b"ftyp":
        box_size = int.from_bytes(content[:4], byteorder="big")
        box_end = min(len(content), box_size) if box_size >= 16 else len(content)
        brands = [content[8:12]]
        brands.extend(
            content[offset:offset + 4]
            for offset in range(16, box_end, 4)
            if len(content[offset:offset + 4]) == 4
        )
        if b"avif" in brands or b"avis" in brands:
            return "avif"

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


def resolve_private_docs_path(file_path: str | None, prefix: str) -> Path | None:
    """Convert a stored '<prefix>...' marker to an absolute filesystem path
    under the private docs root, refusing to resolve outside that root
    (e.g. via a '../' segment)."""
    if not file_path or not file_path.startswith(prefix):
        return None

    relative = file_path[len(prefix):]
    root = get_private_docs_root().resolve()
    candidate = (root / relative).resolve()

    if candidate != root and root not in candidate.parents:
        return None

    return candidate
