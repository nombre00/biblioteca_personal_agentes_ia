import logging
import re
import requests

from app.shared.llm.gemini_client import gemini_client

logger = logging.getLogger(__name__)

WIKIPEDIA_SEARCH_URL_TEMPLATE = "https://{idioma}.wikipedia.org/w/api.php"
WIKIPEDIA_SUMMARY_URL_TEMPLATE = "https://{idioma}.wikipedia.org/api/rest_v1/page/summary/{titulo}"
WIKIPEDIA_PAGEPROPS_URL_TEMPLATE = "https://{idioma}.wikipedia.org/w/api.php"
WIKIDATA_URL = "https://www.wikidata.org/w/api.php"

# Orden de idiomas a intentar al buscar un título. Se prueba primero
# español (mejor cobertura para el catálogo típico de este proyecto:
# clásicos traducidos, historia latinoamericana) y se cae a inglés
# solo si no hay resultados — nunca se traduce el string de búsqueda,
# se reintenta tal cual contra el otro dominio de Wikipedia.
IDIOMAS_FALLBACK = ["es", "en"]

# Cuántos candidatos pedir al search de Wikipedia por cada idioma, para
# que los validadores de relevancia tengan de dónde elegir en vez de
# aceptar a ciegas el primer resultado (fuzzy/texto libre, sin score de
# relevancia confiable expuesto por la API).
LIMITE_CANDIDATOS = 7

# Propiedades de Wikidata que nos interesan
PROP_FECHA_NACIMIENTO = "P569"
PROP_FECHA_DEFUNCION = "P570"
PROP_PAIS_CIUDADANIA = "P27"
PROP_LENGUA_MATERNA = "P103"

# Wikimedia exige un User-Agent identificable en su política de uso de API
# (https://meta.wikimedia.org/wiki/User-Agent_policy). Sin esto, es común
# recibir 403 de forma intermitente en vez de la respuesta esperada.
HEADERS = {"User-Agent": "Biblioteca/1.0 (proyecto personal; contacto: spleo1988@gmail.com)"}


def _limpiar_snippet(snippet_html: str) -> str:
    """Wikipedia devuelve el snippet de cada resultado de search con tags
    <span class="searchmatch"> resaltando las palabras que matchearon.
    Se limpian para pasarle texto plano a Gemini en los validadores de
    relevancia."""
    return re.sub(r"<[^>]+>", "", snippet_html)


def _buscar_candidatos(query: str, idioma: str = "es", limite: int = LIMITE_CANDIDATOS) -> list[dict]:
    """
    Pide varios candidatos (no solo el primero) al search de Wikipedia,
    con título y snippet de cada uno. La elección de cuál corresponde
    de verdad al query se delega a los validadores de relevancia (uno por
    dominio: biografía, sinopsis, o el genérico legacy) — esta función
    solo trae las opciones crudas. Compartida entre todos esos flujos.
    """
    url = WIKIPEDIA_SEARCH_URL_TEMPLATE.format(idioma=idioma)
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "format": "json",
        "srlimit": limite,
    }
    logger.info(f"[wikipedia_client] _buscar_candidatos -> idioma={idioma} query enviada: {query!r} | params: {params}")

    respuesta = requests.get(url, params=params, headers=HEADERS, timeout=5)
    logger.info(f"[wikipedia_client] _buscar_candidatos -> status_code={respuesta.status_code} url_final={respuesta.url}")

    respuesta.raise_for_status()
    data = respuesta.json()
    resultados = data.get("query", {}).get("search", [])

    candidatos = [
        {"titulo": r["title"], "snippet": _limpiar_snippet(r.get("snippet", ""))}
        for r in resultados
    ]
    logger.info(f"[wikipedia_client] _buscar_candidatos -> idioma={idioma} {len(candidatos)} candidato(s) crudos: "
                f"{[c['titulo'] for c in candidatos]}")

    if not candidatos:
        logger.warning(f"[wikipedia_client] _buscar_candidatos -> SIN candidatos para query={query!r} idioma={idioma}")

    return candidatos


