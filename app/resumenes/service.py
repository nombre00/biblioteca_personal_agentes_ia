from sqlalchemy.orm import Session

from app.resumenes import repository
from app.resumenes.model import ResumenLibro
from app.resumenes.prompt import construir_prompt_resumen
from app.resumenes.schema import ResumenRequest
from app.configuracion_prompt import service as configuracion_prompt_service
from app.shared.config import settings
from app.shared.llm.gemini_client import gemini_client
from app.shared.wikipedia_client import obtener_contexto_sinopsis



def obtener_resumen(db: Session, libro_id: int, datos: ResumenRequest) -> ResumenLibro:
    """
    Lazy generation: si ya existe un resumen guardado para este libro, lo devuelve
    tal cual. Si no, lo genera (Wikipedia -> config activa/default -> prompt -> Gemini),
    lo guarda y lo devuelve.
    """
    existente = repository.buscar_por_libro_id(db, libro_id)
    if existente is not None:
        return existente

    contexto_wikipedia = obtener_contexto_sinopsis(datos.titulo_libro, datos.nombre_autor)

    configuracion = configuracion_prompt_service.obtener_activa_o_default(
        db, tipo_tarea="sinopsis"
    )

    prompt = construir_prompt_resumen(
        titulo_libro=datos.titulo_libro,
        nombre_autor=datos.nombre_autor,
        genero=datos.genero,
        contexto_wikipedia=contexto_wikipedia,
        lineas=[linea.texto for linea in configuracion.lineas],
        limite_parrafos=configuracion.limite_parrafos,
        evitar_spoilers=configuracion.evitar_spoilers,
    )

    texto_generado = gemini_client.generar_texto(prompt)

    return repository.guardar(
        db,
        libro_id=libro_id,
        texto=texto_generado,
        modelo_usado=settings.gemini_model,
    ) 

def buscar_guardado(db: Session, libro_id: int) -> ResumenLibro | None:
    """
    Devuelve el resumen ya guardado para este libro, o None si no existe.
    A diferencia de obtener_resumen, NUNCA genera ni guarda nada — es de solo lectura,
    pensado para el panel de comparación del frontend.
    """
    return repository.buscar_por_libro_id(db, libro_id)

def adoptar(db: Session, libro_id: int, texto: str) -> ResumenLibro:
    """
    Sobrescribe (o crea) el resumen guardado con un texto ya generado externamente
    (vía /probar), sin volver a llamar a Wikipedia ni a Gemini.
    """
    return repository.guardar(
        db,
        libro_id=libro_id,
        texto=texto,
        modelo_usado=settings.gemini_model,
    )