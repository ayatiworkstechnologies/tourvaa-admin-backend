from functools import lru_cache
from pathlib import PurePosixPath
from time import time
from urllib.parse import urlparse

import cloudinary
import cloudinary.uploader
import cloudinary.utils
from fastapi import HTTPException

from app.config import settings


@lru_cache
def _configure() -> None:
    """Parse CLOUDINARY_URL (cloudinary://API_KEY:API_SECRET@CLOUD_NAME) ourselves
    and configure the SDK explicitly, rather than relying on the SDK's own
    os.environ auto-detection - this app loads settings via pydantic-settings,
    which does not propagate .env values into the real process environment.
    """
    raw = settings.CLOUDINARY_URL.strip()
    if not raw:
        raise HTTPException(status_code=503, detail="Image/document upload storage is not configured")

    parsed = urlparse(raw)
    if parsed.scheme != "cloudinary" or not parsed.username or not parsed.password or not parsed.hostname:
        raise HTTPException(status_code=503, detail="CLOUDINARY_URL is not a valid cloudinary://API_KEY:API_SECRET@CLOUD_NAME value")

    cloudinary.config(
        cloud_name=parsed.hostname,
        api_key=parsed.username,
        api_secret=parsed.password,
        secure=True,
    )


def _resource_type_for(content_type: str | None, filename: str) -> str:
    """Cloudinary needs the right resource_type both to upload and to later
    build a delivery URL. Only true raster images go as "image" - PDFs go as
    "raw" too, even though Cloudinary *can* upload a PDF as "image" (for
    page-thumbnail rendering). "raw" is the appropriate fit for files we
    store and serve as-is. Some Cloudinary product environments still
    restrict direct PDF delivery, which is why public tour brochures use a
    signed attachment download route.
    """
    lowered = (filename or "").lower()
    if (content_type or "").startswith("image/"):
        return "image"
    if lowered.endswith((".png", ".jpg", ".jpeg", ".webp", ".avif", ".gif")):
        return "image"
    if (content_type or "").startswith("video/"):
        return "video"
    if lowered.endswith((".mp4", ".webm", ".mov")):
        return "video"
    return "raw"


def upload_to_cloudinary(content: bytes, filename: str, folder: str, is_private: bool = False, content_type: str | None = None) -> dict:
    """Upload raw bytes to Cloudinary. Returns {"url", "public_id", "resource_type"}.

    Public uploads (`is_private=False`) get a normal, permanently-public `url` -
    store that as-is. Private uploads (KYC documents etc.) are uploaded with
    type="authenticated" so the plain URL is not publicly fetchable; store
    `public_id`/`resource_type` and use `get_private_file_url` to build a
    freshly-signed delivery URL on each authorized access, same pattern as
    the private-document endpoints already use.

    `filename` (expected pre-sanitized, e.g. via app.utils.media.sanitize_filename)
    is used as the base of the Cloudinary public_id (`use_filename=True`) so
    stored/displayed names stay human-readable instead of opaque generated
    ids. `unique_filename=True` is kept alongside it so Cloudinary appends a
    short random suffix only on an actual name collision, rather than
    silently reusing or overwriting an unrelated asset that happens to
    sanitize to the same name.
    """
    _configure()
    resource_type = _resource_type_for(content_type, filename)
    try:
        result = cloudinary.uploader.upload(
            content,
            folder=folder.strip("/"),
            resource_type=resource_type,
            type="authenticated" if is_private else "upload",
            filename=filename,
            use_filename=True,
            unique_filename=True,
            overwrite=False,
        )
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Cloudinary upload failed: {error}") from error

    url = result.get("secure_url") or result.get("url")
    public_id = result.get("public_id")
    if not url or not public_id:
        raise HTTPException(status_code=502, detail="Cloudinary upload did not return a usable file reference")

    return {"url": url, "public_id": public_id, "resource_type": result.get("resource_type", resource_type)}


def get_private_file_url(public_id: str, resource_type: str = "image") -> str:
    """Build a freshly-signed delivery URL for a private ("authenticated" type)
    Cloudinary asset. Called on each authorized access (see
    routers/private_documents.py), so a short-lived link never needs to be
    cached or reused.
    """
    _configure()

    # Cloudinary's CDN signed-delivery URL is appropriate for authenticated
    # images and video. Raw files (PDF/DOC/DOCX) need its signed download API
    # instead. A CDN delivery URL for an authenticated raw file may be
    # rejected by Cloudinary even when its signature is present, leaving the
    # admin "View document" tab on an error page. The download API returns a
    # short-lived URL which preserves inline PDF viewing and never exposes a
    # permanent public document URL.
    if resource_type == "raw":
        extension = PurePosixPath(public_id).suffix.removeprefix(".").lower()
        if not extension:
            raise HTTPException(status_code=500, detail="Private raw document is missing its file extension")
        try:
            url = cloudinary.utils.private_download_url(
                public_id,
                extension,
                resource_type="raw",
                type="authenticated",
                attachment=False,
                expires_at=int(time()) + 300,
            )
        except Exception as error:
            raise HTTPException(status_code=502, detail="Could not prepare the private document") from error
        if not url:
            raise HTTPException(status_code=502, detail="Could not prepare the private document")
        return url

    url, _options = cloudinary.utils.cloudinary_url(
        public_id,
        resource_type=resource_type,
        type="authenticated",
        sign_url=True,
        secure=True,
    )
    if not url:
        raise HTTPException(status_code=502, detail="Could not build a signed Cloudinary URL")
    return url


def get_signed_download_url(public_id: str, *, resource_type: str = "raw", extension: str = "pdf") -> str:
    """Create a short-lived attachment URL for a public document.

    Cloudinary can block direct PDF delivery at the product-environment level.
    Public tour brochures are intentionally downloadable, so the public API
    uses this server-side signature instead of exposing a raw, blocked URL.
    """
    _configure()
    try:
        url = cloudinary.utils.private_download_url(
            public_id,
            extension,
            resource_type=resource_type,
            type="upload",
            attachment=True,
            expires_at=int(time()) + 300,
        )
    except Exception as error:
        raise HTTPException(status_code=502, detail="Could not prepare the document download") from error
    if not url:
        raise HTTPException(status_code=502, detail="Could not prepare the document download")
    return url


def delete_from_cloudinary(public_id: str, resource_type: str = "image", is_private: bool = False) -> None:
    _configure()
    try:
        cloudinary.uploader.destroy(
            public_id,
            resource_type=resource_type,
            type="authenticated" if is_private else "upload",
        )
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Cloudinary delete failed: {error}") from error
