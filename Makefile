# Omarchy keeps users out of the root-equivalent docker group and reaches the
# daemon through a prompt instead. omarchy-sudo-docker exits 0 when sudo is
# needed, so this works on Omarchy and on a plain docker-group setup alike.
DOCKER := $(shell command -v omarchy-sudo-docker >/dev/null 2>&1 && omarchy-sudo-docker && echo "sudo docker" || echo "docker")
PY     := .venv/bin/python
BIN    := .venv/bin

.PHONY: venv lock lint test up down logs build sudo-keepalive

venv:            ## create .venv on Python 3.12 and install dev deps
	uv venv --python 3.12
	uv pip install -r requirements-dev.txt

lock:            ## refresh requirements.lock (exact pins used by the image)
	uv pip compile requirements.txt -o requirements.lock --python-version 3.12

lint:
	$(BIN)/ruff check .

test:
	$(BIN)/pytest -q

sudo-keepalive:  ## prompt once, keep sudo warm for a batch of docker commands
	omarchy-sudo-keepalive

up:
	$(DOCKER) compose up --build -d

down:
	$(DOCKER) compose down -v

logs:
	$(DOCKER) compose logs -f api

build:
	$(DOCKER) build -t net-inventory-api:dev .
