import imghdr
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, UploadFile, File

router = APIRouter(prefix="/uploads", tags=["Uploads"])

MAX_IMAGE_SIZE = 2 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
ALLOWED_IMAGE_TYPES = {
    "jpeg": "jpg",
    "png": "png",
    "webp": "webp",
}
PROFILE_IMAGE_DIR = (
    Path(__file__).resolve().parents[3] / "storage" / "uploads" / "profile-images"
)


@router.post("/profile-image")
async def upload_profile_image(request: Request, file: UploadFile = File(...)):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Only JPG, PNG, and WEBP images are allowed")

    content = await file.read()

    if not content:
        raise HTTPException(status_code=400, detail="Image file is required")

    if len(content) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="Image must be 2MB or smaller")

    detected_type = imghdr.what(None, h=content)

    if detected_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Invalid image file")

    extension = ALLOWED_IMAGE_TYPES[detected_type]
    PROFILE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid4().hex}.{extension}"
    file_path = PROFILE_IMAGE_DIR / filename
    file_path.write_bytes(content)

    image_path = f"/storage/uploads/profile-images/{filename}"
    image_url = str(request.base_url).rstrip("/") + image_path

    return {
        "status": "success",
        "message": "Profile image uploaded successfully",
        "data": {
            "path": image_path,
            "url": image_url,
            "filename": filename,
        },
    }
