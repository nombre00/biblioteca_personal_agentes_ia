from app.shared.prompt_builder import construir_prompt_desde_configuracion


BLOQUE_SPOILERS = (
    "Si la obra es de ficción (novela, cuento, teatro), no reveles el "
    "desenlace ni el final, ni anticipes cómo se resuelve el conflicto "
    "central. Si es una obra de no ficción (ensayo, filosofía, "
    "historia), describe el tema y el enfoque general sin listar todas "
    "sus conclusiones o argumentos punto por punto."
)


class TestConstruirPromptDesdeConfiguracion:

    def test_una_linea_limite_uno_singular(self):
        resultado = construir_prompt_desde_configuracion(
            lineas=["Eres un asistente literario."],
            limite_parrafos=1,
        )

        assert resultado == (
            "Eres un asistente literario. Extensión máxima: 1 párrafo."
        )

    def test_varias_lineas_se_unen_con_espacio_simple(self):
        resultado = construir_prompt_desde_configuracion(
            lineas=["Primera línea.", "Segunda línea.", "Tercera línea."],
            limite_parrafos=2,
        )

        assert resultado.startswith(
            "Primera línea. Segunda línea. Tercera línea. "
        )
        assert "  " not in resultado

    def test_lineas_vacias_no_deja_espacio_extra_al_inicio(self):
        resultado = construir_prompt_desde_configuracion(
            lineas=[],
            limite_parrafos=1,
        )

        assert resultado == "Extensión máxima: 1 párrafo."
        assert not resultado.startswith(" ")

    def test_limite_parrafos_dos_usa_plural(self):
        resultado = construir_prompt_desde_configuracion(
            lineas=["Contexto."],
            limite_parrafos=2,
        )

        assert "Extensión máxima: 2 párrafos." in resultado

    def test_limite_parrafos_tres_usa_plural(self):
        resultado = construir_prompt_desde_configuracion(
            lineas=["Contexto."],
            limite_parrafos=3,
        )

        assert "Extensión máxima: 3 párrafos." in resultado

    def test_limite_parrafos_cero_usa_plural(self):
        resultado = construir_prompt_desde_configuracion(
            lineas=["Contexto."],
            limite_parrafos=0,
        )

        assert "Extensión máxima: 0 párrafos." in resultado

    def test_evitar_spoilers_true_agrega_bloque(self):
        resultado = construir_prompt_desde_configuracion(
            lineas=["Contexto."],
            limite_parrafos=1,
            evitar_spoilers=True,
        )

        assert BLOQUE_SPOILERS in resultado

    def test_evitar_spoilers_false_no_agrega_bloque(self):
        resultado = construir_prompt_desde_configuracion(
            lineas=["Contexto."],
            limite_parrafos=1,
            evitar_spoilers=False,
        )

        assert BLOQUE_SPOILERS not in resultado

    def test_evitar_spoilers_none_no_agrega_bloque(self):
        resultado = construir_prompt_desde_configuracion(
            lineas=["Contexto."],
            limite_parrafos=1,
            evitar_spoilers=None,
        )

        assert BLOQUE_SPOILERS not in resultado

    def test_evitar_spoilers_omitido_equivale_a_none(self):
        resultado = construir_prompt_desde_configuracion(
            lineas=["Contexto."],
            limite_parrafos=1,
        )

        assert BLOQUE_SPOILERS not in resultado

    def test_bloque_spoilers_queda_al_final(self):
        resultado = construir_prompt_desde_configuracion(
            lineas=["Contexto."],
            limite_parrafos=1,
            evitar_spoilers=True,
        )

        assert resultado == (
            "Contexto. Extensión máxima: 1 párrafo. " + BLOQUE_SPOILERS
        )