"""
Configuration for the radiology-extractor service.
All settings are read from environment variables with sensible defaults.
"""

import os

# Azure OpenAI
AZURE_ENDPOINT = os.environ.get(
    "AZURE_ENDPOINT",
    "https://sherpartap1101-5077-resource.cognitiveservices.azure.com/",
)
AZURE_DEPLOYMENT = os.environ.get("AZURE_DEPLOYMENT", "gpt-4o-mini")
AZURE_API_VERSION = os.environ.get("AZURE_API_VERSION", "2025-01-01-preview")
AZURE_API_KEY = os.environ.get("AZURE_API_KEY", "")

# RadLex ontology path — must be accessible at runtime
RADLEX_PATH = os.environ.get("RADLEX_PATH", "/app/data/Radlex.xls")

# Service settings
SERVICE_PORT = int(os.environ.get("PORT", "5003"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
