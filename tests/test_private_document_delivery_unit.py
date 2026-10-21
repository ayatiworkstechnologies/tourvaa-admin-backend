from app.utils import cloudinary_client


def test_authenticated_raw_document_uses_short_lived_inline_download_url(monkeypatch):
    captured = {}

    monkeypatch.setattr(cloudinary_client, "_configure", lambda: None)

    def private_download_url(public_id, extension, **options):
        captured.update(public_id=public_id, extension=extension, **options)
        return "https://api.cloudinary.test/document-download"

    monkeypatch.setattr(cloudinary_client.cloudinary.utils, "private_download_url", private_download_url)

    url = cloudinary_client.get_private_file_url(
        "tourvaa/suppliers/12/documents/registration-certificate.pdf",
        "raw",
    )

    assert url == "https://api.cloudinary.test/document-download"
    assert captured["public_id"].endswith("registration-certificate.pdf")
    assert captured["extension"] == "pdf"
    assert captured["resource_type"] == "raw"
    assert captured["type"] == "authenticated"
    assert captured["attachment"] is False
    assert captured["expires_at"] > 0


def test_authenticated_image_document_keeps_signed_delivery_url(monkeypatch):
    captured = {}

    monkeypatch.setattr(cloudinary_client, "_configure", lambda: None)

    def cloudinary_url(public_id, **options):
        captured.update(public_id=public_id, **options)
        return "https://res.cloudinary.test/image", {}

    monkeypatch.setattr(cloudinary_client.cloudinary.utils, "cloudinary_url", cloudinary_url)

    url = cloudinary_client.get_private_file_url("tourvaa/suppliers/12/documents/licence", "image")

    assert url == "https://res.cloudinary.test/image"
    assert captured["type"] == "authenticated"
    assert captured["sign_url"] is True
