from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.configuracion_prompt import repository
from app.configuracion_prompt.model import ConfiguracionPrompt
from app.configuracion_prompt.schema import (
    ConfiguracionPromptCreate,
    ConfiguracionPromptUpdate,
)

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