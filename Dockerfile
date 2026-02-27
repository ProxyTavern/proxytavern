FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml /app/
COPY src /app/src

RUN pip install --no-cache-dir .

RUN mkdir -p /data

EXPOSE 8080

CMD ["uvicorn", "proxytavern.app:build_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
