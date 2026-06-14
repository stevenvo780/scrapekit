#!/usr/bin/env python3
"""
index_batch.py - Indexador batch para ScrapeKit Colombia.

Ejecutar desde cualquier maquina con acceso a Neon:
  python scripts/index_batch.py --source colombia_camara --start 1 --end 100

Variables de entorno requeridas (mismas que .env.local o exportadas):
  SCRAPEKIT_DATABASE_URL
  SCRAPEKIT_API_KEY (solo para el modo --api, ver abajo)

Modos:
  --mode direct   : Llama al pipeline directamente (necesita SCRAPEKIT_DATABASE_URL).
  --mode api      : Llama a POST /api/documents con X-API-Key (para indexar via deploy).

Ejemplo via API (GitHub Actions / cron):
  python scripts/index_batch.py \\
    --mode api --base-url https://scrapekit.vercel.app \\
    --source colombia_camara --ids 101,202,303
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Permite importar lib/ cuando se ejecuta desde la raiz del proyecto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def run_direct(source: str, ids: list[str]) -> None:
    from lib.pipeline import ProcessingPipeline
    pipeline = ProcessingPipeline()
    for doc_id in ids:
        try:
            print(f"[{source}] Procesando {doc_id}...", end=" ")
            await pipeline.process(doc_id, source)
            print("OK")
        except Exception as exc:
            print(f"ERROR: {exc}")


async def run_api(base_url: str, api_key: str, source: str, ids: list[str]) -> None:
    import httpx
    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        for doc_id in ids:
            try:
                print(f"[{source}] POST {doc_id}...", end=" ")
                resp = await client.post(
                    "/api/documents",
                    json={"document_id": doc_id, "source_key": source},
                    headers={"X-API-Key": api_key},
                )
                if resp.status_code == 200:
                    print("OK")
                else:
                    print(f"HTTP {resp.status_code}: {resp.text[:120]}")
            except Exception as exc:
                print(f"ERROR: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Indexador batch ScrapeKit Colombia")
    parser.add_argument("--source", default="colombia_camara", help="Clave del adaptador fuente")
    parser.add_argument("--start", type=int, help="ID inicial (modo rango)")
    parser.add_argument("--end", type=int, help="ID final (modo rango)")
    parser.add_argument("--ids", help="Lista de IDs separados por coma")
    parser.add_argument("--mode", choices=["direct", "api"], default="direct")
    parser.add_argument("--base-url", default="http://localhost:8000", help="URL base (modo api)")
    args = parser.parse_args()

    if args.ids:
        ids = [i.strip() for i in args.ids.split(",") if i.strip()]
    elif args.start is not None and args.end is not None:
        ids = [str(i) for i in range(args.start, args.end + 1)]
    else:
        parser.error("Especifica --ids o --start/--end")

    print(f"Fuente: {args.source} | Modo: {args.mode} | Total IDs: {len(ids)}")

    if args.mode == "direct":
        asyncio.run(run_direct(args.source, ids))
    else:
        api_key = os.environ.get("SCRAPEKIT_API_KEY", "")
        if not api_key:
            sys.exit("ERROR: SCRAPEKIT_API_KEY no definida para modo api")
        asyncio.run(run_api(args.base_url, api_key, args.source, ids))


if __name__ == "__main__":
    main()
