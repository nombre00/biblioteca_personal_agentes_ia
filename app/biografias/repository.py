from sqlalchemy.orm import Session

from app.biografias.model import BiografiaAutor


def buscar_por_autor_id(db: Session, autor_id: int) -> BiografiaAutor | None:
    return db.query(BiografiaAutor).filter(BiografiaAutor.autor_id == autor_id).first()


def guardar(db: Session, autor_id: int, texto: str, modelo_usado: str) -> BiografiaAutor:
    """
    Guarda o sobrescribe la biografía de un autor (upsert manual).
    Consistente con la regla de negocio: se sobrescribe, no se versiona.
    """
    biografia = buscar_por_autor_id(db, autor_id)

    if biografia is None:
        biografia = BiografiaAutor(autor_id=autor_id, texto=texto, modelo_usado=modelo_usado)
        db.add(biografia)
    else:
        biografia.texto = texto
        biografia.modelo_usado = modelo_usado
        # fecha_generacion se actualiza sola vía onupdate en el modelo

    db.commit()
    db.refresh(biografia)
    return biografia