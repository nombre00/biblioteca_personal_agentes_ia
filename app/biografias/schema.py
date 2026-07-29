from datetime import datetime
from pydantic import BaseModel, ConfigDict


class BiografiaRequest(BaseModel):
    """Datos del autor enviados por Angular, necesarios para armar el prompt."""
    nombre_autor: str
    nacionalidad: str | None = None
    anio_nacimiento: int | None = None
    anio_defuncion: int | None = None


class BiografiaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    autor_id: int
    texto: str
    modelo_usado: str
    fecha_generacion: datetime