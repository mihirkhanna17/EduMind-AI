from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    poe_api_key: str = ""
    database_url: str = "postgresql+psycopg://edumind:edumind@localhost:5433/edumind"
    redis_url: str = ""
    # comma-separated extra CORS origins for deployed frontends
    # e.g. "https://edumind-ai.netlify.app"
    frontend_origins: str = ""
    image_search_api_key: str = ""
    image_search_cx: str = ""
    serpapi_key: str = ""  # SerpAPI Google Images (free tier: 100 searches/mo)

    embedding_dim: int = 1536


settings = Settings()
