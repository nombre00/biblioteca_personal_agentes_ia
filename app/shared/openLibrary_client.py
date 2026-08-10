import logging
import re
import requests

logger = logging.getLogger(__name__)

OPENLIBRARY_ISBN_URL = "https://openlibrary.org/isbn/{isbn}.json"
OPENLIBRARY_WORK_URL = "https://openlibrary.org/works/{work_id}.json"
OPENLIBRARY_COVER_URL = "https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"

# OpenLibrary no exige API key, pero pide identificar el proyecto con un
# User-Agent (mismo criterio que ya aplicás con Wikimedia en wikipedia_client.py).
HEADERS = {"User-Agent": "Biblioteca/1.0 (proyecto personal; contacto: spleo1988@gmail.com)"}


def _obtener_edition(isbn: str) -> dict | None:
    """Trae el registro de Edition (la impresión específica con ese ISBN).
    Devuelve None si OpenLibrary no tiene ese ISBN (404), sin lanzar excepción."""
    url = OPENLIBRARY_ISBN_URL.format(isbn=isbn)
    respuesta = requests.get(url, headers=HEADERS, timeout=5)

    if respuesta.status_code == 404:
        return None

    respuesta.raise_for_status()
    return respuesta.json()


def _obtener_work_id(edition_data: dict) -> str | None:
    """Extrae el ID del Work asociado a una Edition (ej. '/works/OL27258W'
    -> 'OL27258W'). Una Edition puede no tener Work vinculado en casos
    raros de catalogación incompleta."""
    works = edition_data.get("works") or []
    if not works:
        return None

    work_key = works[0].get("key")
    if not work_key:
        return None

    return work_key.rsplit("/", 1)[-1]


def _obtener_work(work_id: str) -> dict | None:
    """Trae el registro de Work (la obra abstracta, independiente de
    ediciones). Devuelve None si no se encuentra (404)."""
    url = OPENLIBRARY_WORK_URL.format(work_id=work_id)
    respuesta = requests.get(url, headers=HEADERS, timeout=5)

    if respuesta.status_code == 404:
        return None

    respuesta.raise_for_status()
    return respuesta.json()


def _extraer_anio_publicacion_original(work_data: dict) -> int | None:
    """first_publish_date en OpenLibrary viene como texto libre, sin formato
    fijo ('1866', 'Jan 1866', '1866-01-01', etc. según qué tan completo esté
    el registro). En vez de intentar parsear todos los formatos posibles, se
    extrae el primer número de 4 dígitos que aparezca — en la práctica
    siempre es el año."""
    fecha_texto = work_data.get("first_publish_date")
    if not fecha_texto:
        return None

    match = re.search(r"\d{4}", fecha_texto)
    if not match:
        return None

    return int(match.group())


def _existe_portada(isbn: str) -> bool:
    """Verifica sin descargar la imagen completa si existe una portada real
    para este ISBN. Por defecto, la Covers API de OpenLibrary devuelve un
    placeholder en blanco (GIF 1x1) cuando no tiene la portada, en vez de un
    404 — 'default=false' cambia ese comportamiento para poder distinguir
    'no hay portada' de 'sí hay portada' de forma inequívoca."""
    url = OPENLIBRARY_COVER_URL.format(isbn=isbn)
    try:
        respuesta = requests.head(
            url, params={"default": "false"}, headers=HEADERS, timeout=5, allow_redirects=True
        )
        return respuesta.status_code == 200
    except requests.RequestException as e:
        logger.error(f"Error verificando portada OpenLibrary para ISBN '{isbn}': {e}")
        return False


def obtener_datos_estructurados(isbn: str | None) -> dict:
    """
    Dado un ISBN, intenta mejorar portada y año de publicación original
    usando OpenLibrary (Edition -> Work). A diferencia de Google Books, que
    solo conoce la edición puntual que indexó, OpenLibrary separa la obra
    abstracta (Work, con su fecha de publicación original) de sus ediciones
    específicas (Edition, con la fecha de esa impresión en particular).

    Devuelve:
    {
        "portada_url": str | None,                # tamaño grande (L), solo si existe
                                                    # realmente (no el placeholder en blanco)
        "anio_publicacion_original": int | None,   # first_publish_date del Work,
                                                    # nunca la fecha de la edición
    }

    Tolerante a fallos: si no hay ISBN, no se encuentra la edición, no tiene
    Work asociado, o falla la red, devuelve los campos en None sin lanzar
    excepción — mismo criterio que wikipedia_client.py. La decisión de qué
    hacer con esos None (mantener el dato de Google Books o dejarlo vacío)
    es responsabilidad del llamador, no de este cliente.
    """
    resultado_vacio = {"portada_url": None, "anio_publicacion_original": None}

    if not isbn:
        return resultado_vacio

    try:
        portada_url = OPENLIBRARY_COVER_URL.format(isbn=isbn) if _existe_portada(isbn) else None

        edition_data = _obtener_edition(isbn)
        if not edition_data:
            return {**resultado_vacio, "portada_url": portada_url}

        work_id = _obtener_work_id(edition_data)
        if not work_id:
            return {**resultado_vacio, "portada_url": portada_url}

        work_data = _obtener_work(work_id)
        if not work_data:
            return {**resultado_vacio, "portada_url": portada_url}

        anio_publicacion_original = _extraer_anio_publicacion_original(work_data)

        return {
            "portada_url": portada_url,
            "anio_publicacion_original": anio_publicacion_original,
        }

    except requests.RequestException as e:
        logger.error(f"Error consultando OpenLibrary para ISBN '{isbn}': {e}")
        return resultado_vacio