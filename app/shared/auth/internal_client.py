import requests

from app.shared.auth.jwt_generator import generar_jwt_interno
from app.shared.config import settings

HEADER_NAME = "X-Internal-Token"


def _headers(uid: str) -> dict:
    return {HEADER_NAME: generar_jwt_interno(uid)}


def obtener_autores(uid: str) -> list[dict]:
    """Bulk liviano de autores (id + nombre, entre otros campos) para el
    filtro inicial del LLM. GET /api/autores ya devuelve todo el detalle;
    se toma solo lo necesario al armar el prompt."""
    url = f"{settings.backend_java_url}/api/autores"
    respuesta = requests.get(url, headers=_headers(uid), timeout=5)
    respuesta.raise_for_status()
    return respuesta.json()


def obtener_autor_detalle(uid: str, autor_id: int) -> dict:
    """Detalle completo de un autor puntual, para la desambiguación por
    datos duros (fechas, país) cuando el filtro LLM devuelve 'dudoso'."""
    url = f"{settings.backend_java_url}/api/autores/{autor_id}"
    respuesta = requests.get(url, headers=_headers(uid), timeout=5)
    respuesta.raise_for_status()
    return respuesta.json()


def obtener_generos(uid: str) -> list[dict]:
    """Lista completa de géneros existentes, para el matching semántico
    de las categorías crudas de Google Books."""
    url = f"{settings.backend_java_url}/api/generos"
    respuesta = requests.get(url, headers=_headers(uid), timeout=5)
    respuesta.raise_for_status()
    return respuesta.json()


def obtener_paises(uid: str) -> list[dict]:
    """Lista completa de países existentes, para el matching semántico
    del país del autor (con normalización a nivel de país soberano)."""
    url = f"{settings.backend_java_url}/api/paises"
    respuesta = requests.get(url, headers=_headers(uid), timeout=5)
    respuesta.raise_for_status()
    return respuesta.json()