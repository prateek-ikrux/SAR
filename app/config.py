from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    mongodb_uri: str
    mongodb_db: str = "ats"
    mongodb_collection: str = "profiles"
    vector_index_name: str = "autoembed_index"
    vector_path: str = "document"


settings = Settings()
