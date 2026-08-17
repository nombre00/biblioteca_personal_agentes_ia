from sqlalchemy.orm import Session, joinedload

from app.configuracion_prompt.model import ConfiguracionPrompt, LineaPrompt


def buscar_por_id(db: Session, configuracion_id: int) -> ConfiguracionPrompt | None:
    return (
        db.query(ConfiguracionPrompt)
        .options(joinedload(ConfiguracionPrompt.lineas))
        .filter(ConfiguracionPrompt.id == configuracion_id)
        .first()
    )


def listar_por_tarea(db: Session, tipo_tarea: str) -> list[ConfiguracionPrompt]:
    return (
        db.query(ConfiguracionPrompt)
        .options(joinedload(ConfiguracionPrompt.lineas))
        .filter(ConfiguracionPrompt.tipo_tarea == tipo_tarea)
        .order_by(ConfiguracionPrompt.es_default.desc(), ConfiguracionPrompt.nombre)
        .all()
    )


def buscar_default(db: Session, tipo_tarea: str) -> ConfiguracionPrompt | None:
    return (
        db.query(ConfiguracionPrompt)
        .options(joinedload(ConfiguracionPrompt.lineas))
        .filter(
            ConfiguracionPrompt.tipo_tarea == tipo_tarea,
            ConfiguracionPrompt.es_default.is_(True),
        )
        .first()
    )


def buscar_activa(db: Session, tipo_tarea: str) -> ConfiguracionPrompt | None:
    return (
        db.query(ConfiguracionPrompt)
        .options(joinedload(ConfiguracionPrompt.lineas))
        .filter(
            ConfiguracionPrompt.tipo_tarea == tipo_tarea,
            ConfiguracionPrompt.activa.is_(True),
        )
        .first()
    )


def buscar_activa_o_default(db: Session, tipo_tarea: str) -> ConfiguracionPrompt | None:
    """La consulta que va a usar resumenes/biografias en la Fase 2: si hay
    una configuración activa para esta tarea, esa; si no, cae al default."""
    activa = buscar_activa(db, tipo_tarea)
    if activa is not None:
        return activa
    return buscar_default(db, tipo_tarea)


def crear(
    db: Session,
    tipo_tarea: str,
    nombre: str,
    limite_parrafos: int,
    evitar_spoilers: bool | None,
    lineas: list[str],
    es_default: bool = False,
) -> ConfiguracionPrompt:
    """es_default solo se pasa en True desde la siembra inicial (seed),
    nunca desde el flujo normal de creación del usuario."""
    configuracion = ConfiguracionPrompt(
        tipo_tarea=tipo_tarea,
        nombre=nombre,
        es_default=es_default,
        activa=False,
        limite_parrafos=limite_parrafos,
        evitar_spoilers=evitar_spoilers,
    )
    configuracion.lineas = [
        LineaPrompt(orden=indice, texto=texto)
        for indice, texto in enumerate(lineas, start=1)
    ]

    db.add(configuracion)
    db.commit()
    db.refresh(configuracion)
    return configuracion


def actualizar(
    db: Session,
    configuracion: ConfiguracionPrompt,
    nombre: str | None,
    limite_parrafos: int | None,
    evitar_spoilers: bool | None,
    lineas: list[str] | None,
) -> ConfiguracionPrompt:
    """Asume que el llamador (service.py) ya validó que configuracion.es_default
    es False antes de invocar esto — el repository no repite esa validación
    para no duplicar la regla de negocio en dos capas."""
    if nombre is not None:
        configuracion.nombre = nombre
    if limite_parrafos is not None:
        configuracion.limite_parrafos = limite_parrafos
    if evitar_spoilers is not None:
        configuracion.evitar_spoilers = evitar_spoilers
    if lineas is not None:
        # Reemplazo completo de la lista, como acordamos: se borran las
        # líneas existentes (cascade) y se insertan las nuevas en orden.
        configuracion.lineas = [
            LineaPrompt(orden=indice, texto=texto)
            for indice, texto in enumerate(lineas, start=1)
        ]

    db.commit()
    db.refresh(configuracion)
    return configuracion


def eliminar(db: Session, configuracion: ConfiguracionPrompt) -> None:
    """Asume que el llamador ya validó que configuracion.es_default es False."""
    db.delete(configuracion)
    db.commit()


def activar(db: Session, configuracion: ConfiguracionPrompt) -> ConfiguracionPrompt:
    """Desactiva cualquier otra configuración activa de la misma tarea antes
    de activar esta — garantiza que solo haya una activa por tipo_tarea."""
    (
        db.query(ConfiguracionPrompt)
        .filter(
            ConfiguracionPrompt.tipo_tarea == configuracion.tipo_tarea,
            ConfiguracionPrompt.id != configuracion.id,
            ConfiguracionPrompt.activa.is_(True),
        )
        .update({"activa": False})
    )

    configuracion.activa = True
    db.commit()
    db.refresh(configuracion)
    return configuracion