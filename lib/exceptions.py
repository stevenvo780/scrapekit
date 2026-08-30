from __future__ import annotations


class ScrapekitError(Exception):
    """Base para todos los errores de Nómos."""


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


class DatabaseUnavailableError(ScrapekitError):
    """La base de datos no acepta conexiones (cuota agotada, caida, red).

    Es TEMPORAL: se traduce a 503 + Retry-After, nunca a 500. Un 500 le dice al
    rastreador que el fallo es nuestro y permanente; un 503 le dice que vuelva.
    """
