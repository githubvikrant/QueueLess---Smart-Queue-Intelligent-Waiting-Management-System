"""
Application configuration using Pydantic Settings.

This module centralizes all configuration including policy thresholds,
LLM settings, and database connection strings. All values are loaded
from environment variables with sensible defaults.

PURPOSE: Provide centralized configuration management for the application
DEPENDENCIES: pydantic-settings, python-dotenv
SIDE EFFECTS: Reads from .env file at startup
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """
    PURPOSE: Application settings loaded from environment variables

    FIELDS:
        app_name: Application name
        database_url: SQLite database connection string
        cors_origins: Allowed CORS origins

        llm_api_key: API key for Anthropic Claude (LLM provider)
        llm_model: Model name to use (default: claude-sonnet-4-20250514)

        Policy Thresholds (all configurable, no hardcoding):
        - bottleneck_threshold_min: Minutes of wait before bottleneck detection triggers
        - notify_change_threshold_min: Minutes of ETA change to notify users
        - appointment_grace_min: Grace period for late appointment arrivals
        - max_delay_existing_min: Maximum extra delay allowed for existing patients
        - no_show_grace_min: Grace period before marking a no-show

        - actions_requiring_approval: List of action types that need human approval

    CONFIG:
        env_file: ".env" - loads environment variables from .env file in backend directory
        env_file_encoding: "utf-8" - file encoding for .env file

    USAGE: Import settings instance: from app.core.config import settings
    """

    # Basic Configuration
    app_name: str = "QueueLess"
    database_url: str = "sqlite:///./data/queueless.db"
    cors_origins: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "*",
    ]

    # LLM Configuration
    llm_api_key: str = ""
    llm_model: str = "claude-sonnet-4-20250514"

    # Policy Thresholds (Non-Negotiable Rule #9: Nothing hardcoded)
    bottleneck_threshold_min: int = 15
    notify_change_threshold_min: int = 5
    appointment_grace_min: int = 10
    max_delay_existing_min: int = 8
    no_show_grace_min: int = 3

    # Approval Requirements
    actions_requiring_approval: List[str] = ["REASSIGN", "OPEN_COUNTER"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


# Create a global settings instance
# This is imported throughout the application to access configuration
settings = Settings()
