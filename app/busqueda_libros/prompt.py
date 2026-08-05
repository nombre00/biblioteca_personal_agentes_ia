def construir_prompt_clasificar_autor(
    nombre_candidato: str,
    autores_existentes: list[dict],
) -> str:
    """
    Compara el nombre de un autor candidato (obtenido de Google Books) contra
    la lista de autores ya existentes en la biblioteca, para detectar si es la
    misma persona escrita de forma distinta (ej. transliteración, orden de
    nombre/apellido distinto).

    autores_existentes: lista de dicts con forma {"id": int, "nombre": str}.

    Devuelve tres bandas posibles:
    - "existente": match seguro, se vincula directo sin preguntar al usuario.
    - "nuevo": sin parecido a ninguno existente, se crea un autor nuevo.
    - "dudoso": hay un parecido pero no es concluyente solo por el nombre;
      requiere desambiguación adicional (comparación de datos duros contra
      Wikipedia) antes de decidir.
    """
    lista_autores = "\n".join(
        f'- id={a["id"]}: "{a["nombre"]}"' for a in autores_existentes
    ) or "(no hay autores registrados todavía)"

    return f"""
Eres un asistente que compara nombres de autores para evitar duplicados en una
biblioteca personal. Los nombres pueden estar escritos de formas distintas
para la misma persona: transliteraciones distintas (ej. "Dostoievski" vs
"Fyodor Dostoevsky"), con o sin segundo nombre, en distinto orden
nombre/apellido, con o sin tildes.

Autor candidato: "{nombre_candidato}"

Autores ya existentes en la biblioteca:
{lista_autores}

Determina si el autor candidato es la misma persona que alguno de la lista.

Responde ÚNICAMENTE con un JSON con esta forma exacta, sin texto adicional,
sin markdown, sin explicación fuera del campo "motivo":

{{
  "resultado": "existente" | "nuevo" | "dudoso",
  "autor_id": <id del autor existente si "resultado" es "existente" o "dudoso", null si "nuevo">,
  "motivo": "<breve justificación de la decisión>"
}}

Usa "existente" solo si estás razonablemente seguro de que es la misma
persona. Usa "dudoso" si hay una coincidencia parcial o ambigua que no podés
resolver solo con el nombre (ej. nombres comunes, coincidencia parcial de
apellido). Usa "nuevo" si no hay ningún parecido razonable con la lista.
""".strip()


def construir_prompt_matchear_genero(
    categoria_cruda: str,
    generos_existentes: list[dict],
) -> str:
    """
    Compara una categoría cruda proveniente de Google Books (en inglés,
    formato variable, ej. "Fiction / Historical") contra la lista de géneros
    ya existentes en la biblioteca, buscando el equivalente semántico más
    cercano.

    generos_existentes: lista de dicts con forma {"id": int, "nombre": str}.
    """
    lista_generos = "\n".join(
        f'- id={g["id"]}: "{g["nombre"]}"' for g in generos_existentes
    ) or "(no hay géneros registrados todavía)"

    return f"""
Eres un asistente que normaliza categorías de libros contra una lista fija de
géneros de una biblioteca personal en español. Las categorías originales
suelen venir en inglés y con formato inconsistente (ej. "Fiction / Historical",
"Biography & Autobiography").

Categoría original: "{categoria_cruda}"

Géneros ya existentes en la biblioteca:
{lista_generos}

Determina si la categoría original corresponde, en significado, a alguno de
los géneros existentes (aunque esté en otro idioma o con otra redacción).

Responde ÚNICAMENTE con un JSON con esta forma exacta, sin texto adicional,
sin markdown:

{{
  "resultado": "existente" | "nuevo",
  "genero_id": <id del género existente si "resultado" es "existente", null si "nuevo">,
  "nombre_normalizado": "<nombre del género existente si hubo match; si es nuevo, el nombre en español, corto y en el mismo estilo que la lista>",
  "motivo": "<breve justificación de la decisión>"
}}

Usa "existente" si el significado calza con alguno de la lista, aunque la
redacción sea distinta. Usa "nuevo" solo si genuinamente no hay ningún género
existente que represente ese significado.
""".strip()


def construir_prompt_matchear_pais(
    pais_candidato: str,
    paises_existentes: list[dict],
) -> str:
    """
    Compara un país candidato (obtenido de Wikipedia, típicamente en inglés)
    contra la lista de países ya existentes en la biblioteca.

    Regla de granularidad fija: la biblioteca normaliza siempre a nivel de
    país soberano (ej. "Reino Unido"), nunca a nivel de nación constituyente
    (Inglaterra, Escocia, Gales, Irlanda del Norte se consideran todos
    "Reino Unido").

    paises_existentes: lista de dicts con forma {"id": int, "nombre": str}.
    """
    lista_paises = "\n".join(
        f'- id={p["id"]}: "{p["nombre"]}"' for p in paises_existentes
    ) or "(no hay países registrados todavía)"

    return f"""
Eres un asistente que normaliza nacionalidades/países contra una lista fija de
países de una biblioteca personal en español.

Regla de normalización OBLIGATORIA: siempre usa el nivel de país soberano, no
el de nación constituyente. Por ejemplo, "England", "Scotland", "Wales" y
"Northern Ireland" deben normalizarse todos a "Reino Unido". No crees entradas
para naciones constituyentes.

País candidato: "{pais_candidato}"

Países ya existentes en la biblioteca:
{lista_paises}

Responde ÚNICAMENTE con un JSON con esta forma exacta, sin texto adicional,
sin markdown:

{{
  "resultado": "existente" | "nuevo",
  "pais_id": <id del país existente si "resultado" es "existente", null si "nuevo">,
  "nombre_normalizado": "<nombre del país existente si hubo match; si es nuevo, el nombre del país soberano en español>",
  "motivo": "<breve justificación de la decisión>"
}}
""".strip() 