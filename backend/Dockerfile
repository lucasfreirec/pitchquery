# PitchQuery API. The dataset lives in a volume at /data and is built on first start.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    PITCHQUERY_DATA_DIR=/data

# Dependencies first, so code changes do not reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY pitchquery ./pitchquery
RUN uv sync --locked --no-dev

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && useradd --create-home pitchquery \
    && mkdir -p /data && chown pitchquery /data
USER pitchquery

EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "pitchquery.api:app", "--host", "0.0.0.0", "--port", "8000"]
