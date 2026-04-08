from fastapi import FastAPI, HTTPException

from config import get_settings
from models.request import TranslateRequest
from models.response import TranslateResponse
from translation_service import TranslationService

settings = get_settings()
service = TranslationService(settings=settings)

app = FastAPI(title="Translation Layer", version="1.0.0")


@app.get("/health")
def health() -> dict[str, str | int]:
    return {
        "status": "ok",
        "service": settings.service_name,
        "port": settings.port,
    }


@app.post("/api/v1/translate", response_model=TranslateResponse)
def translate(request: TranslateRequest) -> TranslateResponse:
    try:
        return service.process_request(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

