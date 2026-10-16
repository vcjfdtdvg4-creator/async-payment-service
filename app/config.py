from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://payments:payments@localhost:5432/payments"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    api_key: str = "super-secret-key"

    max_attempts: int = 3                 # всего попыток обработки сообщения
    retry_base_delay_seconds: int = 5     # задержки: base * 2^(attempt-1) -> 5s, 10s, ...
    webhook_timeout_seconds: float = 10.0

    outbox_poll_interval_seconds: float = 1.0
    outbox_batch_size: int = 50

    # --- Admin UI ---
    # RabbitMQ Management HTTP API (порт 15672); внутри compose -- имя сервиса.
    rabbitmq_management_url: str = "http://rabbitmq:15672"
    rabbitmq_management_user: str = "guest"
    rabbitmq_management_password: str = "guest"
    ui_page_size: int = 25


settings = Settings()
