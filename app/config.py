from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    APP_NAME: str = "Tourvaa Backend"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True

    DATABASE_URL: str

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # Per-portal JWT secrets — fall back to JWT_SECRET_KEY if not set
    SUPPLIER_JWT_SECRET_KEY: str = ""
    AGENT_JWT_SECRET_KEY: str = ""
    CUSTOMER_JWT_SECRET_KEY: str = ""
    ADMIN_JWT_SECRET_KEY: str = ""
    REQUIRE_EMAIL_VERIFICATION: bool = False
    EMAIL_VERIFICATION_EXPIRE_MINUTES: int = 1440

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

    REDIS_URL: str = ""
    SETTINGS_ENCRYPTION_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    PAYPAL_WEBHOOK_ID: str = ""

    ANTHROPIC_API_KEY: str = ""

    # Countries / States / Cities fallback API (countrystatecity.in)
    COUNTRY_STATE_CITY_API_KEY: str = ""

    VAPID_PUBLIC_KEY: str = ""
    VAPID_PRIVATE_KEY_FILE: str = "vapid_private.pem"
    VAPID_MAILTO: str = "mailto:admin@tourvaa.com"

    def get_portal_secret(self, portal: str) -> str:
        """Return the JWT secret for the given portal, falling back to the main key."""
        mapping = {
            "supplier": self.SUPPLIER_JWT_SECRET_KEY,
            "agent": self.AGENT_JWT_SECRET_KEY,
            "customer": self.CUSTOMER_JWT_SECRET_KEY,
            "admin": self.ADMIN_JWT_SECRET_KEY,
        }
        return mapping.get(portal, "") or self.JWT_SECRET_KEY

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


def get_private_docs_root() -> Path:
    """Private document storage — outside the public /storage static-files mount."""
    return get_storage_root().parent / "private-docs"

