import requests
import pytest

from app.shared import openLibrary_client
from app.shared.openLibrary_client import (
    _obtener_edition,
    _obtener_work,
    _obtener_work_id,
    _extraer_anio_publicacion_original,
    _existe_portada,
    obtener_datos_estructurados,
)


class FakeResponse:
    """Simula una respuesta de requests con los métodos que usa el cliente."""

    def __init__(self, json_data: dict | None = None, status_code: int = 200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._json_data


# ---------------------------------------------------------------------------
# _obtener_work_id (lógica pura)
# ---------------------------------------------------------------------------

class TestObtenerWorkId:

    def test_works_presente_con_key_valida(self):
        edition_data = {"works": [{"key": "/works/OL27258W"}]}

        assert _obtener_work_id(edition_data) == "OL27258W"

    def test_works_lista_vacia(self):
        edition_data = {"works": []}

        assert _obtener_work_id(edition_data) is None

    def test_sin_campo_works(self):
        edition_data = {}

        assert _obtener_work_id(edition_data) is None

    def test_works_con_dict_sin_key(self):
        edition_data = {"works": [{}]}

        assert _obtener_work_id(edition_data) is None


# ---------------------------------------------------------------------------
# _extraer_anio_publicacion_original (lógica pura)
# ---------------------------------------------------------------------------

class TestExtraerAnioPublicacionOriginal:

    def test_fecha_solo_anio(self):
        assert _extraer_anio_publicacion_original({"first_publish_date": "1866"}) == 1866

    def test_fecha_mes_y_anio(self):
        assert _extraer_anio_publicacion_original({"first_publish_date": "Jan 1866"}) == 1866

    def test_fecha_completa_iso(self):
        assert _extraer_anio_publicacion_original({"first_publish_date": "1866-01-01"}) == 1866

    def test_campo_ausente(self):
        assert _extraer_anio_publicacion_original({}) is None

    def test_campo_none(self):
        assert _extraer_anio_publicacion_original({"first_publish_date": None}) is None

    def test_campo_vacio(self):
        assert _extraer_anio_publicacion_original({"first_publish_date": ""}) is None

    def test_sin_numero_de_cuatro_digitos(self):
        assert (
            _extraer_anio_publicacion_original({"first_publish_date": "circa siglo XIX"})
            is None
        )


# ---------------------------------------------------------------------------
# _obtener_edition (red: GET a /isbn/{isbn}.json)
# ---------------------------------------------------------------------------

class TestObtenerEdition:

    def test_200_devuelve_json(self, monkeypatch):
        data = {"works": [{"key": "/works/OL1W"}]}
        monkeypatch.setattr(
            openLibrary_client.requests, "get", lambda *a, **k: FakeResponse(data, 200)
        )

        assert _obtener_edition("9780307474728") == data

    def test_404_devuelve_none(self, monkeypatch):
        monkeypatch.setattr(
            openLibrary_client.requests, "get", lambda *a, **k: FakeResponse(None, 404)
        )

        assert _obtener_edition("isbn-inexistente") is None

    def test_500_propaga_excepcion(self, monkeypatch):
        monkeypatch.setattr(
            openLibrary_client.requests, "get", lambda *a, **k: FakeResponse(None, 500)
        )

        with pytest.raises(requests.HTTPError):
            _obtener_edition("9780307474728")


# ---------------------------------------------------------------------------
# _obtener_work (red: GET a /works/{work_id}.json)
# ---------------------------------------------------------------------------

class TestObtenerWork:

    def test_200_devuelve_json(self, monkeypatch):
        data = {"first_publish_date": "1967"}
        monkeypatch.setattr(
            openLibrary_client.requests, "get", lambda *a, **k: FakeResponse(data, 200)
        )

        assert _obtener_work("OL27258W") == data

    def test_404_devuelve_none(self, monkeypatch):
        monkeypatch.setattr(
            openLibrary_client.requests, "get", lambda *a, **k: FakeResponse(None, 404)
        )

        assert _obtener_work("work-inexistente") is None

    def test_500_propaga_excepcion(self, monkeypatch):
        monkeypatch.setattr(
            openLibrary_client.requests, "get", lambda *a, **k: FakeResponse(None, 500)
        )

        with pytest.raises(requests.HTTPError):
            _obtener_work("OL27258W")


# ---------------------------------------------------------------------------
# _existe_portada (red: HEAD a covers.openlibrary.org)
# ---------------------------------------------------------------------------

class TestExistePortada:

    def test_200_true(self, monkeypatch):
        monkeypatch.setattr(
            openLibrary_client.requests,
            "head",
            lambda *a, **k: FakeResponse(None, 200),
        )

        assert _existe_portada("9780307474728") is True

    def test_status_distinto_de_200_false(self, monkeypatch):
        monkeypatch.setattr(
            openLibrary_client.requests,
            "head",
            lambda *a, **k: FakeResponse(None, 404),
        )

        assert _existe_portada("isbn-sin-portada") is False

    def test_request_exception_false(self, monkeypatch):
        def head_que_falla(*args, **kwargs):
            raise requests.ConnectionError("timeout simulado")

        monkeypatch.setattr(openLibrary_client.requests, "head", head_que_falla)

        assert _existe_portada("9780307474728") is False


# ---------------------------------------------------------------------------
# obtener_datos_estructurados (orquestación, mockeando las funciones privadas)
# ---------------------------------------------------------------------------

class TestObtenerDatosEstructurados:

    def test_isbn_none_no_llama_a_nada(self, monkeypatch):
        llamadas = []
        monkeypatch.setattr(
            openLibrary_client,
            "_existe_portada",
            lambda isbn: llamadas.append("portada") or True,
        )
        monkeypatch.setattr(
            openLibrary_client,
            "_obtener_edition",
            lambda isbn: llamadas.append("edition") or {},
        )

        resultado = obtener_datos_estructurados(None)

        assert resultado == {"portada_url": None, "anio_publicacion_original": None}
        assert llamadas == []

    def test_flujo_feliz_completo(self, monkeypatch):
        isbn = "9780307474728"
        monkeypatch.setattr(openLibrary_client, "_existe_portada", lambda i: True)
        monkeypatch.setattr(
            openLibrary_client,
            "_obtener_edition",
            lambda i: {"works": [{"key": "/works/OL27258W"}]},
        )
        monkeypatch.setattr(
            openLibrary_client, "_obtener_work_id", lambda edition_data: "OL27258W"
        )
        monkeypatch.setattr(
            openLibrary_client,
            "_obtener_work",
            lambda work_id: {"first_publish_date": "1967"},
        )
        monkeypatch.setattr(
            openLibrary_client,
            "_extraer_anio_publicacion_original",
            lambda work_data: 1967,
        )

        resultado = obtener_datos_estructurados(isbn)

        assert resultado == {
            "portada_url": openLibrary_client.OPENLIBRARY_COVER_URL.format(isbn=isbn),
            "anio_publicacion_original": 1967,
        }

    def test_edition_none_conserva_portada_si_existia(self, monkeypatch):
        isbn = "9780307474728"
        monkeypatch.setattr(openLibrary_client, "_existe_portada", lambda i: True)
        monkeypatch.setattr(openLibrary_client, "_obtener_edition", lambda i: None)

        resultado = obtener_datos_estructurados(isbn)

        assert resultado == {
            "portada_url": openLibrary_client.OPENLIBRARY_COVER_URL.format(isbn=isbn),
            "anio_publicacion_original": None,
        }

    def test_work_id_none_conserva_portada_si_existia(self, monkeypatch):
        isbn = "9780307474728"
        monkeypatch.setattr(openLibrary_client, "_existe_portada", lambda i: True)
        monkeypatch.setattr(
            openLibrary_client, "_obtener_edition", lambda i: {"works": []}
        )
        monkeypatch.setattr(
            openLibrary_client, "_obtener_work_id", lambda edition_data: None
        )

        resultado = obtener_datos_estructurados(isbn)

        assert resultado == {
            "portada_url": openLibrary_client.OPENLIBRARY_COVER_URL.format(isbn=isbn),
            "anio_publicacion_original": None,
        }

    def test_work_none_conserva_portada_si_existia(self, monkeypatch):
        isbn = "9780307474728"
        monkeypatch.setattr(openLibrary_client, "_existe_portada", lambda i: True)
        monkeypatch.setattr(
            openLibrary_client,
            "_obtener_edition",
            lambda i: {"works": [{"key": "/works/OL27258W"}]},
        )
        monkeypatch.setattr(
            openLibrary_client, "_obtener_work_id", lambda edition_data: "OL27258W"
        )
        monkeypatch.setattr(openLibrary_client, "_obtener_work", lambda work_id: None)

        resultado = obtener_datos_estructurados(isbn)

        assert resultado == {
            "portada_url": openLibrary_client.OPENLIBRARY_COVER_URL.format(isbn=isbn),
            "anio_publicacion_original": None,
        }

    def test_sin_portada_pero_con_anio(self, monkeypatch):
        isbn = "9780307474728"
        monkeypatch.setattr(openLibrary_client, "_existe_portada", lambda i: False)
        monkeypatch.setattr(
            openLibrary_client,
            "_obtener_edition",
            lambda i: {"works": [{"key": "/works/OL27258W"}]},
        )
        monkeypatch.setattr(
            openLibrary_client, "_obtener_work_id", lambda edition_data: "OL27258W"
        )
        monkeypatch.setattr(
            openLibrary_client,
            "_obtener_work",
            lambda work_id: {"first_publish_date": "1967"},
        )
        monkeypatch.setattr(
            openLibrary_client,
            "_extraer_anio_publicacion_original",
            lambda work_data: 1967,
        )

        resultado = obtener_datos_estructurados(isbn)

        assert resultado == {"portada_url": None, "anio_publicacion_original": 1967}

    def test_request_exception_en_cualquier_punto_retorna_vacio_total(self, monkeypatch):
        isbn = "9780307474728"
        monkeypatch.setattr(openLibrary_client, "_existe_portada", lambda i: True)

        def edition_que_falla(isbn):
            raise requests.ConnectionError("timeout simulado")

        monkeypatch.setattr(openLibrary_client, "_obtener_edition", edition_que_falla)

        resultado = obtener_datos_estructurados(isbn)

        assert resultado == {"portada_url": None, "anio_publicacion_original": None}