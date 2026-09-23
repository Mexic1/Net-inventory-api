"""REST API over a network device inventory.

The point of `/export/nornir` is that N1 (config backup / drift detection) can
consume it with no hand-editing, so its shape is a contract: top-level keys are
hostnames, and each value is a Nornir host definition.
"""

from contextlib import asynccontextmanager
from ipaddress import IPv4Address, IPv6Address
from typing import Annotated

import yaml
from fastapi import Depends, FastAPI, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import Base, engine, get_session
from .models import Device

# Nornir identifies drivers by platform, not by vendor name.
PLATFORM_BY_VENDOR = {
    "cisco": "ios",
    "arista": "eos",
    "juniper": "junos",
}

# Annotated form rather than a Depends() default: same dependency, but it keeps
# the call out of the signature default (ruff B008).
SessionDep = Annotated[Session, Depends(get_session)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # First connection of the process. Deliberately not at import time: that
    # would couple module import to database availability.
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="net-inventory-api", version="0.1.0", lifespan=lifespan)


class DeviceIn(BaseModel):
    hostname: str = Field(min_length=1, max_length=255)
    mgmt_ip: IPv4Address | IPv6Address
    vendor: str = Field(default="cisco", max_length=64)
    model: str | None = Field(default=None, max_length=128)
    site: str | None = Field(default=None, max_length=128)
    role: str = Field(default="router", max_length=64)

    @field_validator("vendor")
    @classmethod
    def _normalize_vendor(cls, value: str) -> str:
        """Fold vendor casing at the edge.

        PLATFORM_BY_VENDOR is keyed lowercase, and a miss falls back to the raw
        vendor string. Without this, "Cisco" would reach Nornir as platform
        "Cisco", which no netmiko/napalm driver recognizes, and the failure
        would only surface much later as a connection error.
        """
        return value.strip().lower()

    @field_serializer("mgmt_ip")
    def _ip_to_str(self, value: IPv4Address | IPv6Address) -> str:
        return str(value)


class DeviceOut(DeviceIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


def _get_or_404(session: Session, device_id: int) -> Device:
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail=f"device {device_id} not found")
    return device


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/devices", response_model=list[DeviceOut])
def list_devices(session: SessionDep) -> list[Device]:
    return list(session.scalars(select(Device).order_by(Device.hostname)))


@app.get("/devices/{device_id}", response_model=DeviceOut)
def get_device(device_id: int, session: SessionDep) -> Device:
    return _get_or_404(session, device_id)


@app.post("/devices", response_model=DeviceOut, status_code=201)
def create_device(payload: DeviceIn, session: SessionDep) -> Device:
    device = Device(**payload.model_dump(mode="json"))
    session.add(device)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409, detail=f"hostname {payload.hostname!r} already exists"
        ) from exc
    return device


@app.put("/devices/{device_id}", response_model=DeviceOut)
def replace_device(
    device_id: int, payload: DeviceIn, session: SessionDep
) -> Device:
    device = _get_or_404(session, device_id)
    for field, value in payload.model_dump(mode="json").items():
        setattr(device, field, value)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409, detail=f"hostname {payload.hostname!r} already exists"
        ) from exc
    return device


@app.delete("/devices/{device_id}", status_code=204)
def delete_device(device_id: int, session: SessionDep) -> Response:
    session.delete(_get_or_404(session, device_id))
    session.commit()
    return Response(status_code=204)


@app.get("/export/nornir")
def export_nornir(session: SessionDep, fmt: str = "json"):
    """Nornir inventory, consumed directly by N1.

    JSON is a subset of YAML 1.2, so the default body can be redirected straight
    into a hosts.yaml. `?fmt=yaml` emits block-style YAML for readability.
    """
    if fmt not in {"json", "yaml"}:
        raise HTTPException(status_code=400, detail="fmt must be 'json' or 'yaml'")

    hosts = {
        device.hostname: {
            "hostname": device.mgmt_ip,
            "platform": PLATFORM_BY_VENDOR.get(device.vendor, device.vendor),
            "groups": [device.role],
            "data": {"site": device.site, "model": device.model},
        }
        for device in session.scalars(select(Device).order_by(Device.hostname))
    }

    if fmt == "yaml":
        return Response(
            content=yaml.safe_dump(hosts, sort_keys=False, default_flow_style=False),
            media_type="application/yaml",
        )
    return hosts
