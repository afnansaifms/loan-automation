from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://loanuser:loanpass@db:5432/loandb"
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    groq_extraction_model: str = ""
    upload_dir: str = "/app/uploads"

    class Config:
        env_file = ".env"


settings = Settings()