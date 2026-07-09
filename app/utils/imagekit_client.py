from functools import lru_cache

from fastapi import HTTPException
from imagekitio import ImageKit

from app.config import settings


@lru_cache
def get_imagekit_client() -> ImageKit:
    if not settings.IMAGEKIT_PRIVATE_KEY.strip():
        raise HTTPException(
            status_code=503,
            detail="Image upload storage is not configured",
        )

    return ImageKit(private_key=settings.IMAGEKIT_PRIVATE_KEY)


def _read_upload_attr(result: object, key: str) -> str:
    if isinstance(result, dict):
        value = result.get(key)
    else:
        value = getattr(result, key, None)

    if not value:
        raise HTTPException(status_code=502, detail="Image storage upload failed")

    return str(value)


def upload_to_imagekit(content: bytes, filename: str, folder: str, is_private: bool = False) -> dict:
    """Upload raw bytes to ImageKit. Returns {"url", "file_path", "file_id"}.

    `file_path` is ImageKit's internal path (e.g. "/suppliers/abc123.pdf") - store this
    for private files so a fresh signed URL can be generated on each access via
    `get_private_file_url`. `url` is the direct/public CDN URL, safe to store as-is for
    public (non-private) uploads.
    """
    client = get_imagekit_client()
    result = client.files.upload(
        file=content,
        file_name=filename,
        folder=folder,
        is_private_file=is_private,
        use_unique_file_name=True,
    )
    return {
        "url": _read_upload_attr(result, "url"),
        "file_path": _read_upload_attr(result, "file_path"),
        "file_id": _read_upload_attr(result, "file_id"),
    }


def get_private_file_url(file_path: str, expires_in: int = 3600) -> str:
    """Generate a signed, time-limited URL for a private ImageKit file path."""
    if not settings.IMAGEKIT_URL_ENDPOINT.strip():
        raise HTTPException(
            status_code=503,
            detail="Image upload URL endpoint is not configured",
        )

    client = get_imagekit_client()
    return client.helper.build_url(
        src=file_path,
        url_endpoint=settings.IMAGEKIT_URL_ENDPOINT,
        signed=True,
        expires_in=expires_in,
    )


def delete_from_imagekit(file_id: str) -> None:
    client = get_imagekit_client()
    client.files.delete(file_id)