def _elegir_candidato_relevante(query: str, candidatos: list[dict]) -> str | None:
    """
    Le pide a Gemini que elija, de una lista de candidatos de search, cuál
    corresponde realmente al query original (o ninguno). Reemplaza la
    heurística de "aceptar el primer resultado" por una decisión basada en
    contenido (título + snippet), no solo en coincidencia de texto —
    necesario porque el search de Wikipedia es fuzzy/texto libre y puede
    matchear por menciones dentro del artículo, no por el tema real de la
    página (ver contexto de la sesión: "Richard Francis Burton" trayendo
    la página de "Premio Eagle" por homonimia con un cofundador del premio).

    Devuelve el título elegido, o None si Gemini determina que ninguno
    corresponde, o si la respuesta no se puede interpretar con confianza
    (en cuyo caso se descarta por seguridad, mismo criterio de "mejor sin
    contexto que con contexto erróneo" ya establecido para este módulo).

    NOTA: esta es la versión genérica original, sin criterio de
    jerarquización. Se mantiene intacta porque la sigue usando
    obtener_datos_estructurados (flujo de búsqueda de libros para
    ingresarlos a la base de datos, fuera de alcance de la separación
    biografía/sinopsis). Los flujos de biografía y sinopsis usan sus
    propias variantes: _elegir_candidato_biografia y
    _elegir_candidato_sinopsis.
    """
    if not candidatos:
        return None

    lista_texto = "\n".join(
        f"{i + 1}. Título: \"{c['titulo']}\" — Extracto: \"{c['snippet']}\""
        for i, c in enumerate(candidatos)
    )

    prompt = (
        f"Estoy buscando información sobre: \"{query}\"\n\n"
        f"Estos son resultados de una búsqueda en Wikipedia:\n{lista_texto}\n\n"
        "¿Cuál de estos artículos corresponde específicamente a lo que busco? "
        "Ten en cuenta que un artículo puede mencionar el tema buscado sin "
        "tratar realmente sobre él (por ejemplo, por una coincidencia de "
        "nombre con otra persona u obra). "
        "Responde ÚNICAMENTE con el número del artículo correcto (ej. \"3\"), "
        "o con la palabra NINGUNO si ninguno corresponde de verdad. "
        "No agregues explicaciones ni ningún otro texto."
    )

    logger.info(f"[wikipedia_client] _elegir_candidato_relevante -> query={query!r} "
                f"evaluando {len(candidatos)} candidato(s)")

    try:
        respuesta = gemini_client.generar_texto(prompt).strip()
    except Exception as e:
        logger.error(f"[wikipedia_client] _elegir_candidato_relevante -> error consultando Gemini "
                     f"para query={query!r}: {e}")
        return None

    logger.info(f"[wikipedia_client] _elegir_candidato_relevante -> respuesta cruda de Gemini: {respuesta!r}")

    if respuesta.upper().startswith("NINGUNO"):
        logger.info(f"[wikipedia_client] _elegir_candidato_relevante -> "
                     f"Gemini determinó que ningún candidato corresponde a query={query!r}")
        return None

    match = re.search(r"\d+", respuesta)
    if not match:
        logger.warning(f"[wikipedia_client] _elegir_candidato_relevante -> "
                        f"respuesta no interpretable: {respuesta!r}, se descarta por seguridad")
        return None

    indice = int(match.group()) - 1
    if not (0 <= indice < len(candidatos)):
        logger.warning(f"[wikipedia_client] _elegir_candidato_relevante -> "
                        f"índice fuera de rango recibido: {indice + 1}, se descarta")
        return None

    titulo_elegido = candidatos[indice]["titulo"]
    logger.info(f"[wikipedia_client] _elegir_candidato_relevante -> "
                f"elegido: {titulo_elegido!r} (opción {indice + 1}) para query={query!r}")
    return titulo_elegido


