from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "Email Assistant"
    app_env: str = "development"
    database_url: str = "sqlite:///./emailassistant.db"
    jwt_secret: str = "development-only-change-this-secret"
    bootstrap_email: str = "owner@example.com"
    bootstrap_password: str = "change-this-password"
    field_encryption_key: str = ""
    frontend_origin: str = "http://localhost:8080"
    timezone: str = "Asia/Kolkata"
    max_active_tasks: int = 3
    ai_provider: str = "disabled"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8080/api/oauth/gmail/callback"
    auto_sync_times: str = "08:00,12:00,17:00"
    initial_sync_days: int = 90
    max_messages_per_sync: int = 500

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
