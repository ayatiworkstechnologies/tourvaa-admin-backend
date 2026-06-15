from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    APP_NAME: str = "Tourvaa Backend"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True

    DATABASE_URL: str

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    FRONTEND_URL: str = "http://127.0.0.1:3000"
    API_BASE_URL: str = "http://127.0.0.1:8000"
    ALLOWED_ORIGINS: str = "*"
    MOBILE_DEEP_LINK_URL: str = "tourvaa://reset-password"
    STORAGE_ROOT: str = "storage"

    SUPER_ADMIN_NAME: str = "Super Admin"
    SUPER_ADMIN_EMAIL: str = "admin@tourvaa.com"
    SUPER_ADMIN_PASSWORD: str = "Admin@123"
    SUPER_ADMIN_RESET_PASSWORD_ON_STARTUP: bool = False

    SMTP_HOST: str | None = None
    SMTP_PORT: int = 465
    SMTP_USERNAME: str | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_NAME: str = "Tourvaa"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )

    @property
    def cors_origins(self):
        if self.ALLOWED_ORIGINS.strip() == "*":
            return ["*"]

        return [
            origin.strip()
            for origin in self.ALLOWED_ORIGINS.split(",")
            if origin.strip()
        ]


settings = Settings()


def get_storage_root() -> Path:
    path = Path(settings.STORAGE_ROOT)

    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path

    return path
