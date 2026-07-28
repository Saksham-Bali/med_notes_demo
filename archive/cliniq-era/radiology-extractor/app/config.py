"""
Configuration for the radiology-extractor service.
All settings are read from environment variables with sensible defaults.
"""

import os

# OpenRouter / LLM
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "openai/gpt-4o-mini")

# RadLex ontology path — must be accessible at runtime
RADLEX_PATH = os.environ.get("RADLEX_PATH", "/app/data/Radlex.xls")

# Service settings
SERVICE_PORT = int(os.environ.get("PORT", "5003"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
