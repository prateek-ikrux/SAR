from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # App
    app_name: str = "Candidate Search"
    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    api_prefix: str = "/api"

    # MongoDB
    mongodb_uri: str
    mongo_db_ats: str = "ats"
    profiles_collection: str = "profiles"
    mongo_db_app: str = "search_and_retrieval"

    # Vector search
    vector_index_name: str = "autoembed_index"
    vector_path: str = "document"
    search_default_exact: bool = True
    search_pool_size: int = 100
    search_max_pool_size: int = 500
    search_ann_num_candidates_multiplier: int = 15
    search_cache_ttl_seconds: int = 300
    search_snippet_chars: int = 1200

    # Auth
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    # A single stateless access token. No refresh, no server-side session:
    # everyone signs in again once a day.
    access_token_ttl_hours: int = 24

    # Auth transport
    #   cookie - httpOnly cookies only. Requires the web app and this API to be
    #            same-site (one origin behind a proxy, or sibling subdomains).
    #   bearer - Authorization: Bearer headers only, tokens returned in the login
    #            body. Works across unrelated domains, where browsers increasingly
    #            refuse third-party cookies outright.
    #   both   - accept either. Cookies are still set; tokens are also returned.
    auth_transport: Literal["cookie", "bearer", "both"] = "cookie"

    # Cookies
    cookie_secure: bool = True
    cookie_samesite: Literal["strict", "lax", "none"] = "strict"
    cookie_domain: str | None = None
    access_cookie_name: str = "cs_access"
    csrf_cookie_name: str = "cs_csrf"
    csrf_header_name: str = "X-CSRF-Token"
    csrf_enabled: bool = True

    # One-time codes
    otp_length: int = 6
    otp_ttl_minutes: int = 10
    otp_max_attempts: int = 5
    otp_resend_cooldown_seconds: int = 60
    otp_max_per_hour: int = 5
    # When Graph is not configured, log the code instead of mailing it. Local
    # development only - refused in production by the validator below.
    otp_log_code_when_mail_unconfigured: bool = False

    # Microsoft Graph (Microsoft 365 mail)
    graph_tenant_id: str = ""
    graph_client_id: str = ""
    graph_client_secret: str = ""
    graph_sender: str = "service@ikrux.com"
    graph_timeout_seconds: float = 15.0

    # Login protection
    login_rate_limit_per_minute: int = 10

    # MinIO
    minio_endpoint: str = ""
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = ""
    minio_secure: bool = True
    minio_prefix: str = ""
    minio_presign_expiry_seconds: int = 300

    # CORS
    cors_origins: str = ""

    @field_validator("jwt_secret")
    @classmethod
    def _secret_must_be_strong(cls, value: str) -> str:
        # HS256 signs with the raw secret; anything short is brute-forceable.
        if len(value) < 32:
            raise ValueError(
                "JWT_SECRET must be at least 32 characters. "
                'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(64))"'
            )
        if "change-me" in value.lower():
            raise ValueError("JWT_SECRET is still the placeholder from .env.example.")
        return value

    @model_validator(mode="after")
    def _normalise_minio_endpoint(self) -> Settings:
        """Accept a full URL in MINIO_ENDPOINT even though the client wants host[:port].

        Pasting the console URL is the obvious thing to do, and the resulting
        failure ("Invalid endpoint") gives no hint why. Strip the scheme, and let
        an explicit scheme decide MINIO_SECURE.
        """
        endpoint = self.minio_endpoint.strip().rstrip("/")
        for scheme, secure in (("https://", True), ("http://", False)):
            if endpoint.lower().startswith(scheme):
                endpoint = endpoint[len(scheme) :]
                object.__setattr__(self, "minio_secure", secure)
                break
        object.__setattr__(self, "minio_endpoint", endpoint)
        return self

    @model_validator(mode="after")
    def _check_cookie_policy(self) -> Settings:
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError("COOKIE_SAMESITE=none requires COOKIE_SECURE=true.")
        if self.environment == "production" and not self.cookie_secure:
            raise ValueError("COOKIE_SECURE must be true in production.")
        if self.uses_cookies and self.cookie_samesite == "none" and not self.cors_origin_list:
            raise ValueError(
                "COOKIE_SAMESITE=none is a cross-site deployment, so CORS_ORIGINS must list "
                "the frontend origin(s). Credentialed CORS cannot use a wildcard."
            )
        return self

    @model_validator(mode="after")
    def _check_mail_policy(self) -> Settings:
        if self.environment == "production" and not self.graph_configured:
            raise ValueError(
                "Sign-in codes are delivered by email, so GRAPH_TENANT_ID, GRAPH_CLIENT_ID and "
                "GRAPH_CLIENT_SECRET are required in production. Without them nobody can log in."
            )
        if self.environment == "production" and self.otp_log_code_when_mail_unconfigured:
            raise ValueError(
                "OTP_LOG_CODE_WHEN_MAIL_UNCONFIGURED writes sign-in codes to the logs. "
                "It must be false in production."
            )
        return self

    @property
    def graph_configured(self) -> bool:
        return bool(
            self.graph_tenant_id and self.graph_client_id and self.graph_client_secret and self.graph_sender
        )

    @property
    def uses_cookies(self) -> bool:
        return self.auth_transport in ("cookie", "both")

    @property
    def uses_bearer(self) -> bool:
        return self.auth_transport in ("bearer", "both")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def minio_configured(self) -> bool:
        return bool(
            self.minio_endpoint and self.minio_access_key and self.minio_secret_key and self.minio_bucket
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
