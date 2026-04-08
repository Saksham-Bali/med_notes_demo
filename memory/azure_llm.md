---
name: Azure LLM Config
description: Azure OpenAI endpoint, deployment name, API key, and Python client pattern
type: reference
---

# Azure OpenAI Config

Endpoint: `https://sherpartap1101-5077-resource.cognitiveservices.azure.com/`
Deployment: `gpt-4o-mini`
API Version: `2025-01-01-preview`
Key env var: `AZURE_API_KEY` (in `.env`)

## Python client pattern
```python
from openai import AzureOpenAI
import os

client = AzureOpenAI(
    azure_endpoint=os.environ.get("AZURE_ENDPOINT", "https://sherpartap1101-5077-resource.cognitiveservices.azure.com/"),
    api_key=os.environ["AZURE_API_KEY"],
    api_version=os.environ.get("AZURE_API_VERSION", "2025-01-01-preview"),
)
response = client.chat.completions.create(
    model=os.environ.get("AZURE_DEPLOYMENT", "gpt-4o-mini"),
    messages=[...],
    max_tokens=4000,
    temperature=0,
)
```

For vision (OCR), pass image as base64 in message content with `image_url` type.

## TypeScript client (Med copy / platform-ui)
Already configured in `Med copy/lib/azure-openai.ts` using env var `AZURE_KEY`.
