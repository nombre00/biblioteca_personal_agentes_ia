import logging
import re
import unicodedata
import requests

from app.shared.llm.gemini_client import gemini_client

logger = logging.getLogger(__name__)

WIKIPEDIA_SEARCH_URL_TEMPLATE = "https://{idioma}.wikipedia.org/w/api.php"
WIKIPEDIA_SUMMARY_URL_TEMPLATE = "https://{idioma}.wikipedia.org/api/rest_v1/page/summary/{titulo}"
WIKIPEDIA_PAGEPROPS_URL_TEMPLATE = "https://{idioma}.wikipedia.org/w/api.php"
WIKIDATA_URL = "https://www.wikidata.org/w/api.php"
WIKIDATA_SEARCH_URL = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"

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
PROP_OBRA_NOTABLE = "P800"

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


def _normalizar_texto(texto: str) -> str:
    """Minúsculas + sin tildes/diacríticos, para comparar títulos entre
    idiomas sin que un acento (o su ausencia) genere un falso negativo."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sin_tildes.strip().lower()


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
    _elegir_candidato_relevante, porque este flujo actúa como fallback de
    la resolución vía Wikidata (ver más abajo) y conviene que ese cambio
    no toque ni arrastre nada del flujo de biografía ni del legacy de
    obtener_datos_estructurados.
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

    Nota: esta función implementa la búsqueda por texto libre, que ahora
    actúa como fallback de la resolución vía Wikidata (ver
    _obtener_contexto_sinopsis_via_wikidata) para autores/obras no
    catalogados en Wikidata con la cobertura suficiente.
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
    """
    Trae el lead/introducción completa del artículo (todos los párrafos
    previos al primer encabezado de sección), vía action=query&prop=extracts
    (exintro=true corta justo antes de la primera sección tipo "Early
    life"/"Biografía"; explaintext=true da texto plano, sin markup ni
    marcas de referencia [1][2]).

    Reemplaza al endpoint REST de summary (/api/rest_v1/page/summary/...)
    usado antes, que solo devolvía la primera oración del artículo.
    Cambio motivado por evidencia real: para "Richard Francis Burton" el
    summary REST devolvía 266 caracteres (solo la primera oración),
    mientras que el lead completo trae ~3 párrafos con datos concretos
    (cargos, expediciones, obras traducidas) que antes se perdían y
    dejaban a Gemini con muy poco material del cual partir.
    """
    url = WIKIPEDIA_SEARCH_URL_TEMPLATE.format(idioma=idioma)
    params = {
        "action": "query",
        "prop": "extracts",
        "exintro": True,
        "explaintext": True,
        "redirects": 1,
        "titles": titulo,
        "format": "json",
    }
    logger.info(f"[wikipedia_client] _obtener_extracto -> idioma={idioma} título={titulo!r} params={params}")

    respuesta = requests.get(url, params=params, headers=HEADERS, timeout=5)
    logger.info(f"[wikipedia_client] _obtener_extracto -> status_code={respuesta.status_code} url_final={respuesta.url}")

    if respuesta.status_code != 200:
        logger.warning(f"[wikipedia_client] _obtener_extracto -> status != 200 para título={titulo!r} "
                        f"idioma={idioma}, body={respuesta.text[:300]!r}")
        return None

    data = respuesta.json()
    paginas = data.get("query", {}).get("pages", {})

    if not paginas:
        logger.warning(f"[wikipedia_client] _obtener_extracto -> respuesta sin 'pages' para título={titulo!r} "
                        f"idioma={idioma}")
        return None

    pagina = next(iter(paginas.values()))

    if "missing" in pagina:
        logger.warning(f"[wikipedia_client] _obtener_extracto -> página inexistente para título={titulo!r} "
                        f"idioma={idioma}")
        return None

    extracto = pagina.get("extract")
    logger.info(f"[wikipedia_client] _obtener_extracto -> extract presente={bool(extracto)} "
                f"longitud={len(extracto) if extracto else 0} pageid={pagina.get('pageid')}")

    if not extracto:
        logger.warning(f"[wikipedia_client] _obtener_extracto -> respuesta sin 'extract' para título={titulo!r} "
                        f"idioma={idioma}, claves recibidas={list(pagina.keys())}")

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


# ==========================================
# Extensión: sinopsis vía Wikidata (autor -> obras conocidas)
#
# Reemplaza progresivamente la búsqueda por texto libre para sinopsis
# (ver contexto_40, pendiente #4): en vez de buscar "{titulo} {autor}"
# como string fuzzy en Wikipedia -algo que falla cuando el título está
# traducido de forma distinta en cada idioma, caso real confirmado:
# "Memorabilia" de Jenofonte publicado en español como "Recuerdos de
# Sócrates"- se resuelve primero al autor como entidad de Wikidata, se
# listan sus obras conocidas como datos estructurados (no texto libre),
# y se identifica cuál corresponde comparando labels/alias multi-idioma.
#
# Tres capas en orden de costo creciente: P800 (obra notable, directo
# del autor) -> P50 inverso vía SPARQL (más exhaustivo, requiere
# consulta aparte) -> mecanismo de texto libre ya existente, como red
# de seguridad si Wikidata no tiene cobertura para este autor/obra.
# Todo silencioso: si una capa no encuentra nada, se prueba la
# siguiente sin ruido hacia el llamador (mismo criterio del resto del
# módulo).
# ==========================================


def _buscar_candidatos_autor_wikidata(query: str, idioma: str = "es", limite: int = LIMITE_CANDIDATOS) -> list[dict]:
    """
    Busca directamente en Wikidata (no en Wikipedia) entidades que podrían
    corresponder al autor buscado, vía wbsearchentities -que matchea
    contra labels y alias de Wikidata directamente, y trae homónimos
    reales como resultados separados (ej. buscar "Jenofonte" trae tanto
    al historiador griego como a "Jenofonte de Éfeso", un novelista
    distinto, y hasta un buque de guerra sin relación). Por eso este
    resultado también necesita pasar por un validador de relevancia,
    igual que las búsquedas de Wikipedia.
    """
    params = {
        "action": "wbsearchentities",
        "search": query,
        "language": idioma,
        "type": "item",
        "limit": limite,
        "format": "json",
    }
    logger.info(f"[wikipedia_client] _buscar_candidatos_autor_wikidata -> idioma={idioma} query={query!r} params={params}")

    respuesta = requests.get(WIKIDATA_SEARCH_URL, params=params, headers=HEADERS, timeout=15)
    respuesta.raise_for_status()

    resultados = respuesta.json().get("search", [])
    candidatos = [
        {
            "qid": r["id"],
            "label": r.get("label", ""),
            "description": r.get("description", ""),
        }
        for r in resultados
    ]
    logger.info(f"[wikipedia_client] _buscar_candidatos_autor_wikidata -> idioma={idioma} "
                f"{len(candidatos)} candidato(s): {[(c['qid'], c['label']) for c in candidatos]}")

    if not candidatos:
        logger.warning(f"[wikipedia_client] _buscar_candidatos_autor_wikidata -> "
                        f"SIN candidatos para query={query!r} idioma={idioma}")

    return candidatos


def _elegir_autor_wikidata(query: str, candidatos: list[dict]) -> str | None:
    """
    Análoga a los validadores de Wikipedia, pero sobre entidades de
    Wikidata: le pide a Gemini que elija cuál candidato (label +
    descripción) es la persona autora que se está buscando, no un
    homónimo. Devuelve el QID elegido, o None si Gemini elige NINGUNO
    o la respuesta no es interpretable.
    """
    if not candidatos:
        return None

    lista_texto = "\n".join(
        f"{i + 1}. {c['label']} — {c['description'] or 'sin descripción'} (QID: {c['qid']})"
        for i, c in enumerate(candidatos)
    )

    prompt = (
        f"Estoy buscando a la persona autora de una obra literaria: \"{query}\"\n\n"
        f"Estos son candidatos encontrados en Wikidata:\n{lista_texto}\n\n"
        "¿Cuál de estos corresponde específicamente a esa persona? Ten en cuenta "
        "que puede haber homónimos (otra persona con el mismo nombre, o incluso "
        "entidades no humanas como barcos u organizaciones). "
        "Responde ÚNICAMENTE con el número del candidato correcto (ej. \"2\"), "
        "o con la palabra NINGUNO si ninguno corresponde de verdad. "
        "No agregues explicaciones ni ningún otro texto."
    )

    logger.info(f"[wikipedia_client] _elegir_autor_wikidata -> query={query!r} evaluando {len(candidatos)} candidato(s)")

    try:
        respuesta = gemini_client.generar_texto(prompt).strip()
    except Exception as e:
        logger.error(f"[wikipedia_client] _elegir_autor_wikidata -> error consultando Gemini para query={query!r}: {e}")
        return None

    logger.info(f"[wikipedia_client] _elegir_autor_wikidata -> respuesta cruda de Gemini: {respuesta!r}")

    if respuesta.upper().startswith("NINGUNO"):
        logger.info(f"[wikipedia_client] _elegir_autor_wikidata -> "
                     f"Gemini determinó que ningún candidato corresponde a query={query!r}")
        return None

    match = re.search(r"\d+", respuesta)
    if not match:
        logger.warning(f"[wikipedia_client] _elegir_autor_wikidata -> respuesta no interpretable: {respuesta!r}, se descarta")
        return None

    indice = int(match.group()) - 1
    if not (0 <= indice < len(candidatos)):
        logger.warning(f"[wikipedia_client] _elegir_autor_wikidata -> índice fuera de rango: {indice + 1}, se descarta")
        return None

    qid_elegido = candidatos[indice]["qid"]
    logger.info(f"[wikipedia_client] _elegir_autor_wikidata -> "
                f"elegido: {qid_elegido} ({candidatos[indice]['label']!r}) para query={query!r}")
    return qid_elegido


def _buscar_autor_wikidata_con_fallback(nombre_autor: str) -> str | None:
    """Resuelve el QID del autor probando cada idioma de IDIOMAS_FALLBACK
    en orden (mismo patrón que el resto del módulo), sin traducir el
    nombre ingresado."""
    for idioma in IDIOMAS_FALLBACK:
        candidatos = _buscar_candidatos_autor_wikidata(nombre_autor, idioma=idioma)
        if not candidatos:
            logger.info(f"[wikipedia_client] _buscar_autor_wikidata_con_fallback -> "
                        f"sin candidatos en idioma={idioma}, probando siguiente")
            continue

        qid = _elegir_autor_wikidata(nombre_autor, candidatos)
        if qid:
            return qid

        logger.info(f"[wikipedia_client] _buscar_autor_wikidata_con_fallback -> "
                    f"ningún candidato relevante en idioma={idioma}, probando siguiente")

    logger.warning(f"[wikipedia_client] _buscar_autor_wikidata_con_fallback -> "
                    f"SIN resultado para nombre_autor={nombre_autor!r}")
    return None


def _obtener_obras_p800(qid_autor: str) -> list[str]:
    """
    Lee la propiedad P800 (obra notable) del autor. Puede tener cero,
    una, o varias obras listadas -devuelve la lista de QIDs tal cual,
    sin desambiguar todavía cuál corresponde al libro buscado.

    Usa wbgetclaims con property=P800 en vez de _obtener_claims (que
    trae TODAS las claims del ítem sin filtrar) -necesario porque
    autores muy documentados en Wikidata (ej. Jenofonte: miles de años
    de tradición, cientos de propiedades y referencias) generan una
    respuesta lo bastante pesada como para superar el timeout=5 de
    _obtener_claims, que fue pensado para perfiles más livianos (caso
    real: Read timed out contra wikidata.org al intentar traer el
    ítem completo de Xenophon/Q129772).
    """
    params = {
        "action": "wbgetclaims",
        "entity": qid_autor,
        "property": PROP_OBRA_NOTABLE,
        "format": "json",
    }
    logger.info(f"[wikipedia_client] _obtener_obras_p800 -> qid_autor={qid_autor} params={params}")

    try:
        respuesta = requests.get(WIKIDATA_URL, params=params, headers=HEADERS, timeout=15)
        respuesta.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"[wikipedia_client] _obtener_obras_p800 -> "
                     f"error consultando wbgetclaims para qid_autor={qid_autor}: {e}")
        return []

    lista = respuesta.json().get("claims", {}).get(PROP_OBRA_NOTABLE, [])

    qids_obras = []
    for claim in lista:
        try:
            qid = claim["mainsnak"]["datavalue"]["value"]["id"]
            qids_obras.append(qid)
        except (KeyError, TypeError):
            continue

    logger.info(f"[wikipedia_client] _obtener_obras_p800 -> qid_autor={qid_autor} "
                f"{len(qids_obras)} obra(s) vía P800: {qids_obras}")
    return qids_obras


def _buscar_obras_reverse_p50(qid_autor: str, limite: int = 50) -> list[str]:
    """
    Fallback cuando el autor no tiene P800 poblado: busca, vía SPARQL
    contra el Wikidata Query Service, todos los ítems que declaran a
    este autor como P50 (autor de). Más exhaustivo que P800 -encuentra
    cualquier obra catalogada, no solo las "notables"- pero requiere
    una consulta distinta, por eso se prueba solo como segundo intento.
    """
    query_sparql = f"""
    SELECT ?obra WHERE {{
      ?obra wdt:P50 wd:{qid_autor} .
    }}
    LIMIT {limite}
    """
    params = {"query": query_sparql, "format": "json"}
    sparql_headers = {**HEADERS, "Accept": "application/sparql-results+json"}

    logger.info(f"[wikipedia_client] _buscar_obras_reverse_p50 -> qid_autor={qid_autor}")

    try:
        respuesta = requests.get(WIKIDATA_SPARQL_URL, params=params, headers=sparql_headers, timeout=10)
        respuesta.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"[wikipedia_client] _buscar_obras_reverse_p50 -> "
                     f"error consultando SPARQL para qid_autor={qid_autor}: {e}")
        return []

    bindings = respuesta.json().get("results", {}).get("bindings", [])
    qids_obras = []
    for b in bindings:
        uri = b.get("obra", {}).get("value", "")
        qid = uri.rsplit("/", 1)[-1] if uri else None
        if qid:
            qids_obras.append(qid)

    logger.info(f"[wikipedia_client] _buscar_obras_reverse_p50 -> "
                f"qid_autor={qid_autor} {len(qids_obras)} obra(s) vía P50 inverso")
    return qids_obras


def _obtener_info_obras(qids_obras: list[str]) -> dict[str, dict]:
    """
    Trae, en un solo request (wbgetentities acepta varios ids separados
    por '|'), label + alias + descripción en español e inglés de cada
    obra candidata. Se usa tanto para el match directo por texto como
    para armar los candidatos que ve Gemini si el match directo falla.
    """
    if not qids_obras:
        return {}

    params = {
        "action": "wbgetentities",
        "ids": "|".join(qids_obras),
        "props": "labels|aliases|descriptions",
        "languages": "es|en",
        "format": "json",
    }
    respuesta = requests.get(WIKIDATA_URL, params=params, headers=HEADERS, timeout=15)
    respuesta.raise_for_status()

    entidades = respuesta.json().get("entities", {})
    info = {}
    for qid, entidad in entidades.items():
        labels = entidad.get("labels", {})
        aliases = entidad.get("aliases", {})
        descriptions = entidad.get("descriptions", {})

        info[qid] = {
            "label_es": labels.get("es", {}).get("value"),
            "label_en": labels.get("en", {}).get("value"),
            "alias_es": [a["value"] for a in aliases.get("es", [])],
            "alias_en": [a["value"] for a in aliases.get("en", [])],
            "descripcion": descriptions.get("es", {}).get("value") or descriptions.get("en", {}).get("value"),
        }

    logger.info(f"[wikipedia_client] _obtener_info_obras -> {len(info)} obra(s) con info recuperada")
    return info


def _resolver_obra_por_titulo(titulo_libro: str, info_obras: dict[str, dict]) -> str | None:
    """
    Intenta un match directo (sin Gemini) entre el título buscado y los
    labels/alias de cada obra candidata, en cualquiera de los dos
    idiomas -este es el paso que resuelve el caso "Memorabilia"/
    "Recuerdos de Sócrates": ambos títulos suelen estar registrados
    como label/alias del mismo ítem de Wikidata, así que comparar
    contra ambos evita depender de que el string de búsqueda coincida
    con el idioma "correcto" de antemano.

    Devuelve el QID si hay match exacto (normalizado: minúsculas, sin
    tildes), o None si ninguno matchea -en cuyo caso el llamador debe
    recurrir al validador de Gemini sobre este mismo universo acotado.
    """
    objetivo = _normalizar_texto(titulo_libro)

    for qid, info in info_obras.items():
        candidatos_texto = [info["label_es"], info["label_en"], *info["alias_es"], *info["alias_en"]]
        for texto in candidatos_texto:
            if texto and _normalizar_texto(texto) == objetivo:
                logger.info(f"[wikipedia_client] _resolver_obra_por_titulo -> "
                            f"match directo: {titulo_libro!r} == {texto!r} (qid={qid})")
                return qid

    logger.info(f"[wikipedia_client] _resolver_obra_por_titulo -> "
                f"sin match directo para titulo_libro={titulo_libro!r}")
    return None


def _elegir_obra_wikidata(titulo_libro: str, info_obras: dict[str, dict]) -> str | None:
    """
    Fallback cuando _resolver_obra_por_titulo no encuentra match directo:
    le pide a Gemini que elija, entre las obras conocidas del autor (ya
    acotadas -no es una búsqueda a ciegas en toda Wikipedia-, cuál
    corresponde al título buscado. Útil para variantes no registradas
    como alias (ej. títulos parciales, subtítulos).
    """
    if not info_obras:
        return None

    candidatos = list(info_obras.items())
    lista_texto = "\n".join(
        f"{i + 1}. {info['label_es'] or info['label_en'] or '(sin título)'} — "
        f"{info['descripcion'] or 'sin descripción'} (QID: {qid})"
        for i, (qid, info) in enumerate(candidatos)
    )

    prompt = (
        f"Estoy buscando la obra literaria titulada: \"{titulo_libro}\"\n\n"
        f"Estas son las obras conocidas de su autor, según Wikidata:\n{lista_texto}\n\n"
        "¿Cuál de estas corresponde a la obra que busco? Ten en cuenta que el "
        "título puede estar en un idioma distinto o ser una traducción diferente "
        "del mismo título original. "
        "Responde ÚNICAMENTE con el número de la obra correcta (ej. \"2\"), "
        "o con la palabra NINGUNO si ninguna corresponde de verdad. "
        "No agregues explicaciones ni ningún otro texto."
    )

    logger.info(f"[wikipedia_client] _elegir_obra_wikidata -> "
                f"titulo_libro={titulo_libro!r} evaluando {len(candidatos)} obra(s)")

    try:
        respuesta = gemini_client.generar_texto(prompt).strip()
    except Exception as e:
        logger.error(f"[wikipedia_client] _elegir_obra_wikidata -> "
                     f"error consultando Gemini para titulo_libro={titulo_libro!r}: {e}")
        return None

    logger.info(f"[wikipedia_client] _elegir_obra_wikidata -> respuesta cruda de Gemini: {respuesta!r}")

    if respuesta.upper().startswith("NINGUNO"):
        logger.info(f"[wikipedia_client] _elegir_obra_wikidata -> "
                     f"Gemini determinó que ninguna obra corresponde a titulo_libro={titulo_libro!r}")
        return None

    match = re.search(r"\d+", respuesta)
    if not match:
        logger.warning(f"[wikipedia_client] _elegir_obra_wikidata -> respuesta no interpretable: {respuesta!r}, se descarta")
        return None

    indice = int(match.group()) - 1
    if not (0 <= indice < len(candidatos)):
        logger.warning(f"[wikipedia_client] _elegir_obra_wikidata -> índice fuera de rango: {indice + 1}, se descarta")
        return None

    qid_elegido = candidatos[indice][0]
    logger.info(f"[wikipedia_client] _elegir_obra_wikidata -> elegido: {qid_elegido} para titulo_libro={titulo_libro!r}")
    return qid_elegido


def _obtener_titulo_wikipedia_desde_qid(qid: str) -> tuple[str | None, str | None]:
    """
    De un QID de Wikidata, obtiene el título de la página de Wikipedia
    correspondiente -probando cada idioma de IDIOMAS_FALLBACK en orden,
    igual que el resto del módulo- vía sitelinks. Es el paso inverso a
    _obtener_wikidata_id (que va de título de Wikipedia a QID).
    """
    params = {
        "action": "wbgetentities",
        "ids": qid,
        "props": "sitelinks",
        "format": "json",
    }
    respuesta = requests.get(WIKIDATA_URL, params=params, headers=HEADERS, timeout=5)
    respuesta.raise_for_status()

    entidad = respuesta.json().get("entities", {}).get(qid, {})
    sitelinks = entidad.get("sitelinks", {})

    for idioma in IDIOMAS_FALLBACK:
        clave_sitelink = f"{idioma}wiki"
        if clave_sitelink in sitelinks:
            titulo = sitelinks[clave_sitelink]["title"]
            logger.info(f"[wikipedia_client] _obtener_titulo_wikipedia_desde_qid -> "
                        f"qid={qid} título={titulo!r} idioma={idioma}")
            return titulo, idioma

    logger.warning(f"[wikipedia_client] _obtener_titulo_wikipedia_desde_qid -> "
                    f"qid={qid} sin sitelink en ningún idioma de {IDIOMAS_FALLBACK}, "
                    f"disponibles: {list(sitelinks.keys())}")
    return None, None


def _obtener_contexto_sinopsis_via_wikidata(titulo_libro: str, nombre_autor: str) -> str | None:
    """
    Orquesta el flujo completo de resolución vía Wikidata: autor -> QID
    -> obras conocidas -> desambiguar cuál obra corresponde (match
    directo por label/alias, o Gemini sobre el universo acotado) ->
    título de Wikipedia de esa obra -> extracto.

    Las obras conocidas se arman combinando P800 (obra notable) y P50
    inverso (autor de) SIEMPRE, no en cascada -caso real que motivó
    este cambio: Jenofonte tiene P800 poblado con 2 obras (Hiero,
    Cyropaedia), pero "Memorabilia" no está entre ellas; con la
    lógica anterior (P50 solo si P800 viene vacío) ese caso nunca
    hubiera llegado a probar P50, que sí puede tener la obra buscada.
    Se deduplican los QIDs por si una obra aparece en ambas fuentes.

    Devuelve None en cualquier punto donde la ruta no tenga resultado
    (silencioso) -el llamador debe entonces recurrir al mecanismo de
    texto libre existente.
    """
    qid_autor = _buscar_autor_wikidata_con_fallback(nombre_autor)
    if not qid_autor:
        return None

    qids_p800 = _obtener_obras_p800(qid_autor)
    qids_p50 = _buscar_obras_reverse_p50(qid_autor)

    # Combinar sin duplicar, preservando el orden (P800 primero, ya que
    # son las obras marcadas como "notables" -si el match directo
    # encuentra varias coincidencias en teoría, esto no afecta el
    # resultado porque _resolver_obra_por_titulo compara contra todas
    # igual, pero mantiene el log más legible).
    qids_obras = list(dict.fromkeys(qids_p800 + qids_p50))

    if not qids_obras:
        logger.info(f"[wikipedia_client] _obtener_contexto_sinopsis_via_wikidata -> "
                    f"sin obras (P800 ni P50) para qid_autor={qid_autor}")
        return None

    logger.info(f"[wikipedia_client] _obtener_contexto_sinopsis_via_wikidata -> "
                f"qid_autor={qid_autor} {len(qids_p800)} obra(s) P800 + {len(qids_p50)} obra(s) P50 "
                f"= {len(qids_obras)} obra(s) combinadas (sin duplicados): {qids_obras}")

    info_obras = _obtener_info_obras(qids_obras)

    qid_obra = _resolver_obra_por_titulo(titulo_libro, info_obras)
    if not qid_obra:
        qid_obra = _elegir_obra_wikidata(titulo_libro, info_obras)

    if not qid_obra:
        logger.info(f"[wikipedia_client] _obtener_contexto_sinopsis_via_wikidata -> "
                    f"ninguna obra candidata corresponde a titulo_libro={titulo_libro!r}")
        return None

    titulo_wikipedia, idioma = _obtener_titulo_wikipedia_desde_qid(qid_obra)
    if not titulo_wikipedia:
        return None

    return _obtener_extracto(titulo_wikipedia, idioma=idioma)


def obtener_contexto_sinopsis(titulo_libro: str, nombre_autor: str) -> str | None:
    """
    Resuelve el contexto de Wikipedia para generar la sinopsis de un libro.

    Intenta primero la ruta vía Wikidata (autor -> obras conocidas,
    desambiguación por datos estructurados en vez de texto libre) — ver
    _obtener_contexto_sinopsis_via_wikidata. Si esa ruta no encuentra
    nada (autor no catalogado en Wikidata, sin obras en P800/P50, o
    ninguna obra corresponde al título buscado), cae al mecanismo
    original de búsqueda por texto libre como red de seguridad.
    """
    logger.info(f"[wikipedia_client] obtener_contexto_sinopsis -> INICIO "
                f"titulo_libro={titulo_libro!r} nombre_autor={nombre_autor!r}")
    try:
        extracto = _obtener_contexto_sinopsis_via_wikidata(titulo_libro, nombre_autor)
        if extracto:
            logger.info(f"[wikipedia_client] obtener_contexto_sinopsis -> "
                        f"FIN resuelto vía Wikidata titulo_libro={titulo_libro!r} nombre_autor={nombre_autor!r}")
            return extracto

        logger.info(f"[wikipedia_client] obtener_contexto_sinopsis -> "
                    f"Wikidata sin resultado, cayendo a búsqueda por texto libre")

        titulo, idioma = _buscar_titulo_sinopsis_con_fallback(titulo_libro, nombre_autor)
        if not titulo:
            logger.warning(f"[wikipedia_client] obtener_contexto_sinopsis -> "
                            f"FIN sin título para titulo_libro={titulo_libro!r} nombre_autor={nombre_autor!r}")
            return None

        extracto = _obtener_extracto(titulo, idioma=idioma)
        logger.info(f"[wikipedia_client] obtener_contexto_sinopsis -> FIN (texto libre) "
                    f"titulo_libro={titulo_libro!r} nombre_autor={nombre_autor!r} título={titulo!r} "
                    f"idioma={idioma} resultado={'OK' if extracto else 'VACÍO'}")
        return extracto
    except requests.RequestException as e:
        logger.error(f"Error consultando Wikipedia/Wikidata (contexto sinopsis) para "
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
    """Reutiliza el mismo endpoint de summary que se usaba antes para el
    extracto, pero tomando la imagen en vez del texto (el endpoint REST
    de summary sigue siendo válido y suficiente para este uso puntual,
    a diferencia del extracto de texto que sí necesitaba el lead completo)."""
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