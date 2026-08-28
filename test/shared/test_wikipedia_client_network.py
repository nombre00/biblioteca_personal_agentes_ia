import requests
import pytest

from app.shared import wikipedia_client
from app.shared.wikipedia_client import (
    _buscar_candidatos,
    _obtener_extracto,
    _obtener_retrato,
    _obtener_wikidata_id,
    _obtener_label,
    _obtener_claims,
    _buscar_candidatos_autor_wikidata,
    _obtener_obras_p800,
    _buscar_obras_reverse_p50,
    _obtener_info_obras,
    _obtener_titulo_wikipedia_desde_qid,
)


class FakeResponse:
    """Simula una respuesta de requests con los métodos que usa el cliente."""

    def __init__(self, json_data=None, status_code: int = 200, url: str = "", text: str = ""):
        self._json_data = json_data
        self.status_code = status_code
        self.url = url
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._json_data


# ---------------------------------------------------------------------------
# _buscar_candidatos
# ---------------------------------------------------------------------------

class TestBuscarCandidatos:

    def test_candidatos_con_snippet_limpio(self, monkeypatch):
        data = {
            "query": {
                "search": [
                    {"title": "Jenofonte", "snippet": '<span class="searchmatch">Jenofonte</span> fue...'},
                    {"title": "Jenofonte de Éfeso", "snippet": "novelista griego"},
                ]
            }
        }
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        candidatos = _buscar_candidatos("Jenofonte")

        assert candidatos == [
            {"titulo": "Jenofonte", "snippet": "Jenofonte fue..."},
            {"titulo": "Jenofonte de Éfeso", "snippet": "novelista griego"},
        ]

    def test_sin_resultados_devuelve_lista_vacia(self, monkeypatch):
        data = {"query": {"search": []}}
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        assert _buscar_candidatos("query sin resultados") == []

    def test_snippet_ausente_se_trata_como_vacio(self, monkeypatch):
        data = {"query": {"search": [{"title": "Título sin snippet"}]}}
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        candidatos = _buscar_candidatos("query")

        assert candidatos == [{"titulo": "Título sin snippet", "snippet": ""}]

    def test_status_error_propaga_excepcion(self, monkeypatch):
        monkeypatch.setattr(
            wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(None, 500)
        )

        with pytest.raises(requests.HTTPError):
            _buscar_candidatos("query")


# ---------------------------------------------------------------------------
# _obtener_extracto
# ---------------------------------------------------------------------------

class TestObtenerExtracto:

    def test_extracto_presente(self, monkeypatch):
        data = {"query": {"pages": {"123": {"pageid": 123, "extract": "Texto del lead."}}}}
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        assert _obtener_extracto("Un título") == "Texto del lead."

    def test_status_distinto_de_200_devuelve_none(self, monkeypatch):
        monkeypatch.setattr(
            wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(None, 503, text="error")
        )

        assert _obtener_extracto("Un título") is None

    def test_pages_vacio_devuelve_none(self, monkeypatch):
        data = {"query": {"pages": {}}}
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        assert _obtener_extracto("Un título") is None

    def test_pagina_faltante_devuelve_none(self, monkeypatch):
        data = {"query": {"pages": {"-1": {"missing": ""}}}}
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        assert _obtener_extracto("Un título inexistente") is None

    def test_sin_campo_extract_devuelve_none(self, monkeypatch):
        data = {"query": {"pages": {"123": {"pageid": 123}}}}
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        assert _obtener_extracto("Un título") is None


# ---------------------------------------------------------------------------
# _obtener_retrato
# ---------------------------------------------------------------------------

class TestObtenerRetrato:

    def test_originalimage_presente(self, monkeypatch):
        data = {"originalimage": {"source": "https://x/foto_grande.jpg"}}
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        assert _obtener_retrato("Autor") == "https://x/foto_grande.jpg"

    def test_fallback_a_thumbnail_si_no_hay_originalimage(self, monkeypatch):
        data = {"thumbnail": {"source": "https://x/thumb.jpg"}}
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        assert _obtener_retrato("Autor") == "https://x/thumb.jpg"

    def test_sin_imagen_devuelve_none(self, monkeypatch):
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse({}))

        assert _obtener_retrato("Autor") is None

    def test_status_distinto_de_200_devuelve_none(self, monkeypatch):
        monkeypatch.setattr(
            wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(None, 404)
        )

        assert _obtener_retrato("Autor inexistente") is None


# ---------------------------------------------------------------------------
# _obtener_wikidata_id
# ---------------------------------------------------------------------------

class TestObtenerWikidataId:

    def test_qid_presente(self, monkeypatch):
        data = {"query": {"pages": {"123": {"pageprops": {"wikibase_item": "Q3306"}}}}}
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        assert _obtener_wikidata_id("Fyodor Dostoevsky") == "Q3306"

    def test_sin_pageprops_devuelve_none(self, monkeypatch):
        data = {"query": {"pages": {"123": {}}}}
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        assert _obtener_wikidata_id("Un título") is None

    def test_sin_wikibase_item_devuelve_none(self, monkeypatch):
        data = {"query": {"pages": {"123": {"pageprops": {}}}}}
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        assert _obtener_wikidata_id("Un título") is None

    def test_status_error_propaga_excepcion(self, monkeypatch):
        monkeypatch.setattr(
            wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(None, 500)
        )

        with pytest.raises(requests.HTTPError):
            _obtener_wikidata_id("Un título")


