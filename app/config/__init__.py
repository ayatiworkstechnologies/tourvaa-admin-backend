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
    ADMIN_JWT_SECRET_KEY: str = ""
    NORMAL_JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Admin roles and all normal portal users use separate signing keys.
    REQUIRE_EMAIL_VERIFICATION: bool = False
    EMAIL_VERIFICATION_EXPIRE_MINUTES: int = 1440
    OTP_EXPIRE_MINUTES: int = 10
    OTP_MAX_ATTEMPTS: int = 5
    LOGIN_MAX_FAILED_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15

    FRONTEND_URL: str = ""
    API_BASE_URL: str = "http://127.0.0.1:8000"
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = ""
    ALLOWED_ORIGINS: str = "*"
    # Only trust X-Forwarded-For for rate-limiting when requests genuinely
    # pass through a proxy that sets it - otherwise it's a header any direct
    # caller can spoof to dodge rate limits.
    TRUST_PROXY_HEADERS: bool = False
    MOBILE_DEEP_LINK_URL: str = "tourvaa://reset-password"
    STORAGE_ROOT: str = "storage"

    CLOUDINARY_URL: str = ""
    # Public website assets are deliberately segregated from authenticated
    # supplier, vehicle, agent, and affiliate documents. Cloudinary creates
    # these folders lazily on the first public upload.
    CLOUDINARY_PUBLIC_ROOT: str = "tourvaa_demo/public"
    # Public media can be kept local during development before being moved to
    # a configured CDN/SFTP provider. Private documents always remain on the
    # authenticated storage path.
    PUBLIC_MEDIA_STORAGE: str = "cloudinary"
    PUBLIC_MEDIA_BASE_URL: str = ""

    SUPER_ADMIN_NAME: str = "Super Admin"
    SUPER_ADMIN_EMAIL: str = "admin@tourvaa.com"
    # Local/bootstrap seed default only. Production rejects these unchanged
    # defaults, so deployments must provide distinct environment credentials.
    SUPER_ADMIN_PASSWORD: str = "Tourvaa@2026!"
    SUPER_ADMIN_RESET_PASSWORD_ON_STARTUP: bool = False

    # Bootstrap logins for the two day-to-day back-office roles.
    # Keep these separate from the super-admin account so production can use
    # distinct credentials and rotate each account independently.
    ADMIN_NAME: str = "Admin"
    ADMIN_EMAIL: str = "admin.user@tourvaa.com"
    ADMIN_PASSWORD: str = "Tourvaa@2026!"
    ADMIN_RESET_PASSWORD_ON_STARTUP: bool = False

    SUB_ADMIN_NAME: str = "Sub Admin"
    SUB_ADMIN_EMAIL: str = "subadmin@tourvaa.com"
    SUB_ADMIN_PASSWORD: str = "Tourvaa@2026!"
    SUB_ADMIN_RESET_PASSWORD_ON_STARTUP: bool = False

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

    # Local ONNX embedding model (fastembed) used for chatbot RAG retrieval.
    # No API key needed -- downloads once on first use and runs on CPU.
    CHATBOT_EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"

    # Viator Partner API (Basic Access) - powers the "External Day Trips"
    # public section. The real, admin-editable values live in the
    # api_settings DB table (Admin -> Settings -> API Settings), managed via
    # app/services/settings.py / app/services/viator.py - these two are only
    # a fallback for environments without DB access (scripts, CI). Both are
    # optional: the section renders an empty state when no key is set
    # anywhere instead of failing.
    VIATOR_API_KEY: str = ""
    VIATOR_AFFILIATE_PID: str = ""
    # Alias for VIATOR_AFFILIATE_PID (either name works; this one wins).
    VIATOR_PID: str = ""
    # "sandbox" or "production" - picks the Partner API host below. Sandbox
    # keys only work against the sandbox host and vice versa (a sandbox key on
    # the production host answers 401 "Invalid API Key").
    VIATOR_ENV: str = "sandbox"
    # Optional explicit override of the Partner API base URL.
    VIATOR_API_BASE_URL: str = ""
    # Deployment-level kill switch, in addition to the admin's Enable toggle
    # (Admin -> Integrations -> Viator). Both must be on for any Viator call.
    VIATOR_ENABLED: bool = True
    # Prefix of the campaign value appended to Viator affiliate links, e.g.
    # "tourvaa" -> campaign=tourvaa-day-tours.
    VIATOR_CAMPAIGN_PREFIX: str = "tourvaa"
    VIATOR_TIMEOUT_SECONDS: float = 15.0

    VAPID_PUBLIC_KEY: str = ""
    VAPID_PRIVATE_KEY_FILE: str = "vapid_private.pem"
    # Optional: the private key itself (PEM text or base64url raw key) instead
    # of a file - handy on hosts where shipping a .pem file is awkward.
    VAPID_PRIVATE_KEY: str = ""
    VAPID_MAILTO: str = "mailto:admin@tourvaa.com"

    # IP -> country geolocation used only for browsing-currency detection
    # (never for anything booking/checkout-critical - lookups are always
    # best-effort and fall back to DEFAULT_CURRENCY/DEFAULT_LOCALE on any
    # failure). Defaults to the existing ip-api.com free-tier endpoint for
    # continuity; set GEOIP_PROVIDER + GEOIP_API_KEY to switch to a licensed
    # provider (e.g. "ipapi" for ipapi.com, "ip-api" for a paid ip-api.com
    # plan) before going to production, since the ip-api.com free tier is
    # not licensed for commercial/production use.
    GEOIP_PROVIDER: str = "ip-api"
    GEOIP_API_KEY: str = ""
    DEFAULT_CURRENCY: str = "USD"
    DEFAULT_LOCALE: str = "en-US"

    def get_auth_secret(self, auth_domain: str) -> str:
        if auth_domain == "admin":
            return self.ADMIN_JWT_SECRET_KEY.strip() or self.JWT_SECRET_KEY
        if auth_domain == "normal":
            return self.NORMAL_JWT_SECRET_KEY.strip() or self.JWT_SECRET_KEY
        raise ValueError("Unknown authentication domain")

    def get_portal_secret(self, portal: str | None = None) -> str:
        return self.get_auth_secret("admin" if portal == "admin" else "normal")

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
        if self.is_production and self.ALLOWED_ORIGINS.strip() == "*":
            raise ValueError(
                "ALLOWED_ORIGINS must be set to an explicit comma-separated origin "
                "list in production - wildcard '*' disables credentialed CORS and "
                "breaks cookie-based login."
            )
        return self

    @property
    def is_production(self) -> bool:
        """True for any deployment that isn't explicitly local/dev.

        Security- and correctness-critical gates (webhook signature
        enforcement, docs exposure, test-payment endpoints, startup config
        validation) must treat every non-development environment - staging,
        UAT, a misspelled env name, or simply APP_ENV left unset - the same
        as production. Checking `APP_ENV == "production"` literally instead
        would silently disable that hardening for anything but the exact
        string "production", which defeats the fail-closed default above.
        """
        return self.APP_ENV != "development"

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
        # Relative storage belongs beside the backend project, not inside
        # app/. This keeps uploaded public files directly under ./storage
        # in both local development and deployments using a relative root.
        path = Path(__file__).resolve().parents[2] / path

    return path


def get_private_docs_root() -> Path:
    """Private document storage - outside the public /storage static-files mount."""
    return get_storage_root().parent / "private-docs"

