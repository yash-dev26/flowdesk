from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: str = "groq"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    llm_timeout_seconds: float = 15.0
    llm_max_retries: int = 2
    db_path: str = "data/flowdesk.db"
    max_message_chars: int = 4000


def get_settings() -> Settings:
    return Settings()
