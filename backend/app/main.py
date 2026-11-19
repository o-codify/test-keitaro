import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.config import ROOT_DIR, get_settings
from app.errors import AppError
from app.keitaro import KeitaroError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("keitaro-wrapper")

settings = get_settings()
app = FastAPI(title="Keitaro wrapper", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(KeitaroError)
async def keitaro_error_handler(_: Request, exc: KeitaroError):
    logger.warning("Keitaro error %s: %s", exc.status_code, exc.message)
    # 4xx от Keitaro (валидация, not found) отдаём как 400/404, остальное — 502
    if exc.status_code == 404:
        status = 404
    elif exc.status_code and 400 <= exc.status_code < 500 and exc.status_code not in (401, 403):
        status = 400
    else:
        status = 502
    detail = f"Keitaro: {exc.message}"
    if exc.status_code in (401, 403):
        detail = "Keitaro отклонил API-ключ (проверьте KEITARO_API_KEY)"
    return JSONResponse(status_code=status, content={"detail": detail})


app.include_router(router)


@app.get("/api/health")
def health():
    return {"status": "ok", "mock": settings.keitaro_mock}


# Собранный фронтенд (npm run build) раздаём с того же порта
DIST = ROOT_DIR / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        file = (DIST / path).resolve()
        if path and file.is_file() and file.is_relative_to(DIST.resolve()):
            return FileResponse(file)
        return FileResponse(DIST / "index.html")
