from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracion central de ScrapeKit Colombia."""

    # Postgres Neon
    database_url: str = Field(
        ...,
        description="Cadena de conexion pooled (asyncpg) para runtime.",
        alias="SCRAPEKIT_DATABASE_URL",
    )
    direct_url: Optional[str] = Field(
        None,
        description="Cadena de conexion directa (sin pool) para migraciones DDL.",
        alias="SCRAPEKIT_DIRECT_URL",
    )

    # Autenticacion basica
    api_key: str = Field(
        "dev-insecure-key",
        description="API key requerida en cabecera X-API-Key para endpoints de escritura.",
        alias="SCRAPEKIT_API_KEY",
    )

    # Fuente predeterminada
    default_source: str = Field(
        "colombia_camara",
        description="Adaptador fuente por defecto.",
        alias="SCRAPEKIT_DEFAULT_SOURCE",
    )

    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        populate_by_name=True,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_cache() -> None:
    get_settings.cache_clear()