def _elegir_candidato_biografia(query: str, candidatos: list[dict]) -> str | None:
    """
    Variante de _elegir_candidato_relevante especializada para biografía:
    además de exigir que el candidato corresponda al tema buscado, prioriza
    explícitamente el artículo principal/biográfico sobre sub-artículos
    relacionados (bibliografías, listas de obras, desambiguación).

    Necesaria porque un sub-artículo puede calzar con una lectura literal
    de "¿corresponde a lo que busco?" sin ser la mejor fuente para generar
    una biografía completa (caso real: "Richard Francis Burton bibliography"
    elegido sobre "Richard Francis Burton", el artículo biográfico principal,
    dando un extracto de solo 390 caracteres en vez del lead completo).
    """
    if not candidatos:
        return None

    lista_texto = "\n".join(
        f"{i + 1}. Título: \"{c['titulo']}\" — Extracto: \"{c['snippet']}\""
        for i, c in enumerate(candidatos)
    )

    prompt = (
        f"Estoy buscando información biográfica sobre: \"{query}\"\n\n"
        f"Estos son resultados de una búsqueda en Wikipedia:\n{lista_texto}\n\n"
        "¿Cuál de estos artículos corresponde específicamente a la persona que "
        "busco? Ten en cuenta que un artículo puede mencionar a la persona sin "
        "tratar realmente sobre ella (por ejemplo, por coincidencia de nombre "
        "con otra persona). "
        "IMPORTANTE: si hay varios artículos relacionados con la misma persona "
        "(por ejemplo, el artículo biográfico principal junto con una "
        "bibliografía, una lista de obras, o una página de desambiguación), "
        "elige SIEMPRE el artículo biográfico principal — el que trata sobre "
        "su vida en general — y no un sub-artículo especializado en un aspecto "
        "puntual. "
        "Responde ÚNICAMENTE con el número del artículo correcto (ej. \"3\"), "
        "o con la palabra NINGUNO si ninguno corresponde de verdad. "
        "No agregues explicaciones ni ningún otro texto."
    )

    logger.info(f"[wikipedia_client] _elegir_candidato_biografia -> query={query!r} "
                f"evaluando {len(candidatos)} candidato(s)")

    try:
        respuesta = gemini_client.generar_texto(prompt).strip()
    except Exception as e:
        logger.error(f"[wikipedia_client] _elegir_candidato_biografia -> error consultando Gemini "
                     f"para query={query!r}: {e}")
        return None

    logger.info(f"[wikipedia_client] _elegir_candidato_biografia -> respuesta cruda de Gemini: {respuesta!r}")

    if respuesta.upper().startswith("NINGUNO"):
        logger.info(f"[wikipedia_client] _elegir_candidato_biografia -> "
                     f"Gemini determinó que ningún candidato corresponde a query={query!r}")
        return None

    match = re.search(r"\d+", respuesta)
    if not match:
        logger.warning(f"[wikipedia_client] _elegir_candidato_biografia -> "
                        f"respuesta no interpretable: {respuesta!r}, se descarta por seguridad")
        return None

    indice = int(match.group()) - 1
    if not (0 <= indice < len(candidatos)):
        logger.warning(f"[wikipedia_client] _elegir_candidato_biografia -> "
                        f"índice fuera de rango recibido: {indice + 1}, se descarta")
        return None

    titulo_elegido = candidatos[indice]["titulo"]
    logger.info(f"[wikipedia_client] _elegir_candidato_biografia -> "
                f"elegido: {titulo_elegido!r} (opción {indice + 1}) para query={query!r}")
    return titulo_elegido


