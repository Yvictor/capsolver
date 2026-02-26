FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY . /app

RUN uv sync && apt-get update && apt-get install -y --no-install-recommends curl libgtk-3-0 libasound2 libx11-xcb1 && rm -rf /var/lib/apt/lists/*

# Pre-download camoufox browser binary so it's cached in the image
RUN uv run python -c "from camoufox.pkgman import camoufox_path; camoufox_path()"

EXPOSE 9987

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:9987/health || exit 1

CMD ["uv", "run", "app"]
