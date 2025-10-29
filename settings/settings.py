from functools import lru_cache
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_API_KEY: str
    SUPABASE_JWT: str
    API_KEY: str
    MODEL_NAME: str
    BUCKET_REVISTAS: str

    class Config:
        env_file = ".env"
    
@lru_cache
def importar_configs() -> Settings:
    return Settings()