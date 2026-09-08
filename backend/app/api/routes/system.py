from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.session import check_database_connectivity, get_db_session
from backend.app.schemas.system import SystemReadinessResponse, SystemStatus
from backend.app.services.system import get_system_readiness

router = APIRouter(prefix="/v1/system", tags=["system"])
SessionDependency = Annotated[Session, Depends(get_db_session)]


@router.get("/status", response_model=SystemStatus)
def get_system_status() -> SystemStatus:
    settings = get_settings()
    return SystemStatus(
        app_name=settings.app_name,
        app_version=settings.app_version,
        environment=settings.environment,
        database_connected=check_database_connectivity(settings.database_url),
        data_modes=[
            "public_observed",
            "public_derived",
            "scenario_simulated",
            "user_uploaded",
        ],
        no_auto_trading=True,
    )


@router.get("/readiness", response_model=SystemReadinessResponse)
def get_readiness(session: SessionDependency) -> SystemReadinessResponse:
    return get_system_readiness(session=session)
