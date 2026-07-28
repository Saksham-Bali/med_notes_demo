import os
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

# Validate required env var at startup (deferred so tests can patch it)
app = FastAPI(title="ocr-agent", version="1.0.0")

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/jpg",
    "application/pdf",
}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ocr-agent"}


@app.post("/api/v1/extract")
async def extract(
    image: UploadFile = File(...),
    patient_id: str = Form(...),
    department: str = Form(default=""),
    source_type: str = Form(default="handwritten"),
):
    mime_type = image.content_type or "image/jpeg"
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported media type '{mime_type}'. Allowed: {sorted(ALLOWED_MIME_TYPES)}",
        )

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Import here so tests can patch app.ocr.get_client before the module is used
    from app.ocr import run_ocr

    try:
        result = run_ocr(image_bytes, mime_type)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return JSONResponse(content={"result": result})
