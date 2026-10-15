# API and worker image (same image, different command). Python 3.12, non-root, no secrets baked in.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv
RUN pip install --no-cache-dir uv==0.8.* && useradd -m -u 10001 app
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra gcp --no-install-project
COPY src ./src
COPY db ./db
RUN uv sync --frozen --no-dev --extra gcp
USER app
ENV PATH=/opt/venv/bin:$PATH PORT=8080
# API by default; the worker overrides the command: ["python", "-m", "finassist.worker"]
CMD ["sh", "-c", "uvicorn finassist.api.app:app --host 0.0.0.0 --port ${PORT} --proxy-headers"]
