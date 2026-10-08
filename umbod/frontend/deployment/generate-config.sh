#!/bin/sh
set -eu

jq -n --arg apiBaseUrl "${PUBLIC_API_BASE_URL:-/api}" --arg mcpBaseUrl "${PUBLIC_MCP_BASE_URL:-/mcp}" '{apiBaseUrl: $apiBaseUrl, mcpBaseUrl: $mcpBaseUrl}'
