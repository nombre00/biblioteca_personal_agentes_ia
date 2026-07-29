from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ResumenRequest(BaseModel):
    """Datos del libro enviados por Angular, necesarios para armar el prompt."""
    titulo_libro: str
    nombre_autor: str
    genero: str | None = None


class ResumenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    libro_id: int
    texto: str
    modelo_usado: str
    fecha_generacion: datetime