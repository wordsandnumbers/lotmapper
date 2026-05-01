from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "Parking Lot Mapping Tool"
    debug: bool = False

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/parking_lots"

    # JWT Auth
    secret_key: str = "change-this-in-production-use-openssl-rand-hex-32"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Model paths (relative to backend directory)
    model_path: str = "../model/parking_lot_model.pt"

    # Google Maps
    google_maps_api_key: str = ""
    google_maps_monthly_tile_limit: int = 100000

    # RabbitMQ
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
