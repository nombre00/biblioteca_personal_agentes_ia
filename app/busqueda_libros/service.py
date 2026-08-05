"""
Orquestación de búsqueda-libros: los tres pasos del flujo de importación
externa vía Google Books (buscar -> resolver -> importar).

- buscar_libros: wrapper fino sobre el provider de Google Books.
- resolver_libro: el núcleo del entity resolution — filtro LLM de autor,
  desambiguación por datos duros de Wikidata cuando corresponde, y matching
  semántico de género/país.
- importar_libro: reenvía el payload final a Java (endpoint pendiente del
  lado Java, ver contexto de sesión — esto queda listo para cuando exista).

Nota de alcance: el manejo de excepciones acá es básico (se deja que las
excepciones de requests/Gemini se propaguen); un manejo más prolijo queda
pendiente para más adelante, igual que en el resto de agentes-ia.
"""

import requests
from datetime import date

from app.shared.config import settings
from app.shared.auth.jwt_generator import generar_jwt_interno
from app.shared.llm.gemini_client import gemini_client
from app.shared import internal_client, wikipedia_client

from app.shared.google_books_client import google_books
from app.busqueda_libros.prompt import (
    construir_prompt_clasificar_autor,
    construir_prompt_matchear_genero,
    construir_prompt_matchear_pais,
)
from app.busqueda_libros.schema import (
    BusquedaLibroRequest,
    LibroExternoResponse,
    ResolverLibroRequest,
    ResolverLibroResponse,
    ImportarLibroRequest,
    PaisCreateSchema,
    GeneroCreateSchema,
    AutorCreateSchema,
    PaisResolucion,
    PaisResolucionExistente,
    PaisResolucionNueva,
    GeneroResolucion,
    GeneroResolucionExistente,
    GeneroResolucionNueva,
    AutorResolucion,
    AutorResolucionExistente,
    AutorResolucionNueva,
    AutorResolucionPendiente,
)

MARGEN_ANIOS_AUTOR = 20


# ==========================================
# 1. Búsqueda (paso 1: /buscar)
# ==========================================

def buscar_libros(request: BusquedaLibroRequest) -> list[LibroExternoResponse]:
    """Wrapper fino sobre el provider — mapea directo a LibroExternoResponse,
    los campos ya calzan uno a uno con lo que devuelve google_books.py."""
    resultados_crudos = google_books.buscar_libros_externos(
        request.query, request.max_results
    )
    return [LibroExternoResponse(**r) for r in resultados_crudos]


# ==========================================
# 2. Resolución (paso 2: /resolver)
# ==========================================

def resolver_libro(uid: str, request: ResolverLibroRequest) -> ResolverLibroResponse:
    """Orquesta la resolución completa: autor (dos etapas si hace falta) y
    géneros (uno a uno). País se resuelve solo como parte de la construcción
    de un autor nuevo, no tiene paso propio a este nivel."""

    autor_resolucion = _resolver_autor(uid, request)
    generos_resolucion = _resolver_generos(uid, request.categorias)

    return ResolverLibroResponse(
        titulo=request.titulo,
        anio_publicacion=request.anio_publicacion,
        descripcion=request.descripcion,
        portada_url=request.portada_url,
        isbn=request.isbn,
        autor=autor_resolucion,
        generos=generos_resolucion,
    )


def _resolver_autor(uid: str, request: ResolverLibroRequest) -> AutorResolucion:
    autores_existentes = internal_client.obtener_autores(uid)
    autores_bulk = [{"id": a["id"], "nombre": a["nombre"]} for a in autores_existentes]

    prompt = construir_prompt_clasificar_autor(request.autor_nombre, autores_bulk)
    resultado = gemini_client.generar_json(prompt)

    if resultado["resultado"] == "nuevo":
        datos_wikidata = wikipedia_client.obtener_datos_estructurados(request.autor_nombre)
        datos = _construir_autor_nuevo(uid, request.autor_nombre, request.idioma, datos_wikidata)
        return AutorResolucionNueva(datos=datos)

    autor_id = resultado["autor_id"]
    nombre_match = next(
        (a["nombre"] for a in autores_bulk if a["id"] == autor_id), request.autor_nombre
    )

    if resultado["resultado"] == "existente":
        return AutorResolucionExistente(autor_id=autor_id, nombre=nombre_match)

    # "dudoso" -> desambiguación por datos duros contra Wikidata
    return _desambiguar_autor(uid, autor_id, nombre_match, request)


def _desambiguar_autor(
    uid: str, autor_id: int, nombre_candidato: str, request: ResolverLibroRequest
) -> AutorResolucion:
    autor_existente = internal_client.obtener_autor_detalle(uid, autor_id)
    datos_wikidata = wikipedia_client.obtener_datos_estructurados(request.autor_nombre)

    coincide_nacimiento = _fechas_coinciden(
        autor_existente.get("fechaNacimiento"),
        autor_existente.get("anioNacimientoAprox"),
        datos_wikidata["fecha_nacimiento"],
        datos_wikidata["anio_nacimiento_aprox"],
    )
    coincide_defuncion = _fechas_coinciden(
        autor_existente.get("fechaDefuncion"),
        autor_existente.get("anioDefuncionAprox"),
        datos_wikidata["fecha_defuncion"],
        datos_wikidata["anio_defuncion_aprox"],
    )

    # Criterio conservador (asimetría de costo, sección 2 del contexto):
    # confirma "existente" solo si al menos una de las dos fechas coincide
    # con certeza. Cualquier otra combinación (desacuerdo, datos
    # insuficientes en ambos) queda pendiente de confirmación del usuario.
    if coincide_nacimiento is True or coincide_defuncion is True:
        return AutorResolucionExistente(autor_id=autor_id, nombre=nombre_candidato)

    datos_si_es_nuevo = _construir_autor_nuevo(
        uid, request.autor_nombre, request.idioma, datos_wikidata
    )
    motivo = _construir_motivo_pendiente(coincide_nacimiento, coincide_defuncion)

    return AutorResolucionPendiente(
        autor_id_candidato=autor_id,
        nombre_candidato=nombre_candidato,
        datos_si_es_nuevo=datos_si_es_nuevo,
        motivo=motivo,
    )