def _elegir_candidato_sinopsis(query: str, candidatos: list[dict]) -> str | None:
    """
    Variante de _elegir_candidato_relevante para sinopsis. Hoy es idéntica
    en criterio a la genérica (sin lógica de jerarquización, no aplica al
    caso de una obra) — se mantiene como función propia, en vez de reusar
    _elegir_candidato_relevante, porque este flujo va a ser reemplazado por
    completo por una resolución vía Wikidata (autor -> obras conocidas) en
    una sesión futura, y conviene que ese cambio no toque ni arrastre nada
    del flujo de biografía ni del legacy de obtener_datos_estructurados.
    """
    if not candidatos:
        return None

    lista_texto = "\n".join(
        f"{i + 1}. Título: \"{c['titulo']}\" — Extracto: \"{c['snippet']}\""
        for i, c in enumerate(candidatos)
    )

    prompt = (
        f"Estoy buscando información sobre: \"{query}\"\n\n"
        f"Estos son resultados de una búsqueda en Wikipedia:\n{lista_texto}\n\n"
        "¿Cuál de estos artículos corresponde específicamente a lo que busco? "
        "Ten en cuenta que un artículo puede mencionar el tema buscado sin "
        "tratar realmente sobre él (por ejemplo, por una coincidencia de "
        "nombre con otra persona u obra). "
        "Responde ÚNICAMENTE con el número del artículo correcto (ej. \"3\"), "
        "o con la palabra NINGUNO si ninguno corresponde de verdad. "
        "No agregues explicaciones ni ningún otro texto."
    )

    logger.info(f"[wikipedia_client] _elegir_candidato_sinopsis -> query={query!r} "
                f"evaluando {len(candidatos)} candidato(s)")

    try:
        respuesta = gemini_client.generar_texto(prompt).strip()
    except Exception as e:
        logger.error(f"[wikipedia_client] _elegir_candidato_sinopsis -> error consultando Gemini "
                     f"para query={query!r}: {e}")
        return None

    logger.info(f"[wikipedia_client] _elegir_candidato_sinopsis -> respuesta cruda de Gemini: {respuesta!r}")

    if respuesta.upper().startswith("NINGUNO"):
        logger.info(f"[wikipedia_client] _elegir_candidato_sinopsis -> "
                     f"Gemini determinó que ningún candidato corresponde a query={query!r}")
        return None

    match = re.search(r"\d+", respuesta)
    if not match:
        logger.warning(f"[wikipedia_client] _elegir_candidato_sinopsis -> "
                        f"respuesta no interpretable: {respuesta!r}, se descarta por seguridad")
        return None

    indice = int(match.group()) - 1
    if not (0 <= indice < len(candidatos)):
        logger.warning(f"[wikipedia_client] _elegir_candidato_sinopsis -> "
                        f"índice fuera de rango recibido: {indice + 1}, se descarta")
        return None

    titulo_elegido = candidatos[indice]["titulo"]
    logger.info(f"[wikipedia_client] _elegir_candidato_sinopsis -> "
                f"elegido: {titulo_elegido!r} (opción {indice + 1}) para query={query!r}")
    return titulo_elegido


def _buscar_titulo_con_fallback(query: str) -> tuple[str | None, str | None]:
    """
    Intenta resolver un título contra cada idioma de IDIOMAS_FALLBACK en
    orden, sin traducir el query. Por cada idioma: trae varios candidatos
    (_buscar_candidatos) y le pide a Gemini que elija cuál corresponde de
    verdad (_elegir_candidato_relevante). Solo si no hay candidatos, o
    ninguno es relevante, se prueba el siguiente idioma.

    Devuelve (titulo, idioma) del primer idioma que resolvió un candidato
    relevante, o (None, None) si ningún idioma de la lista lo logró.

    NOTA: función genérica original, usada exclusivamente hoy por
    obtener_datos_estructurados (flujo de búsqueda de libros para
    ingresarlos a la base de datos). Los flujos de biografía y sinopsis
    usan sus propias variantes especializadas (ver más abajo).
    """
    for idioma in IDIOMAS_FALLBACK:
        candidatos = _buscar_candidatos(query, idioma=idioma)
        if not candidatos:
            logger.info(f"[wikipedia_client] _buscar_titulo_con_fallback -> "
                        f"sin candidatos en idioma={idioma}, probando siguiente")
            continue

        titulo = _elegir_candidato_relevante(query, candidatos)
        if titulo:
            return titulo, idioma

        logger.info(f"[wikipedia_client] _buscar_titulo_con_fallback -> "
                    f"ningún candidato relevante en idioma={idioma}, probando siguiente")

    logger.warning(f"[wikipedia_client] _buscar_titulo_con_fallback -> "
                    f"SIN resultado relevante en ningún idioma de {IDIOMAS_FALLBACK} para query={query!r}")
    return None, None


def _buscar_titulo_biografia_con_fallback(nombre_autor: str) -> tuple[str | None, str | None]:
    """
    Análoga a _buscar_titulo_con_fallback, especializada para biografía:
    arma el query (nombre del autor + sufijo "writer") y usa
    _elegir_candidato_biografia, que prioriza el artículo principal sobre
    sub-artículos relacionados.
    """
    query = f"{nombre_autor} writer"

    for idioma in IDIOMAS_FALLBACK:
        candidatos = _buscar_candidatos(query, idioma=idioma)
        if not candidatos:
            logger.info(f"[wikipedia_client] _buscar_titulo_biografia_con_fallback -> "
                        f"sin candidatos en idioma={idioma}, probando siguiente")
            continue

        titulo = _elegir_candidato_biografia(query, candidatos)
        if titulo:
            return titulo, idioma

        logger.info(f"[wikipedia_client] _buscar_titulo_biografia_con_fallback -> "
                    f"ningún candidato relevante en idioma={idioma}, probando siguiente")

    logger.warning(f"[wikipedia_client] _buscar_titulo_biografia_con_fallback -> "
                    f"SIN resultado relevante en ningún idioma de {IDIOMAS_FALLBACK} para query={query!r}")
    return None, None


