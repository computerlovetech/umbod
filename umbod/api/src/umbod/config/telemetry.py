from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from umbod.config import defaults
from umbod.config.app import OtlpReceiverConfig, RuntimeConfig, TelemetryAnalyticsConfig


class TelemetryAppConfig(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    runtime: RuntimeConfig
    otlp_receiver: OtlpReceiverConfig
    telemetry_analytics: TelemetryAnalyticsConfig

    @model_validator(mode="after")
    def validate_receiver_security(self) -> "TelemetryAppConfig":
        if self.runtime.profile not in ("local", "production"):
            raise ValueError("UMBOD_PROFILE must be local or production")
        receiver = self.otlp_receiver
        if receiver.allow_unauthenticated and self.runtime.profile != "local":
            raise ValueError(
                "UMBOD_OTLP_ALLOW_UNAUTHENTICATED requires UMBOD_PROFILE=local"
            )
        if receiver.enabled and not receiver.allow_unauthenticated:
            if not receiver.bearer_token.strip():
                raise ValueError("UMBOD_OTLP_BEARER_TOKEN is required")
            if any(character.isspace() for character in receiver.bearer_token):
                raise ValueError("UMBOD_OTLP_BEARER_TOKEN must not contain whitespace")
        return self


class TelemetrySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="UMBOD_",
        env_file=".env",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_name: str = defaults.APP_NAME
    log_level: str = defaults.LOG_LEVEL
    profile: Literal["local", "production"] = "local"
    otlp_enabled: bool = False
    otlp_bearer_token: str = Field(default="", repr=False)
    otlp_allow_unauthenticated: bool = False
    otlp_max_request_bytes: int = Field(default=defaults.OTLP_MAX_REQUEST_BYTES, gt=0)
    otlp_host: str = "0.0.0.0"
    otlp_port: int = Field(default=4318, ge=1, le=65535)
    telemetry_analytics_enabled: bool = False
    telemetry_analytics_sqlite_path: str = defaults.TELEMETRY_ANALYTICS_SQLITE_PATH


def load_telemetry_app_config(env_file: str) -> TelemetryAppConfig:
    settings = TelemetrySettings(_env_file=env_file)
    return TelemetryAppConfig(
        runtime=RuntimeConfig(
            app_name=settings.app_name,
            log_level=settings.log_level,
            profile=settings.profile,
        ),
        otlp_receiver=OtlpReceiverConfig(
            enabled=settings.otlp_enabled,
            bearer_token=settings.otlp_bearer_token,
            allow_unauthenticated=settings.otlp_allow_unauthenticated,
            max_request_bytes=settings.otlp_max_request_bytes,
            host=settings.otlp_host,
            port=settings.otlp_port,
        ),
        telemetry_analytics=TelemetryAnalyticsConfig(
            enabled=settings.telemetry_analytics_enabled,
            sqlite_path=settings.telemetry_analytics_sqlite_path,
        ),
    )