# ---------------------------------------------------------------------------
# _obtener_label
# ---------------------------------------------------------------------------

class TestObtenerLabel:

    def test_label_presente(self, monkeypatch):
        data = {"entities": {"Q159": {"labels": {"en": {"value": "Russia"}}}}}
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        assert _obtener_label("Q159", idioma="en") == "Russia"

    def test_sin_label_en_idioma_pedido_devuelve_none(self, monkeypatch):
        data = {"entities": {"Q159": {"labels": {}}}}
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        assert _obtener_label("Q159", idioma="es") is None

    def test_entidad_inexistente_devuelve_none(self, monkeypatch):
        data = {"entities": {}}
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        assert _obtener_label("Q0", idioma="en") is None

    def test_status_error_propaga_excepcion(self, monkeypatch):
        monkeypatch.setattr(
            wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(None, 500)
        )

        with pytest.raises(requests.HTTPError):
            _obtener_label("Q159")


# ---------------------------------------------------------------------------
# _obtener_claims
# ---------------------------------------------------------------------------

class TestObtenerClaims:

    def test_claims_presentes(self, monkeypatch):
        data = {"entities": {"Q159": {"claims": {"P569": [{"mainsnak": {}}]}}}}
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        assert _obtener_claims("Q159") == {"P569": [{"mainsnak": {}}]}

    def test_sin_claims_devuelve_dict_vacio(self, monkeypatch):
        data = {"entities": {"Q159": {}}}
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        assert _obtener_claims("Q159") == {}

    def test_entidad_inexistente_devuelve_dict_vacio(self, monkeypatch):
        data = {"entities": {}}
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        assert _obtener_claims("Q0") == {}

    def test_status_error_propaga_excepcion(self, monkeypatch):
        monkeypatch.setattr(
            wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(None, 500)
        )

        with pytest.raises(requests.HTTPError):
            _obtener_claims("Q159")


# ---------------------------------------------------------------------------
# _buscar_candidatos_autor_wikidata
# ---------------------------------------------------------------------------

class TestBuscarCandidatosAutorWikidata:

    def test_candidatos_mapeados_correctamente(self, monkeypatch):
        data = {
            "search": [
                {"id": "Q192515", "label": "Jenofonte", "description": "historiador griego"},
                {"id": "Q3806", "label": "Jenofonte de Éfeso", "description": "novelista"},
            ]
        }
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        candidatos = _buscar_candidatos_autor_wikidata("Jenofonte")

        assert candidatos == [
            {"qid": "Q192515", "label": "Jenofonte", "description": "historiador griego"},
            {"qid": "Q3806", "label": "Jenofonte de Éfeso", "description": "novelista"},
        ]

    def test_sin_description_usa_string_vacio(self, monkeypatch):
        data = {"search": [{"id": "Q1", "label": "Autor"}]}
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        candidatos = _buscar_candidatos_autor_wikidata("Autor")

        assert candidatos == [{"qid": "Q1", "label": "Autor", "description": ""}]

    def test_sin_resultados_devuelve_lista_vacia(self, monkeypatch):
        data = {"search": []}
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        assert _buscar_candidatos_autor_wikidata("autor inexistente") == []

    def test_status_error_propaga_excepcion(self, monkeypatch):
        monkeypatch.setattr(
            wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(None, 500)
        )

        with pytest.raises(requests.HTTPError):
            _buscar_candidatos_autor_wikidata("query")


# ---------------------------------------------------------------------------
# _obtener_obras_p800
# ---------------------------------------------------------------------------

class TestObtenerObrasP800:

    def test_obras_presentes(self, monkeypatch):
        data = {
            "claims": {
                "P800": [
                    {"mainsnak": {"datavalue": {"value": {"id": "Q1"}}}},
                    {"mainsnak": {"datavalue": {"value": {"id": "Q2"}}}},
                ]
            }
        }
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        assert _obtener_obras_p800("Q192515") == ["Q1", "Q2"]

    def test_sin_p800_devuelve_lista_vacia(self, monkeypatch):
        data = {"claims": {}}
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        assert _obtener_obras_p800("Q192515") == []

    def test_claim_malformado_se_ignora(self, monkeypatch):
        data = {"claims": {"P800": [{"mainsnak": {}}, {"mainsnak": {"datavalue": {"value": {"id": "Q1"}}}}]}}
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        assert _obtener_obras_p800("Q192515") == ["Q1"]

    def test_request_exception_devuelve_lista_vacia_sin_explotar(self, monkeypatch):
        def get_que_falla(*args, **kwargs):
            raise requests.ConnectionError("timeout simulado")

        monkeypatch.setattr(wikipedia_client.requests, "get", get_que_falla)

        assert _obtener_obras_p800("Q129772") == []

    def test_status_error_devuelve_lista_vacia_sin_explotar(self, monkeypatch):
        # raise_for_status() sobre un 500 lanza requests.HTTPError, que es
        # subclase de RequestException — debe quedar atrapado igual.
        monkeypatch.setattr(
            wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(None, 500)
        )

        assert _obtener_obras_p800("Q192515") == []


