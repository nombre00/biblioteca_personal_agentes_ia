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