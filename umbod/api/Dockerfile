FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

WORKDIR /workspace

ENV UV_PROJECT_ENVIRONMENT=/app/.venv

COPY umbod/api/pyproject.toml umbod/api/uv.lock umbod/api/
COPY packages/umbod-sdk/pyproject.toml packages/umbod-sdk/README.md packages/umbod-sdk/
RUN uv sync --project umbod/api --frozen --no-default-groups --group shared --group api --group mcp --no-install-project --no-install-local

COPY umbod/api/README.md umbod/api/
COPY umbod/api/src umbod/api/src
COPY packages/umbod-sdk/src packages/umbod-sdk/src
RUN uv sync --project umbod/api --frozen --no-default-groups --group shared --group api --group mcp --no-editable --compile-bytecode
RUN apt-get update \
    && apt-get install --no-install-recommends --yes binutils \
    && find /app/.venv -type f -name '*.so' -exec strip --strip-unneeded {} + \
    && rm -rf /var/lib/apt/lists/*

FROM python:3.14-slim AS python-runtime
RUN mkdir /runtime-libs && cp /usr/lib/*/libsqlite3.so.0* /runtime-libs/

FROM gcr.io/distroless/cc-debian13

WORKDIR /app

COPY --from=python-runtime /usr/local /usr/local
COPY --from=python-runtime /runtime-libs /usr/local/lib
COPY --from=builder /app/.venv ./.venv

ENV PATH="/app/.venv/bin:$PATH"
ENV LD_LIBRARY_PATH="/usr/local/lib"
ENV PORT=8000

EXPOSE 8000 8001 8011 8012

CMD ["umbod", "api", "serve"]
