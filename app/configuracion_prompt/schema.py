from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


# ==========================================
# LineaPrompt
# ==========================================

class LineaPromptCreate(BaseModel):
    """Una línea libre del prompt, tal como la envía el usuario al crear
    o editar un preset. El orden lo determina la posición en la lista
    que llega desde Angular, no un campo propio del payload."""
    texto: str


class LineaPromptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    orden: int
    texto: str


# ==========================================
# ConfiguracionPrompt
# ==========================================

class ConfiguracionPromptCreate(BaseModel):
    """Payload para crear un preset nuevo. tipo_tarea, es_default y activa
    NO vienen del usuario: tipo_tarea se fija por endpoint/ruta, es_default
    siempre nace en False (se siembra aparte), y activa se maneja con un
    endpoint separado (activar), no en la creación."""
    nombre: str
    limite_parrafos: int = Field(gt=0)
    evitar_spoilers: bool | None = None
    lineas: list[LineaPromptCreate]


class ConfiguracionPromptUpdate(BaseModel):
    """Payload para editar un preset existente. Todos los campos opcionales
    (edición parcial). No incluye es_default ni activa a propósito:
    - es_default nunca se edita (regla de negocio, aplicada en el service).
    - activa se cambia solo vía el endpoint de activación, nunca mezclado
      con una edición de contenido.
    """
    nombre: str | None = None
    limite_parrafos: int | None = Field(default=None, gt=0)
    evitar_spoilers: bool | None = None
    lineas: list[LineaPromptCreate] | None = None


class ConfiguracionPromptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo_tarea: str
    nombre: str
    es_default: bool
    activa: bool
    limite_parrafos: int
    evitar_spoilers: bool | None
    fecha_creacion: datetime
    fecha_actualizacion: datetime
    lineas: list[LineaPromptResponse]