"""Validated runtime settings with file-backed production secrets."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings.

    Secret values may be supplied directly for development or through ``*_FILE``
    variables for read-only Docker secret mounts. Secret fields are excluded from
    repr/serialization so diagnostics cannot accidentally disclose them.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    telegram_bot_token: SecretStr | None = Field(default=None, repr=False, exclude=True)
    telegram_bot_token_file: Path | None = None
    data_encryption_key: SecretStr | None = Field(default=None, repr=False, exclude=True)
    data_encryption_key_file: Path | None = None
    lookup_hmac_key: SecretStr | None = Field(default=None, repr=False, exclude=True)
    lookup_hmac_key_file: Path | None = None
    database_url: SecretStr | None = Field(default=None, repr=False, exclude=True)
    database_url_file: Path | None = None
    bot_username: str = "RejoinLaterBot"
    log_level: str = "INFO"
    scheduler_interval_seconds: int = Field(default=45, ge=30, le=60)
    scheduler_batch_size: int = Field(default=100, ge=1, le=1000)
    invite_ttl_hours: int = Field(default=24, ge=1, le=168)
    max_custom_days: int = Field(default=3650, ge=1)
    backup_retention_days: int = Field(default=7, ge=1)

    @model_validator(mode="after")
    def secrets_are_available(self) -> Settings:
        """Fail during startup, before a partially configured bot can poll."""

        for value_name, file_name in (
            ("telegram_bot_token", "telegram_bot_token_file"),
            ("data_encryption_key", "data_encryption_key_file"),
            ("lookup_hmac_key", "lookup_hmac_key_file"),
            ("database_url", "database_url_file"),
        ):
            if getattr(self, value_name) is None and getattr(self, file_name) is None:
                raise ValueError(f"configure {value_name.upper()} or {file_name.upper()}")
        return self

    def secret(self, value_name: str) -> str:
        """Resolve one secret without retaining file contents in the settings model."""

        value = getattr(self, value_name)
        if isinstance(value, SecretStr):
            return value.get_secret_value()
        path = getattr(self, f"{value_name}_file")
        if not isinstance(path, Path):
            raise RuntimeError(f"missing secret: {value_name}")
        return path.read_text(encoding="utf-8").strip()
