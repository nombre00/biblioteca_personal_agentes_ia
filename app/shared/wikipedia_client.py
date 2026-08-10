import logging
import requests

logger = logging.getLogger(__name__)

WIKIPEDIA_SEARCH_URL = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{titulo}"
WIKIPEDIA_PAGEPROPS_URL = "https://en.wikipedia.org/w/api.php"
WIKIDATA_URL = "https://www.wikidata.org/w/api.php"

# Propiedades de Wikidata que nos interesan
PROP_FECHA_NACIMIENTO = "P569"
PROP_FECHA_DEFUNCION = "P570"
PROP_PAIS_CIUDADANIA = "P27"
PROP_LENGUA_MATERNA = "P103"

# Wikimedia exige un User-Agent identificable en su política de uso de API
# (https://meta.wikimedia.org/wiki/User-Agent_policy). Sin esto, es común
# recibir 403 de forma intermitente en vez de la respuesta esperada.
HEADERS = {"User-Agent": "Biblioteca/1.0 (proyecto personal; contacto: spleo1988@gmail.com)"}


def _buscar_titulo(query: str) -> str | None:
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "format": "json",
        "srlimit": 1,
    }
    respuesta = requests.get(WIKIPEDIA_SEARCH_URL, params=params, headers=HEADERS, timeout=5)
    respuesta.raise_for_status()
    resultados = respuesta.json().get("query", {}).get("search", [])

    if not resultados:
        return None

    return resultados[0]["title"]


def _obtener_extracto(titulo: str) -> str | None:
    url = WIKIPEDIA_SUMMARY_URL.format(titulo=titulo.replace(" ", "_"))
    respuesta = requests.get(url, headers=HEADERS, timeout=5)

    if respuesta.status_code != 200:
        return None

    return respuesta.json().get("extract")


def obtener_contexto(query: str) -> str | None:
    try:
        titulo = _buscar_titulo(query)
        if not titulo:
            return None

        return _obtener_extracto(titulo)
    except requests.RequestException as e:
        logger.error(f"Error consultando Wikipedia (contexto) para '{query}': {e}")
        return None


# ==========================================
# Extensión: datos estructurados vía Wikidata
# (fechas, país, idioma, retrato — para desambiguación
# de autor y creación de autor nuevo)
# ==========================================


def _obtener_retrato(titulo: str) -> str | None:
    """Reutiliza el mismo endpoint de summary que _obtener_extracto, pero
    tomando la imagen en vez del texto."""
    url = WIKIPEDIA_SUMMARY_URL.format(titulo=titulo.replace(" ", "_"))
    respuesta = requests.get(url, headers=HEADERS, timeout=5)

    if respuesta.status_code != 200:
        return None

    data = respuesta.json()
    imagen = data.get("originalimage") or data.get("thumbnail")
    return imagen.get("source") if imagen else None


def _obtener_wikidata_id(titulo: str) -> str | None:
    """De un título de Wikipedia obtiene el ID de Wikidata asociado
    (ej. 'Fyodor Dostoevsky' -> 'Q3306'), vía pageprops."""
    params = {
        "action": "query",
        "prop": "pageprops",
        "titles": titulo,
        "format": "json",
    }
    respuesta = requests.get(WIKIPEDIA_PAGEPROPS_URL, params=params, headers=HEADERS, timeout=5)
    respuesta.raise_for_status()

    paginas = respuesta.json().get("query", {}).get("pages", {})
    for pagina in paginas.values():
        wikidata_id = pagina.get("pageprops", {}).get("wikibase_item")
        if wikidata_id:
            return wikidata_id

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
    la lengua materna (P103), que en el claim vienen solo como ID."""
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
    return entidad.get("claims", {})


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
    Busca el autor en Wikipedia y trae sus datos estructurados vía Wikidata:
    fechas de nacimiento/defunción (exactas o aproximadas según precisión),
    país de ciudadanía, lengua materna, y retrato.

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
        "idioma": str | None,             # lengua materna (P103), mismo criterio que país:
                                           # nombre tal cual lo da Wikidata, sin traducir acá.
                                           # Si el autor no tiene P103 en Wikidata, queda en
                                           # None a propósito (no hay fallback implícito acá —
                                           # ese es el punto de este cambio: antes de esto, el
                                           # llamador rellenaba con el idioma del libro, que no
                                           # es lo mismo que el idioma del autor).
    }

    Si no se encuentra la página o no tiene ítem de Wikidata asociado,
    devuelve todos los campos en None (no lanza excepción — mismo criterio
    de tolerancia a fallos que obtener_contexto).
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

    try:
        titulo = _buscar_titulo(query)
        if not titulo:
            return resultado_vacio

        retrato_url = _obtener_retrato(titulo)

        qid = _obtener_wikidata_id(titulo)
        if not qid:
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
                idioma = _obtener_label(qid_idioma)

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