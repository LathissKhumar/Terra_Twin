FROM python:3.12.16-slim-bookworm
RUN apt-get update \
    && apt-get install -y --no-install-recommends libexpat1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /bin/uv
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY app ./app
COPY config ./config
RUN uv sync --locked --no-dev --no-editable
COPY migrations ./migrations
COPY alembic.ini ./
RUN useradd --uid 10001 --create-home terratwin
USER terratwin
ENV PATH="/opt/venv/bin:$PATH" DATA_DIR=/app/data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

