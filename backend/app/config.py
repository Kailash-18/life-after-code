import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "sentinel-backend"
    sentinel_env: str = os.getenv("SENTINEL_ENV", "development")
    version: str = "0.1.0"
    port: int = int(os.getenv("PORT", "8000"))

    # Secrets (configured via Secret Manager or masked CI vars)
    api_key: str = os.getenv(
        "SENTINEL_API_KEY", "sk-sentinel-live-9f8a2b3c4d5e"
    )
    hmac_secret: str = os.getenv(
        "SENTINEL_HMAC_SECRET", "sentinel-dev-secret-key-change-in-prod"
    )
    gitlab_webhook_secret: str = os.getenv(
        "GITLAB_WEBHOOK_SECRET", "sentinel-gitlab-token-change-in-prod"
    )

    # Allowed CORS origins for Mission Control Frontend
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "https://sentinel-mission-control.web.app",
    ]


settings = Settings()
