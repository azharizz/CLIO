FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY backend/pyproject.toml ./pyproject.toml
COPY backend/filmgraph ./filmgraph
COPY data ./data
RUN pip install --no-cache-dir .

EXPOSE 8080

CMD ["sh", "-c", "uvicorn filmgraph.main:app --host 0.0.0.0 --port ${PORT}"]
