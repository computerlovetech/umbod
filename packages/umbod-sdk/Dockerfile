FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

ARG UMBOD_RELEASE=development

ENV UMBOD_RELEASE=${UMBOD_RELEASE}
ENV UV_LINK_MODE=copy

WORKDIR /workspace

COPY packages/umbod-sdk /opt/umbod-connector-sdk
RUN uv pip install --system /opt/umbod-connector-sdk

CMD ["python"]
