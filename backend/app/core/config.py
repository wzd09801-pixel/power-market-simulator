from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Power Market Simulator"
    app_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"
    database_url: str = Field(
        default="postgresql+psycopg://power:power@localhost:5432/power_market",
        validation_alias="DATABASE_URL",
    )
    open_meteo_forecast_url: str = Field(
        default="https://api.open-meteo.com/v1/forecast",
        validation_alias="OPEN_METEO_FORECAST_URL",
    )
    open_meteo_timeout_seconds: float = Field(
        default=10.0,
        gt=0,
        validation_alias="OPEN_METEO_TIMEOUT_SECONDS",
    )
    open_meteo_max_retries: int = Field(
        default=2,
        ge=0,
        le=5,
        validation_alias="OPEN_METEO_MAX_RETRIES",
    )
    open_meteo_retry_backoff_seconds: float = Field(
        default=0.25,
        ge=0,
        validation_alias="OPEN_METEO_RETRY_BACKOFF_SECONDS",
    )
    market_health_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        validation_alias="MARKET_HEALTH_TIMEOUT_SECONDS",
    )
    market_health_max_retries: int = Field(
        default=1,
        ge=0,
        le=3,
        validation_alias="MARKET_HEALTH_MAX_RETRIES",
    )
    market_health_retry_backoff_seconds: float = Field(
        default=0.25,
        ge=0,
        validation_alias="MARKET_HEALTH_RETRY_BACKOFF_SECONDS",
    )
    market_health_min_interval_seconds: float = Field(
        default=30.0,
        gt=0,
        validation_alias="MARKET_HEALTH_MIN_INTERVAL_SECONDS",
    )
    bench_dispatch_timeout_seconds: float = Field(
        default=20.0,
        gt=0,
        validation_alias="BENCH_DISPATCH_TIMEOUT_SECONDS",
    )
    bench_dispatch_max_retries: int = Field(
        default=2,
        ge=0,
        le=5,
        validation_alias="BENCH_DISPATCH_MAX_RETRIES",
    )
    bench_dispatch_retry_backoff_seconds: float = Field(
        default=0.5,
        ge=0,
        validation_alias="BENCH_DISPATCH_RETRY_BACKOFF_SECONDS",
    )
    minio_endpoint: str = Field(
        default="http://localhost:9000",
        validation_alias="MINIO_ENDPOINT",
    )
    minio_access_key: str = Field(default="minioadmin", validation_alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(default="minioadmin", validation_alias="MINIO_SECRET_KEY")
    minio_bucket: str = Field(default="power-market-raw", validation_alias="MINIO_BUCKET")
    prefect_api_url: str = Field(
        default="http://localhost:4200/api",
        validation_alias="PREFECT_API_URL",
    )
    prefect_work_pool: str = Field(
        default="local-workstation",
        validation_alias="PREFECT_WORK_POOL",
    )
    operation_worker_poll_seconds: float = Field(
        default=2.0,
        gt=0,
        validation_alias="OPERATION_WORKER_POLL_SECONDS",
    )
    operation_worker_lease_seconds: int = Field(
        default=300,
        gt=0,
        validation_alias="OPERATION_WORKER_LEASE_SECONDS",
    )
    operation_worker_retry_delay_seconds: int = Field(
        default=60,
        ge=0,
        validation_alias="OPERATION_WORKER_RETRY_DELAY_SECONDS",
    )
    embedding_service_url: str = Field(
        default="http://localhost:8090",
        validation_alias="EMBEDDING_SERVICE_URL",
    )
    embedding_model: str = Field(default="BAAI/bge-m3", validation_alias="EMBEDDING_MODEL")
    reranker_model: str = Field(
        default="BAAI/bge-reranker-v2-m3",
        validation_alias="RERANKER_MODEL",
    )
    deepseek_api_key: SecretStr | None = Field(default=None, validation_alias="DEEPSEEK_API_KEY")
    deepseek_api_url: str = Field(
        default="https://api.deepseek.com/chat/completions",
        validation_alias="DEEPSEEK_API_URL",
    )
    deepseek_default_model: str = Field(
        default="deepseek-v4-flash",
        validation_alias="DEEPSEEK_DEFAULT_MODEL",
    )
    deepseek_deep_analysis_model: str = Field(
        default="deepseek-v4-pro",
        validation_alias="DEEPSEEK_DEEP_ANALYSIS_MODEL",
    )
    deepseek_timeout_seconds: float = Field(
        default=30,
        gt=0,
        validation_alias="DEEPSEEK_TIMEOUT_SECONDS",
    )
    deepseek_max_retries: int = Field(
        default=2,
        ge=0,
        le=5,
        validation_alias="DEEPSEEK_MAX_RETRIES",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
