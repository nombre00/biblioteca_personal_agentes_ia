import requests
import pytest

from app.shared import wikipedia_client
from app.shared.wikipedia_client import (
    _buscar_titulo_con_fallback,
    _buscar_titulo_biografia_con_fallback,
    _buscar_titulo_sinopsis_con_fallback,
    _buscar_autor_wikidata_con_fallback,
    obtener_contexto_biografia,
    _obtener_contexto_sinopsis_via_wikidata,
    obtener_contexto_sinopsis,
    obtener_datos_estructurados,
)


CANDIDATOS = [{"titulo": "Un título", "snippet": "un snippet"}]
CANDIDATOS_AUTOR = [{"qid": "Q1", "label": "Autor", "description": "descripción"}]


# ---------------------------------------------------------------------------
# _buscar_titulo_con_fallback
# ---------------------------------------------------------------------------

class TestBuscarTituloConFallback:

    def test_primer_idioma_exitoso_no_prueba_segundo(self, monkeypatch):
        idiomas_consultados = []

        def fake_buscar_candidatos(query, idioma="es", limite=None):
            idiomas_consultados.append(idioma)
            return CANDIDATOS

        monkeypatch.setattr(wikipedia_client, "_buscar_candidatos", fake_buscar_candidatos)
        monkeypatch.setattr(
            wikipedia_client, "_elegir_candidato_relevante", lambda q, c: "Un título"
        )

        resultado = _buscar_titulo_con_fallback("query")

        assert resultado == ("Un título", "es")
        assert idiomas_consultados == ["es"]

    def test_primer_idioma_sin_candidatos_prueba_segundo(self, monkeypatch):
        def fake_buscar_candidatos(query, idioma="es", limite=None):
            return [] if idioma == "es" else CANDIDATOS

        monkeypatch.setattr(wikipedia_client, "_buscar_candidatos", fake_buscar_candidatos)
        monkeypatch.setattr(
            wikipedia_client, "_elegir_candidato_relevante", lambda q, c: "Un título"
        )

        resultado = _buscar_titulo_con_fallback("query")

        assert resultado == ("Un título", "en")

    def test_primer_idioma_con_candidatos_pero_ninguno_relevante_prueba_segundo(self, monkeypatch):
        monkeypatch.setattr(wikipedia_client, "_buscar_candidatos", lambda q, idioma="es", limite=None: CANDIDATOS)

        def fake_elegir(query, candidatos):
            return None

        llamadas_por_idioma = {"count": 0}

        def fake_elegir_secuencial(query, candidatos):
            llamadas_por_idioma["count"] += 1
            return "Un título" if llamadas_por_idioma["count"] == 2 else None

        monkeypatch.setattr(wikipedia_client, "_elegir_candidato_relevante", fake_elegir_secuencial)

        resultado = _buscar_titulo_con_fallback("query")

        assert resultado == ("Un título", "en")
        assert llamadas_por_idioma["count"] == 2

    def test_ningun_idioma_resuelve_devuelve_none_none(self, monkeypatch):
        monkeypatch.setattr(wikipedia_client, "_buscar_candidatos", lambda q, idioma="es", limite=None: CANDIDATOS)
        monkeypatch.setattr(wikipedia_client, "_elegir_candidato_relevante", lambda q, c: None)

        assert _buscar_titulo_con_fallback("query") == (None, None)


# ---------------------------------------------------------------------------
# _buscar_titulo_biografia_con_fallback
# ---------------------------------------------------------------------------

