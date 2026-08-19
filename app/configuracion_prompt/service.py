from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.configuracion_prompt import repository
from app.configuracion_prompt.model import ConfiguracionPrompt
from app.configuracion_prompt.schema import (
    ConfiguracionPromptCreate,
    ConfiguracionPromptUpdate,
    PruebaPromptRequest, 
    PruebaPromptResponse,
)

from app.biografias.prompt import construir_prompt_biografia
from app.resumenes.prompt import construir_prompt_resumen
from app.shared.llm.gemini_client import gemini_client
from app.shared.wikipedia_client import obtener_contexto


TIPOS_TAREA_VALIDOS = {"sinopsis", "biografia"}


def _validar_tipo_tarea(tipo_tarea: str) -> None:
    if tipo_tarea not in TIPOS_TAREA_VALIDOS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"tipo_tarea inválido: '{tipo_tarea}'",
        )


def _obtener_o_404(db: Session, configuracion_id: int) -> ConfiguracionPrompt:
    configuracion = repository.buscar_por_id(db, configuracion_id)
    if configuracion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Configuración no encontrada",
        )
    return configuracion


def listar(db: Session, tipo_tarea: str) -> list[ConfiguracionPrompt]:
    _validar_tipo_tarea(tipo_tarea)
    return repository.listar_por_tarea(db, tipo_tarea)


def obtener(db: Session, configuracion_id: int) -> ConfiguracionPrompt:
    return _obtener_o_404(db, configuracion_id)


def crear(
    db: Session, tipo_tarea: str, datos: ConfiguracionPromptCreate
) -> ConfiguracionPrompt:
    _validar_tipo_tarea(tipo_tarea)
    return repository.crear(
        db,
        tipo_tarea=tipo_tarea,
        nombre=datos.nombre,
        limite_parrafos=datos.limite_parrafos,
        evitar_spoilers=datos.evitar_spoilers,
        lineas=[linea.texto for linea in datos.lineas],
        es_default=False,
    )


def actualizar(
    db: Session, configuracion_id: int, datos: ConfiguracionPromptUpdate
) -> ConfiguracionPrompt:
    configuracion = _obtener_o_404(db, configuracion_id)

    if configuracion.es_default:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El preset default no se puede editar.",
        )

    lineas_texto = (
        [linea.texto for linea in datos.lineas] if datos.lineas is not None else None
    )

    return repository.actualizar(
        db,
        configuracion=configuracion,
        nombre=datos.nombre,
        limite_parrafos=datos.limite_parrafos,
        evitar_spoilers=datos.evitar_spoilers,
        lineas=lineas_texto,
    )


def eliminar(db: Session, configuracion_id: int) -> None:
    configuracion = _obtener_o_404(db, configuracion_id)

    if configuracion.es_default:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El preset default no se puede eliminar.",
        )

    repository.eliminar(db, configuracion)


def activar(db: Session, configuracion_id: int) -> ConfiguracionPrompt:
    configuracion = _obtener_o_404(db, configuracion_id)
    return repository.activar(db, configuracion)


def obtener_activa_o_default(db: Session, tipo_tarea: str) -> ConfiguracionPrompt:
    """Usada por resumenes/service.py y biografias/service.py en la Fase 2
    para saber con qué configuración armar el prompt. Si ni siquiera hay
    default sembrado (estado inconsistente, no debería pasar en producción
    con el seed corrido), falla fuerte en vez de devolver None silenciosamente
    — un prompt sin configuración no debería generarse nunca."""
    configuracion = repository.buscar_activa_o_default(db, tipo_tarea)
    if configuracion is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No hay configuración default para la tarea '{tipo_tarea}'. "
            "Revisar que el seed se haya ejecutado.",
        )
    return configuracion 

def probar(tipo_tarea: str, datos: PruebaPromptRequest) -> PruebaPromptResponse:
    """
    Genera un prompt a partir de un borrador de configuración (sin guardar) y
    datos reales de autor/libro, consulta Wikipedia igual que producción,
    ejecuta Gemini, y devuelve el prompt armado y el texto generado.
    No cachea ni persiste nada (a diferencia de obtener_biografia/obtener_resumen).
    """
    lineas = [linea.texto for linea in datos.lineas]

    if tipo_tarea == "biografia":
        if not datos.nombre_autor:
            raise HTTPException(
                status_code=400,
                detail="nombre_autor es obligatorio para probar un preset de biografía.",
            )

        contexto_wikipedia = obtener_contexto(f"{datos.nombre_autor} writer")

        prompt = construir_prompt_biografia(
            nombre_autor=datos.nombre_autor,
            nacionalidad=datos.nacionalidad,
            anio_nacimiento=datos.anio_nacimiento,
            anio_defuncion=datos.anio_defuncion,
            contexto_wikipedia=contexto_wikipedia,
            lineas=lineas,
            limite_parrafos=datos.limite_parrafos,
        )

    elif tipo_tarea == "sinopsis":
        if not datos.titulo_libro or not datos.nombre_autor:
            raise HTTPException(
                status_code=400,
                detail="titulo_libro y nombre_autor son obligatorios para probar un preset de sinopsis.",
            )

        contexto_wikipedia = obtener_contexto(f"{datos.titulo_libro} {datos.nombre_autor}")

        prompt = construir_prompt_resumen(
            titulo_libro=datos.titulo_libro,
            nombre_autor=datos.nombre_autor,
            genero=datos.genero,
            contexto_wikipedia=contexto_wikipedia,
            lineas=lineas,
            limite_parrafos=datos.limite_parrafos,
            evitar_spoilers=datos.evitar_spoilers,
        )

    else:
        raise HTTPException(status_code=400, detail=f"tipo_tarea desconocido: {tipo_tarea}")

    texto_generado = gemini_client.generar_texto(prompt)

    return PruebaPromptResponse(prompt=prompt, texto_generado=texto_generado)