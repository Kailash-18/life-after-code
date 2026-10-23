import os

from pydantic_settings import BaseSettings

DEV_HMAC_SECRET = "sentinel-dev-secret-key-change-in-prod"
DEV_WEBHOOK_SECRET = "sentinel-gitlab-token-change-in-prod"


def _csv(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = {"env_prefix": "SENTINEL_UNUSED_", "extra": "ignore"}

    service_name: str = "sentinel-backend"
    sentinel_env: str = os.getenv("SENTINEL_ENV", "development")
    version: str = "0.2.0"
    port: int = int(os.getenv("PORT", "8000"))

    # Secrets (configured via Secret Manager or masked CI vars). Dev defaults are
    # refused at startup when SENTINEL_ENV=production (see validate_for_startup).
    hmac_secret: str = os.getenv("SENTINEL_HMAC_SECRET", DEV_HMAC_SECRET)
    gitlab_webhook_secret: str = os.getenv("GITLAB_WEBHOOK_SECRET", DEV_WEBHOOK_SECRET)

    # Allowed CORS origins for Mission Control (comma-separated env var)
    cors_origins: list[str] = _csv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:5173",
    )

    # Persistence Configuration (sqlite | memory)
    persistence_backend: str = os.getenv("SENTINEL_PERSISTENCE_BACKEND", "sqlite")
    sqlite_db_path: str = os.getenv("SENTINEL_SQLITE_PATH", "sentinel.db")

    # Event contract location (fail closed if it cannot be found)
    event_schema_path: str | None = os.getenv("SENTINEL_EVENT_SCHEMA_PATH")

    # Flow dispatch (Task R5). Mode "disabled" means the backend never starts the
    # flow itself; a CI job does and reports `flow.started` (fallback route 2).
    flow_dispatch_mode: str = os.getenv("SENTINEL_FLOW_DISPATCH_MODE", "disabled")
    flow_timeout_minutes: int = int(os.getenv("SENTINEL_FLOW_TIMEOUT_MINUTES", "30"))
    gitlab_api_url: str = os.getenv("GITLAB_API_URL", "https://gitlab.com/api/v4")
    gitlab_project_id: str | None = os.getenv("GITLAB_PROJECT_ID")
    gitlab_flow_token: str | None = os.getenv("GITLAB_FLOW_TOKEN")
    gitlab_flow_definition: str | None = os.getenv("SENTINEL_FLOW_DEFINITION")
    # Read-only token (read_api / read_repository) used to fetch analysis.json from repair MRs.
    gitlab_read_token: str | None = os.getenv("GITLAB_READ_TOKEN")

    def validate_for_startup(self) -> None:
        """Refuse to run in production with development secrets or no flow config."""
        if self.sentinel_env.lower() != "production":
            return
        problems = []
        if self.hmac_secret == DEV_HMAC_SECRET or len(self.hmac_secret) < 32:
            problems.append("SENTINEL_HMAC_SECRET must be set to a random value of 32+ chars")
        if self.gitlab_webhook_secret == DEV_WEBHOOK_SECRET:
            problems.append("GITLAB_WEBHOOK_SECRET must be set")
        if self.flow_dispatch_mode == "gitlab_api" and not (
            self.gitlab_project_id and self.gitlab_flow_token and self.gitlab_flow_definition
        ):
            problems.append(
                "gitlab_api dispatch needs GITLAB_PROJECT_ID, GITLAB_FLOW_TOKEN, SENTINEL_FLOW_DEFINITION"
            )
        if problems:
            raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))


settings = Settings()
