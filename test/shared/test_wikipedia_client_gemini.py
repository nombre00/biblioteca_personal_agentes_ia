from app.shared import wikipedia_client
from app.shared.wikipedia_client import (
    _elegir_candidato_relevante,
    _elegir_candidato_biografia,
    _elegir_candidato_sinopsis,
    _elegir_autor_wikidata,
    _elegir_obra_wikidata,
)


CANDIDATOS_WIKIPEDIA = [
    {"titulo": "Richard Francis Burton", "snippet": "explorador y escritor británico"},
    {"titulo": "Richard Francis Burton bibliography", "snippet": "lista de obras"},
    {"titulo": "Premio Eagle", "snippet": "premio literario cofundado por Richard Burton"},
]

CANDIDATOS_WIKIDATA_AUTOR = [
    {"qid": "Q192515", "label": "Jenofonte", "description": "historiador y filósofo griego"},
    {"qid": "Q3806", "label": "Jenofonte de Éfeso", "description": "novelista griego"},
]

INFO_OBRAS_WIKIDATA = {
    "Q123": {"label_es": "Anábasis", "label_en": "Anabasis", "descripcion": "obra sobre una expedición"},
    "Q456": {"label_es": None, "label_en": "Memorabilia", "descripcion": "diálogos socráticos"},
}


def _mockear_gemini(monkeypatch, respuesta=None, excepcion=None):
    """Reemplaza gemini_client.generar_texto con un valor fijo o una excepción."""
    def fake_generar_texto(prompt):
        if excepcion:
            raise excepcion
        return respuesta

    monkeypatch.setattr(wikipedia_client.gemini_client, "generar_texto", fake_generar_texto)


# ---------------------------------------------------------------------------
# _elegir_candidato_relevante
# ---------------------------------------------------------------------------

class TestElegirCandidatoRelevante:

    def test_candidatos_vacios_no_llama_a_gemini(self, monkeypatch):
        llamado = []
        _mockear_gemini(monkeypatch, respuesta="1")
        monkeypatch.setattr(
            wikipedia_client.gemini_client,
            "generar_texto",
            lambda p: llamado.append(True) or "1",
        )

        resultado = _elegir_candidato_relevante("query", [])

        assert resultado is None
        assert llamado == []

    def test_respuesta_numerica_valida_elige_candidato(self, monkeypatch):
        _mockear_gemini(monkeypatch, respuesta="1")

        resultado = _elegir_candidato_relevante("Richard Burton", CANDIDATOS_WIKIPEDIA)

        assert resultado == "Richard Francis Burton"

    def test_respuesta_ninguno_devuelve_none(self, monkeypatch):
        _mockear_gemini(monkeypatch, respuesta="NINGUNO")

        resultado = _elegir_candidato_relevante("query inexistente", CANDIDATOS_WIKIPEDIA)

        assert resultado is None

    def test_respuesta_no_interpretable_devuelve_none(self, monkeypatch):
        _mockear_gemini(monkeypatch, respuesta="no estoy seguro")

        resultado = _elegir_candidato_relevante("query", CANDIDATOS_WIKIPEDIA)

        assert resultado is None

    def test_indice_fuera_de_rango_devuelve_none(self, monkeypatch):
        _mockear_gemini(monkeypatch, respuesta="99")

        resultado = _elegir_candidato_relevante("query", CANDIDATOS_WIKIPEDIA)

        assert resultado is None

    def test_excepcion_de_gemini_devuelve_none(self, monkeypatch):
        _mockear_gemini(monkeypatch, excepcion=RuntimeError("fallo de API"))

        resultado = _elegir_candidato_relevante("query", CANDIDATOS_WIKIPEDIA)

        assert resultado is None


# ---------------------------------------------------------------------------
# _elegir_candidato_biografia
# ---------------------------------------------------------------------------

