FROM python:3.11-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip wheel --wheel-dir /wheels .

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    DATABASE_URL=sqlite:////app/data/veriagent.db

RUN groupadd --gid 10001 veriagent \
    && useradd --uid 10001 --gid veriagent --shell /usr/sbin/nologin --create-home veriagent

COPY --from=builder /wheels /wheels
RUN python -m pip install --no-index --find-links=/wheels /wheels/veriagent-*.whl \
    && rm -rf /wheels

WORKDIR /app
RUN mkdir -p /app/data /app/corpus /app/chroma_data && chown -R veriagent:veriagent /app

USER veriagent
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/health', timeout=3)" || exit 1

CMD ["sh", "-c", "exec uvicorn veriagent.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
