def construir_prompt_biografia(
    nombre_autor: str,
    nacionalidad: str | None,
    anio_nacimiento: int | None,
    anio_defuncion: int | None,
    contexto_wikipedia: str | None,
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

    return (
        f"Escribe una biografía breve y objetiva del autor {nombre_autor}{contexto_vida}"
        f"{contexto_nacionalidad} en español. "
        f"Enfócate en su trayectoria literaria, obras más relevantes y contexto histórico. "
        f"Extensión máxima: 3 párrafos. No incluyas títulos ni encabezados, solo el texto de la biografía."
        f"{bloque_contexto}"
    )