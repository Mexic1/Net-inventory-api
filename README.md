# net-inventory-api

REST API over a network device inventory. Its `GET /export/nornir` endpoint emits a
Nornir-compatible `hosts.yaml`, which becomes the source of truth for the config
backup / drift-detection project (N1).

> Status: scaffolding (phase 0). Full README, architecture diagram and quick start land in phase 6.

## Stack

| Layer | Tool | Version |
|---|---|---|
| API | FastAPI + uvicorn | see `requirements.txt` |
| ORM | SQLAlchemy | 2.x |
| Database | PostgreSQL | 17 |
| Runtime | Python | 3.12 |
| Container | Docker Engine / Compose | 29.x / v2 |
| CI | GitHub Actions (ruff, pytest, Trivy, GHCR) | — |

## Local setup

```bash
make venv      # uv venv on Python 3.12 + dev deps
make lint
make test
```

## Docker on Omarchy

Omarchy deliberately leaves users out of the root-equivalent `docker` group, so
Docker commands elevate instead. The Makefile detects this via `omarchy-sudo-docker`
and prefixes `sudo` automatically — `make up` works either way. To avoid repeated
prompts during a work session:

```bash
make sudo-keepalive   # prompts once, keeps the credential warm
```
