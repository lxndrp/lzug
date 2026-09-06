"""Typed, secret-safe runtime configuration assembled at process startup."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

_MEDIA_TYPE = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$")


def _value(environment: Mapping[str, str], name: str, default: Any = None) -> Any:
    value = environment.get(name, default)
    return value


def _optional_text(value: Any) -> Any:
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    return stripped or None


def _boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ValueError("must be true or false")


def _origin(value: str, name: str) -> str:
    try:
        parsed = urlsplit(value)
        parsed_port = parsed.port
    except ValueError as error:
        raise ValueError(f"{name} must contain an exact HTTP origin") from error
    if (
        value == "*"
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.hostname is None
        or (parsed_port is None and ":" in parsed.netloc.rsplit("]", 1)[-1])
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or value.endswith("/")
    ):
        raise ValueError(f"{name} must contain an exact HTTP origin")
    return value


def _http_origin_or_empty(value: str | None, name: str) -> str | None:
    value = _optional_text(value)
    return _origin(value, name) if value else None


def _safe_validation_error(error: ValidationError) -> ValueError:
    messages = []
    for item in error.errors(include_context=False):
        location = ".".join(str(part) for part in item["loc"])
        message = str(item["msg"])
        if location == "LZUG_MAX_UPLOAD_BYTES" and "greater than or equal" in message:
            message = "LZUG_MAX_UPLOAD_BYTES must be between 1024 and 104857600"
        messages.append(f"{location}: {message}")
    return ValueError("; ".join(messages))


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)


class SecuritySettings(_Model):
    """HTTP and request-security values shared by every application start path."""

    https_only: bool = Field(True, validation_alias="LZUG_HTTPS_ONLY")
    cors_allowed_origins: frozenset[str] = Field(
        default_factory=frozenset, validation_alias="LZUG_CORS_ALLOWED_ORIGINS"
    )
    session_ttl_seconds: int = Field(
        8 * 60 * 60,
        ge=5 * 60,
        le=24 * 60 * 60,
        validation_alias="LZUG_SESSION_TTL_SECONDS",
    )
    max_request_bytes: int = Field(
        1024 * 1024,
        ge=1024,
        le=10 * 1024 * 1024,
        validation_alias="LZUG_MAX_REQUEST_BYTES",
    )
    auth_rate_limit: int = Field(20, ge=1, le=1000, validation_alias="LZUG_AUTH_RATE_LIMIT")
    auth_rate_window_seconds: int = Field(
        60,
        ge=1,
        le=60 * 60,
        validation_alias="LZUG_AUTH_RATE_WINDOW_SECONDS",
    )

    @field_validator("https_only", mode="before")
    @classmethod
    def parse_https_only(cls, value: Any) -> bool:
        try:
            return _boolean(value)
        except ValueError as error:
            raise ValueError("LZUG_HTTPS_ONLY must be true or false") from error

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: Any) -> frozenset[str]:
        if value is None:
            return frozenset()
        if isinstance(value, (set, frozenset, list, tuple)):
            origins = frozenset(str(origin).strip() for origin in value if str(origin).strip())
        elif isinstance(value, str):
            origins = frozenset(origin.strip() for origin in value.split(",") if origin.strip())
        else:
            raise ValueError(
                "LZUG_CORS_ALLOWED_ORIGINS must contain comma-separated exact HTTP origins"
            )
        for origin in origins:
            try:
                _origin(origin, "LZUG_CORS_ALLOWED_ORIGINS")
            except ValueError as error:
                raise ValueError(
                    "LZUG_CORS_ALLOWED_ORIGINS must contain comma-separated exact HTTP origins"
                ) from error
        return origins


class PersistenceSettings(_Model):
    """Filesystem and SQLite settings for the persistent data boundary."""

    data_dir: Path = Field(Path("/data"), validation_alias="LZUG_DATA_DIR")
    database_path_value: str | None = Field(None, validation_alias="LZUG_DATABASE_PATH")
    database_url: str | None = Field(None, validation_alias="LZUG_DATABASE_URL")
    documents_path: Path | None = Field(None, validation_alias="LZUG_DOCUMENTS_PATH")
    backups_path: Path | None = Field(None, validation_alias="LZUG_BACKUPS_PATH")
    backup_recipient_public_key: str | None = Field(
        None, validation_alias="LZUG_BACKUP_RECIPIENT_PUBLIC_KEY"
    )

    @field_validator("database_path_value", "database_url", mode="before")
    @classmethod
    def empty_database_values_are_unset(cls, value: Any) -> Any:
        return _optional_text(value)

    @field_validator("documents_path", "backups_path", mode="before")
    @classmethod
    def empty_paths_are_unset(cls, value: Any) -> Any:
        return _optional_text(value)

    @field_validator("backup_recipient_public_key", mode="before")
    @classmethod
    def empty_backup_key_is_unset(cls, value: Any) -> Any:
        return _optional_text(value)

    @model_validator(mode="after")
    def database_sources_are_exclusive(self) -> PersistenceSettings:
        if self.database_path_value and self.database_url:
            raise ValueError("Set only one of LZUG_DATABASE_URL and LZUG_DATABASE_PATH")
        return self

    def paths(self) -> tuple[str | Path | None, str | Path | None, str | Path | None, Path]:
        database = self.database_url or self.database_path_value
        return database, self.documents_path, self.backups_path, self.data_dir


class DocumentSettings(_Model):
    """Document upload policy."""

    max_upload_bytes: int = Field(
        10 * 1024 * 1024,
        ge=1024,
        le=100 * 1024 * 1024,
        validation_alias="LZUG_MAX_UPLOAD_BYTES",
    )
    allowed_upload_media_types: frozenset[str] = Field(
        default_factory=lambda: frozenset(
            {"application/pdf", "image/jpeg", "image/png", "text/plain"}
        ),
        validation_alias="LZUG_ALLOWED_UPLOAD_MEDIA_TYPES",
    )

    @field_validator("allowed_upload_media_types", mode="before")
    @classmethod
    def parse_media_types(cls, value: Any) -> frozenset[str]:
        if value is None:
            return frozenset()
        if isinstance(value, (set, frozenset, list, tuple)):
            values = frozenset(str(item).strip().lower() for item in value if str(item).strip())
        elif isinstance(value, str):
            values = frozenset(item.strip().lower() for item in value.split(",") if item.strip())
        else:
            raise ValueError(
                "LZUG_ALLOWED_UPLOAD_MEDIA_TYPES must contain comma-separated exact media types"
            )
        if not values or any(_MEDIA_TYPE.fullmatch(item) is None for item in values):
            raise ValueError(
                "LZUG_ALLOWED_UPLOAD_MEDIA_TYPES must contain comma-separated exact media types"
            )
        return values


class NotificationSettings(_Model):
    """Optional notification channels; secret material is never represented as plain text."""

    notification_sink: str = Field("", validation_alias="LZUG_NOTIFICATION_SINK")
    web_push_vapid_private_key: SecretStr | None = Field(
        None, validation_alias="LZUG_WEB_PUSH_VAPID_PRIVATE_KEY"
    )
    web_push_subject: str | None = Field(None, validation_alias="LZUG_WEB_PUSH_SUBJECT")
    smtp_host: str | None = Field(None, validation_alias="LZUG_SMTP_HOST")
    smtp_port: int = Field(25, ge=1, le=65535, validation_alias="LZUG_SMTP_PORT")
    smtp_from: str = Field("lzug@localhost", validation_alias="LZUG_SMTP_FROM")
    smtp_starttls: bool = Field(False, validation_alias="LZUG_SMTP_STARTTLS")
    smtp_username: str | None = Field(None, validation_alias="LZUG_SMTP_USERNAME")
    smtp_password: SecretStr | None = Field(None, validation_alias="LZUG_SMTP_PASSWORD")

    @field_validator(
        "web_push_vapid_private_key",
        "web_push_subject",
        "smtp_host",
        "smtp_username",
        mode="before",
    )
    @classmethod
    def normalize_optional_values(cls, value: Any) -> Any:
        if isinstance(value, SecretStr):
            return value if value.get_secret_value().strip() else None
        value = _optional_text(value)
        return value

    @field_validator("smtp_password", mode="before")
    @classmethod
    def normalize_secret_password(cls, value: Any) -> Any:
        if isinstance(value, SecretStr):
            return value if value.get_secret_value() else None
        return value.strip() if isinstance(value, str) and value.strip() else None

    @field_validator("notification_sink", mode="before")
    @classmethod
    def validate_sink(cls, value: Any) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in {"", "0", "1", "false", "true", "operator"}:
            raise ValueError("LZUG_NOTIFICATION_SINK must be true, false, or operator")
        return normalized

    @field_validator("smtp_starttls", mode="before")
    @classmethod
    def parse_starttls(cls, value: Any) -> bool:
        try:
            return _boolean(value)
        except ValueError as error:
            raise ValueError("LZUG_SMTP_STARTTLS must be true or false") from error

    @field_validator("web_push_subject")
    @classmethod
    def validate_push_subject(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if not (
            (value.startswith("mailto:") and "@" in value.removeprefix("mailto:"))
            or (parsed.scheme == "https" and parsed.netloc)
        ):
            raise ValueError("Web Push subject must be a mailto or HTTPS URI")
        return value

    @model_validator(mode="after")
    def push_values_are_paired(self) -> NotificationSettings:
        if bool(self.web_push_vapid_private_key) != bool(self.web_push_subject):
            raise ValueError(
                "LZUG_WEB_PUSH_VAPID_PRIVATE_KEY and LZUG_WEB_PUSH_SUBJECT must be set together"
            )
        if self.web_push_vapid_private_key:
            try:
                key = serialization.load_pem_private_key(
                    self.web_push_vapid_private_key.get_secret_value()
                    .replace("\\n", "\n")
                    .encode(),
                    password=None,
                )
            except (TypeError, ValueError) as error:
                raise ValueError("Invalid Web Push VAPID private key") from error
            if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(
                key.curve, ec.SECP256R1
            ):
                raise ValueError("Web Push VAPID key must use P-256")
        return self

    @property
    def sink_enabled(self) -> bool:
        return self.notification_sink in {"1", "true", "operator"}

    @property
    def push_private_key(self) -> str | None:
        return (
            self.web_push_vapid_private_key.get_secret_value()
            if self.web_push_vapid_private_key
            else None
        )

    @property
    def smtp_password_value(self) -> str | None:
        return self.smtp_password.get_secret_value() if self.smtp_password else None


class IntegrationSettings(_Model):
    """Public URL and optional map provider settings."""

    external_url: str | None = Field(None, validation_alias="LZUG_EXTERNAL_URL")
    map_provider: str = Field("off", validation_alias="LZUG_MAP_PROVIDER")
    nominatim_url: str = Field(
        "https://nominatim.openstreetmap.org/search", validation_alias="LZUG_NOMINATIM_URL"
    )
    nominatim_user_agent: str | None = Field(None, validation_alias="LZUG_NOMINATIM_USER_AGENT")
    google_maps_api_key: SecretStr | None = Field(None, validation_alias="LZUG_GOOGLE_MAPS_API_KEY")

    @field_validator("external_url", "nominatim_user_agent", mode="before")
    @classmethod
    def normalize_integration_text(cls, value: Any, info) -> Any:
        value = _optional_text(value)
        return (
            _http_origin_or_empty(value, "LZUG_EXTERNAL_URL")
            if info.field_name == "external_url"
            else value
        )

    @field_validator("map_provider", mode="before")
    @classmethod
    def normalize_provider(cls, value: Any) -> str:
        return str(value or "off").strip().lower()

    @field_validator("google_maps_api_key", mode="before")
    @classmethod
    def normalize_google_key(cls, value: Any) -> Any:
        return _optional_text(value)

    @model_validator(mode="after")
    def validate_provider(self) -> IntegrationSettings:
        if self.map_provider not in {"off", "osm", "google"}:
            raise ValueError("LZUG_MAP_PROVIDER must be off, osm, or google")
        if self.map_provider == "off":
            return self
        parsed = urlsplit(self.nominatim_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("LZUG_NOMINATIM_URL must be an HTTPS endpoint")
        if (
            self.nominatim_user_agent is None
            or "\n" in self.nominatim_user_agent
            or "\r" in self.nominatim_user_agent
        ):
            raise ValueError("LZUG_NOMINATIM_USER_AGENT is required when maps are enabled")
        if self.map_provider == "google" and self.google_maps_api_key is None:
            raise ValueError("LZUG_GOOGLE_MAPS_API_KEY is required for Google Maps mode")
        return self

    @property
    def google_key(self) -> str | None:
        return self.google_maps_api_key.get_secret_value() if self.google_maps_api_key else None


class ServerSettings(_Model):
    host: str = Field("127.0.0.1", validation_alias="LZUG_HOST")
    port: int = Field(8000, ge=1, le=65535, validation_alias="LZUG_PORT")
    static_dir: Path | None = Field(None, validation_alias="LZUG_STATIC_DIR")

    @field_validator("host", mode="before")
    @classmethod
    def host_must_not_be_empty(cls, value: Any) -> str:
        value = str(value or "").strip()
        if not value:
            raise ValueError("LZUG_HOST must not be empty")
        return value

    @field_validator("static_dir", mode="before")
    @classmethod
    def empty_static_dir_is_unset(cls, value: Any) -> Any:
        return _optional_text(value)


class LocalAuthSettings(_Model):
    encryption_key: SecretStr | None = Field(None, validation_alias="LZUG_AUTH_ENCRYPTION_KEY")

    @field_validator("encryption_key", mode="before")
    @classmethod
    def normalize_key(cls, value: Any) -> Any:
        return _optional_text(value)

    @property
    def encryption_key_value(self) -> str | None:
        return self.encryption_key.get_secret_value() if self.encryption_key else None


class CalendarSettings(_Model):
    time_zone: str | None = Field(None, validation_alias="LZUG_CALENDAR_TIMEZONE")
    fallback_time_zone: str = Field("Europe/Berlin", validation_alias="LZUG_TIMEZONE")

    @field_validator("time_zone", "fallback_time_zone", mode="before")
    @classmethod
    def normalize_time_zone(cls, value: Any) -> str | None:
        return _optional_text(value)


class HealthSettings(_Model):
    url: str = Field("http://127.0.0.1:8000/api/health", validation_alias="LZUG_HEALTHCHECK_URL")

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path != "/api/health"
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("LZUG_HEALTHCHECK_URL must use loopback HTTP and /api/health")
        return value


class LifecycleSettings(_Model):
    maintenance: bool = Field(False, validation_alias="LZUG_LIFECYCLE_MAINTENANCE")
    required_external_config: str = Field("", validation_alias="LZUG_REQUIRED_EXTERNAL_CONFIG")

    @field_validator("maintenance", mode="before")
    @classmethod
    def parse_maintenance(cls, value: Any) -> bool:
        try:
            return _boolean(value)
        except ValueError as error:
            raise ValueError("LZUG_LIFECYCLE_MAINTENANCE must be true or false") from error

    @field_validator("required_external_config")
    @classmethod
    def validate_required_names(cls, value: str) -> str:
        names = [item.strip() for item in value.split(",") if item.strip()]
        if any(re.fullmatch(r"LZUG_[A-Z0-9_]+", name) is None for name in names):
            raise ValueError(
                "LZUG_REQUIRED_EXTERNAL_CONFIG must contain comma-separated LZUG names"
            )
        return ",".join(sorted(set(names)))


class ObservabilitySettings(_Model):
    deployment_digest: str = Field("", validation_alias="LZUG_DEPLOYMENT_DIGEST")


class DemoSettings(_Model):
    app_manifest: Path = Field(
        Path("/app/demo-app-manifest.json"), validation_alias="LZUG_DEMO_APP_MANIFEST"
    )
    workspace_capacity: int = Field(
        32, ge=1, le=1000, validation_alias="LZUG_DEMO_WORKSPACE_CAPACITY"
    )
    workspace_dir: Path = Field(
        Path("/tmp/lzug-demo-workspaces"), validation_alias="LZUG_DEMO_WORKSPACE_DIR"
    )

    @field_validator("app_manifest", "workspace_dir", mode="before")
    @classmethod
    def normalize_demo_paths(cls, value: Any) -> Any:
        return _optional_text(value)


class RuntimeSettings(BaseSettings):
    """One explicit assembly for product, demo, E2E, and admin startup paths."""

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=True, extra="ignore")

    security: SecuritySettings = Field(default_factory=SecuritySettings)
    persistence: PersistenceSettings = Field(default_factory=PersistenceSettings)
    documents: DocumentSettings = Field(default_factory=DocumentSettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    integrations: IntegrationSettings = Field(default_factory=IntegrationSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    local_auth: LocalAuthSettings = Field(default_factory=LocalAuthSettings)
    calendar: CalendarSettings = Field(default_factory=CalendarSettings)
    health: HealthSettings = Field(default_factory=HealthSettings)
    lifecycle: LifecycleSettings = Field(default_factory=LifecycleSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    demo: DemoSettings = Field(default_factory=DemoSettings)
    _raw_environment: dict[str, str] = PrivateAttr(default_factory=dict)

    def __init__(self, **data: Any) -> None:
        if data:
            super().__init__(**data)
            return
        loaded = type(self).from_environment()
        super().__init__(**loaded.model_dump())
        self._raw_environment = dict(loaded.environment_values())

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> RuntimeSettings:
        values = dict(os.environ if environment is None else environment)
        settings = cls(
            security=cls._validate(SecuritySettings, values),
            persistence=cls._validate(PersistenceSettings, values),
            documents=cls._validate(DocumentSettings, values),
            notifications=cls._validate(NotificationSettings, values),
            integrations=cls._validate(IntegrationSettings, values),
            server=cls._validate(ServerSettings, values),
            local_auth=cls._validate(LocalAuthSettings, values),
            calendar=cls._validate(CalendarSettings, values),
            health=cls._validate(HealthSettings, values),
            lifecycle=cls._validate(LifecycleSettings, values),
            observability=cls._validate(ObservabilitySettings, values),
            demo=cls._validate(DemoSettings, values),
        )
        settings._raw_environment = values
        return settings

    @staticmethod
    def environment_snapshot() -> Mapping[str, str]:
        """Capture process configuration without making it a service dependency."""
        return dict(os.environ)

    @staticmethod
    def _validate(model: type[_Model], values: Mapping[str, str]) -> _Model:
        try:
            return model.model_validate(values)
        except ValidationError as error:
            raise _safe_validation_error(error) from error

    def environment_values(self) -> Mapping[str, str]:
        """Return the startup snapshot for legacy dynamic-name contracts."""
        return dict(self._raw_environment)
