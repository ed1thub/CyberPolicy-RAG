from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "CyberPolicy-RAG"
    environment: str = "development"
    secret_key: str = "change-this-secret-key"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    database_url: str = "sqlite:///./app.db"
    chroma_path: str = "../data/chroma"
    llm_provider: str = "mock"
    rag_top_k: int = 3
    llm_temperature: float = 0.1
    llm_max_output_tokens: int = 120
    openai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"


settings = Settings()
