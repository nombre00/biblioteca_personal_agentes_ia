from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Base de datos
    db_url: str
    db_username: str
    db_password: str

    # JWT interno (mismo secreto que Gateway y backend)
    jwt_internal_secret: str
    jwt_algorithm: str = "HS512"

    # Gemini
    gemini_api_key: str
    gemini_model: str = "gemini-3.5-flash-lite"

    @property
    def database_url(self) -> str:
        return f"mysql+pymysql://{self.db_username}:{self.db_password}@{self.db_url}"


settings = Settings()