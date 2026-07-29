from sqlalchemy import Column, BigInteger, Text, String, DateTime
from sqlalchemy.sql import func

from app.shared.database import Base


class ResumenLibro(Base):
    __tablename__ = "resumen_libro"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    libro_id = Column(BigInteger, nullable=False, unique=True, index=True)
    texto = Column(Text, nullable=False)
    modelo_usado = Column(String(100), nullable=False)
    fecha_generacion = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())