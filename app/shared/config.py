from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Base de datos
    db_url: str
    db_username: str
    db_password: str

    # JWT interno (mismo secreto que Gateway y backend)
    jwt_internal_secret: str
    jwt_algorithm: str = "HS256"

    # GitHub Models
    github_models_token: str
    github_models_endpoint: str = "https://models.inference.ai.azure.com"
    github_models_model: str = "gpt-4o-mini"

    @property
    def database_url(self) -> str:
        return f"mysql+pymysql://{self.db_username}:{self.db_password}@{self.db_url}"


settings = Settings()