class TestBuscarTituloBiografiaConFallback:

    def test_primer_idioma_exitoso(self, monkeypatch):
        monkeypatch.setattr(wikipedia_client, "_buscar_candidatos", lambda q, idioma="es", limite=None: CANDIDATOS)
        monkeypatch.setattr(wikipedia_client, "_elegir_candidato_biografia", lambda q, c: "Un título")

        assert _buscar_titulo_biografia_con_fallback("Autor") == ("Un título", "es")

    def test_fallback_a_segundo_idioma(self, monkeypatch):
        monkeypatch.setattr(
            wikipedia_client, "_buscar_candidatos", lambda q, idioma="es", limite=None: [] if idioma == "es" else CANDIDATOS
        )
        monkeypatch.setattr(wikipedia_client, "_elegir_candidato_biografia", lambda q, c: "Un título")

        assert _buscar_titulo_biografia_con_fallback("Autor") == ("Un título", "en")

    def test_query_armado_con_sufijo_writer(self, monkeypatch):
        queries_recibidas = []

        def fake_buscar_candidatos(query, idioma="es", limite=None):
            queries_recibidas.append(query)
            return CANDIDATOS

        monkeypatch.setattr(wikipedia_client, "_buscar_candidatos", fake_buscar_candidatos)
        monkeypatch.setattr(wikipedia_client, "_elegir_candidato_biografia", lambda q, c: "Un título")

        _buscar_titulo_biografia_con_fallback("Richard Burton")

        assert queries_recibidas[0] == "Richard Burton writer"


# ---------------------------------------------------------------------------
# _buscar_titulo_sinopsis_con_fallback
# ---------------------------------------------------------------------------

class TestBuscarTituloSinopsisConFallback:

    def test_primer_idioma_exitoso(self, monkeypatch):
        monkeypatch.setattr(wikipedia_client, "_buscar_candidatos", lambda q, idioma="es", limite=None: CANDIDATOS)
        monkeypatch.setattr(wikipedia_client, "_elegir_candidato_sinopsis", lambda q, c: "Un título")

        assert _buscar_titulo_sinopsis_con_fallback("Libro", "Autor") == ("Un título", "es")

    def test_fallback_a_segundo_idioma(self, monkeypatch):
        monkeypatch.setattr(
            wikipedia_client, "_buscar_candidatos", lambda q, idioma="es", limite=None: [] if idioma == "es" else CANDIDATOS
        )
        monkeypatch.setattr(wikipedia_client, "_elegir_candidato_sinopsis", lambda q, c: "Un título")

        assert _buscar_titulo_sinopsis_con_fallback("Libro", "Autor") == ("Un título", "en")

    def test_query_armado_con_titulo_y_autor(self, monkeypatch):
        queries_recibidas = []

        def fake_buscar_candidatos(query, idioma="es", limite=None):
            queries_recibidas.append(query)
            return CANDIDATOS

        monkeypatch.setattr(wikipedia_client, "_buscar_candidatos", fake_buscar_candidatos)
        monkeypatch.setattr(wikipedia_client, "_elegir_candidato_sinopsis", lambda q, c: "Un título")

        _buscar_titulo_sinopsis_con_fallback("Memorabilia", "Jenofonte")

        assert queries_recibidas[0] == "Memorabilia Jenofonte"


# ---------------------------------------------------------------------------
# _buscar_autor_wikidata_con_fallback
# ---------------------------------------------------------------------------

class TestBuscarAutorWikidataConFallback:

    def test_primer_idioma_exitoso(self, monkeypatch):
        monkeypatch.setattr(
            wikipedia_client, "_buscar_candidatos_autor_wikidata", lambda q, idioma="es", limite=None: CANDIDATOS_AUTOR
        )
        monkeypatch.setattr(wikipedia_client, "_elegir_autor_wikidata", lambda q, c: "Q1")

        assert _buscar_autor_wikidata_con_fallback("Jenofonte") == "Q1"

    def test_fallback_a_segundo_idioma(self, monkeypatch):
        monkeypatch.setattr(
            wikipedia_client,
            "_buscar_candidatos_autor_wikidata",
            lambda q, idioma="es", limite=None: [] if idioma == "es" else CANDIDATOS_AUTOR,
        )
        monkeypatch.setattr(wikipedia_client, "_elegir_autor_wikidata", lambda q, c: "Q1")

        assert _buscar_autor_wikidata_con_fallback("Jenofonte") == "Q1"

    def test_ningun_idioma_resuelve_devuelve_none(self, monkeypatch):
        monkeypatch.setattr(
            wikipedia_client, "_buscar_candidatos_autor_wikidata", lambda q, idioma="es", limite=None: CANDIDATOS_AUTOR
        )
        monkeypatch.setattr(wikipedia_client, "_elegir_autor_wikidata", lambda q, c: None)

        assert _buscar_autor_wikidata_con_fallback("autor inexistente") is None


# ---------------------------------------------------------------------------
# obtener_contexto_biografia
# ---------------------------------------------------------------------------