def _buscar_titulo_sinopsis_con_fallback(titulo_libro: str, nombre_autor: str) -> tuple[str | None, str | None]:
    """
    Análoga a _buscar_titulo_con_fallback, especializada para sinopsis:
    arma el query (título + autor) y usa _elegir_candidato_sinopsis.

    Nota: esta función queda a propósito con la misma lógica de búsqueda
    por texto libre que tenía el flujo compartido — el reemplazo por
    resolución vía Wikidata (autor -> obras conocidas) queda pendiente
    para una sesión futura.
    """
    query = f"{titulo_libro} {nombre_autor}"

    for idioma in IDIOMAS_FALLBACK:
        candidatos = _buscar_candidatos(query, idioma=idioma)
        if not candidatos:
            logger.info(f"[wikipedia_client] _buscar_titulo_sinopsis_con_fallback -> "
                        f"sin candidatos en idioma={idioma}, probando siguiente")
            continue

        titulo = _elegir_candidato_sinopsis(query, candidatos)
        if titulo:
            return titulo, idioma

        logger.info(f"[wikipedia_client] _buscar_titulo_sinopsis_con_fallback -> "
                    f"ningún candidato relevante en idioma={idioma}, probando siguiente")

    logger.warning(f"[wikipedia_client] _buscar_titulo_sinopsis_con_fallback -> "
                    f"SIN resultado relevante en ningún idioma de {IDIOMAS_FALLBACK} para query={query!r}")
    return None, None


def _obtener_extracto(titulo: str, idioma: str = "es") -> str | None:
    url = WIKIPEDIA_SUMMARY_URL_TEMPLATE.format(idioma=idioma, titulo=titulo.replace(" ", "_"))
    logger.info(f"[wikipedia_client] _obtener_extracto -> GET {url}")

    respuesta = requests.get(url, headers=HEADERS, timeout=5)
    logger.info(f"[wikipedia_client] _obtener_extracto -> status_code={respuesta.status_code}")

    if respuesta.status_code != 200:
        logger.warning(f"[wikipedia_client] _obtener_extracto -> status != 200 para título={titulo!r} "
                        f"idioma={idioma}, body={respuesta.text[:300]!r}")
        return None

    data = respuesta.json()
    extracto = data.get("extract")
    logger.info(f"[wikipedia_client] _obtener_extracto -> extract presente={bool(extracto)} "
                f"longitud={len(extracto) if extracto else 0} "
                f"pageid={data.get('pageid')} type={data.get('type')}")

    if not extracto:
        logger.warning(f"[wikipedia_client] _obtener_extracto -> respuesta sin 'extract' para título={titulo!r} "
                        f"idioma={idioma}, claves recibidas={list(data.keys())}")

    return extracto


def obtener_contexto_biografia(nombre_autor: str) -> str | None:
    """
    Resuelve el contexto de Wikipedia para generar la biografía de un
    autor. Arma internamente el query (nombre + "writer") y usa el flujo
    especializado de biografía (jerarquización: prioriza el artículo
    principal sobre sub-artículos relacionados).
    """
    logger.info(f"[wikipedia_client] obtener_contexto_biografia -> INICIO nombre_autor={nombre_autor!r}")
    try:
        titulo, idioma = _buscar_titulo_biografia_con_fallback(nombre_autor)
        if not titulo:
            logger.warning(f"[wikipedia_client] obtener_contexto_biografia -> "
                            f"FIN sin título para nombre_autor={nombre_autor!r}")
            return None

        extracto = _obtener_extracto(titulo, idioma=idioma)
        logger.info(f"[wikipedia_client] obtener_contexto_biografia -> FIN nombre_autor={nombre_autor!r} "
                    f"título={titulo!r} idioma={idioma} resultado={'OK' if extracto else 'VACÍO'}")
        return extracto
    except requests.RequestException as e:
        logger.error(f"Error consultando Wikipedia (contexto biografía) para '{nombre_autor}': {e}")
        return None


