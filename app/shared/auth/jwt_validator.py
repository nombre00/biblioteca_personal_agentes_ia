# app/shared/auth/jwt_validator.py

import base64
import jwt
from fastapi import Header, HTTPException, status

from app.shared.config import settings


def _obtener_clave_decodificada() -> bytes:
    """
    El secreto vive en el .env como string Base64 (mismo formato que usa
    el backend Java, que lo decodifica antes de construir la clave HMAC).
    Hay que replicar ese mismo paso acá o la verificación de firma no calza.
    """
    return base64.b64decode(settings.jwt_internal_secret)


def validar_jwt_interno(x_internal_token: str = Header(...)) -> str:
    """
    Dependencia de FastAPI (usar con Depends(validar_jwt_interno) en cada router).
    Valida el JWT interno emitido por el Gateway y devuelve el uid (claim 'sub').

    Replica el contrato de JwtService.java: mismo header (X-Internal-Token),
    mismo secreto (Base64 decodificado), mismo claim relevante (sub = uid Firebase).
    """
    try:
        payload = jwt.decode(
            x_internal_token,
            _obtener_clave_decodificada(),
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token interno inválido o expirado",
        )

    uid = payload.get("sub")
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token interno sin claim 'sub'",
        )

    return uid