# Versión 2 que ocupa parámetros de config.
from app.shared.prompt_builder import construir_prompt_desde_configuracion


def construir_prompt_biografia(
    nombre_autor: str,
    nacionalidad: str | None,
    anio_nacimiento: int | None,
    anio_defuncion: int | None,
    contexto_wikipedia: str | None,
    lineas: list[str],
    limite_parrafos: int,
) -> str:
    contexto_vida = ""
    if anio_nacimiento:
        if anio_defuncion:
            contexto_vida = f" ({anio_nacimiento}-{anio_defuncion})"
        else:
            contexto_vida = f" (nacido en {anio_nacimiento})"

    contexto_nacionalidad = f", de nacionalidad {nacionalidad}," if nacionalidad else ""

    bloque_contexto = (
        f"\n\nUsa la siguiente información de referencia (en inglés) como base para la biografía:\n{contexto_wikipedia}"
        if contexto_wikipedia
        else "\n\nNo se encontró información de referencia externa; sé conservador y evita inventar datos específicos no verificables."
    )

    segmento_configuracion = construir_prompt_desde_configuracion(
        lineas=lineas,
        limite_parrafos=limite_parrafos,
        evitar_spoilers=None,  # no aplica a biografía
    )

    return (
        f"Escribe una biografía breve y objetiva del autor {nombre_autor}{contexto_vida}"
        f"{contexto_nacionalidad} en español. "
        f"{segmento_configuracion} "
        f"No incluyas títulos ni encabezados, solo el texto de la biografía."
        f"{bloque_contexto}"
    )