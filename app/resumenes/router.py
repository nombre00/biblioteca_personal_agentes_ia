from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.resumenes import service
from app.resumenes.schema import ResumenRequest, ResumenResponse
from app.shared.auth.jwt_validator import validar_jwt_interno
from app.shared.database import get_db

router = APIRouter(prefix="/resumenes", tags=["resumenes"])


@router.post("/{libro_id}", response_model=ResumenResponse)
def obtener_resumen(
    libro_id: int,
    datos: ResumenRequest,
    db: Session = Depends(get_db),
    uid: str = Depends(validar_jwt_interno),
):
    return service.obtener_resumen(db, libro_id, datos) 