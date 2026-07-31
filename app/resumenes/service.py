from sqlalchemy.orm import Session

from app.resumenes import repository
from app.resumenes.model import ResumenLibro
from app.resumenes.prompt import construir_prompt_resumen
from app.resumenes.schema import ResumenRequest
from app.shared.config import settings
from app.shared.llm.gemini_client import gemini_client
from app.shared.wikipedia_client import obtener_contexto


def obtener_resumen(db: Session, libro_id: int, datos: ResumenRequest) -> ResumenLibro:
    """
    Lazy generation: si ya existe un resumen guardado para este libro, lo devuelve
    tal cual. Si no, lo genera (Wikipedia -> prompt -> Gemini), lo guarda y lo devuelve.
    """
    existente = repository.buscar_por_libro_id(db, libro_id)
    if existente is not None:
        return existente

    contexto_wikipedia = obtener_contexto(f"{datos.titulo_libro} {datos.nombre_autor}")

    prompt = construir_prompt_resumen(
        titulo_libro=datos.titulo_libro,
        nombre_autor=datos.nombre_autor,
        genero=datos.genero,
        contexto_wikipedia=contexto_wikipedia,
    )

    texto_generado = gemini_client.generar_texto(prompt)

    return repository.guardar(
        db,
        libro_id=libro_id,
        texto=texto_generado,
        modelo_usado=settings.gemini_model,
    )