class TestObtenerContextoBiografia:

    def test_flujo_feliz(self, monkeypatch):
        monkeypatch.setattr(
            wikipedia_client, "_buscar_titulo_biografia_con_fallback", lambda autor: ("Un título", "es")
        )
        monkeypatch.setattr(
            wikipedia_client, "_obtener_extracto", lambda titulo, idioma: "Texto biográfico."
        )

        assert obtener_contexto_biografia("Autor") == "Texto biográfico."

    def test_sin_titulo_devuelve_none(self, monkeypatch):
        monkeypatch.setattr(
            wikipedia_client, "_buscar_titulo_biografia_con_fallback", lambda autor: (None, None)
        )

        assert obtener_contexto_biografia("Autor inexistente") is None

    def test_request_exception_devuelve_none(self, monkeypatch):
        def falla(autor):
            raise requests.ConnectionError("timeout simulado")

        monkeypatch.setattr(wikipedia_client, "_buscar_titulo_biografia_con_fallback", falla)

        assert obtener_contexto_biografia("Autor") is None


# ---------------------------------------------------------------------------
# _obtener_contexto_sinopsis_via_wikidata
# ---------------------------------------------------------------------------

class TestObtenerContextoSinopsisViaWikidata:

    def _mockear_flujo_completo(self, monkeypatch, qids_p800=None, qids_p50=None, qid_obra_directo="Q456",
                                 qid_obra_gemini=None, titulo_wikipedia="Recuerdos de Sócrates",
                                 idioma_wikipedia="es", extracto="Texto de la obra."):
        monkeypatch.setattr(wikipedia_client, "_buscar_autor_wikidata_con_fallback", lambda autor: "Q192515")
        monkeypatch.setattr(wikipedia_client, "_obtener_obras_p800", lambda qid: qids_p800 or [])
        monkeypatch.setattr(wikipedia_client, "_buscar_obras_reverse_p50", lambda qid: qids_p50 or [])
        monkeypatch.setattr(wikipedia_client, "_obtener_info_obras", lambda qids: {q: {} for q in qids})
        monkeypatch.setattr(
            wikipedia_client, "_resolver_obra_por_titulo", lambda titulo, info: qid_obra_directo
        )
        monkeypatch.setattr(wikipedia_client, "_elegir_obra_wikidata", lambda titulo, info: qid_obra_gemini)
        monkeypatch.setattr(
            wikipedia_client,
            "_obtener_titulo_wikipedia_desde_qid",
            lambda qid: (titulo_wikipedia, idioma_wikipedia),
        )
        monkeypatch.setattr(wikipedia_client, "_obtener_extracto", lambda titulo, idioma: extracto)

    def test_flujo_feliz_con_match_directo(self, monkeypatch):
        self._mockear_flujo_completo(monkeypatch, qids_p800=["Q1"], qids_p50=["Q2"])

        resultado = _obtener_contexto_sinopsis_via_wikidata("Memorabilia", "Jenofonte")

        assert resultado == "Texto de la obra."

    def test_sin_qid_autor_devuelve_none(self, monkeypatch):
        monkeypatch.setattr(wikipedia_client, "_buscar_autor_wikidata_con_fallback", lambda autor: None)

        assert _obtener_contexto_sinopsis_via_wikidata("Libro", "Autor inexistente") is None

    def test_sin_obras_p800_ni_p50_devuelve_none(self, monkeypatch):
        monkeypatch.setattr(wikipedia_client, "_buscar_autor_wikidata_con_fallback", lambda autor: "Q192515")
        monkeypatch.setattr(wikipedia_client, "_obtener_obras_p800", lambda qid: [])
        monkeypatch.setattr(wikipedia_client, "_buscar_obras_reverse_p50", lambda qid: [])

        assert _obtener_contexto_sinopsis_via_wikidata("Libro", "Autor") is None

    def test_ninguna_obra_corresponde_devuelve_none(self, monkeypatch):
        self._mockear_flujo_completo(
            monkeypatch, qids_p800=["Q1"], qid_obra_directo=None, qid_obra_gemini=None
        )

        assert _obtener_contexto_sinopsis_via_wikidata("Obra inexistente", "Autor") is None

    def test_cae_a_gemini_si_no_hay_match_directo(self, monkeypatch):
        self._mockear_flujo_completo(
            monkeypatch, qids_p800=["Q1"], qid_obra_directo=None, qid_obra_gemini="Q456"
        )

        resultado = _obtener_contexto_sinopsis_via_wikidata("Memorabilia", "Jenofonte")

        assert resultado == "Texto de la obra."

    def test_sin_sitelink_devuelve_none(self, monkeypatch):
        self._mockear_flujo_completo(monkeypatch, qids_p800=["Q1"], titulo_wikipedia=None, idioma_wikipedia=None)

        assert _obtener_contexto_sinopsis_via_wikidata("Memorabilia", "Jenofonte") is None

    def test_p800_y_p50_se_combinan_sin_duplicados(self, monkeypatch):
        qids_recibidos = {}

        monkeypatch.setattr(wikipedia_client, "_buscar_autor_wikidata_con_fallback", lambda autor: "Q192515")
        monkeypatch.setattr(wikipedia_client, "_obtener_obras_p800", lambda qid: ["Q1", "Q2"])
        monkeypatch.setattr(wikipedia_client, "_buscar_obras_reverse_p50", lambda qid: ["Q2", "Q3"])

        def fake_obtener_info_obras(qids):
            qids_recibidos["valor"] = qids
            return {q: {} for q in qids}

        monkeypatch.setattr(wikipedia_client, "_obtener_info_obras", fake_obtener_info_obras)
        monkeypatch.setattr(wikipedia_client, "_resolver_obra_por_titulo", lambda titulo, info: None)
        monkeypatch.setattr(wikipedia_client, "_elegir_obra_wikidata", lambda titulo, info: None)

        _obtener_contexto_sinopsis_via_wikidata("Libro", "Autor")

        # Sin duplicar Q2 (presente en ambas fuentes), preservando orden P800 primero.
        assert qids_recibidos["valor"] == ["Q1", "Q2", "Q3"]


