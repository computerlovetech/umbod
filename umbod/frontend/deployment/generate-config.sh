#!/bin/sh
set -eu

jq -n --arg apiBaseUrl "${PUBLIC_API_BASE_URL:-/api}" --arg mcpBaseUrl "${PUBLIC_MCP_BASE_URL:-/mcp}" \
  --arg auth0Domain "${PUBLIC_AUTH0_DOMAIN:-}" --arg clientId "${PUBLIC_AUTH0_CLIENT_ID:-}" \
  --arg returnTo "${PUBLIC_LOGOUT_RETURN_URL:-}" '
  def dns: length <= 253 and (test("\\s") | not) and test("^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\\.)+[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$");
  def return_url:
    (test("\\s") | not) and test("^https://[a-zA-Z0-9.-]+(?::[0-9]{1,5})?/signed-out\\.html$") and
    (capture("^https://(?<host>[^/:]+)(?::(?<port>[0-9]+))?/signed-out\\.html$") |
      (.host | dns) and ((.port == null) or ((.port | tonumber) > 0 and (.port | tonumber) <= 65535)));
  if $auth0Domain == "" and $clientId == "" and $returnTo == "" then
    {apiBaseUrl: $apiBaseUrl, mcpBaseUrl: $mcpBaseUrl, logout: null}
  elif ($auth0Domain | dns) and ($clientId | length > 0 and length <= 256 and test("^[^\\s\u0000-\u001f\u007f]+$")) and ($returnTo | return_url) then
    {apiBaseUrl: $apiBaseUrl, mcpBaseUrl: $mcpBaseUrl, logout: {auth0Domain: $auth0Domain, clientId: $clientId, returnTo: $returnTo}}
  else error("Invalid public logout configuration") end'
