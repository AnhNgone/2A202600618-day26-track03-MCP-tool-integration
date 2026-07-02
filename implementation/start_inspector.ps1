# Launches MCP Inspector against this lab's FastMCP server (Windows PowerShell).
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Force .npm-cache | Out-Null
$env:NPM_CONFIG_CACHE = Join-Path $PSScriptRoot ".npm-cache"
# Local-only lab server: skip the proxy session-token prompt so the browser
# tab connects immediately instead of silently failing without it.
$env:DANGEROUSLY_OMIT_AUTH = "true"
# Inspector embeds the full inherited PATH (JSON + URL-encoded) into the
# STDIO connect request URL. A long dev-machine PATH (IDEs, Docker, JDKs,
# etc.) can push that URL past the proxy's request-size limit and cause
# silent "SSE connection not established" / timeout failures. Trim PATH to
# just what's needed to run python/node for this lab.
$pythonDir = Split-Path (Get-Command python).Source
$env:PATH = "$pythonDir;$pythonDir\Scripts;C:\WINDOWS\system32;C:\WINDOWS;C:\WINDOWS\System32\Wbem;C:\Program Files\nodejs\"
npx -y @modelcontextprotocol/inspector python mcp_server.py
