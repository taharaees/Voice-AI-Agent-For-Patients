from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./patients.db"
    api_key: str | None = None
    vapi_server_secret: str | None = None
    vapi_assistant_id: str | None = None
    public_api_base_url: str = "http://localhost:8000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()


def sqlalchemy_database_url(url: str) -> str:
    # Render/Supabase commonly expose the libpq-style postgres:// URL. Use the
    # psycopg 3 SQLAlchemy dialect explicitly (psycopg2 is not installed).
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url
