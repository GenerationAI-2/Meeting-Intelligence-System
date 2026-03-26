"""Meeting Intelligence MCP Server - Configuration"""

from pydantic_settings import BaseSettings
from pydantic import ConfigDict, Field
from functools import lru_cache

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Azure SQL Database
    azure_sql_server: str = ""
    azure_sql_database: str = "meeting-intelligence"
    control_db_name: str = ""  # e.g., 'acme-mi-control'. Empty = workspace features disabled.
    # Authenticated via Azure Entra ID (CLI or Managed Identity), so no password needed
    # Rename env vars to avoid conflict with DefaultAzureCredential
    azure_tenant_id: str = Field(default="", validation_alias="API_AZURE_TENANT_ID")
    azure_client_id: str = Field(default="", validation_alias="API_AZURE_CLIENT_ID")  # The API App Registration Client ID (b5a8...)
    
    # User whitelist (comma-separated emails) — only used in legacy mode (no control DB)
    allowed_users: str = ""

    # CORS origins (comma-separated URLs)
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # OAuth 2.1 (B17 — per-user MCP auth for Claude Teams / ChatGPT connectors)
    jwt_secret: str = ""  # HS256 signing key for OAuth JWTs. Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
    oauth_base_url: str = ""  # Public URL of this MI instance (e.g., https://fero.claritylayer.co.nz). Required for OAuth.

    # Azure AD OAuth proxy (Phase 3 — replaces PAT consent with Azure AD login)
    # When all three are set, /authorize redirects to Azure AD instead of the PAT consent page.
    # Uses the existing per-client App Registration (same as SPA auth).
    azure_oauth_tenant_id: str = ""   # MyAdvisor tenant: 12e7fcaa-f776-4545-aacf-e89be7737cf3
    azure_oauth_client_id: str = ""   # App Registration client ID (e.g., d3c1c727... for genai)
    azure_oauth_client_secret: str = ""  # App Registration client secret (create in Azure Portal)

    # Branding
    favicon_path: str = ""  # Absolute path to per-client favicon (PNG). Empty = default favicon.svg.

    # Observability (optional but recommended for production)
    applicationinsights_connection_string: str = ""  # Get from Azure Portal > Application Insights > Connection String

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
    
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore deprecated env vars
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
