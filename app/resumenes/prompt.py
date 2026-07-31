def construir_prompt_resumen(
    titulo_libro: str,
    nombre_autor: str,
    genero: str | None,
    contexto_wikipedia: str | None,
) -> str:
    contexto_genero = f" del género {genero}" if genero else ""

    bloque_contexto = (
        f"\n\nUsa la siguiente información de referencia (en inglés) como base para la sinopsis:\n{contexto_wikipedia}"
        if contexto_wikipedia
        else "\n\nNo se encontró información de referencia externa; sé conservador y evita inventar detalles de la trama no verificables."
    )

    return (
        f"Escribe una sinopsis breve y objetiva del libro '{titulo_libro}', escrito por {nombre_autor}"
        f"{contexto_genero}, en español. "
        f"Una sinopsis presenta la premisa, el escenario y los personajes o ideas centrales de la obra, "
        f"tal como aparecería en la contraportada de un libro — NO es un resumen capítulo a capítulo ni un relato del desarrollo completo de la trama. "
        f"Si la obra es de ficción (novela, cuento, teatro), no reveles el desenlace ni el final, ni anticipes cómo se resuelve el conflicto central. "
        f"Si es una obra de no ficción (ensayo, filosofía, historia), describe el tema y el enfoque general sin listar todas sus conclusiones o argumentos punto por punto. "
        f"Extensión máxima: 2 párrafos. No incluyas títulos ni encabezados, solo el texto de la sinopsis."
        f"{bloque_contexto}"
    )