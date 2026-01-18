"""Meeting Intelligence MCP Server - Configuration"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Azure SQL Database
    azure_sql_server: str = ""
    azure_sql_database: str = "meeting-intelligence"
    # Authenticated via Azure Entra ID (CLI or Managed Identity), so no password needed
    
    # Fireflies API
    fireflies_api_key: str = ""
    
    # API Authentication
    api_key: str = ""
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
