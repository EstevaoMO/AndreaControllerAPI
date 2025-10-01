from functools import lru_cache
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_API_KEY: str
    SUPABASE_JWT: str
    BUCKET: str
    API_KEY: str
    MODEL_NAME: str

    class Config:
        env_file = ".env"
    
@lru_cache
def importar_configs() -> Settings:
    return Settings()