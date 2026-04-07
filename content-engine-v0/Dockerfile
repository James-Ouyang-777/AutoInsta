FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir -e .[dev]

EXPOSE 8000

ENV LLM_API_BASE="https://api.openai.com/v1" \
    LLM_MODEL="gpt-4o-mini" \
    REQUEST_TIMEOUT_SECONDS="30" \
    DEFAULT_VARIANTS="3"

CMD ["uvicorn", "content_engine.api:app", "--host", "0.0.0.0", "--port", "8000"]