class TestElegirCandidatoBiografia:

    def test_candidatos_vacios_no_llama_a_gemini(self, monkeypatch):
        llamado = []
        monkeypatch.setattr(
            wikipedia_client.gemini_client,
            "generar_texto",
            lambda p: llamado.append(True) or "1",
        )

        resultado = _elegir_candidato_biografia("query", [])

        assert resultado is None
        assert llamado == []

    def test_prioriza_articulo_principal_sobre_bibliografia(self, monkeypatch):
        # Caso real documentado en el código: Gemini debe elegir el
        # artículo principal (índice 1) y no la bibliografía (índice 2).
        _mockear_gemini(monkeypatch, respuesta="1")

        resultado = _elegir_candidato_biografia("Richard Burton", CANDIDATOS_WIKIPEDIA)

        assert resultado == "Richard Francis Burton"

    def test_respuesta_ninguno_devuelve_none(self, monkeypatch):
        _mockear_gemini(monkeypatch, respuesta="NINGUNO")

        resultado = _elegir_candidato_biografia("query inexistente", CANDIDATOS_WIKIPEDIA)

        assert resultado is None

    def test_respuesta_no_interpretable_devuelve_none(self, monkeypatch):
        _mockear_gemini(monkeypatch, respuesta="tal vez el segundo")

        resultado = _elegir_candidato_biografia("query", CANDIDATOS_WIKIPEDIA)

        assert resultado is None

    def test_indice_fuera_de_rango_devuelve_none(self, monkeypatch):
        _mockear_gemini(monkeypatch, respuesta="50")

        resultado = _elegir_candidato_biografia("query", CANDIDATOS_WIKIPEDIA)

        assert resultado is None

    def test_excepcion_de_gemini_devuelve_none(self, monkeypatch):
        _mockear_gemini(monkeypatch, excepcion=RuntimeError("fallo de API"))

        resultado = _elegir_candidato_biografia("query", CANDIDATOS_WIKIPEDIA)

        assert resultado is None


# ---------------------------------------------------------------------------
# _elegir_candidato_sinopsis
# ---------------------------------------------------------------------------

class TestElegirCandidatoSinopsis:

    def test_candidatos_vacios_no_llama_a_gemini(self, monkeypatch):
        llamado = []
        monkeypatch.setattr(
            wikipedia_client.gemini_client,
            "generar_texto",
            lambda p: llamado.append(True) or "1",
        )

        resultado = _elegir_candidato_sinopsis("query", [])

        assert resultado is None
        assert llamado == []

    def test_respuesta_numerica_valida_elige_candidato(self, monkeypatch):
        _mockear_gemini(monkeypatch, respuesta="3")

        resultado = _elegir_candidato_sinopsis("query", CANDIDATOS_WIKIPEDIA)

        assert resultado == "Premio Eagle"

    def test_respuesta_ninguno_devuelve_none(self, monkeypatch):
        _mockear_gemini(monkeypatch, respuesta="NINGUNO")

        resultado = _elegir_candidato_sinopsis("query inexistente", CANDIDATOS_WIKIPEDIA)

        assert resultado is None

    def test_respuesta_no_interpretable_devuelve_none(self, monkeypatch):
        _mockear_gemini(monkeypatch, respuesta="ninguno de estos me convence")

        # Nota: esta respuesta empieza con "ninguno" en minúscula seguido de
        # más texto — igual matchea el chequeo .upper().startswith("NINGUNO"),
        # así que el resultado esperado es None por esa vía, no por regex.
        resultado = _elegir_candidato_sinopsis("query", CANDIDATOS_WIKIPEDIA)

        assert resultado is None

    def test_respuesta_sin_numero_ni_ninguno_devuelve_none(self, monkeypatch):
        _mockear_gemini(monkeypatch, respuesta="no lo sé")

        resultado = _elegir_candidato_sinopsis("query", CANDIDATOS_WIKIPEDIA)

        assert resultado is None

    def test_indice_fuera_de_rango_devuelve_none(self, monkeypatch):
        _mockear_gemini(monkeypatch, respuesta="7")

        resultado = _elegir_candidato_sinopsis("query", CANDIDATOS_WIKIPEDIA)

        assert resultado is None

    def test_excepcion_de_gemini_devuelve_none(self, monkeypatch):
        _mockear_gemini(monkeypatch, excepcion=RuntimeError("fallo de API"))

        resultado = _elegir_candidato_sinopsis("query", CANDIDATOS_WIKIPEDIA)

        assert resultado is None


