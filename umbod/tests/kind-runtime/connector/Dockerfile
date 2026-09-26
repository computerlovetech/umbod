FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

WORKDIR /workspace
COPY pyproject.toml ./
COPY src ./src
RUN uv build --wheel --out-dir /tmp/wheels \
    && uv pip install --python /usr/local/bin/python3 --target /plugin-bundle --no-deps /tmp/wheels/*.whl \
    && test ! -e /plugin-bundle/umbod_sdk

FROM alpine:3.23
COPY --from=builder /plugin-bundle /plugin-bundle
ENTRYPOINT ["sh", "-c", "cp -R /plugin-bundle/. /plugins/"]
