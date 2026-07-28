from __future__ import annotations

from fastapi import FastAPI, HTTPException
import httpx

from agents import ContextAssembler, ModelRefusalError, OutputFormatter, SummaryComposer
from config import Settings, get_settings
from models.request import GenerateSummaryRequest
from models.response import GenerateSummaryResponse, HealthResponse


def create_app(
    settings: Settings | None = None,
    assembler: ContextAssembler | None = None,
    composer: SummaryComposer | None = None,
    formatter: OutputFormatter | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    resolved_assembler = assembler or ContextAssembler(resolved_settings)
    resolved_composer = composer or SummaryComposer(resolved_settings)
    resolved_formatter = formatter or OutputFormatter()

    app = FastAPI(
        title="Summary Generator",
        version="1.0.0",
        description="Standalone discharge summary generation microservice.",
    )

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=resolved_settings.app_name,
            model=resolved_settings.openai_model,
            fact_graph_base_url=resolved_settings.fact_graph_base_url,
        )

    @app.post("/api/v1/generate", response_model=GenerateSummaryResponse)
    async def generate_summary(
        request: GenerateSummaryRequest,
    ) -> GenerateSummaryResponse:
        try:
            context = await resolved_assembler.assemble_context(request)
            summary = await resolved_composer.compose_summary(request, context)
            return resolved_formatter.format(request, summary, context)
        except httpx.HTTPStatusError as exc:
            detail = (
                f"Fact Graph returned {exc.response.status_code} for {exc.request.url.path}."
            )
            raise HTTPException(status_code=502, detail=detail) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=504,
                detail="Fact Graph request failed or timed out.",
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ModelRefusalError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Summary generation refused: {exc}",
            ) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app


app = create_app()
