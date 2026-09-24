from typing import Annotated

from fastapi import APIRouter, Depends

from umbod.config.inspection import InstanceConfigurationInspector
from umbod.rest.instance_configuration.dependencies import (
    get_instance_configuration_inspector,
)
from umbod.rest.instance_configuration.schemas import InstanceConfigurationResponse

router = APIRouter(tags=["instance-configuration"])


@router.get("/instance-configuration")
def get_instance_configuration(
    inspector: Annotated[
        InstanceConfigurationInspector,
        Depends(get_instance_configuration_inspector),
    ],
) -> InstanceConfigurationResponse:
    return InstanceConfigurationResponse(
        groups=[group.model_dump() for group in inspector.inspect()]
    )
