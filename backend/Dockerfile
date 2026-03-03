FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip

COPY pyproject.toml /app/pyproject.toml

RUN pip install --no-cache-dir -e .[dev]

COPY app /app/app
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini
COPY start.sh /app/start.sh

EXPOSE 8000

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