def _fechas_coinciden(
    fecha_existente_iso: str | None,
    anio_existente_aprox: int | None,
    fecha_wikidata_iso: str | None,
    anio_wikidata_aprox: int | None,
    margen: int = MARGEN_ANIOS_AUTOR,
) -> bool | None:
    """Compara dos fechas (nacimiento o defunción) con el criterio acordado:
    fecha exacta si existe en ambos lados, año aproximado si no. Margen de
    tolerancia de 20 años.

    Devuelve True (coincide), False (fuera de margen), o None (no hay datos
    suficientes de algún lado para comparar).
    """

    def _extraer_anio(fecha_iso: str | None, anio_aprox: int | None) -> int | None:
        if fecha_iso:
            try:
                return int(fecha_iso.split("-")[0])
            except (ValueError, IndexError):
                pass
        return anio_aprox

    anio_existente = _extraer_anio(fecha_existente_iso, anio_existente_aprox)
    anio_wikidata = _extraer_anio(fecha_wikidata_iso, anio_wikidata_aprox)

    if anio_existente is None or anio_wikidata is None:
        return None

    return abs(anio_existente - anio_wikidata) <= margen


def _construir_motivo_pendiente(
    coincide_nacimiento: bool | None, coincide_defuncion: bool | None
) -> str:
    if coincide_nacimiento is False or coincide_defuncion is False:
        return "Las fechas disponibles no coinciden dentro del margen de tolerancia."
    return "No hay datos suficientes para confirmar o descartar la coincidencia por fechas."


def _construir_autor_nuevo(
    uid: str, nombre: str, idioma: str | None, datos_wikidata: dict
) -> AutorCreateSchema:
    pais_resolucion: PaisResolucion | None = None
    if datos_wikidata["pais"]:
        pais_resolucion = _resolver_pais(uid, datos_wikidata["pais"])

    fecha_nacimiento = (
        date.fromisoformat(datos_wikidata["fecha_nacimiento"])
        if datos_wikidata["fecha_nacimiento"]
        else None
    )
    fecha_defuncion = (
        date.fromisoformat(datos_wikidata["fecha_defuncion"])
        if datos_wikidata["fecha_defuncion"]
        else None
    )

    return AutorCreateSchema(
        nombre=nombre,
        idioma=idioma,
        pais=pais_resolucion,
        retrato_url=datos_wikidata["retrato_url"],
        fecha_nacimiento=fecha_nacimiento,
        anio_nacimiento_aprox=datos_wikidata["anio_nacimiento_aprox"],
        fecha_defuncion=fecha_defuncion,
        anio_defuncion_aprox=datos_wikidata["anio_defuncion_aprox"],
    )


def _resolver_pais(uid: str, pais_candidato: str) -> PaisResolucion:
    paises_existentes = internal_client.obtener_paises(uid)
    paises_bulk = [{"id": p["id"], "nombre": p["nombre"]} for p in paises_existentes]

    prompt = construir_prompt_matchear_pais(pais_candidato, paises_bulk)
    resultado = gemini_client.generar_json(prompt)

    if resultado["resultado"] == "existente":
        return PaisResolucionExistente(
            pais_id=resultado["pais_id"], nombre=resultado["nombre_normalizado"]
        )

    return PaisResolucionNueva(
        datos=PaisCreateSchema(nombre=resultado["nombre_normalizado"])
    )


def _resolver_generos(uid: str, categorias: list[str]) -> list[GeneroResolucion]:
    if not categorias:
        return []

    generos_existentes = internal_client.obtener_generos(uid)
    generos_bulk = [{"id": g["id"], "nombre": g["nombre"]} for g in generos_existentes]

    resoluciones = []
    for categoria in categorias:
        prompt = construir_prompt_matchear_genero(categoria, generos_bulk)
        resultado = gemini_client.generar_json(prompt)
        resoluciones.append(_mapear_resolucion_genero(resultado))

    return resoluciones


def _mapear_resolucion_genero(resultado: dict) -> GeneroResolucion:
    if resultado["resultado"] == "existente":
        return GeneroResolucionExistente(
            genero_id=resultado["genero_id"], nombre=resultado["nombre_normalizado"]
        )

    return GeneroResolucionNueva(
        datos=GeneroCreateSchema(nombre=resultado["nombre_normalizado"])
    )


# ==========================================
# 3. Importación (paso 3: /importar)
# ==========================================

def importar_libro(uid: str, request: ImportarLibroRequest) -> dict:
    """Reenvía el payload final a Java.

    TODO: endpoint pendiente en Java (POST /api/libros/importar-externo,
    ver sección 6 del contexto — falla con 404 hasta que se implemente ahí).
    El código queda listo para cuando exista.
    """
    url = f"{settings.backend_java_url}/api/libros/importar-externo"
    headers = {"X-Internal-Token": generar_jwt_interno(uid)}

    respuesta = requests.post(
        url,
        json=request.model_dump(exclude_none=True),
        headers=headers,
        timeout=10,
    )
    respuesta.raise_for_status()
    return respuesta.json()