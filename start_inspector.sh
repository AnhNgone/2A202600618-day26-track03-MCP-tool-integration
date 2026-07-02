#!/usr/bin/env bash
# Launches MCP Inspector against this lab's FastMCP server.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p .npm-cache
# Local-only lab server: skip the proxy session-token prompt so the browser
# tab connects immediately instead of silently failing without it.
export DANGEROUSLY_OMIT_AUTH=true
# Inspector embeds the full inherited PATH (JSON + URL-encoded) into the
# STDIO connect request URL. A long dev-machine PATH can push that URL past
# the proxy's request-size limit and cause silent "SSE connection not
# established" / timeout failures. Trim PATH to just what's needed.
PYTHON_DIR="$(dirname "$(command -v python)")"
export PATH="$PYTHON_DIR:/usr/bin:/bin"
NPM_CONFIG_CACHE="$PWD/.npm-cache" npx -y @modelcontextprotocol/inspector python mcp_server.py
