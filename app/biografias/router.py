from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.biografias import service
from app.biografias.schema import BiografiaRequest, BiografiaResponse
from app.shared.auth.jwt_validator import validar_jwt_interno
from app.shared.database import get_db

router = APIRouter(prefix="/biografias", tags=["biografias"])


@router.post("/{autor_id}", response_model=BiografiaResponse)
def obtener_biografia(
    autor_id: int,
    datos: BiografiaRequest,
    db: Session = Depends(get_db),
    uid: str = Depends(validar_jwt_interno),
):
    return service.obtener_biografia(db, autor_id, datos)