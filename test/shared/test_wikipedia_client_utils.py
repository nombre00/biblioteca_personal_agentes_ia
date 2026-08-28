from app.shared.wikipedia_client import (
    _limpiar_snippet,
    _normalizar_texto,
    _parsear_fecha_wikidata,
    _extraer_valor_claim,
    _resolver_obra_por_titulo,
)


# ---------------------------------------------------------------------------
# _limpiar_snippet
# ---------------------------------------------------------------------------

class TestLimpiarSnippet:

    def test_un_tag_se_elimina(self):
        snippet = '<span class="searchmatch">Jenofonte</span> fue un historiador.'

        assert _limpiar_snippet(snippet) == "Jenofonte fue un historiador."

    def test_multiples_tags_se_eliminan(self):
        snippet = (
            '<span class="searchmatch">Jenofonte</span> escribió sobre '
            '<span class="searchmatch">Sócrates</span>.'
        )

        assert _limpiar_snippet(snippet) == "Jenofonte escribió sobre Sócrates."

    def test_sin_tags_no_cambia(self):
        snippet = "Texto plano sin ningún tag."

        assert _limpiar_snippet(snippet) == "Texto plano sin ningún tag."

    def test_snippet_vacio(self):
        assert _limpiar_snippet("") == ""


# ---------------------------------------------------------------------------
# _normalizar_texto
# ---------------------------------------------------------------------------

class TestNormalizarTexto:

    def test_pasa_a_minusculas(self):
        assert _normalizar_texto("MEMORABILIA") == "memorabilia"

    def test_elimina_tildes(self):
        assert _normalizar_texto("Recuérdos") == "recuerdos"

    def test_elimina_ene_con_tilde(self):
        assert _normalizar_texto("Jiménez") == "jimenez"

    def test_recorta_espacios(self):
        assert _normalizar_texto("  Jenofonte  ") == "jenofonte"

    def test_combinado_mayusculas_tildes_espacios(self):
        assert _normalizar_texto("  Recuerdos de Sócrates  ") == "recuerdos de socrates"


# ---------------------------------------------------------------------------
# _parsear_fecha_wikidata
# ---------------------------------------------------------------------------

class TestParsearFechaWikidata:

    def test_precision_dia_fecha_exacta(self):
        valor = {"time": "+1821-11-11T00:00:00Z", "precision": 11}

        assert _parsear_fecha_wikidata(valor) == ("1821-11-11", None)

    def test_precision_anio_sin_fecha_exacta(self):
        valor = {"time": "+1990-00-00T00:00:00Z", "precision": 9}

        assert _parsear_fecha_wikidata(valor) == (None, 1990)

    def test_precision_decada_sin_fecha_exacta(self):
        valor = {"time": "+1980-00-00T00:00:00Z", "precision": 8}

        assert _parsear_fecha_wikidata(valor) == (None, 1980)

    def test_anio_antes_de_cristo_usa_solo_anio_aproximado(self):
        # Precisión de día, pero año negativo (a.C.): no se arma fecha ISO,
        # se cae al año aproximado igual que precisión menor.
        valor = {"time": "-0470-01-01T00:00:00Z", "precision": 11}

        assert _parsear_fecha_wikidata(valor) == (None, -470)

    def test_time_vacio(self):
        valor = {"time": "", "precision": 11}

        assert _parsear_fecha_wikidata(valor) == (None, None)

    def test_time_ausente(self):
        assert _parsear_fecha_wikidata({"precision": 11}) == (None, None)

    def test_formato_invalido_no_explota(self):
        valor = {"time": "+formato-raro", "precision": 11}

        assert _parsear_fecha_wikidata(valor) == (None, None)


# ---------------------------------------------------------------------------
# _extraer_valor_claim
# ---------------------------------------------------------------------------

class TestExtraerValorClaim:

    def test_propiedad_presente_devuelve_valor(self):
        claims = {
            "P569": [
                {"mainsnak": {"datavalue": {"value": {"time": "+1821-11-11T00:00:00Z"}}}}
            ]
        }

        resultado = _extraer_valor_claim(claims, "P569")

        assert resultado == {"time": "+1821-11-11T00:00:00Z"}

    def test_propiedad_ausente_devuelve_none(self):
        assert _extraer_valor_claim({}, "P569") is None

    def test_lista_vacia_devuelve_none(self):
        assert _extraer_valor_claim({"P569": []}, "P569") is None

    def test_estructura_incompleta_devuelve_none(self):
        claims = {"P569": [{"mainsnak": {}}]}

        assert _extraer_valor_claim(claims, "P569") is None


# ---------------------------------------------------------------------------
# _resolver_obra_por_titulo
# ---------------------------------------------------------------------------

def _info_obra(label_es=None, label_en=None, alias_es=None, alias_en=None, descripcion=None):
    return {
        "label_es": label_es,
        "label_en": label_en,
        "alias_es": alias_es or [],
        "alias_en": alias_en or [],
        "descripcion": descripcion,
    }


class TestResolverObraPorTitulo:

    def test_match_directo_en_label_es(self):
        info_obras = {"Q1": _info_obra(label_es="Recuerdos de Sócrates")}

        assert _resolver_obra_por_titulo("Recuerdos de Sócrates", info_obras) == "Q1"

    def test_match_directo_en_label_en(self):
        info_obras = {"Q1": _info_obra(label_en="Memorabilia")}

        assert _resolver_obra_por_titulo("Memorabilia", info_obras) == "Q1"

    def test_match_en_alias_es(self):
        info_obras = {"Q1": _info_obra(label_es="Otro título", alias_es=["Recuerdos de Sócrates"])}

        assert _resolver_obra_por_titulo("Recuerdos de Sócrates", info_obras) == "Q1"

    def test_match_en_alias_en(self):
        info_obras = {"Q1": _info_obra(label_en="Otro título", alias_en=["Memorabilia"])}

        assert _resolver_obra_por_titulo("Memorabilia", info_obras) == "Q1"

    def test_match_ignora_mayusculas_y_tildes(self):
        info_obras = {"Q1": _info_obra(label_es="Recuerdos de Sócrates")}

        assert _resolver_obra_por_titulo("RECUERDOS DE SOCRATES", info_obras) == "Q1"

    def test_sin_match_devuelve_none(self):
        info_obras = {"Q1": _info_obra(label_es="Anábasis")}

        assert _resolver_obra_por_titulo("Memorabilia", info_obras) is None

    def test_info_obras_vacio_devuelve_none(self):
        assert _resolver_obra_por_titulo("Memorabilia", {}) is None