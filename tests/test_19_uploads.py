"""Module 19 - Uploads"""
import io
import pytest
import requests
from tests.conftest import BASE_URL, skip_if_readonly
from app.utils.media import detect_image_type


PROFILE_IMAGE_URL = f"{BASE_URL}/uploads/profile-image"
ADMIN_ASSET_URL = f"{BASE_URL}/uploads/admin-asset"


def test_avif_signature_is_detected():
    avif_bytes = (
        b"\x00\x00\x00\x20ftypavif\x00\x00\x00\x00"
        b"avifmif1\x00\x00\x00\x00"
    )
    assert detect_image_type(avif_bytes) == "avif"


def test_non_avif_iso_media_is_not_accepted_as_avif():
    heic_bytes = (
        b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00"
        b"mif1heic"
    )
    assert detect_image_type(heic_bytes) is None


def test_upload_profile_image_endpoint_exists(headers):
    # POST without file should give 422 (missing field), not 404
    resp = requests.post(PROFILE_IMAGE_URL, headers=headers, timeout=10)
    assert resp.status_code in (422, 400), f"Expected 422/400 (no file), got {resp.status_code}"


def test_upload_admin_asset_endpoint_exists(headers):
    resp = requests.post(ADMIN_ASSET_URL, headers=headers, timeout=10)
    assert resp.status_code in (422, 400), f"Expected 422/400 (no file), got {resp.status_code}"


def test_upload_requires_auth():
    files = {"file": ("test.jpg", io.BytesIO(b"fake"), "image/jpeg")}
    resp = requests.post(PROFILE_IMAGE_URL, files=files, timeout=10)
    assert resp.status_code in (401, 403, 422)


@skip_if_readonly()
def test_upload_profile_image_jpeg(headers):
    # 1x1 minimal JPEG bytes
    jpeg_bytes = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c"
        b"\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c"
        b"\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\x1edL\t\x16\x17\r\xff\xc0"
        b"\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01"
        b"\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03"
        b"\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xf5\x01"
        b"\xff\xd9"
    )
    files = {"file": ("test.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")}
    resp = requests.post(PROFILE_IMAGE_URL, headers=headers, files=files, timeout=30)
    assert resp.status_code in (200, 201)
    body = resp.json()
    data = body.get("data", body)
    url = data.get("url") or data.get("file_url") or data.get("image_url") or data.get("path")
    assert url, "Upload response should contain a file URL"


@skip_if_readonly()
def test_upload_admin_asset_png(headers):
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    files = {"file": ("test.png", io.BytesIO(png_bytes), "image/png")}
    resp = requests.post(ADMIN_ASSET_URL, headers=headers, files=files, timeout=30)
    assert resp.status_code in (200, 201)


@skip_if_readonly()
def test_upload_non_image_rejected(headers):
    files = {"file": ("script.sh", io.BytesIO(b"#!/bin/bash\nrm -rf /"), "application/x-sh")}
    resp = requests.post(ADMIN_ASSET_URL, headers=headers, files=files, timeout=10)
    assert resp.status_code in (400, 415, 422)
