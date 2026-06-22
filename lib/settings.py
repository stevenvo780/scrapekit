from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuración central de Nómos · Mouseîon.

    Env vars leidas (con prefijo SCRAPEKIT_):
      SCRAPEKIT_DATABASE_URL  - Neon pooled URL (runtime)
      SCRAPEKIT_DIRECT_URL    - Neon direct URL (migraciones)
      SCRAPEKIT_API_KEY       - API key para endpoints de escritura
      SCRAPEKIT_DEFAULT_SOURCE - Adaptador por defecto
    """

    # env_prefix hace que pydantic-settings lea SCRAPEKIT_DATABASE_URL
    # como el campo `database_url`, etc.
    database_url: str = Field(
        default="",
        description="Cadena de conexion pooled (asyncpg) para runtime.",
    )
    direct_url: Optional[str] = Field(
        default=None,
        description="Cadena de conexion directa (sin pool) para migraciones DDL.",
    )
    api_key: str = Field(
        default="dev-insecure-key",
        description="API key requerida en cabecera X-API-Key para endpoints de escritura.",
    )
    default_source: str = Field(
        default="colombia_camara",
        description="Adaptador fuente por defecto.",
    )

    model_config = SettingsConfigDict(
        env_prefix="SCRAPEKIT_",
        env_file=".env.local",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_cache() -> None:
    get_settings.cache_clear()
