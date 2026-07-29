# app/main.py

from fastapi import FastAPI

from app.shared.database import Base, engine

# Import necesario aunque no se use directamente: registra los modelos
# en Base.metadata para que create_all() sepa qué tablas crear.
from app.biografias.model import BiografiaAutor
from app.resumenes.model import ResumenLibro

from app.biografias.router import router as biografias_router
from app.resumenes.router import router as resumenes_router

app = FastAPI(title="agentes-ia")

# Crea las tablas que todavía no existan en biblioteca_ia.
# No altera tablas ya existentes si el modelo cambia después (ver nota en contexto).
Base.metadata.create_all(bind=engine)

app.include_router(biografias_router)
app.include_router(resumenes_router)


@app.get("/health")
def health():
    return {"status": "ok"}