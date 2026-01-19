"""Meeting Intelligence MCP Server - Configuration"""

from pydantic_settings import BaseSettings
from functools import lru_cache


from pydantic import Field

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
    # Rename env vars to avoid conflict with DefaultAzureCredential
    azure_tenant_id: str = Field(default="", validation_alias="API_AZURE_TENANT_ID")
    azure_client_id: str = Field(default="", validation_alias="API_AZURE_CLIENT_ID")  # The API App Registration Client ID (b5a8...)
    
    # MCP Authentication (JSON mapping of token -> email)
    # Example: '{"token1": "user1@example.com", "token2": "user2@example.com"}'
    mcp_auth_tokens: str = ""

    def get_mcp_user(self, token: str) -> str | None:
        """Look up user email from MCP token. Returns None if token invalid."""
        if not self.mcp_auth_tokens:
            return None
        try:
            import json
            tokens = json.loads(self.mcp_auth_tokens)
            return tokens.get(token)
        except Exception:
            return None

    def get_valid_mcp_tokens(self) -> list[str]:
        """Get list of all valid MCP tokens."""
        if not self.mcp_auth_tokens:
            return []
        try:
            import json
            tokens = json.loads(self.mcp_auth_tokens)
            return list(tokens.keys())
        except Exception:
            return []
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
