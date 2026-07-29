from sqlalchemy import Column, BigInteger, Text, String, DateTime
from sqlalchemy.sql import func

from app.shared.database import Base


class BiografiaAutor(Base):
    __tablename__ = "biografia_autor"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    autor_id = Column(BigInteger, nullable=False, unique=True, index=True)
    texto = Column(Text, nullable=False)
    modelo_usado = Column(String(100), nullable=False)
    fecha_generacion = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())