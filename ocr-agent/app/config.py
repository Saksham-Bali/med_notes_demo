import os

AZURE_ENDPOINT = os.environ.get(
    "AZURE_ENDPOINT",
    "https://sherpartap1101-5077-resource.cognitiveservices.azure.com/",
)
AZURE_API_KEY = os.environ["AZURE_API_KEY"]
AZURE_API_VERSION = os.environ.get("AZURE_API_VERSION", "2025-01-01-preview")
AZURE_DEPLOYMENT = os.environ.get("AZURE_DEPLOYMENT", "gpt-4o-mini")
