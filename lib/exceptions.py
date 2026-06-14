from __future__ import annotations


class ScrapekitError(Exception):
    """Base para todos los errores de ScrapeKit."""


class DocumentNotFoundError(ScrapekitError):
    """El documento_id no existe en la fuente (404)."""


class DownloadError(ScrapekitError):
    """Error de red o HTTP al descargar el documento."""


class InvalidContentTypeError(DownloadError):
    """La respuesta no es un PDF."""


class EmptyDocumentError(ScrapekitError):
    """El PDF no contiene texto extraible."""


class ParsingError(ScrapekitError):
    """Fallo al parsear el PDF."""
