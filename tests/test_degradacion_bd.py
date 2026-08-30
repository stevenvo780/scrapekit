"""La base caida NO debe devolver 500.

Contexto: el 2026-08-30 Neon agoto la cuota de computo y `nomos.stevenvallejo.com`
sirvio `500 Internal Server Error` en texto plano durante horas. Un 500 le dice al
rastreador que el fallo es nuestro y sin plazo; lo correcto es 503 + Retry-After.

Los dos controles importan por igual:
  - NEGATIVO: con la base inalcanzable, nada devuelve 500.
  - POSITIVO: con la base sana, nada degrada ni muestra el aviso.
Una bateria que solo comprueba el modo de fallo no dice si el camino bueno sigue vivo.
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lib.database as dbmod  # noqa: E402
from api.index import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

# Puerto sin servicio: mismo tipo de fallo que "Neon rechaza la conexion".
URL_INALCANZABLE = "postgresql+asyncpg://u:p@127.0.0.1:59999/nada"


def _fijar_engine(url: str):
    """Sustituye la fabrica de engine (es especifica de Postgres: pasa
    connect_args de ssl, que sqlite rechaza). Lo que se prueba aqui es la
    degradacion de api/index.py, no la fabrica."""
    engine = create_async_engine(url, future=True)
    dbmod._get_engine = lambda _u, _e=engine: _e
    return engine


@pytest.fixture
def caida(monkeypatch):
    original = dbmod._get_engine
    _fijar_engine(URL_INALCANZABLE)
    yield TestClient(app, raise_server_exceptions=False)
    dbmod._get_engine = original


@pytest.fixture
def sana():
    original = dbmod._get_engine
    engine = _fijar_engine(f"sqlite+aiosqlite:///{tempfile.mktemp(suffix='.db')}")

    async def crear() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

    asyncio.run(crear())
    yield TestClient(app, raise_server_exceptions=False)
    dbmod._get_engine = original


# --- NEGATIVO: la base no responde -------------------------------------------

def test_ninguna_ruta_devuelve_500(caida):
    for ruta in ("/", "/health", "/api/documents", "/sitemap.xml", "/api/sources", "/robots.txt"):
        assert caida.get(ruta).status_code != 500, ruta


def test_health_reporta_la_caida_en_vez_de_afirmar_salud(caida):
    r = caida.get("/health")
    assert r.status_code == 503
    assert r.json()["database"] == "unavailable"
    assert r.headers["retry-after"] == "300"


def test_home_sigue_sirviendo_pagina_con_aviso(caida):
    r = caida.get("/")
    assert r.status_code == 503
    assert r.headers["retry-after"] == "300"
    assert "text/html" in r.headers["content-type"]
    assert 'id="documents-unavailable"' in r.text


def test_api_devuelve_503_json(caida):
    r = caida.get("/api/documents")
    assert r.status_code == 503
    assert r.json()["error"] == "database_unavailable"


def test_sitemap_sigue_siendo_valido_con_la_raiz(caida):
    # Un 503 aqui hace que el rastreador descarte el sitemap entero.
    r = caida.get("/sitemap.xml")
    assert r.status_code == 200
    assert "nomos.stevenvallejo.com/</loc>" in r.text


# --- POSITIVO: la base responde ----------------------------------------------

def test_camino_sano_no_degrada(sana):
    r = sana.get("/health")
    assert r.status_code == 200 and r.json()["database"] == "ok"

    r = sana.get("/")
    assert r.status_code == 200
    assert 'id="documents-unavailable"' not in r.text
    assert '<p id="documents-empty"' in r.text

    assert sana.get("/api/documents").status_code == 200
    assert sana.get("/sitemap.xml").status_code == 200