# ---------------------------------------------------------------------------
# obtener_contexto_sinopsis
# ---------------------------------------------------------------------------

class TestObtenerContextoSinopsis:

    def test_resuelto_via_wikidata_no_llama_a_texto_libre(self, monkeypatch):
        llamado_texto_libre = []

        monkeypatch.setattr(
            wikipedia_client, "_obtener_contexto_sinopsis_via_wikidata", lambda t, a: "Texto vía Wikidata."
        )
        monkeypatch.setattr(
            wikipedia_client,
            "_buscar_titulo_sinopsis_con_fallback",
            lambda t, a: llamado_texto_libre.append(True) or ("Un título", "es"),
        )

        resultado = obtener_contexto_sinopsis("Memorabilia", "Jenofonte")

        assert resultado == "Texto vía Wikidata."
        assert llamado_texto_libre == []

    def test_wikidata_sin_resultado_cae_a_texto_libre(self, monkeypatch):
        monkeypatch.setattr(wikipedia_client, "_obtener_contexto_sinopsis_via_wikidata", lambda t, a: None)
        monkeypatch.setattr(
            wikipedia_client, "_buscar_titulo_sinopsis_con_fallback", lambda t, a: ("Un título", "es")
        )
        monkeypatch.setattr(wikipedia_client, "_obtener_extracto", lambda titulo, idioma: "Texto vía búsqueda.")

        resultado = obtener_contexto_sinopsis("Libro raro", "Autor poco conocido")

        assert resultado == "Texto vía búsqueda."

    def test_ambas_rutas_fallan_devuelve_none(self, monkeypatch):
        monkeypatch.setattr(wikipedia_client, "_obtener_contexto_sinopsis_via_wikidata", lambda t, a: None)
        monkeypatch.setattr(
            wikipedia_client, "_buscar_titulo_sinopsis_con_fallback", lambda t, a: (None, None)
        )

        assert obtener_contexto_sinopsis("Libro inexistente", "Autor inexistente") is None

    def test_request_exception_devuelve_none(self, monkeypatch):
        def falla(t, a):
            raise requests.Timeout("timeout simulado")

        monkeypatch.setattr(wikipedia_client, "_obtener_contexto_sinopsis_via_wikidata", falla)

        assert obtener_contexto_sinopsis("Libro", "Autor") is None


