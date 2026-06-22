"""
Adaptadores de fuente para Nómos · Mouseîon.

Cada adaptador sabe cómo construir la URL de descarga de un documento
a partir de un document_id. La abstracción permite agregar nuevas fuentes
sin tocar el pipeline principal.

Fuentes disponibles:
  - colombia_camara     : Cámara de Representantes de Colombia
  - colombia_senado     : Senado de la República de Colombia
  - dominicana_camara   : Cámara de Diputados, República Dominicana (fuente original)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(slots=True)
class SourceAdapter:
    key: str
    label: str
    base_url: str
    query_param: str
    country: str
    institution: str

    def build_url(self, document_id: str) -> str:
        import httpx
        return str(httpx.URL(self.base_url, params={self.query_param: document_id}))


# Registro de adaptadores disponibles
ADAPTERS: Dict[str, SourceAdapter] = {
    "colombia_camara": SourceAdapter(
        key="colombia_camara",
        label="Cámara de Representantes de Colombia",
        # El portal de la Cámara expone PDFs de proyectos de ley y actas vía este endpoint.
        # Formato: /documentos/descarga/{document_id} (redirige al PDF real).
        base_url="https://www.camara.gov.co/documentos/descarga",
        query_param="id",
        country="Colombia",
        institution="Cámara de Representantes",
    ),
    "colombia_senado": SourceAdapter(
        key="colombia_senado",
        label="Senado de la República de Colombia",
        # Portal Senado: endpoint de expedientes y actas.
        base_url="https://www.senado.gov.co/index.php/component/search",
        query_param="docId",
        country="Colombia",
        institution="Senado de la República",
    ),
    "dominicana_camara": SourceAdapter(
        key="dominicana_camara",
        label="Cámara de Diputados, República Dominicana",
        base_url="https://s-sil.camaradediputados.gob.do:8095/ReportesGenerales/VerDocumento",
        query_param="documentoId",
        country="República Dominicana",
        institution="Cámara de Diputados",
    ),
}


def get_adapter(key: str) -> SourceAdapter:
    adapter = ADAPTERS.get(key)
    if adapter is None:
        valid = ", ".join(ADAPTERS.keys())
        raise ValueError(f"Adaptador '{key}' no existe. Opciones validas: {valid}")
    return adapter


def list_adapters() -> list[dict]:
    return [
        {
            "key": a.key,
            "label": a.label,
            "country": a.country,
            "institution": a.institution,
        }
        for a in ADAPTERS.values()
    ]
