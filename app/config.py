from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: str = "groq"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    llm_timeout_seconds: float = 15.0
    llm_max_retries: int = 2
    llm_base_delay_seconds: float = 0.5
    llm_max_delay_seconds: float = 8.0
    price_per_1m_input_usd: float = 0.59
    price_per_1m_output_usd: float = 0.79
    embedding_provider: str = "fastembed"  # fastembed | hashing (offline, used in tests)
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    kb_dir: str = "kb"
    retrieval_top_k: int = 3
    retrieval_min_score: float = 0.5
    demo_mode: bool = False  # enables /demo/* routes (fault injection) for the showcase
    db_path: str = "data/flowdesk.db"
    max_message_chars: int = 4000


def get_settings() -> Settings:
    return Settings()
