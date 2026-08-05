from pydantic import BaseModel, Field
from typing import Optional, List, Literal, Union
from datetime import date


# ==========================================
# 1. Esquemas para Búsqueda Externa (Google Books)
# ========================================== 

class BusquedaLibroRequest(BaseModel):
    """Esquema para recibir la consulta de búsqueda desde el frontend."""
    query: str = Field(..., min_length=1, description="Título o autor a buscar")
    max_results: Optional[int] = Field(40, ge=1, le=40)


class LibroExternoResponse(BaseModel):
    """Esquema de un libro devuelto por Google Books para que el usuario elija.

    El frontend retiene la lista completa en memoria; al elegir uno, se
    reenvía tal cual (con un solo autor ya seleccionado si había varios)
    al endpoint de resolución. No hay estado guardado en agentes-ia entre
    la búsqueda y la resolución.
    """
    google_id: str
    titulo: str
    autores: List[str]
    idioma: Optional[str] = None
    categorias: List[str] = []
    anio_publicacion: Optional[int] = None
    descripcion: Optional[str] = ""
    portada_url: Optional[str] = ""
    isbn: Optional[str] = None


# ==========================================
# 2. Esquemas de Soporte (datos "nuevo" de Autor, País, Género)
# ==========================================

class PaisCreateSchema(BaseModel):
    """Datos para crear un país nuevo (no existe match en la tabla Pais)."""
    nombre: str


class GeneroCreateSchema(BaseModel):
    """Datos para crear un género nuevo (no existe match en la tabla Genero).

    icono_slug queda en None: los íconos son PNGs curados a mano por Leo,
    un género creado automáticamente no tiene ícono propio todavía.
    """
    nombre: str
    icono_slug: Optional[str] = None


class AutorCreateSchema(BaseModel):
    """Datos para crear un autor nuevo (no existe match, o el usuario
    confirmó que es una persona distinta a un candidato dudoso)."""
    nombre: str
    idioma: Optional[str] = None
    pais: Optional["PaisResolucion"] = None
    retrato_url: Optional[str] = None
    fecha_nacimiento: Optional[date] = None
    anio_nacimiento_aprox: Optional[int] = None
    fecha_defuncion: Optional[date] = None
    anio_defuncion_aprox: Optional[int] = None


# ==========================================
# 3. Resoluciones: existente vs. nuevo (discriminated unions)
# ==========================================
#
# Cada entidad (pais, genero, autor) puede resolverse de dos formas
# distintas: "vincular a algo que ya existe" (solo se necesita el id) o
# "crear algo nuevo" (se necesitan los datos completos). El campo `tipo`
# discrimina cuál de las dos aplica, para que no haya ambigüedad al
# armar el payload final hacia Java.

class PaisResolucionExistente(BaseModel):
    tipo: Literal["existente"] = "existente"
    pais_id: int
    nombre: str


class PaisResolucionNueva(BaseModel):
    tipo: Literal["nuevo"] = "nuevo"
    datos: PaisCreateSchema


PaisResolucion = Union[PaisResolucionExistente, PaisResolucionNueva]


class GeneroResolucionExistente(BaseModel):
    tipo: Literal["existente"] = "existente"
    genero_id: int
    nombre: str


class GeneroResolucionNueva(BaseModel):
    tipo: Literal["nuevo"] = "nuevo"
    datos: GeneroCreateSchema


GeneroResolucion = Union[GeneroResolucionExistente, GeneroResolucionNueva]


class AutorResolucionExistente(BaseModel):
    """Match seguro: se vincula directo al autor ya existente."""
    tipo: Literal["existente"] = "existente"
    autor_id: int
    nombre: str


class AutorResolucionNueva(BaseModel):
    """Sin match: se crea un autor nuevo."""
    tipo: Literal["nuevo"] = "nuevo"
    datos: AutorCreateSchema


class AutorResolucionPendiente(BaseModel):
    """Match dudoso que ni el filtro LLM ni la comparación contra Wikipedia
    lograron confirmar o descartar con confianza. El frontend debe
    preguntarle al usuario si es el mismo autor o uno distinto, y con esa
    respuesta armar el AutorImportSchema final (existente o nuevo)."""
    tipo: Literal["requiere_confirmacion"] = "requiere_confirmacion"
    autor_id_candidato: int
    nombre_candidato: str
    datos_si_es_nuevo: AutorCreateSchema
    motivo: str


AutorResolucion = Union[
    AutorResolucionExistente,
    AutorResolucionNueva,
    AutorResolucionPendiente,
]


# ==========================================
# 4. Endpoint intermedio: resolución de autor/país/género
# ==========================================

class ResolverLibroRequest(BaseModel):
    """Libro elegido por el usuario en la lista de búsqueda, con un único
    autor ya seleccionado (si Google Books traía varios, el frontend le
    pidió al usuario elegir uno antes de llegar acá)."""
    titulo: str
    autor_nombre: str
    idioma: Optional[str] = None
    categorias: List[str] = []
    anio_publicacion: Optional[int] = None
    descripcion: Optional[str] = ""
    portada_url: Optional[str] = ""
    isbn: Optional[str] = None


class ResolverLibroResponse(BaseModel):
    """Resultado de la resolución. El libro se pasa de vuelta tal cual
    (sin transformar) junto con las decisiones tomadas para autor/géneros."""
    titulo: str
    anio_publicacion: Optional[int] = None
    descripcion: Optional[str] = ""
    portada_url: Optional[str] = ""
    isbn: Optional[str] = None
    autor: AutorResolucion
    generos: List[GeneroResolucion] = []


# ==========================================
# 5. Esquemas de importación final (hacia Java)
# ==========================================

class AutorImportSchema(BaseModel):
    """Uno de los dos, nunca ambos: autor_id (vincular a existente) o
    datos (crear nuevo)."""
    autor_id: Optional[int] = None
    datos: Optional[AutorCreateSchema] = None


class GeneroImportSchema(BaseModel):
    """Uno de los dos, nunca ambos: genero_id (vincular a existente) o
    datos (crear nuevo)."""
    genero_id: Optional[int] = None
    datos: Optional[GeneroCreateSchema] = None


class ImportarLibroRequest(BaseModel):
    """Payload final, ya sin ambigüedades (incluida la confirmación del
    usuario si el autor había quedado pendiente), que agentes-ia reenvía
    a Java para el insert transaccional: país -> autor -> géneros ->
    libro -> libro_genero."""
    titulo: str
    anio_publicacion: Optional[int] = None
    descripcion: Optional[str] = ""
    portada_url: Optional[str] = ""
    isbn: Optional[str] = None
    estado: str = "POR_LEER"
    autor: AutorImportSchema
    generos: List[GeneroImportSchema] = []