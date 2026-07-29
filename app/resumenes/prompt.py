def construir_prompt_resumen(
    titulo_libro: str,
    nombre_autor: str,
    genero: str | None,
    contexto_wikipedia: str | None,
) -> str:
    contexto_genero = f" del género {genero}" if genero else ""

    bloque_contexto = (
        f"\n\nUsa la siguiente información de referencia (en inglés) como base para el resumen:\n{contexto_wikipedia}"
        if contexto_wikipedia
        else "\n\nNo se encontró información de referencia externa; sé conservador y evita inventar detalles de la trama no verificables."
    )

    return (
        f"Escribe un resumen breve y objetivo del libro '{titulo_libro}', escrito por {nombre_autor}"
        f"{contexto_genero}, en español. "
        f"Enfócate en la premisa general y el contexto de la obra, sin revelar el final ni detalles clave de la trama (evita spoilers). "
        f"Extensión máxima: 2 párrafos. No incluyas títulos ni encabezados, solo el texto del resumen."
        f"{bloque_contexto}"
    )