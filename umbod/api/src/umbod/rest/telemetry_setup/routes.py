from typing import Annotated

from fastapi import APIRouter, Depends

from .deps import get_telemetry_setup
from .models import TelemetrySetup

router = APIRouter(prefix="/telemetry", tags=["telemetry-setup"])


@router.get("/setup", response_model=TelemetrySetup)
def read_telemetry_setup(
    setup: Annotated[TelemetrySetup, Depends(get_telemetry_setup)],
) -> TelemetrySetup:
    return setup
