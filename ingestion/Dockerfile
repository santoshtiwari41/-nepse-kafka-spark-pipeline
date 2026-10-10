# Data collection + live/replay producers. Dependencies are installed with uv at build time,
# so nothing has to be installed on the host (no virtual environment).
FROM python:3.12-slim

# uv: fast Python package installer
COPY --from=ghcr.io/astral-sh/uv:0.4.30 /uv /usr/local/bin/uv

# git is needed for the NepseUnofficialApi dependency (installed from GitHub)
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN uv pip install --system --no-cache -r /tmp/requirements.txt

# Code (ingestion/) and data (data/) are mounted at run time by docker compose
WORKDIR /app
ENV PYTHONUNBUFFERED=1 HOME=/tmp
