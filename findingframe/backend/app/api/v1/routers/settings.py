"""Read-only configuration surface (GET /api/v1/settings).

Exposes the active model/provider, reasoning effort, engine git sha, region and env so the
UI can show the "model-agnostic" story and current run configuration. NEVER exposes secrets
(API keys, DSNs). This is read-only for now: model selection is driven by the engine
configuration / manifest per run, so there is no org-level override table yet.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.deps import CtxDep, SessionDep
from app.core.config import settings as app_settings
from app.db.models import Org
from app.engine.adapter import get_engine
from app.schemas.dto import SettingsOut

router = APIRouter(tags=["settings"])

# The models the engine can be pointed at. The active model always appears in the list so the
# UI can render it as selected even if it is not one of the presets. This is a display list;
# it does not grant access to any provider.
_AVAILABLE_MODELS = [
    "deepseek/deepseek-v4-pro",
    "openai/gpt-5.5",
    "anthropic/claude-opus-4.8",
    "google/gemini-3-pro",
    "meta-llama/llama-4-405b-instruct",
]


@router.get("/settings", response_model=SettingsOut)
async def get_settings(ctx: CtxDep, session: SessionDep):
    org = await session.get(Org, ctx.org_id)
    region = org.region if org and org.region else app_settings.region_default()

    try:
        manifest = get_engine().manifest_base()
        engine_git_sha = manifest.engine_git_sha or "unknown"
        prompt_version = manifest.prompt_version or None
        schema_version = manifest.schema_version or None
    except Exception:  # engine unavailable -> still return config
        engine_git_sha = app_settings.engine_git_sha or "unknown"
        prompt_version = None
        schema_version = None

    active_model = app_settings.llm_model
    available = list(_AVAILABLE_MODELS)
    if active_model and active_model not in available:
        available.insert(0, active_model)

    return SettingsOut(
        llm_provider=app_settings.llm_provider,
        llm_model=active_model,
        available_models=available,
        reasoning_effort=app_settings.llm_reasoning_effort,
        temperature=app_settings.llm_temperature,
        engine_git_sha=engine_git_sha,
        region=region,
        env=app_settings.env,
        read_only=True,
        prompt_version=prompt_version,
        schema_version=schema_version,
    )
