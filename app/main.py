from fastapi import FastAPI
import logging


from app.shared.database import Base, engine

# Import necesario aunque no se use directamente: registra los modelos
# en Base.metadata para que create_all() sepa qué tablas crear.
from app.biografias.model import BiografiaAutor
from app.resumenes.model import ResumenLibro
from app.configuracion_prompt.model import ConfiguracionPrompt, LineaPrompt

from app.router import router_ia


app = FastAPI(title="agentes-ia")

logging.basicConfig(level=logging.INFO)

# Crea las tablas que todavía no existan en biblioteca_ia.
# No altera tablas ya existentes si el modelo cambia después (ver nota en contexto).
Base.metadata.create_all(bind=engine)

app.include_router(router_ia)


@app.get("/health")
def health():
    return {"status": "ok"}