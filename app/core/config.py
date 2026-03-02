from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, RedisDsn


class Settings(BaseSettings):
    # FastAPI
    app_name: str = "Rate Limiter Service"
    debug: bool = False
    environment: str = "production"
    DATABASE_URL: str
    # Redis
    redis_dsn: RedisDsn = Field("redis://localhost:6379/0", env="REDIS_DSN")
    redis_pool_size: int = 20

    # Logging
    log_level: str = "INFO"
    json_logs: bool = True
    SECRET_KEY:str
    ALGORITHM:str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES:int=30
    REFRESH_TOKEN_EXPIRE_DAYS:int=30
    REDIS_URL :str
    CELERY_BROKER_URL :str
    CELERY_RESULT_BACKEND :str

    UPLOAD_DIR: str = "media/quiz/file"
    MAX_PDF_SIZE: int = 5 * 1024 * 1024

    GEMINI_API_KEY: str = "AIzaSyDBi9n_v8g_xylGaOliE7EwAb3DFqhNIdY"
    GEMINI_MODEL: str = "gemini-3-flash-preview"

    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4.1-mini"

    DEEPSEEK_API_KEY: str | None = None
    DEEPSEEK_MODEL: str = "deepseek-chat"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
