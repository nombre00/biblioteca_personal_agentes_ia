from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.configuracion_prompt import service
from app.configuracion_prompt.schema import (
    ConfiguracionPromptCreate,
    ConfiguracionPromptResponse,
    ConfiguracionPromptUpdate,
)
from app.shared.auth.jwt_validator import validar_jwt_interno
from app.shared.database import get_db

router = APIRouter(prefix="/configuracion-prompt", tags=["configuracion-prompt"])


@router.get("/{tipo_tarea}", response_model=list[ConfiguracionPromptResponse])
def listar(
    tipo_tarea: str,
    db: Session = Depends(get_db),
    uid: str = Depends(validar_jwt_interno),
):
    return service.listar(db, tipo_tarea)


@router.get("/detalle/{configuracion_id}", response_model=ConfiguracionPromptResponse)
def obtener(
    configuracion_id: int,
    db: Session = Depends(get_db),
    uid: str = Depends(validar_jwt_interno),
):
    return service.obtener(db, configuracion_id)


@router.post("/{tipo_tarea}", response_model=ConfiguracionPromptResponse)
def crear(
    tipo_tarea: str,
    datos: ConfiguracionPromptCreate,
    db: Session = Depends(get_db),
    uid: str = Depends(validar_jwt_interno),
):
    return service.crear(db, tipo_tarea, datos)


@router.put("/detalle/{configuracion_id}", response_model=ConfiguracionPromptResponse)
def actualizar(
    configuracion_id: int,
    datos: ConfiguracionPromptUpdate,
    db: Session = Depends(get_db),
    uid: str = Depends(validar_jwt_interno),
):
    return service.actualizar(db, configuracion_id, datos)


@router.delete("/detalle/{configuracion_id}", status_code=204)
def eliminar(
    configuracion_id: int,
    db: Session = Depends(get_db),
    uid: str = Depends(validar_jwt_interno),
):
    service.eliminar(db, configuracion_id)


@router.patch("/detalle/{configuracion_id}/activar", response_model=ConfiguracionPromptResponse)
def activar(
    configuracion_id: int,
    db: Session = Depends(get_db),
    uid: str = Depends(validar_jwt_interno),
):
    return service.activar(db, configuracion_id) 