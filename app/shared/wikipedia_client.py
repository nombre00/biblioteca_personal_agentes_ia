import requests

WIKIPEDIA_SEARCH_URL = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{titulo}"


def _buscar_titulo(query: str) -> str | None:
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "format": "json",
        "srlimit": 1,
    }
    respuesta = requests.get(WIKIPEDIA_SEARCH_URL, params=params, timeout=5)
    respuesta.raise_for_status()
    resultados = respuesta.json().get("query", {}).get("search", [])

    if not resultados:
        return None

    return resultados[0]["title"]


def _obtener_extracto(titulo: str) -> str | None:
    url = WIKIPEDIA_SUMMARY_URL.format(titulo=titulo.replace(" ", "_"))
    respuesta = requests.get(url, timeout=5)

    if respuesta.status_code != 200:
        return None

    return respuesta.json().get("extract")


def obtener_contexto(query: str) -> str | None:
    try:
        titulo = _buscar_titulo(query)
        if not titulo:
            return None

        return _obtener_extracto(titulo)
    except requests.RequestException:
        return None