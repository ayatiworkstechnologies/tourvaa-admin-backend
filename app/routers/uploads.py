from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from app.auth.permissions import get_current_user
from app.utils.imagekit_client import upload_to_imagekit
from app.utils.media import detect_image_type
from app.models.users import User

router = APIRouter(prefix="/uploads", tags=["Uploads"])

MAX_IMAGE_SIZE = 2 * 1024 * 1024
MAX_ADMIN_ASSET_SIZE = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/avif": "avif",
}
ALLOWED_IMAGE_TYPES = {
    "jpeg": "jpg",
    "png": "png",
    "webp": "webp",
    "avif": "avif",
}


@router.post("/profile-image")
async def upload_profile_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Only JPG, PNG, WEBP, and AVIF images are allowed")

    content = await file.read()

    if not content:
        raise HTTPException(status_code=400, detail="Image file is required")

    if len(content) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="Image must be 2MB or smaller")

    detected_type = detect_image_type(content)

    if detected_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Invalid image file")

    extension = ALLOWED_IMAGE_TYPES[detected_type]
    filename = f"{uuid4().hex}.{extension}"
    uploaded = upload_to_imagekit(content, filename, folder="/tourvaa/profile-images")

    return {
        "status": "success",
        "message": "Profile image uploaded successfully",
        "data": {
            "path": uploaded["url"],
            "url": uploaded["url"],
            "filename": filename,
            "uploaded_by": current_user.id,
        },
    }


@router.post("/admin-asset")
async def upload_admin_asset(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    content = await file.read()

    if not content:
        raise HTTPException(status_code=400, detail="File is required")

    if len(content) > MAX_ADMIN_ASSET_SIZE:
        raise HTTPException(status_code=400, detail="File must be 10MB or smaller")

    allowed_types = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/avif": "avif",
        "application/pdf": "pdf",
    }
    extension = allowed_types.get(file.content_type or "")

    if not extension:
        raise HTTPException(status_code=400, detail="Only JPG, PNG, WEBP, AVIF, and PDF files are allowed")

    if extension in {"jpg", "png", "webp", "avif"}:
        detected_type = detect_image_type(content)
        if detected_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=400, detail="Invalid image file")
        extension = ALLOWED_IMAGE_TYPES[detected_type]
    elif not content.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Invalid PDF file")

    filename = f"{uuid4().hex}.{extension}"
    uploaded = upload_to_imagekit(content, filename, folder="/tourvaa/admin-assets")

    return {
        "status": "success",
        "message": "File uploaded successfully",
        "data": {
            "path": uploaded["url"],
            "url": uploaded["url"],
            "filename": filename,
            "file_size": len(content),
            "mime_type": file.content_type,
            "uploaded_by": current_user.id,
        },
    }
