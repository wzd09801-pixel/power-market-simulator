from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.app.api.routes import (
    forecasting,
    intelligence,
    knowledge,
    market,
    operations,
    recommendations,
    scenarios,
    system,
    weather,
)
from backend.app.core.config import get_settings
from backend.app.core.errors import AppError


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.app_version)

    @app.get("/healthz", tags=["health"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: object, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Invalid request payload.",
                    "details": [
                        {
                            "type": error["type"],
                            "loc": error["loc"],
                            "msg": error["msg"],
                        }
                        for error in exc.errors()
                    ],
                }
            },
        )

    @app.exception_handler(AppError)
    async def app_error_handler(_request: object, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    app.include_router(system.router)
    app.include_router(scenarios.router)
    app.include_router(recommendations.router)
    app.include_router(weather.router)
    app.include_router(market.router)
    app.include_router(forecasting.router)
    app.include_router(operations.router)
    app.include_router(knowledge.router)
    app.include_router(intelligence.router)
    return app


app = create_app()