# ---------------------------------------------------------------------------
# obtener_datos_estructurados
# ---------------------------------------------------------------------------

RESULTADO_VACIO = {
    "retrato_url": None,
    "fecha_nacimiento": None,
    "anio_nacimiento_aprox": None,
    "fecha_defuncion": None,
    "anio_defuncion_aprox": None,
    "pais": None,
    "idioma": None,
}


class TestObtenerDatosEstructurados:

    def test_flujo_feliz_completo(self, monkeypatch):
        monkeypatch.setattr(wikipedia_client, "_buscar_titulo_con_fallback", lambda q: ("Fiódor Dostoyevski", "es"))
        monkeypatch.setattr(wikipedia_client, "_obtener_retrato", lambda t, idioma: "https://x/retrato.jpg")
        monkeypatch.setattr(wikipedia_client, "_obtener_wikidata_id", lambda t, idioma: "Q3306")
        monkeypatch.setattr(
            wikipedia_client,
            "_obtener_claims",
            lambda qid: {
                "P569": [{}],
                "P570": [{}],
                "P27": [{}],
                "P103": [{}],
            },
        )

        def fake_extraer_valor_claim(claims, propiedad):
            valores = {
                "P569": {"time": "+1821-11-11T00:00:00Z", "precision": 11},
                "P570": {"time": "+1881-02-09T00:00:00Z", "precision": 11},
                "P27": {"id": "Q159"},
                "P103": {"id": "Q7737"},
            }
            return valores.get(propiedad)

        monkeypatch.setattr(wikipedia_client, "_extraer_valor_claim", fake_extraer_valor_claim)
        monkeypatch.setattr(
            wikipedia_client,
            "_obtener_label",
            lambda qid, idioma="en": "Russia" if qid == "Q159" else "ruso",
        )

        resultado = obtener_datos_estructurados("Dostoyevski")

        assert resultado == {
            "retrato_url": "https://x/retrato.jpg",
            "fecha_nacimiento": "1821-11-11",
            "anio_nacimiento_aprox": None,
            "fecha_defuncion": "1881-02-09",
            "anio_defuncion_aprox": None,
            "pais": "Russia",
            "idioma": "ruso",
        }

    def test_sin_titulo_devuelve_resultado_vacio(self, monkeypatch):
        monkeypatch.setattr(wikipedia_client, "_buscar_titulo_con_fallback", lambda q: (None, None))

        assert obtener_datos_estructurados("query inexistente") == RESULTADO_VACIO

    def test_sin_qid_conserva_retrato_url(self, monkeypatch):
        monkeypatch.setattr(wikipedia_client, "_buscar_titulo_con_fallback", lambda q: ("Un título", "es"))
        monkeypatch.setattr(wikipedia_client, "_obtener_retrato", lambda t, idioma: "https://x/retrato.jpg")
        monkeypatch.setattr(wikipedia_client, "_obtener_wikidata_id", lambda t, idioma: None)

        resultado = obtener_datos_estructurados("query")

        assert resultado == {**RESULTADO_VACIO, "retrato_url": "https://x/retrato.jpg"}

    def test_sin_claims_relevantes_deja_campos_en_none(self, monkeypatch):
        monkeypatch.setattr(wikipedia_client, "_buscar_titulo_con_fallback", lambda q: ("Un título", "es"))
        monkeypatch.setattr(wikipedia_client, "_obtener_retrato", lambda t, idioma: None)
        monkeypatch.setattr(wikipedia_client, "_obtener_wikidata_id", lambda t, idioma: "Q1")
        monkeypatch.setattr(wikipedia_client, "_obtener_claims", lambda qid: {})
        monkeypatch.setattr(wikipedia_client, "_extraer_valor_claim", lambda claims, prop: None)

        resultado = obtener_datos_estructurados("query")

        assert resultado == RESULTADO_VACIO

    def test_request_exception_devuelve_resultado_vacio(self, monkeypatch):
        def falla(q):
            raise requests.ConnectionError("timeout simulado")

        monkeypatch.setattr(wikipedia_client, "_buscar_titulo_con_fallback", falla)

        assert obtener_datos_estructurados("query") == RESULTADO_VACIO