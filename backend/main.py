from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import ValidationError

from backend.frontend_assets import APP_JS, INDEX_HTML, STYLES_CSS
from backend.routers import analyze

app = FastAPI(title="DichVariables API", version="0.1.0")


@app.exception_handler(ValidationError)
async def pydantic_validation_handler(_request, exc: ValidationError):
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def serve_index():
    return HTMLResponse(INDEX_HTML)


@app.get("/app.js")
def serve_app_js():
    return Response(APP_JS, media_type="application/javascript")


@app.get("/styles.css")
def serve_styles():
    return Response(STYLES_CSS, media_type="text/css")


app.include_router(analyze.router, prefix="/api/v1")
