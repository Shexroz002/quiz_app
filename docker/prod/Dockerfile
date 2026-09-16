# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Builder: compiles the wheels that need a toolchain, so the toolchain itself
# never reaches the image that runs in production.
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    TZ=Asia/Tashkent

# libpq5 is what psycopg2 links against at run time (Alembic uses it), curl
# serves the health check, tzdata makes TZ=Asia/Tashkent resolve.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY . .

# media/ is a mounted volume in production. The directory has to exist for
# StaticFiles to mount at start-up, but the image must not carry any files that
# would sit under the volume.
RUN rm -rf media && mkdir -p media \
    && useradd -m -u 1000 appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/ || exit 1

# One worker, deliberately. The WebSocket registries in app/websocket (chat,
# notifications, live sessions) are plain in-process dicts, so a second worker
# would hold its own set of connections and silently drop broadcasts between
# clients that landed on different workers. Scaling past one worker needs those
# broadcasts to go through Redis first.
#
# There is no --max-requests recycling either: with a single worker a recycle is
# a full restart that drops every open WebSocket.
CMD ["gunicorn", "app.main:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "--workers", "1", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--keep-alive", "30", \
     "--worker-tmp-dir", "/dev/shm"]
