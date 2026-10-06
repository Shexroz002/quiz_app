from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, RedisDsn


class Settings(BaseSettings):
    # FastAPI
    app_name: str = "Rate Limiter Service"
    debug: bool = False
    environment: str = "production"
    DATABASE_URL: str
    APP_TIME_ZONE: str = "Asia/Tashkent"
    DATABASE_TIME_ZONE: str = "UTC"
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
    AVATAR_DIR: str = "media/avatars"
    CHAT_UPLOAD_DIR: str = "media/uploads"
    MAX_PDF_SIZE: int = 5 * 1024 * 1024
    MAX_CHAT_FILE_SIZE: int = 50 * 1024 * 1024

    GEMINI_API_KEY: str
    GEMINI_MODEL: str

    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4.1-mini"

    MISTRAL_API_KEY: str
    MISTRAL_MODEL: str
    MISTRAL_REQUEST_TIMEOUT_SEC: int = Field(default=120, gt=0)
    MISTRAL_RETRY_MAX_ELAPSED_SEC: int = Field(default=30, gt=0)

    DEEPSEEK_API_KEY: str | None = None
    DEEPSEEK_MODEL: str = "deepseek-chat"
    BASE_URL: str = "https://api.myedunova.uz"
    MONGO_INITDB_ROOT_USERNAME:str
    MONGO_INITDB_ROOT_PASSWORD:str
    MONGODB_URL:str
    MONGODB_DB_NAME :str
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_WEBAPP_URL: str | None = None

    # Step-by-step solutions. Separate from GEMINI_MODEL on purpose: quiz
    # generation keeps its own model, and solving needs one that reasons.
    # An alias, not a pinned name: on 2026-10-05 gemini-2.5-flash worked in the
    # morning and answered 404 "no longer available to new users" by the
    # afternoon. Each row records the concrete model that wrote it.
    SOLUTION_MODEL: str = "gemini-flash-latest"
    # Reading a photo is transcription, not reasoning: a light model is enough,
    # answers faster, and draws on a separate per-model quota.
    SOLUTION_RECOGNIZE_MODEL: str = "gemini-flash-lite-latest"
    # Tried in order when the main model's daily quota is spent or the model is
    # withdrawn (404). Quotas are counted per model, so on the free tier — 20
    # requests a day each — this keeps solving alive. Comma-separated.
    SOLUTION_FALLBACK_MODELS: str = "gemini-3.7-flash,gemini-3.5-flash"
    SOLUTION_DAILY_LIMIT: int = Field(default=10, gt=0)
    SOLUTION_UPLOAD_DIR: str = "media/solve"
    SOLUTION_MAX_IMAGE_BYTES: int = 8 * 1024 * 1024
    SOLUTION_TIMEOUT_SEC: int = Field(default=60, gt=0)
    # One deadline for a whole task — every call, retry and fallback inside it.
    # Without it, a busy provider (503s that took 79 s to arrive, a 504 after
    # 89 s) once kept a student waiting 199 s for a failure.
    SOLUTION_TASK_BUDGET_SEC: int = Field(default=120, gt=0)
    # A photo is read inside an HTTP call the app waits on for 30 s.
    SOLUTION_RECOGNIZE_BUDGET_SEC: int = Field(default=25, gt=0)
    # Caps how long the model thinks. Unbounded, the same school problem took
    # 24 s once and timed out at 129 s the next time.
    SOLUTION_THINKING_BUDGET: int = Field(default=4096, ge=0)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
