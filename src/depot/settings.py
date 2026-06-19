"""Load and validate settings.yaml into a typed, cached Settings model."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
_SETTINGS_FILE = _CONFIG_DIR / "settings.yaml"
_REGIONS_DIR = _CONFIG_DIR / "regions"


class PathsConfig(BaseModel):
    files_root: str
    inbox: str
    runs: str


class MailDbConfig(BaseModel):
    server_env: str
    default_server: str
    database: str
    process_name: str


class IcmsDbConfig(BaseModel):
    server_env: str
    default_server: str
    database: str
    driver: str
    chunk_size: int = 1000


class InsertDbConfig(BaseModel):
    database: str


class RedisConfig(BaseModel):
    url_env: str
    default_url: str
    dedup_ttl_days: int = 30


class CeleryConfig(BaseModel):
    broker_env: str
    result_env: str


class AttachmentApiConfig(BaseModel):
    base_url: str
    skip_if_name_contains: list[str] = Field(default_factory=list)
    keep_only_if_name_contains: list[str] = Field(default_factory=list)


class DetectionConfig(BaseModel):
    min_header_cells: int = 3
    title_scan_rows: int = 2


class BatchConfig(BaseModel):
    workbook_concurrency: int = 8


class Settings(BaseModel):
    paths: PathsConfig
    mail_db: MailDbConfig
    icms_db: IcmsDbConfig
    insert_db: InsertDbConfig
    redis: RedisConfig
    celery: CeleryConfig
    attachment_api: AttachmentApiConfig
    detection: DetectionConfig
    batch: BatchConfig
    gate_in_status_valid: list[int]
    relevant_status_ids: list[int]

    @property
    def regions_dir(self) -> Path:
        return _REGIONS_DIR

    def mail_server(self) -> str:
        return os.environ.get(self.mail_db.server_env) or self.mail_db.default_server

    def icms_server(self) -> str:
        return os.environ.get(self.icms_db.server_env) or self.icms_db.default_server

    def redis_url(self) -> str:
        return os.environ.get(self.redis.url_env) or self.redis.default_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings.yaml once, validate it, and cache the result."""
    if not _SETTINGS_FILE.exists():
        raise FileNotFoundError(f"settings.yaml not found at {_SETTINGS_FILE}")
    with _SETTINGS_FILE.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return Settings.model_validate(raw)
