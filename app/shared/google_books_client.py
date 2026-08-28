import logging
import requests 

from app.shared.config import settings 

logger = logging.getLogger(__name__)

GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"


def buscar_libros_externos(query: str, max_results: int = 20, start_index: int = 0) -> dict:
    """
    Busca libros en la API pública de Google Books y extrae los campos
    útiles para mapear con nuestras entidades (Libro, Autor, Genero).

    start_index es el offset de paginación que espera Google Books
    (0-based): para la página N con tamaño de página P, el caller debe
    pasar start_index = (N - 1) * P.

    Devuelve un dict {"items": [...], "total_items": int} en vez de una
    lista plana, porque el caller necesita el total para poder calcular
    cuántas páginas hay disponibles (paginación clásica, no scroll
    infinito). total_items es el total real que reporta Google Books
    para la query completa, no la cantidad de items en esta página.
    """
    params = {
        "q": query,
        "maxResults": max_results,
        "startIndex": start_index,
        "key": settings.google_books_api_key,
    }

    try:
        respuesta = requests.get(GOOGLE_BOOKS_URL, params=params, timeout=5)
        respuesta.raise_for_status()

        data = respuesta.json()
        items = data.get("items", [])
        total_items = data.get("totalItems", 0)

        if not items:
            return {"items": [], "total_items": total_items}

        resultados_limpios = []
        for item in items:
            volume_info = item.get("volumeInfo", {})

            # Extraer ISBN (si existe, buscamos preferiblemente ISBN_13 o ISBN_10)
            isbn = None
            for identifier in volume_info.get("industryIdentifiers", []):
                if identifier.get("type") in ["ISBN_13", "ISBN_10"]:
                    isbn = identifier.get("identifier")
                    break

            # Extraer año de publicación de la fecha (ej: "2020-05-12" -> 2020)
            published_date = volume_info.get("publishedDate", "")
            anio_publicacion = None
            if published_date:
                try:
                    anio_publicacion = int(published_date.split("-")[0])
                except (ValueError, IndexError):
                    anio_publicacion = None

            # Portada: preferimos resolución mayor a thumbnail si está disponible,
            # y forzamos https (Google Books a veces devuelve http)
            image_links = volume_info.get("imageLinks", {})
            portada_url = (
                image_links.get("small")
                or image_links.get("medium")
                or image_links.get("thumbnail")
                or image_links.get("smallThumbnail")
                or ""
            )
            if portada_url:
                portada_url = portada_url.replace("http://", "https://")

            libro_info = {
                "google_id": item.get("id"),
                "titulo": volume_info.get("title", "Sin título"),
                # Lista cruda: puede venir vacía, con uno, o con varios autores.
                # El criterio de qué hacer con múltiples autores se decide en el mapeo a DTO.
                "autores": volume_info.get("authors", []),
                # None si no viene, en vez de asumir "es" como si fuera un dato real
                "idioma": volume_info.get("language"),
                "categorias": volume_info.get("categories", []),
                "anio_publicacion": anio_publicacion,
                "descripcion": volume_info.get("description", ""),
                "portada_url": portada_url,
                "isbn": isbn,
            }
            resultados_limpios.append(libro_info)

        return {"items": resultados_limpios, "total_items": total_items}

    except requests.RequestException as e:
        logger.error(f"Error consultando Google Books API (query='{query}'): {e}")
        return {"items": [], "total_items": 0}