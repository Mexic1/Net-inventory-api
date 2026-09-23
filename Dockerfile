# Alpine, not Debian slim: the Debian base plus its Python apt layers cost ~130 MB
# before a single dependency is installed, which puts the 150 MB budget out of
# reach on its own.
FROM python:3.12-alpine AS build

WORKDIR /app
COPY requirements.lock .
# psycopg[c] is compiled here rather than taken as a wheel. The pure-Python
# build finds libpq through ctypes.util.find_library, which needs ldconfig or
# gcc -- neither exists in the runtime image, so it fails there while working on
# a normal host. The C extension links libpq directly and sidesteps that. Its
# version is read from the lock so it cannot drift from psycopg itself.
# The toolchain stays in this stage and never reaches the runtime image.
# The final two finds drop the debug symbols the freshly compiled extension
# carries and the bytecode caches pip leaves behind: neither is any use at
# runtime, and together they account for most of psycopg[c]'s footprint.
RUN apk add --no-cache gcc musl-dev libpq-dev binutils \
    && pip install --no-cache-dir --prefix=/install -r requirements.lock \
    && pip install --no-cache-dir --prefix=/install \
        "psycopg[c]==$(sed -n 's/^psycopg==//p' requirements.lock)" \
    && find /install -name '*.so' -exec strip --strip-unneeded {} + \
    && find /install -name '__pycache__' -type d -prune -exec rm -rf {} +


# Runtime stage: no pip cache, no compilers, no test code (see .dockerignore).
FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# psycopg reaches PostgreSQL through libpq. The pure-Python build loads the
# system library at runtime rather than bundling its own copy, which is what
# psycopg[binary] does and what made the previous image 35 MB heavier.
RUN apk add --no-cache libpq

COPY --from=build /install /usr/local
COPY app/ ./app/

# A fixed high UID, so the container does not run as root and the numeric owner
# is predictable if a volume is ever mounted into it.
RUN adduser -D -H -u 10001 -s /sbin/nologin appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