def obtener_contexto_sinopsis(titulo_libro: str, nombre_autor: str) -> str | None:
    """
    Resuelve el contexto de Wikipedia para generar la sinopsis de un libro.
    Arma internamente el query (título + autor) y usa el flujo especializado
    de sinopsis.

    NOTA: implementación actual sigue siendo búsqueda por texto libre —
    pendiente reemplazo por resolución vía Wikidata (autor -> obras
    conocidas) en una sesión futura, para resolver el caso de títulos
    traducidos de forma distinta en cada idioma (ej. "Memorabilia" de
    Jenofonte, publicado en español como "Recuerdos").
    """
    logger.info(f"[wikipedia_client] obtener_contexto_sinopsis -> INICIO "
                f"titulo_libro={titulo_libro!r} nombre_autor={nombre_autor!r}")
    try:
        titulo, idioma = _buscar_titulo_sinopsis_con_fallback(titulo_libro, nombre_autor)
        if not titulo:
            logger.warning(f"[wikipedia_client] obtener_contexto_sinopsis -> "
                            f"FIN sin título para titulo_libro={titulo_libro!r} nombre_autor={nombre_autor!r}")
            return None

        extracto = _obtener_extracto(titulo, idioma=idioma)
        logger.info(f"[wikipedia_client] obtener_contexto_sinopsis -> FIN "
                    f"titulo_libro={titulo_libro!r} nombre_autor={nombre_autor!r} título={titulo!r} "
                    f"idioma={idioma} resultado={'OK' if extracto else 'VACÍO'}")
        return extracto
    except requests.RequestException as e:
        logger.error(f"Error consultando Wikipedia (contexto sinopsis) para "
                      f"'{titulo_libro}' de '{nombre_autor}': {e}")
        return None


# ==========================================
# Extensión: datos estructurados vía Wikidata
# (fechas, país, idioma, retrato — para desambiguación
# de autor y creación de autor nuevo)
#
# Flujo independiente: pertenece a la búsqueda de libros para
# ingresarlos a la base de datos, no a biografía ni sinopsis.
# Sigue usando _buscar_titulo_con_fallback / _elegir_candidato_relevante
# (las funciones genéricas originales) sin ningún cambio.
# ==========================================


def _obtener_retrato(titulo: str, idioma: str = "es") -> str | None:
    """Reutiliza el mismo endpoint de summary que _obtener_extracto, pero
    tomando la imagen en vez del texto."""
    url = WIKIPEDIA_SUMMARY_URL_TEMPLATE.format(idioma=idioma, titulo=titulo.replace(" ", "_"))
    respuesta = requests.get(url, headers=HEADERS, timeout=5)
    logger.info(f"[wikipedia_client] _obtener_retrato -> status_code={respuesta.status_code} "
                f"título={titulo!r} idioma={idioma}")

    if respuesta.status_code != 200:
        return None

    data = respuesta.json()
    imagen = data.get("originalimage") or data.get("thumbnail")
    url_imagen = imagen.get("source") if imagen else None
    logger.info(f"[wikipedia_client] _obtener_retrato -> imagen encontrada={bool(url_imagen)}")
    return url_imagen


def _obtener_wikidata_id(titulo: str, idioma: str = "es") -> str | None:
    """De un título de Wikipedia obtiene el ID de Wikidata asociado
    (ej. 'Fyodor Dostoevsky' -> 'Q3306'), vía pageprops."""
    url = WIKIPEDIA_PAGEPROPS_URL_TEMPLATE.format(idioma=idioma)
    params = {
        "action": "query",
        "prop": "pageprops",
        "titles": titulo,
        "format": "json",
    }
    logger.info(f"[wikipedia_client] _obtener_wikidata_id -> título={titulo!r} idioma={idioma} params={params}")

    respuesta = requests.get(url, params=params, headers=HEADERS, timeout=5)
    respuesta.raise_for_status()

    paginas = respuesta.json().get("query", {}).get("pages", {})
    for pagina in paginas.values():
        wikidata_id = pagina.get("pageprops", {}).get("wikibase_item")
        if wikidata_id:
            logger.info(f"[wikipedia_client] _obtener_wikidata_id -> QID encontrado: {wikidata_id} "
                        f"para título={titulo!r} idioma={idioma}")
            return wikidata_id

    logger.warning(f"[wikipedia_client] _obtener_wikidata_id -> SIN wikibase_item para título={titulo!r} "
                    f"idioma={idioma}, páginas recibidas={list(paginas.keys())}")
    return None


