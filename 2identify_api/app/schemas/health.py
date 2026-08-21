"""Foundation endpoint schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class RootResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: Literal["running"]


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "degraded"]
    database: Literal["connected", "disconnected"]

