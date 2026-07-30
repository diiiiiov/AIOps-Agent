FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /opt/ops-diagnosis

RUN python -m pip install --no-cache-dir "uv==0.12.0"

COPY pyproject.toml uv.lock README.md ./
COPY app/ ./app/
COPY skills/ ./skills/
COPY static/ ./static/

RUN uv sync --frozen --no-dev --no-managed-python \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /opt/ops-diagnosis/logs /opt/ops-diagnosis/uploads /opt/ops-diagnosis/volumes \
    && chown -R appuser:appuser /opt/ops-diagnosis

USER appuser
EXPOSE 9900

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["/opt/venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9900/health', timeout=3)"]

CMD ["/opt/venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9900"]
