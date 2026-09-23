"""API tests.

The /export/nornir cases carry the most weight: that endpoint is a contract the
config-backup project (N1) consumes without hand-editing, so its shape and the
vendor->platform mapping are asserted explicitly rather than just smoke-tested.
"""

import yaml
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.db import Base
from app.main import app


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_device(client, device_payload):
    response = client.post("/devices", json=device_payload)
    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["hostname"] == "edge-01"
    assert body["mgmt_ip"] == "10.0.0.1"


def test_create_applies_defaults(client):
    response = client.post("/devices", json={"hostname": "sw-01", "mgmt_ip": "10.0.0.2"})
    assert response.status_code == 201
    body = response.json()
    assert body["vendor"] == "cisco"
    assert body["role"] == "router"
    assert body["model"] is None


def test_duplicate_hostname_conflicts(client, device_payload):
    assert client.post("/devices", json=device_payload).status_code == 201
    response = client.post("/devices", json=device_payload)
    assert response.status_code == 409
    assert "edge-01" in response.json()["detail"]


def test_create_rejects_invalid_ip(client, device_payload):
    response = client.post("/devices", json={**device_payload, "mgmt_ip": "not-an-ip"})
    assert response.status_code == 422


def test_vendor_casing_is_normalized(client, device_payload):
    """A mixed-case vendor must still map to a real Nornir platform."""
    response = client.post("/devices", json={**device_payload, "vendor": "CISCO"})
    assert response.status_code == 201
    assert response.json()["vendor"] == "cisco"
    assert client.get("/export/nornir").json()["edge-01"]["platform"] == "ios"


def test_list_devices_sorted_by_hostname(client, device_payload):
    client.post("/devices", json={**device_payload, "hostname": "sw-01", "mgmt_ip": "10.0.0.2"})
    client.post("/devices", json=device_payload)
    hostnames = [d["hostname"] for d in client.get("/devices").json()]
    assert hostnames == ["edge-01", "sw-01"]


def test_get_device(client, device_payload):
    device_id = client.post("/devices", json=device_payload).json()["id"]
    response = client.get(f"/devices/{device_id}")
    assert response.status_code == 200
    assert response.json()["hostname"] == "edge-01"


def test_get_missing_device_404(client):
    assert client.get("/devices/9999").status_code == 404


def test_replace_device(client, device_payload):
    device_id = client.post("/devices", json=device_payload).json()["id"]
    updated = {**device_payload, "site": "dc", "role": "core"}
    response = client.put(f"/devices/{device_id}", json=updated)
    assert response.status_code == 200
    assert response.json()["site"] == "dc"
    assert response.json()["role"] == "core"
    assert response.json()["id"] == device_id


def test_replace_missing_device_404(client, device_payload):
    assert client.put("/devices/9999", json=device_payload).status_code == 404


def test_replace_onto_taken_hostname_conflicts(client, device_payload):
    client.post("/devices", json=device_payload)
    other_id = client.post(
        "/devices", json={**device_payload, "hostname": "sw-01", "mgmt_ip": "10.0.0.2"}
    ).json()["id"]
    response = client.put(f"/devices/{other_id}", json=device_payload)
    assert response.status_code == 409


def test_delete_device(client, device_payload):
    device_id = client.post("/devices", json=device_payload).json()["id"]
    assert client.delete(f"/devices/{device_id}").status_code == 204
    assert client.get(f"/devices/{device_id}").status_code == 404


def test_delete_missing_device_404(client):
    assert client.delete("/devices/9999").status_code == 404


def test_export_nornir_shape(client, device_payload):
    client.post("/devices", json=device_payload)
    hosts = client.get("/export/nornir").json()
    assert hosts == {
        "edge-01": {
            "hostname": "10.0.0.1",
            "platform": "ios",
            "groups": ["router"],
            "data": {"site": "hq", "model": "ISR4331"},
        }
    }


def test_export_nornir_maps_known_vendors(client, device_payload):
    client.post("/devices", json={**device_payload, "hostname": "a", "vendor": "arista"})
    client.post(
        "/devices",
        json={**device_payload, "hostname": "b", "mgmt_ip": "10.0.0.3", "vendor": "juniper"},
    )
    client.post(
        "/devices",
        json={**device_payload, "hostname": "c", "mgmt_ip": "10.0.0.4", "vendor": "palo"},
    )
    hosts = client.get("/export/nornir").json()
    assert hosts["a"]["platform"] == "eos"
    assert hosts["b"]["platform"] == "junos"
    # An unmapped vendor passes through rather than being dropped or guessed at.
    assert hosts["c"]["platform"] == "palo"


def test_export_nornir_yaml_is_parseable(client, device_payload):
    client.post("/devices", json=device_payload)
    response = client.get("/export/nornir", params={"fmt": "yaml"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/yaml")
    assert yaml.safe_load(response.text) == client.get("/export/nornir").json()


def test_export_nornir_rejects_unknown_format(client):
    assert client.get("/export/nornir", params={"fmt": "toml"}).status_code == 400


def test_export_nornir_empty_inventory(client):
    assert client.get("/export/nornir").json() == {}


def test_ipv6_mgmt_ip_round_trips(client, device_payload):
    payload = {**device_payload, "hostname": "fw-01", "mgmt_ip": "2001:db8::1"}
    assert client.post("/devices", json=payload).status_code == 201
    assert client.get("/export/nornir").json()["fw-01"]["hostname"] == "2001:db8::1"


def test_lifespan_creates_schema(engine):
    """The app's own startup path, not the fixture's.

    Entering TestClient as a context manager runs the lifespan handler, which is
    what create_all relies on in compose and CI. Dropping the table first proves
    the handler recreates it rather than silently relying on the fixture.
    """
    Base.metadata.drop_all(engine)
    assert not inspect(engine).has_table("devices")

    with TestClient(app) as started_client:
        assert started_client.get("/health").status_code == 200

    assert inspect(engine).has_table("devices")
