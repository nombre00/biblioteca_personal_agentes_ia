def construir_prompt_desde_configuracion(
    lineas: list[str],
    limite_parrafos: int,
    evitar_spoilers: bool | None = None,
) -> str:
    """
    Arma el segmento editable de un prompt  a partir de valores planos, sin 
    depender del ORM. Sirve tanto para una ConfiguracionPrompt guardada 
    (pasando sus campos) como para un borrador sin guardar del formulario de prueba.

    evitar_spoilers se ignora (None) para tareas donde no aplica, como
    biografía — el llamador simplemente no lo pasa o pasa None.
    """
    partes = [" ".join(lineas)] if lineas else []

    plural = "" if limite_parrafos == 1 else "s"
    partes.append(f"Extensión máxima: {limite_parrafos} párrafo{plural}.")

    if evitar_spoilers:
        partes.append(
            "Si la obra es de ficción (novela, cuento, teatro), no reveles el "
            "desenlace ni el final, ni anticipes cómo se resuelve el conflicto "
            "central. Si es una obra de no ficción (ensayo, filosofía, "
            "historia), describe el tema y el enfoque general sin listar todas "
            "sus conclusiones o argumentos punto por punto."
        )

    return " ".join(partes)