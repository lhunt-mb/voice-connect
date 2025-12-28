"""Configuration management using Pydantic Settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Server Configuration
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    public_host: str = Field(..., description="Public host for webhooks (e.g., ngrok URL)")
    log_level: str = Field(default="INFO", description="Logging level")

    # Twilio Configuration
    twilio_account_sid: str = Field(..., description="Twilio Account SID")
    twilio_auth_token: str = Field(..., description="Twilio Auth Token")
    twilio_phone_number: str = Field(..., description="Twilio phone number")

    # Voice Provider Configuration
    voice_provider: str = Field(default="openai", description="Voice provider: 'openai' or 'nova'")

    # OpenAI Configuration
    openai_api_key: str | None = Field(default=None, description="OpenAI API key (required if voice_provider=openai)")
    openai_realtime_model: str = Field(
        default="gpt-4o-realtime-preview-2024-12-17", description="OpenAI Realtime model"
    )
    openai_voice: str = Field(default="verse", description="OpenAI voice")

    # AWS Configuration
    aws_region: str = Field(default="ap-southeast-2", description="AWS region for DynamoDB and Lambda")
    nova_region: str | None = Field(
        default=None, description="AWS region for Nova 2 Sonic (required if voice_provider=nova)"
    )
    aws_access_key_id: str | None = Field(default=None, description="AWS access key ID")
    aws_secret_access_key: str | None = Field(default=None, description="AWS secret access key")
    dynamodb_endpoint_url: str | None = Field(default=None, description="DynamoDB endpoint URL (for local dev)")
    dynamodb_table_name: str = Field(default="HandoverTokens", description="DynamoDB table name")

    # Amazon Connect Configuration
    connect_phone_number: str = Field(..., description="Amazon Connect phone number")
    connect_instance_id: str = Field(..., description="Amazon Connect instance ID")

    # HubSpot Configuration (Optional)
    hubspot_access_token: str | None = Field(default=None, description="HubSpot private app access token (optional)")
    hubspot_api_base_url: str = Field(default="https://api.hubapi.com", description="HubSpot API base URL")
    enable_hubspot: bool = Field(default=True, description="Enable HubSpot integration")

    # Token Configuration
    token_ttl_seconds: int = Field(default=600, description="Token TTL in seconds (10 minutes)")
    token_length: int = Field(default=10, description="Token length in digits")

    # Development
    use_local_dynamodb: bool = Field(default=False, description="Use local DynamoDB")


def get_settings() -> Settings:
    """Get application settings instance."""
    return Settings()  # type: ignore[call-arg]
