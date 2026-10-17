import re
from pathlib import Path
from urllib.parse import urlparse

from app.config import get_storage_root, get_private_docs_root

_UNSAFE_CHARS_RE = re.compile(r"[^a-zA-Z0-9]+")
_MAX_FILENAME_BASE_LENGTH = 80


def sanitize_filename(original_name: str | None, extension: str) -> str:
    """Turn a user-supplied filename into a short, storage-safe name instead
    of a generated uuid4 hex string: strip any path, drop the original
    extension, replace anything that isn't alphanumeric with a hyphen, and
    cap the length so folder listings/URLs stay readable. Falls back to
    "file" if nothing usable is left (e.g. an original name that was pure
    punctuation, or no name at all)."""
    base = (original_name or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = base.rsplit(".", 1)[0] if "." in base else base
    base = _UNSAFE_CHARS_RE.sub("-", base).strip("-").lower()
    base = base[:_MAX_FILENAME_BASE_LENGTH].rstrip("-") or "file"
    return f"{base}.{extension}"


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


def detect_video_type(content: bytes) -> str | None:
    """Return the supported video type identified from its file signature."""
    # Inspect the major and compatible brands in the declared ftyp box.
    # Encoders often use a different major brand while declaring MP4
    # compatibility in a later entry.
    if len(content) >= 16 and content[4:8] == b"ftyp":
        box_size = int.from_bytes(content[:4], "big")
        if 16 <= box_size <= len(content) and box_size % 4 == 0:
            brands = {content[8:12]} | {content[i:i + 4] for i in range(16, box_size, 4)}
            mp4_brands = {b"isom", b"iso2", b"iso3", b"iso4", b"iso5", b"iso6", b"mp41", b"mp42", b"avc1", b"M4V ", b"dash", b"MSNV", b"3gp4", b"3gp5", b"3gp6"}
            if not brands.intersection({b"avif", b"avis", b"heic", b"heix", b"mif1"}) and brands.intersection(mp4_brands):
                return "mp4"

    # WebM/Matroska container: EBML magic bytes.
    if content.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm"

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
