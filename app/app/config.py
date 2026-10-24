import os

from pydantic import BaseModel


class AppSettings(BaseModel):
    service_name: str = os.getenv("SERVICE_NAME", "sentinel-target-app")
    app_env: str = os.getenv("APP_ENV", "production")
    version: str = os.getenv("APP_VERSION", "1.0.0")


settings = AppSettings()
