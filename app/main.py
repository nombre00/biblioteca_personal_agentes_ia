from fastapi import FastAPI

from app.shared.database import Base, engine
from app.biografias.model import BiografiaAutor
from app.resumenes.model import ResumenLibro

# Crea nuevas tablas automáticamente.
Base.metadata.create_all(bind=engine)

app = FastAPI(title="agentes-ia")