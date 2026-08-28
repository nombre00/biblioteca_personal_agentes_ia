import requests

from app.shared import google_books_client
from app.shared.google_books_client import buscar_libros_externos


class FakeResponse:
    """Simula una respuesta de requests con los métodos que usa el cliente."""

    def __init__(self, json_data: dict, status_code: int = 200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._json_data


def _item(
    google_id="abc123",
    titulo="Un título",
    autores=None,
    idioma="es",
    categorias=None,
    published_date="2020-05-12",
    descripcion="Una descripción.",
    image_links=None,
    industry_identifiers=None,
):
    """Arma un item crudo con la forma que devuelve Google Books, con
    defaults razonables para no repetir estructura en cada test."""
    return {
        "id": google_id,
        "volumeInfo": {
            "title": titulo,
            "authors": autores if autores is not None else ["Autor Uno"],
            "language": idioma,
            "categories": categorias if categorias is not None else ["Ficción"],
            "publishedDate": published_date,
            "description": descripcion,
            "imageLinks": image_links if image_links is not None else {},
            "industryIdentifiers": (
                industry_identifiers if industry_identifiers is not None else []
            ),
        },
    }


class TestBuscarLibrosExternos:

    def test_mapeo_completo_de_un_item(self, monkeypatch):
        item = _item(
            google_id="xyz1",
            titulo="Cien años de soledad",
            autores=["Gabriel García Márquez"],
            idioma="es",
            categorias=["Realismo mágico"],
            published_date="1967-05-30",
            descripcion="La historia de la familia Buendía.",
            image_links={"thumbnail": "http://books.google.com/thumb.jpg"},
            industry_identifiers=[
                {"type": "ISBN_13", "identifier": "9780307474728"}
            ],
        )
        respuesta = FakeResponse({"items": [item], "totalItems": 1})
        monkeypatch.setattr(
            google_books_client.requests, "get", lambda *a, **k: respuesta
        )

        resultado = buscar_libros_externos("cien años de soledad")

        assert resultado["total_items"] == 1
        assert len(resultado["items"]) == 1
        libro = resultado["items"][0]
        assert libro["google_id"] == "xyz1"
        assert libro["titulo"] == "Cien años de soledad"
        assert libro["autores"] == ["Gabriel García Márquez"]
        assert libro["idioma"] == "es"
        assert libro["categorias"] == ["Realismo mágico"]
        assert libro["anio_publicacion"] == 1967
        assert libro["descripcion"] == "La historia de la familia Buendía."
        assert libro["portada_url"] == "https://books.google.com/thumb.jpg"
        assert libro["isbn"] == "9780307474728"

    def test_sin_industry_identifiers_isbn_none(self, monkeypatch):
        item = _item(industry_identifiers=[])
        respuesta = FakeResponse({"items": [item], "totalItems": 1})
        monkeypatch.setattr(
            google_books_client.requests, "get", lambda *a, **k: respuesta
        )

        resultado = buscar_libros_externos("query")

        assert resultado["items"][0]["isbn"] is None

    def test_industry_identifiers_sin_isbn_valido_isbn_none(self, monkeypatch):
        item = _item(
            industry_identifiers=[{"type": "OTHER", "identifier": "some-id"}]
        )
        respuesta = FakeResponse({"items": [item], "totalItems": 1})
        monkeypatch.setattr(
            google_books_client.requests, "get", lambda *a, **k: respuesta
        )

        resultado = buscar_libros_externos("query")

        assert resultado["items"][0]["isbn"] is None

    def test_toma_isbn_10_si_no_hay_isbn_13(self, monkeypatch):
        item = _item(
            industry_identifiers=[{"type": "ISBN_10", "identifier": "0307474720"}]
        )
        respuesta = FakeResponse({"items": [item], "totalItems": 1})
        monkeypatch.setattr(
            google_books_client.requests, "get", lambda *a, **k: respuesta
        )

        resultado = buscar_libros_externos("query")

        assert resultado["items"][0]["isbn"] == "0307474720"

    def test_published_date_formato_completo_extrae_anio(self, monkeypatch):
        item = _item(published_date="2020-05-12")
        respuesta = FakeResponse({"items": [item], "totalItems": 1})
        monkeypatch.setattr(
            google_books_client.requests, "get", lambda *a, **k: respuesta
        )

        resultado = buscar_libros_externos("query")

        assert resultado["items"][0]["anio_publicacion"] == 2020

    def test_published_date_vacio_anio_none(self, monkeypatch):
        item = _item(published_date="")
        respuesta = FakeResponse({"items": [item], "totalItems": 1})
        monkeypatch.setattr(
            google_books_client.requests, "get", lambda *a, **k: respuesta
        )

        resultado = buscar_libros_externos("query")

        assert resultado["items"][0]["anio_publicacion"] is None

    def test_published_date_formato_invalido_anio_none(self, monkeypatch):
        item = _item(published_date="s.f.")
        respuesta = FakeResponse({"items": [item], "totalItems": 1})
        monkeypatch.setattr(
            google_books_client.requests, "get", lambda *a, **k: respuesta
        )

        resultado = buscar_libros_externos("query")

        assert resultado["items"][0]["anio_publicacion"] is None

    def test_orden_de_preferencia_de_portada(self, monkeypatch):
        item = _item(
            image_links={
                "smallThumbnail": "https://x/small_thumb.jpg",
                "thumbnail": "https://x/thumb.jpg",
                "medium": "https://x/medium.jpg",
                "small": "https://x/small.jpg",
            }
        )
        respuesta = FakeResponse({"items": [item], "totalItems": 1})
        monkeypatch.setattr(
            google_books_client.requests, "get", lambda *a, **k: respuesta
        )

        resultado = buscar_libros_externos("query")

        assert resultado["items"][0]["portada_url"] == "https://x/small.jpg"

    def test_portada_http_se_fuerza_a_https(self, monkeypatch):
        item = _item(image_links={"thumbnail": "http://x/thumb.jpg"})
        respuesta = FakeResponse({"items": [item], "totalItems": 1})
        monkeypatch.setattr(
            google_books_client.requests, "get", lambda *a, **k: respuesta
        )

        resultado = buscar_libros_externos("query")

        assert resultado["items"][0]["portada_url"] == "https://x/thumb.jpg"

    def test_sin_image_links_portada_vacia(self, monkeypatch):
        item = _item(image_links={})
        respuesta = FakeResponse({"items": [item], "totalItems": 1})
        monkeypatch.setattr(
            google_books_client.requests, "get", lambda *a, **k: respuesta
        )

        resultado = buscar_libros_externos("query")

        assert resultado["items"][0]["portada_url"] == ""

    def test_items_vacios_retorna_total_items_real(self, monkeypatch):
        respuesta = FakeResponse({"items": [], "totalItems": 42})
        monkeypatch.setattr(
            google_books_client.requests, "get", lambda *a, **k: respuesta
        )

        resultado = buscar_libros_externos("query")

        assert resultado == {"items": [], "total_items": 42}

    def test_multiples_items_se_mapean_todos(self, monkeypatch):
        items = [
            _item(google_id="1", titulo="Libro Uno"),
            _item(google_id="2", titulo="Libro Dos"),
            _item(google_id="3", titulo="Libro Tres"),
        ]
        respuesta = FakeResponse({"items": items, "totalItems": 3})
        monkeypatch.setattr(
            google_books_client.requests, "get", lambda *a, **k: respuesta
        )

        resultado = buscar_libros_externos("query")

        assert len(resultado["items"]) == 3
        assert [libro["google_id"] for libro in resultado["items"]] == [
            "1",
            "2",
            "3",
        ]

    def test_request_exception_retorna_vacio_sin_explotar(self, monkeypatch):
        def get_que_falla(*args, **kwargs):
            raise requests.ConnectionError("timeout simulado")

        monkeypatch.setattr(google_books_client.requests, "get", get_que_falla)

        resultado = buscar_libros_externos("query")

        assert resultado == {"items": [], "total_items": 0}

    def test_params_enviados_a_requests_get(self, monkeypatch):
        capturado = {}

        def get_espia(url, params=None, timeout=None):
            capturado["url"] = url
            capturado["params"] = params
            capturado["timeout"] = timeout
            return FakeResponse({"items": [], "totalItems": 0})

        monkeypatch.setattr(google_books_client.requests, "get", get_espia)
        monkeypatch.setattr(
            google_books_client.settings, "google_books_api_key", "test-key-123"
        )

        buscar_libros_externos("dune", max_results=10, start_index=20)

        assert capturado["params"]["q"] == "dune"
        assert capturado["params"]["maxResults"] == 10
        assert capturado["params"]["startIndex"] == 20
        assert capturado["params"]["key"] == "test-key-123"