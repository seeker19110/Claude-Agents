from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    llm_provider: str = "openai"  # "openai", "groq", "gemini", "anthropic", "ollama"
    openai_api_key: str = ""
    groq_api_key: str = ""
    google_api_key: str = ""
    anthropic_api_key: str = ""
    model_name: str = "gpt-4o-mini"

    # --- Điều khiển vòng lặp tự sửa lỗi (Reviewer retry loop) ---
    # Số lần Reviewer được phép TỪ CHỐI và bắt worker làm lại trên cùng một yêu cầu.
    # Hết hạn mức thì luồng dừng kèm cảnh báo, thay vì quay vòng vô tận.
    max_review_retries: int = 2
    # Trần số bước của LangGraph cho mỗi lượt chạy (chốt chặn cuối cùng).
    recursion_limit: int = 25

    # --- Persistence ---
    # Đường dẫn file SQLite lưu checkpoint hội thoại. Để rỗng => dùng bộ nhớ RAM
    # (MemorySaver), mất toàn bộ lịch sử khi restart tiến trình.
    checkpoint_db: str = "data/checkpoints.sqlite"

    # LangSmith
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "x_agents_project"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

# Global settings instance
settings = Settings()
