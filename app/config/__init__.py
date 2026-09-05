from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

LOCAL_FRONTEND_URL = "http://localhost:3000"
LIVE_FRONTEND_URL = "https://tourvaa.vercel.app"


class Settings(BaseSettings):
    APP_NAME: str = "Tourvaa Backend"
    # Fail closed: a deployment that forgets to set APP_ENV in its
    # environment should get production's stricter payment/webhook
    # verification behavior, not development's permissive fallbacks.
    # Local/dev workflows are unaffected - .env and .env.example both set
    # APP_ENV=development explicitly.
    APP_ENV: str = "production"
    # Fail closed here too: debug should only turn on when explicitly
    # requested (local .env sets APP_DEBUG=True), never by default.
    APP_DEBUG: bool = False

    DATABASE_URL: str

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Per-portal JWT secrets - fall back to JWT_SECRET_KEY if not set
    SUPPLIER_JWT_SECRET_KEY: str = ""
    AGENT_JWT_SECRET_KEY: str = ""
    CUSTOMER_JWT_SECRET_KEY: str = ""
    ADMIN_JWT_SECRET_KEY: str = ""
    REQUIRE_EMAIL_VERIFICATION: bool = False
    EMAIL_VERIFICATION_EXPIRE_MINUTES: int = 1440
    OTP_EXPIRE_MINUTES: int = 10
    OTP_MAX_ATTEMPTS: int = 5
    LOGIN_MAX_FAILED_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15

    FRONTEND_URL: str = ""
    API_BASE_URL: str = "http://127.0.0.1:8000"
    ALLOWED_ORIGINS: str = "*"
    # Only trust X-Forwarded-For for rate-limiting when requests genuinely
    # pass through a proxy that sets it - otherwise it's a header any direct
    # caller can spoof to dodge rate limits.
    TRUST_PROXY_HEADERS: bool = False
    MOBILE_DEEP_LINK_URL: str = "tourvaa://reset-password"
    STORAGE_ROOT: str = "storage"

    CLOUDINARY_URL: str = ""

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
    SMTP_FROM_EMAIL: str | None = None
    SMTP_REPLY_TO: str | None = None
    SMTP_USE_SSL: bool = True
    SMTP_STARTTLS: bool = False
    SMTP_TIMEOUT_SECONDS: int = 20

    REDIS_URL: str = ""
    SETTINGS_ENCRYPTION_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    PAYPAL_WEBHOOK_ID: str = ""

    ANTHROPIC_API_KEY: str = ""
    CHATBOT_LLM_MODEL: str = "claude-haiku-4-5"
    # Local ONNX embedding model (fastembed) used for chatbot RAG retrieval.
    # No API key needed -- downloads once on first use and runs on CPU.
    CHATBOT_EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"

    # Countries / States / Cities fallback API (countrystatecity.in)
    COUNTRY_STATE_CITY_API_KEY: str = ""

    # Viator Partner API (Basic Access) - powers the "External Day Trips"
    # public section. The real, admin-editable values live in the
    # api_settings DB table (Admin -> Settings -> API Settings), managed via
    # app/services/settings.py / app/services/viator.py - these two are only
    # a fallback for environments without DB access (scripts, CI). Both are
    # optional: the section renders an empty state when no key is set
    # anywhere instead of failing.
    VIATOR_API_KEY: str = ""
    VIATOR_AFFILIATE_PID: str = ""

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

    @model_validator(mode="after")
    def _default_frontend_url(self) -> "Settings":
        if not self.FRONTEND_URL.strip():
            self.FRONTEND_URL = (
                LIVE_FRONTEND_URL if self.APP_ENV == "production" else LOCAL_FRONTEND_URL
            )
        return self

    @model_validator(mode="after")
    def _require_explicit_cors_in_production(self) -> "Settings":
        # Auth uses httpOnly cookies (see routers/auth.py), and browsers refuse
        # credentialed requests against a wildcard CORS origin. A forgotten
        # ALLOWED_ORIGINS in production silently drops the cookies instead of
        # failing loudly, so refuse to boot rather than serve a broken login.
        if self.APP_ENV == "production" and self.ALLOWED_ORIGINS.strip() == "*":
            raise ValueError(
                "ALLOWED_ORIGINS must be set to an explicit comma-separated origin "
                "list in production - wildcard '*' disables credentialed CORS and "
                "breaks cookie-based login."
            )
        return self

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
    """Private document storage - outside the public /storage static-files mount."""
    return get_storage_root().parent / "private-docs"