# ---------------------------------------------------------------------------
# _buscar_obras_reverse_p50
# ---------------------------------------------------------------------------

class TestBuscarObrasReverseP50:

    def test_obras_extraidas_de_bindings(self, monkeypatch):
        data = {
            "results": {
                "bindings": [
                    {"obra": {"value": "http://www.wikidata.org/entity/Q1"}},
                    {"obra": {"value": "http://www.wikidata.org/entity/Q2"}},
                ]
            }
        }
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        assert _buscar_obras_reverse_p50("Q192515") == ["Q1", "Q2"]

    def test_sin_bindings_devuelve_lista_vacia(self, monkeypatch):
        data = {"results": {"bindings": []}}
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        assert _buscar_obras_reverse_p50("Q192515") == []

    def test_request_exception_devuelve_lista_vacia_sin_explotar(self, monkeypatch):
        def get_que_falla(*args, **kwargs):
            raise requests.Timeout("timeout simulado")

        monkeypatch.setattr(wikipedia_client.requests, "get", get_que_falla)

        assert _buscar_obras_reverse_p50("Q192515") == []


# ---------------------------------------------------------------------------
# _obtener_info_obras
# ---------------------------------------------------------------------------

class TestObtenerInfoObras:

    def test_qids_vacios_no_llama_a_requests(self, monkeypatch):
        llamado = []
        monkeypatch.setattr(
            wikipedia_client.requests, "get", lambda *a, **k: llamado.append(True)
        )

        assert _obtener_info_obras([]) == {}
        assert llamado == []

    def test_mapeo_completo_de_una_obra(self, monkeypatch):
        data = {
            "entities": {
                "Q456": {
                    "labels": {"es": {"value": "Recuerdos de Sócrates"}, "en": {"value": "Memorabilia"}},
                    "aliases": {"es": [{"value": "Memorabilia"}], "en": []},
                    "descriptions": {"es": {"value": "diálogos socráticos"}},
                }
            }
        }
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        info = _obtener_info_obras(["Q456"])

        assert info == {
            "Q456": {
                "label_es": "Recuerdos de Sócrates",
                "label_en": "Memorabilia",
                "alias_es": ["Memorabilia"],
                "alias_en": [],
                "descripcion": "diálogos socráticos",
            }
        }

    def test_descripcion_cae_a_ingles_si_no_hay_en_espanol(self, monkeypatch):
        data = {
            "entities": {
                "Q1": {
                    "labels": {},
                    "aliases": {},
                    "descriptions": {"en": {"value": "an epic poem"}},
                }
            }
        }
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        info = _obtener_info_obras(["Q1"])

        assert info["Q1"]["descripcion"] == "an epic poem"

    def test_sin_labels_aliases_ni_descriptions(self, monkeypatch):
        data = {"entities": {"Q1": {}}}
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        info = _obtener_info_obras(["Q1"])

        assert info == {
            "Q1": {
                "label_es": None,
                "label_en": None,
                "alias_es": [],
                "alias_en": [],
                "descripcion": None,
            }
        }


# ---------------------------------------------------------------------------
# _obtener_titulo_wikipedia_desde_qid
# ---------------------------------------------------------------------------

class TestObtenerTituloWikipediaDesdeQid:

    def test_sitelink_en_espanol_se_prioriza(self, monkeypatch):
        data = {
            "entities": {
                "Q456": {
                    "sitelinks": {
                        "eswiki": {"title": "Recuerdos de Sócrates"},
                        "enwiki": {"title": "Memorabilia"},
                    }
                }
            }
        }
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        titulo, idioma = _obtener_titulo_wikipedia_desde_qid("Q456")

        assert (titulo, idioma) == ("Recuerdos de Sócrates", "es")

    def test_fallback_a_ingles_si_no_hay_espanol(self, monkeypatch):
        data = {"entities": {"Q456": {"sitelinks": {"enwiki": {"title": "Memorabilia"}}}}}
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        titulo, idioma = _obtener_titulo_wikipedia_desde_qid("Q456")

        assert (titulo, idioma) == ("Memorabilia", "en")

    def test_sin_sitelinks_en_ningun_idioma_devuelve_none_none(self, monkeypatch):
        data = {"entities": {"Q456": {"sitelinks": {"frwiki": {"title": "Mémorabilia"}}}}}
        monkeypatch.setattr(wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(data))

        assert _obtener_titulo_wikipedia_desde_qid("Q456") == (None, None)

    def test_status_error_propaga_excepcion(self, monkeypatch):
        monkeypatch.setattr(
            wikipedia_client.requests, "get", lambda *a, **k: FakeResponse(None, 500)
        )

        with pytest.raises(requests.HTTPError):
            _obtener_titulo_wikipedia_desde_qid("Q456")