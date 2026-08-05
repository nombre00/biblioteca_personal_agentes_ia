import base64
import time

import jwt

from app.shared.config import settings


def generar_jwt_interno(uid: str) -> str:
    """
    Genera un JWT interno para que agentes-ia llame a endpoints del backend
    Java (ej. GET /api/autores). Replica el contrato de JwtService.java: mismo
    secreto (Base64 decodificado), mismo algoritmo, y el uid va en el claim
    'sub' (lo único que Java lee del token, según JwtAuthenticationFilter).

    uid: el mismo uid ya validado en el token entrante de este request
    (el que devuelve validar_jwt_interno), no uno nuevo — es la misma
    identidad la que originó la búsqueda y la que termina insertando en Java.

    Vida corta (60s): el token se genera y se consume en el acto, para una
    sola llamada saliente, no necesita durar como el que emite el Gateway.
    """
    clave = base64.b64decode(settings.jwt_internal_secret)
    ahora = int(time.time())

    payload = {
        "sub": uid,
        "iat": ahora,
        "exp": ahora + 60,
    }

    return jwt.encode(payload, clave, algorithm=settings.jwt_algorithm)