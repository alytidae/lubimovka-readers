FROM astral/uv:python3.12-bookworm-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

COPY . .

EXPOSE 8000

CMD uv run python manage.py collectstatic --noinput && \
    uv run gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3
