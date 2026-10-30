from app.config import settings
from app.utils.cloudinary_client import upload_to_cloudinary


def test_local_public_media_uses_same_origin_storage_url(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "PUBLIC_MEDIA_STORAGE", "local")
    monkeypatch.setattr(settings, "PUBLIC_MEDIA_BASE_URL", "")
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(tmp_path))

    uploaded = upload_to_cloudinary(
        b"local media",
        "cover.jpg",
        "tourvaa_demo/public/tour/images",
        content_type="image/jpeg",
    )

    assert uploaded["url"].startswith("/storage/public-media/tourvaa_demo/public/tour/images/")
    assert (tmp_path / uploaded["public_id"]).is_file()