def _parsear_fecha_wikidata(claim_valor: dict) -> tuple[str | None, int | None]:
    """
    Convierte un valor de tiempo de Wikidata (ej. '+1821-11-11T00:00:00Z',
    precision 11 = día exacto) en (fecha_iso, anio).

    Devuelve (fecha_iso, None) si la precisión permite fecha exacta (día),
    o (None, anio) si solo se conoce el año o una precisión menor (década,
    siglo) — para calzar con los dos campos separados que ya tiene tu
    entidad Autor (fecha_nacimiento vs anio_nacimiento_aprox).

    Precisión de Wikidata: 11 = día, 10 = mes, 9 = año, <9 = década/siglo/milenio.
    """
    time_str = claim_valor.get("time", "")
    precision = claim_valor.get("precision", 0)

    if not time_str:
        return None, None

    signo = -1 if time_str.startswith("-") else 1
    # Formato: [+-]YYYY-MM-DDTHH:MM:SSZ
    sin_signo = time_str.lstrip("+-")
    try:
        anio_str, mes_str, dia_str = sin_signo.split("T")[0].split("-")[:3]
        anio = signo * int(anio_str)
    except (ValueError, IndexError):
        return None, None

    if precision >= 11 and anio > 0:
        # Fecha exacta solo tiene sentido como campo `date` para años d.C.
        # (LocalDate de Java no representa años a.C.). Para a.C. siempre
        # se usa el año aproximado, sin importar la precisión de Wikidata.
        try:
            return f"{anio:04d}-{mes_str}-{dia_str}", None
        except ValueError:
            return None, anio

    return None, anio


def _obtener_label(qid: str, idioma: str = "en") -> str | None:
    """Resuelve el nombre legible de un ítem de Wikidata a partir de su ID
    (ej. 'Q159' -> 'Russia'). Se usa para el país de ciudadanía (P27) y para
    la lengua materna (P103), que en el claim vienen solo como ID.

    Nota: este 'idioma' es el idioma del LABEL solicitado a Wikidata, no
    tiene relación con el idioma en que se encontró el título de origen
    (Wikidata es independiente del idioma de la Wikipedia de origen)."""
    params = {
        "action": "wbgetentities",
        "ids": qid,
        "props": "labels",
        "languages": idioma,
        "format": "json",
    }
    respuesta = requests.get(WIKIDATA_URL, params=params, headers=HEADERS, timeout=5)
    respuesta.raise_for_status()

    entidad = respuesta.json().get("entities", {}).get(qid, {})
    label = entidad.get("labels", {}).get(idioma, {}).get("value")
    logger.info(f"[wikipedia_client] _obtener_label -> qid={qid} idioma={idioma} label={label!r}")
    return label


def _obtener_claims(qid: str) -> dict:
    params = {
        "action": "wbgetentities",
        "ids": qid,
        "props": "claims",
        "format": "json",
    }
    respuesta = requests.get(WIKIDATA_URL, params=params, headers=HEADERS, timeout=5)
    respuesta.raise_for_status()

    entidad = respuesta.json().get("entities", {}).get(qid, {})
    claims = entidad.get("claims", {})
    logger.info(f"[wikipedia_client] _obtener_claims -> qid={qid} propiedades recibidas={list(claims.keys())}")
    return claims


def _extraer_valor_claim(claims: dict, propiedad: str) -> dict | None:
    lista = claims.get(propiedad)
    if not lista:
        return None
    try:
        return lista[0]["mainsnak"]["datavalue"]["value"]
    except (KeyError, IndexError):
        return None


