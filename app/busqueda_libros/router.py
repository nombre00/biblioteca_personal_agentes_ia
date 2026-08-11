from fastapi import APIRouter, Depends

from app.busqueda_libros import service
from app.busqueda_libros.schema import (
    BusquedaLibroRequest,
    BusquedaLibrosResponse,
    ResolverLibroRequest,
    ResolverLibroResponse,
    ImportarLibroRequest,
) 
from app.shared.auth.jwt_validator import validar_jwt_interno

router = APIRouter(prefix="/busqueda-libros", tags=["busqueda-libros"])


@router.post("/buscar", response_model=BusquedaLibrosResponse)
def buscar_libros(
    datos: BusquedaLibroRequest,
    uid: str = Depends(validar_jwt_interno),
):
    return service.buscar_libros(datos)


@router.post("/resolver", response_model=ResolverLibroResponse)
def resolver_libro(
    datos: ResolverLibroRequest,
    uid: str = Depends(validar_jwt_interno),
):
    return service.resolver_libro(uid, datos)


@router.post("/importar")
def importar_libro(
    datos: ImportarLibroRequest,
    uid: str = Depends(validar_jwt_interno),
):
    return service.importar_libro(uid, datos)