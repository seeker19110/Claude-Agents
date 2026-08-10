from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    llm_provider: str = "openai"  # "openai", "groq", "gemini"
    openai_api_key: str = ""
    groq_api_key: str = ""
    google_api_key: str = ""
    model_name: str = "gpt-4o-mini"
    
    # LangSmith
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "x_agents_project"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

# Global settings instance
settings = Settings()
