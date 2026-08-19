# Versión 2 que ocupa parámetros de config.
from app.shared.prompt_builder import construir_prompt_desde_configuracion


def construir_prompt_resumen(
    titulo_libro: str,
    nombre_autor: str,
    genero: str | None,
    contexto_wikipedia: str | None,
    lineas: list[str],
    limite_parrafos: int,
    evitar_spoilers: bool | None,
) -> str:
    contexto_genero = f" del género {genero}" if genero else ""

    bloque_contexto = (
        f"\n\nUsa la siguiente información de referencia (en inglés) como base para la sinopsis:\n{contexto_wikipedia}"
        if contexto_wikipedia
        else "\n\nNo se encontró información de referencia externa; sé conservador y evita inventar detalles de la trama no verificables."
    )

    segmento_configuracion = construir_prompt_desde_configuracion(
        lineas=lineas,
        limite_parrafos=limite_parrafos,
        evitar_spoilers=evitar_spoilers,
    )

    return (
        f"Escribe una sinopsis breve y objetiva del libro '{titulo_libro}', escrito por {nombre_autor}"
        f"{contexto_genero}, en español. "
        f"{segmento_configuracion} "
        f"No incluyas títulos ni encabezados, solo el texto de la sinopsis."
        f"{bloque_contexto}"
    ) 