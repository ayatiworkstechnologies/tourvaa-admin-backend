from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="/client", tags=["Client"])


@router.get("/config")
def client_config():
    return {
        "status": "success",
        "message": "Client configuration loaded",
        "data": {
            "api_base_url": settings.API_BASE_URL,
            "api_prefix": "/api",
            "auth": {
                "type": "bearer",
                "header": "Authorization",
                "format": "Bearer <access_token>",
            },
            "clients": {
                "web": {
                    "reset_password_url": f"{settings.FRONTEND_URL}/reset-password",
                },
                "mobile": {
                    "reset_password_url": settings.MOBILE_DEEP_LINK_URL,
                },
            },
            "uploads": {
                "profile_image": {
                    "max_size_mb": 2,
                    "mime_types": ["image/png", "image/jpeg", "image/webp"],
                }
            },
            "headers": {
                "client_type": "X-Client-Type",
                "client_version": "X-Client-Version",
                "device_id": "X-Device-Id",
            },
        },
    }
