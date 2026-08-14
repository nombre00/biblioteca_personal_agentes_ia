# app/router.py

from fastapi import APIRouter

from app.biografias.router import router as biografias_router
from app.resumenes.router import router as resumenes_router
from app.busqueda_libros.router import router as busqueda_libros_router

router_ia = APIRouter(prefix="/ia")

router_ia.include_router(biografias_router)
router_ia.include_router(resumenes_router)
router_ia.include_router(busqueda_libros_router)