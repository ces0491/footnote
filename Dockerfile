# The Python services (replayer, processor, agents). One image recipe; SERVICE picks the entry point.
# Only the committed showcase match goes in: the league, the match metadata, the feed and the
# tracking. The answer key stays out (see .dockerignore).

FROM python:3.11.17-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.11.17-slim
ARG SERVICE
RUN useradd --system --uid 10001 --no-create-home footnote
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY data/league.json /app/data/league.json
COPY data/matches/fl-2627-showcase-sal-kin/meta.json data/matches/fl-2627-showcase-sal-kin/feed.jsonl \
     data/matches/fl-2627-showcase-sal-kin/tracking.npz /app/data/matches/fl-2627-showcase-sal-kin/
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    FOOTNOTE_DATA_DIR=/app/data \
    FOOTNOTE_SERVICE=${SERVICE}
USER footnote
CMD ["sh", "-c", "exec python -m footnote.$FOOTNOTE_SERVICE"]
