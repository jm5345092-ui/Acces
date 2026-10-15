from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APKLAB_", env_file=".env", extra="ignore")

    secret_key: str = "change-me-to-a-random-value"
    database_url: str = "sqlite:///./apklab.db"
    storage_root: Path = Path("./storage")
    max_upload_mb: int = 512
    job_timeout_seconds: int = 900

    # Must unlock backend/app/signing/release.jks (the keystore shared with
    # portal/generador de apks) — see signing_service.py.
    test_keystore_password: str = "15264417caf043752d3b"
    test_key_alias: str = "webapp"
    test_key_password: str = "15264417caf043752d3b"

    redis_url: str = "redis://localhost:6379/0"

    ai_provider: str = "claude"
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    @property
    def projects_root(self) -> Path:
        root = self.storage_root / "projects"
        root.mkdir(parents=True, exist_ok=True)
        return root


@lru_cache
def get_settings() -> Settings:
    return Settings()
