from sqlalchemy.orm import Session

from app.resumenes.model import ResumenLibro


def buscar_por_libro_id(db: Session, libro_id: int) -> ResumenLibro | None:
    return db.query(ResumenLibro).filter(ResumenLibro.libro_id == libro_id).first()


def guardar(db: Session, libro_id: int, texto: str, modelo_usado: str) -> ResumenLibro:
    """
    Guarda o sobrescribe el resumen de un libro (upsert manual).
    Consistente con la regla de negocio: se sobrescribe, no se versiona.
    """
    resumen = buscar_por_libro_id(db, libro_id)

    if resumen is None:
        resumen = ResumenLibro(libro_id=libro_id, texto=texto, modelo_usado=modelo_usado)
        db.add(resumen)
    else:
        resumen.texto = texto
        resumen.modelo_usado = modelo_usado

    db.commit()
    db.refresh(resumen)
    return resumen