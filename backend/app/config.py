from functools import lru_cache
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # "production" turns on the startup check below that refuses placeholder
    # secrets. Anything else (the default) keeps local development frictionless.
    environment: str = "development"

    database_url: str = "mysql+pymysql://utender:utender@localhost:3306/utender"

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_minutes: int = 30
    jwt_refresh_ttl_days: int = 30

    # local: files live under storage_root, served through a signed backend
    # route. s3: boto3 presigned URLs. Switching is config-only.
    storage_backend: str = "local"  # "local" | "s3"
    storage_root: str = "./storage"
    storage_signing_secret: str = "change-me-in-production"
    # Stage 9.12: where backup.sh records each run's outcome (last-success /
    # last-failure); the admin overview reads it. Unset = backups not configured.
    backup_dir: str | None = None

    s3_bucket_drawings: str = "project-drawings"
    s3_bucket_documents: str = "service-provider-documents"
    s3_bucket_owner_documents: str = "owner-documents"
    s3_region: str | None = None
    s3_endpoint_url: str | None = None  # set for MinIO / S3-compatible hosts
    s3_object_prefix: str = ""  # optional key prefix, e.g. "prod/" to share a bucket across environments
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    # Fallback signed-URL lifetime for callers with no business-rule-driven
    # expiry of their own (drawings use drawing_url_expiry_seconds instead,
    # tied to the bid deadline, per spec §2.14's "do not rely solely on bid
    # deadline if post-close access is intentionally permitted" note).
    signed_url_default_expiry_seconds: int = 60 * 60 * 24  # 24h

    # Stage 3.8: the currency every requirement is priced in. One market,
    # one currency -- no conversion.
    marketplace_currency: str = "KWD"

    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_id_monthly: str | None = None
    stripe_price_id_annual: str | None = None

    resend_api_key: str | None = None
    email_from: str = "U-Tender <notifications@u-tender.example>"

    cron_secret: str | None = None
    app_url: str = "http://localhost:5173"  # frontend origin, used in email links
    api_url: str = "http://localhost:8000"  # this backend's own public origin

    cors_origins: str = "http://localhost:5173"

    # Secure flag on the auth cookies. Unset follows app_url's scheme (https
    # -> Secure); set explicitly when TLS terminates somewhere app_url
    # doesn't reflect. Browsers drop Secure cookies on plain http, so this
    # must stay off for an http-only deployment.
    cookie_secure: bool | None = None

    # Matches the original app's raised Server Action body limit (25MB ->
    # 50MB) to accommodate zipped folders of drawings.
    max_upload_mb: int = 50

    @property
    def cookies_secure(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.app_url.lower().startswith("https://")

    @model_validator(mode="after")
    def _shared_secret_algorithms_only(self):
        # Security: tokens are signed with the shared JWT_SECRET, so only the
        # HMAC algorithms make sense -- never "none" or an asymmetric one a
        # misconfiguration could turn into a forgery.
        if self.jwt_algorithm not in ("HS256", "HS384", "HS512"):
            raise ValueError("JWT_ALGORITHM must be HS256, HS384 or HS512.")
        return self

    @model_validator(mode="after")
    def _refuse_placeholder_secrets_in_production(self):
        if self.environment.strip().lower() != "production":
            return self
        # Covers both the code defaults ("change-me-in-production") and the
        # .env.example placeholders ("change-me-to-a-...").
        weak = [
            name
            for name in ("jwt_secret", "storage_signing_secret")
            if not getattr(self, name) or getattr(self, name).startswith("change-me")
        ]
        if weak:
            raise ValueError(
                f"ENVIRONMENT=production but {', '.join(w.upper() for w in weak)} is unset or still a placeholder. "
                "Generate a long random value (e.g. `openssl rand -hex 32`)."
            )
        # Stage 9.11: development defaults in production. Localhost URLs can't
        # be a working deployment (email links and CORS would point at the
        # server itself), so they are refused. Development database credentials
        # and non-Secure cookies (plain-http APP_URL, as deploy.sh sets up today)
        # are real risks but may be how a live server runs, so they are warned
        # about loudly at every start instead of stopping it.
        problems = [f"{name.upper()} points at localhost" for name in ("app_url", "api_url", "cors_origins")
                    if "localhost" in getattr(self, name) or "127.0.0.1" in getattr(self, name)]
        if problems:
            raise ValueError("ENVIRONMENT=production but " + "; ".join(problems) + ".")
        import logging

        log = logging.getLogger("config")
        if "utender:utender@" in self.database_url:
            log.warning("SECURITY: ENVIRONMENT=production but DATABASE_URL still uses the development credentials.")
        if not self.cookies_secure:
            log.warning("SECURITY: ENVIRONMENT=production but the login cookies aren't Secure (APP_URL isn't https and "
                        "COOKIE_SECURE isn't true): sessions travel unencrypted. Put the site behind HTTPS.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