def obtener_datos_estructurados(query: str) -> dict:
    """
    Busca el autor en Wikipedia (con fallback es->en, ver
    _buscar_titulo_con_fallback) y trae sus datos estructurados vía
    Wikidata: fechas de nacimiento/defunción (exactas o aproximadas según
    precisión), país de ciudadanía, lengua materna, y retrato.

    Devuelve un dict con esta forma (todos los campos pueden ser None si no
    se encontró información):
    {
        "retrato_url": str | None,
        "fecha_nacimiento": str | None,   # ISO, solo si Wikidata tiene precisión de día
        "anio_nacimiento_aprox": int | None,
        "fecha_defuncion": str | None,
        "anio_defuncion_aprox": int | None,
        "pais": str | None,               # nombre tal cual lo da Wikidata (típicamente en inglés,
                                           # sin traducir acá — el matching semántico de país
                                           # ya resuelve el idioma)
        "idioma": str | None,             # lengua materna (P103). A diferencia de país, acá el
                                           # label se pide directo en español ("es") a Wikidata,
                                           # porque no existe una segunda capa de matching semántico
                                           # que normalice el idioma del texto como sí pasa con país.
                                           # Si el autor no tiene P103 en Wikidata, queda en
                                           # None a propósito (no hay fallback implícito acá —
                                           # ese es el punto de este cambio: antes de esto, el
                                           # llamador rellenaba con el idioma del libro, que no
                                           # es lo mismo que el idioma del autor).
    }

    Si no se encuentra la página o no tiene ítem de Wikidata asociado,
    devuelve todos los campos en None (no lanza excepción — mismo criterio
    de tolerancia a fallos que el resto del módulo).
    """
    resultado_vacio = {
        "retrato_url": None,
        "fecha_nacimiento": None,
        "anio_nacimiento_aprox": None,
        "fecha_defuncion": None,
        "anio_defuncion_aprox": None,
        "pais": None,
        "idioma": None,
    }

    logger.info(f"[wikipedia_client] obtener_datos_estructurados -> INICIO query={query!r}")

    try:
        titulo, idioma_encontrado = _buscar_titulo_con_fallback(query)
        if not titulo:
            logger.warning(f"[wikipedia_client] obtener_datos_estructurados -> sin título, FIN query={query!r}")
            return resultado_vacio

        retrato_url = _obtener_retrato(titulo, idioma=idioma_encontrado)

        qid = _obtener_wikidata_id(titulo, idioma=idioma_encontrado)
        if not qid:
            logger.warning(f"[wikipedia_client] obtener_datos_estructurados -> sin QID para título={titulo!r} "
                            f"idioma={idioma_encontrado}, FIN query={query!r}")
            return {**resultado_vacio, "retrato_url": retrato_url}

        claims = _obtener_claims(qid)

        fecha_nacimiento, anio_nacimiento_aprox = None, None
        valor_nacimiento = _extraer_valor_claim(claims, PROP_FECHA_NACIMIENTO)
        if valor_nacimiento:
            fecha_nacimiento, anio_nacimiento_aprox = _parsear_fecha_wikidata(valor_nacimiento)

        fecha_defuncion, anio_defuncion_aprox = None, None
        valor_defuncion = _extraer_valor_claim(claims, PROP_FECHA_DEFUNCION)
        if valor_defuncion:
            fecha_defuncion, anio_defuncion_aprox = _parsear_fecha_wikidata(valor_defuncion)

        pais = None
        valor_pais = _extraer_valor_claim(claims, PROP_PAIS_CIUDADANIA)
        if valor_pais:
            qid_pais = valor_pais.get("id")
            if qid_pais:
                pais = _obtener_label(qid_pais)

        idioma = None
        valor_idioma = _extraer_valor_claim(claims, PROP_LENGUA_MATERNA)
        if valor_idioma:
            qid_idioma = valor_idioma.get("id")
            if qid_idioma:
                idioma = _obtener_label(qid_idioma, idioma="es")

        logger.info(f"[wikipedia_client] obtener_datos_estructurados -> FIN query={query!r} título={titulo!r} "
                    f"idioma_origen={idioma_encontrado} qid={qid} fecha_nacimiento={fecha_nacimiento} "
                    f"anio_nacimiento_aprox={anio_nacimiento_aprox} fecha_defuncion={fecha_defuncion} "
                    f"anio_defuncion_aprox={anio_defuncion_aprox} pais={pais!r} idioma={idioma!r} "
                    f"retrato={bool(retrato_url)}")

        return {
            "retrato_url": retrato_url,
            "fecha_nacimiento": fecha_nacimiento,
            "anio_nacimiento_aprox": anio_nacimiento_aprox,
            "fecha_defuncion": fecha_defuncion,
            "anio_defuncion_aprox": anio_defuncion_aprox,
            "pais": pais,
            "idioma": idioma,
        }

    except requests.RequestException as e:
        logger.error(f"Error consultando Wikipedia/Wikidata (datos estructurados) para '{query}': {e}")
        return resultado_vacio