# ---------------------------------------------------------------------------
# _elegir_autor_wikidata
# ---------------------------------------------------------------------------

class TestElegirAutorWikidata:

    def test_candidatos_vacios_no_llama_a_gemini(self, monkeypatch):
        llamado = []
        monkeypatch.setattr(
            wikipedia_client.gemini_client,
            "generar_texto",
            lambda p: llamado.append(True) or "1",
        )

        resultado = _elegir_autor_wikidata("query", [])

        assert resultado is None
        assert llamado == []

    def test_respuesta_numerica_valida_elige_qid(self, monkeypatch):
        _mockear_gemini(monkeypatch, respuesta="1")

        resultado = _elegir_autor_wikidata("Jenofonte", CANDIDATOS_WIKIDATA_AUTOR)

        assert resultado == "Q192515"

    def test_elige_segundo_candidato_homonimo(self, monkeypatch):
        _mockear_gemini(monkeypatch, respuesta="2")

        resultado = _elegir_autor_wikidata("Jenofonte de Éfeso", CANDIDATOS_WIKIDATA_AUTOR)

        assert resultado == "Q3806"

    def test_respuesta_ninguno_devuelve_none(self, monkeypatch):
        _mockear_gemini(monkeypatch, respuesta="NINGUNO")

        resultado = _elegir_autor_wikidata("autor inexistente", CANDIDATOS_WIKIDATA_AUTOR)

        assert resultado is None

    def test_respuesta_no_interpretable_devuelve_none(self, monkeypatch):
        _mockear_gemini(monkeypatch, respuesta="difícil de saber")

        resultado = _elegir_autor_wikidata("query", CANDIDATOS_WIKIDATA_AUTOR)

        assert resultado is None

    def test_indice_fuera_de_rango_devuelve_none(self, monkeypatch):
        _mockear_gemini(monkeypatch, respuesta="10")

        resultado = _elegir_autor_wikidata("query", CANDIDATOS_WIKIDATA_AUTOR)

        assert resultado is None

    def test_excepcion_de_gemini_devuelve_none(self, monkeypatch):
        _mockear_gemini(monkeypatch, excepcion=RuntimeError("fallo de API"))

        resultado = _elegir_autor_wikidata("query", CANDIDATOS_WIKIDATA_AUTOR)

        assert resultado is None


# ---------------------------------------------------------------------------
# _elegir_obra_wikidata
# ---------------------------------------------------------------------------

class TestElegirObraWikidata:

    def test_info_obras_vacio_no_llama_a_gemini(self, monkeypatch):
        llamado = []
        monkeypatch.setattr(
            wikipedia_client.gemini_client,
            "generar_texto",
            lambda p: llamado.append(True) or "1",
        )

        resultado = _elegir_obra_wikidata("Memorabilia", {})

        assert resultado is None
        assert llamado == []

    def test_respuesta_numerica_valida_elige_qid(self, monkeypatch):
        _mockear_gemini(monkeypatch, respuesta="2")

        resultado = _elegir_obra_wikidata("Memorabilia", INFO_OBRAS_WIKIDATA)

        assert resultado == "Q456"

    def test_respuesta_ninguno_devuelve_none(self, monkeypatch):
        _mockear_gemini(monkeypatch, respuesta="NINGUNO")

        resultado = _elegir_obra_wikidata("obra inexistente", INFO_OBRAS_WIKIDATA)

        assert resultado is None

    def test_respuesta_no_interpretable_devuelve_none(self, monkeypatch):
        _mockear_gemini(monkeypatch, respuesta="podría ser cualquiera")

        resultado = _elegir_obra_wikidata("query", INFO_OBRAS_WIKIDATA)

        assert resultado is None

    def test_indice_fuera_de_rango_devuelve_none(self, monkeypatch):
        _mockear_gemini(monkeypatch, respuesta="9")

        resultado = _elegir_obra_wikidata("query", INFO_OBRAS_WIKIDATA)

        assert resultado is None

    def test_excepcion_de_gemini_devuelve_none(self, monkeypatch):
        _mockear_gemini(monkeypatch, excepcion=RuntimeError("fallo de API"))

        resultado = _elegir_obra_wikidata("query", INFO_OBRAS_WIKIDATA)

        assert resultado is None