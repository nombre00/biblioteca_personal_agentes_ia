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
        return respuesta.content


gemini_client = GeminiClient()