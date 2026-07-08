from functools import lru_cache

from imagekitio import ImageKit

from app.config import settings


@lru_cache
def get_imagekit_client() -> ImageKit:
    return ImageKit(private_key=settings.IMAGEKIT_PRIVATE_KEY)


def upload_to_imagekit(content: bytes, filename: str, folder: str, is_private: bool = False) -> dict:
    """Upload raw bytes to ImageKit. Returns {"url", "file_path", "file_id"}.

    `file_path` is ImageKit's internal path (e.g. "/suppliers/abc123.pdf") — store this
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
        "url": result.url,
        "file_path": result.file_path,
        "file_id": result.file_id,
    }


def get_private_file_url(file_path: str, expires_in: int = 3600) -> str:
    """Generate a signed, time-limited URL for a private ImageKit file path."""
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
