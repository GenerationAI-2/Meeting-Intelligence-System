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
    # Rename env vars to avoid conflict with DefaultAzureCredential
    azure_tenant_id: str = Field(default="", validation_alias="API_AZURE_TENANT_ID")
    azure_client_id: str = Field(default="", validation_alias="API_AZURE_CLIENT_ID")  # The API App Registration Client ID (b5a8...)
    
    # MCP Authentication: tokens are now stored in the ClientToken database table.
    # Use manage_tokens.py CLI to create/revoke/rotate tokens.
    # Legacy env var kept temporarily for migration — will be removed after migration.
    mcp_auth_tokens: str = ""

    # User whitelist (comma-separated emails)
    allowed_users: str = ""

    # CORS origins (comma-separated URLs)
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # OAuth 2.1 settings (for ChatGPT MCP support)
    jwt_secret: str = ""  # Required for OAuth - generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
    oauth_base_url: str = ""  # Set to deployed URL, e.g., https://meeting-intelligence-team.happystone-42529ebe.australiaeast.azurecontainerapps.io

    # Observability (optional but recommended for production)
    applicationinsights_connection_string: str = ""  # Get from Azure Portal > Application Insights > Connection String

    def get_mcp_auth_tokens_dict(self) -> dict[str, str]:
        """Parse legacy MCP_AUTH_TOKENS env var for migration only."""
        if not self.mcp_auth_tokens:
            return {}
        try:
            import json
            return json.loads(self.mcp_auth_tokens)
        except Exception:
            return {}

    def get_allowed_users_list(self) -> list[str]:
        """Get list of allowed user emails (lowercased)."""
        if not self.allowed_users:
            return []
        return [email.strip().lower() for email in self.allowed_users.split(",")]

    def get_cors_origins_list(self) -> list[str]:
        """Get list of allowed CORS origins."""
        if not self.cors_origins:
            return ["http://localhost:3000"]
        return [origin.strip() for origin in self.cors_origins.split(",")]

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore deprecated env vars


@lru_cache
def get_settings() -> Settings:
    return Settings()
