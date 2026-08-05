from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    mongodb_uri: str
    mongodb_db: str = "ats"
    mongodb_collection: str = "profiles"
    vector_index_name: str = "autoembed_index"
    vector_path: str = "document"

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60 * 24

    otp_length: int = 6
    otp_ttl_minutes: int = 10
    otp_max_attempts: int = 5
    otp_resend_cooldown_seconds: int = 60

    allowed_emails_collection: str = "allowed_emails"
    otp_collection: str = "otp_codes"

    smtp_host: str
    smtp_port: int = 587
    smtp_user: str
    smtp_password: str
    smtp_from_email: str
    smtp_use_tls: bool = True

    cors_allow_origins: str = "*"


settings = Settings()
