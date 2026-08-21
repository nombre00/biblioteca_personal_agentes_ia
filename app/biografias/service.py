from sqlalchemy.orm import Session

from app.biografias import repository
from app.biografias.model import BiografiaAutor
from app.biografias.prompt import construir_prompt_biografia
from app.biografias.schema import BiografiaRequest
from app.configuracion_prompt import service as configuracion_prompt_service
from app.shared.config import settings
from app.shared.llm.gemini_client import gemini_client
from app.shared.wikipedia_client import obtener_contexto


def obtener_biografia(db: Session, autor_id: int, datos: BiografiaRequest) -> BiografiaAutor:
    """
    Lazy generation: si ya existe una biografía guardada para este autor, la devuelve
    tal cual. Si no, la genera (Wikipedia -> config activa/default -> prompt -> Gemini),
    la guarda y la devuelve.
    """
    existente = repository.buscar_por_autor_id(db, autor_id)
    if existente is not None:
        return existente

    contexto_wikipedia = obtener_contexto(f"{datos.nombre_autor} writer")

    configuracion = configuracion_prompt_service.obtener_activa_o_default(
        db, tipo_tarea="biografia"
    )

    prompt = construir_prompt_biografia(
        nombre_autor=datos.nombre_autor,
        nacionalidad=datos.nacionalidad,
        anio_nacimiento=datos.anio_nacimiento,
        anio_defuncion=datos.anio_defuncion,
        contexto_wikipedia=contexto_wikipedia,
        lineas=[linea.texto for linea in configuracion.lineas],
        limite_parrafos=configuracion.limite_parrafos,
    )

    texto_generado = gemini_client.generar_texto(prompt)

    return repository.guardar(
        db,
        autor_id=autor_id,
        texto=texto_generado,
        modelo_usado=settings.gemini_model,
    ) 

def buscar_guardada(db: Session, autor_id: int) -> BiografiaAutor | None:
    """
    Devuelve la biografía ya guardada para este autor, o None si no existe.
    A diferencia de obtener_biografia, NUNCA genera ni guarda nada — es de solo lectura,
    pensado para el panel de comparación del frontend.
    """
    return repository.buscar_por_autor_id(db, autor_id)

def adoptar(db: Session, autor_id: int, texto: str) -> BiografiaAutor:
    """
    Sobrescribe (o crea) la biografía guardada con un texto ya generado externamente
    (vía /probar), sin volver a llamar a Wikipedia ni a Gemini.
    """
    return repository.guardar(
        db,
        autor_id=autor_id,
        texto=texto,
        modelo_usado=settings.gemini_model,
    )