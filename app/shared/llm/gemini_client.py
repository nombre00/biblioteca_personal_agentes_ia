import json
import re

from langchain_google_genai import ChatGoogleGenerativeAI 

from app.shared.config import settings 


class GeminiClient:
    def __init__(self):
        self._modelo = ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.gemini_api_key,
        )

    def generar_texto(self, prompt: str) -> str:
        respuesta = self._modelo.invoke(prompt)
        return self._extraer_texto(respuesta.content)

    def generar_json(self, prompt: str) -> dict:
        """
        Para casos que necesitan salida estructurada y parseable (ej. clasificar
        un autor en una banda de confianza, matchear un género contra una lista
        existente), a diferencia de generar_texto que devuelve texto libre.

        El prompt debe pedirle explícitamente al modelo que responda solo con
        JSON, sin texto adicional. Igual se limpia el resultado por si el modelo
        lo envuelve en un bloque ```json ... ``` (comportamiento común aunque se
        le pida no hacerlo).
        """
        texto = self.generar_texto(prompt)
        texto_limpio = self._limpiar_bloque_json(texto)

        try:
            return json.loads(texto_limpio)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Gemini no devolvió JSON válido. Respuesta cruda: {texto!r}"
            ) from e

    @staticmethod
    def _limpiar_bloque_json(texto: str) -> str:
        """Quita el envoltorio ```json ... ``` o ``` ... ``` si está presente."""
        texto = texto.strip()
        match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", texto, re.DOTALL)
        if match:
            return match.group(1)
        return texto

    @staticmethod
    def _extraer_texto(contenido: str | list) -> str:
        """
        En modelos más nuevos, `.content` puede venir como una lista de bloques
        estructurados (ej. [{'type': 'text', 'text': '...'}]) en vez de un string
        plano. Se concatenan solo los bloques de tipo texto.
        """
        if isinstance(contenido, str):
            return contenido

        partes = []
        for bloque in contenido:
            if isinstance(bloque, dict) and bloque.get("type") == "text":
                partes.append(bloque.get("text", ""))
            elif isinstance(bloque, str):
                partes.append(bloque)

        return "".join(partes)


gemini_client = GeminiClient()  