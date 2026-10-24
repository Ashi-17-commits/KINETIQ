"""KINETIQ FastAPI application entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import APP_NAME, BACKEND_VERSION, get_settings
from app.services.comparison_service import ComparisonService
from app.services.history_store import HistoryStore
from app.services.recovery_service import RecoveryService
from app.services.simulation_service import SimulationService

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    history = HistoryStore(max_entries=settings.history_max_entries)
    simulation_service = SimulationService(history=history)
    comparison_service = ComparisonService(simulation_service)
    recovery_service = RecoveryService(simulation_service)

    app = FastAPI(
        title=f"{APP_NAME} API",
        version=BACKEND_VERSION,
        description="Physics-based EV simulation backend (prototype).",
    )

    app.state.simulation_service = simulation_service
    app.state.comparison_service = comparison_service
    app.state.recovery_service = recovery_service

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": jsonable_encoder(exc.errors())},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled server error")
        if settings.app_env == "development":
            return JSONResponse(status_code=500, content={"detail": str(exc)})
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app


app = create_app()
