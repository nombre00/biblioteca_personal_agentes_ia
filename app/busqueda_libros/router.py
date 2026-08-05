from fastapi import APIRouter, HTTPException, status
from schema import BusquedaLibroRequest, LibroExternoResponse, ImportarLibroRequest
from app.shared.google_books_client import buscar_libros_externos
from app.busqueda_libros.service import procesar_y_enriquecer_libro, enviar_libro_a_backend_java

router = APIRouter(prefix="/api/libros", tags=["Libros Externos"])


@router.get("/buscar", response_model=list[LibroExternoResponse])
def buscar_libros(query: str, max_results: int = 5):
    """
    Busca libros en la API de Google Books y los devuelve al frontend para que el usuario elija.
    """
    try:
        libros = buscar_libros_externos(query=query, max_results=max_results)
        return libros
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al buscar libros externos: {str(e)}"
        )


@router.post("/importar", status_code=status.HTTP_201_CREATED)
def importar_libro(libro_externo: LibroExternoResponse):
    """
    Recibe el libro seleccionado por el usuario desde Angular, lo procesa/enriquece con IA 
    y lo despacha al backend de Java en el puerto 8082 para su persistencia final.
    """
    try:
        # 1. Procesamos y enriquecemos con Gemini (o preparamos el DTO estructurado)
        libro_procesado = procesar_y_enriquecer_libro(libro_externo)
        
        # 2. Enviamos el payload estructurado al backend principal de Java
        resultado = enviar_libro_a_backend_java(libro_procesado)
        
        if not resultado["exito"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=resultado["mensaje"]
            )
            
        return resultado

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error inesperado al procesar la importación: {str(e)}"
        )