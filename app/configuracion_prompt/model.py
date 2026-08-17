from sqlalchemy import (
    Column,
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
    DateTime,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.shared.database import Base


class ConfiguracionPrompt(Base):
    __tablename__ = "configuracion_prompt"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Identifica dónde se usa esta configuración: "sinopsis", "biografia", etc.
    tipo_tarea = Column(String(50), nullable=False, index=True)

    # Nombre visible para el usuario (ej. "Default", "Más formal").
    nombre = Column(String(100), nullable=False)

    # El preset sembrado con el prompt original del código, tal como estaba
    # antes de este sistema. Es de solo lectura a nivel de negocio: no se
    # edita ni se borra (regla aplicada en service.py, no solo en el modelo).
    es_default = Column(Boolean, nullable=False, default=False)

    # Cuál configuración se usa realmente al generar un prompt nuevo.
    # Solo una fila puede estar activa por tipo_tarea; esa regla se aplica
    # en service.py (al activar una, desactivar las demás de la misma tarea),
    # no se garantiza a nivel de base de datos.
    activa = Column(Boolean, nullable=False, default=False)

    limite_parrafos = Column(Integer, nullable=False)

    # Nullable a propósito: aplica a sinopsis, no a biografía. NULL significa
    # "este campo no aplica a esta tarea", no "aplica y está desactivado".
    evitar_spoilers = Column(Boolean, nullable=True)

    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())
    fecha_actualizacion = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    lineas = relationship(
        "LineaPrompt",
        back_populates="configuracion",
        order_by="LineaPrompt.orden",
        cascade="all, delete-orphan",
    )


class LineaPrompt(Base):
    __tablename__ = "linea_prompt"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    configuracion_id = Column(
        BigInteger,
        ForeignKey("configuracion_prompt.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    orden = Column(Integer, nullable=False)
    texto = Column(Text, nullable=False)

    configuracion = relationship("ConfiguracionPrompt", back_populates="lineas")