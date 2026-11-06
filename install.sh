#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
agents=false
case "${1:-}" in --agents) agents=true ;; '') ;; *) echo "Usage: sh install.sh [--agents]" >&2; exit 2 ;; esac
python3 -c 'import sqlite3, sys; sys.exit(0 if sys.version_info >= (3, 9) else "Blinders requires Python 3.9+.")'
bindir="${BLINDERS_BIN_DIR:-$HOME/.local/bin}"
mkdir -p "$bindir"
command_path="$bindir/blinders"
if [ -L "$command_path" ] && [ "$(readlink "$command_path")" = "$repo/bin/blinders" ]; then
  :
elif [ -e "$command_path" ] || [ -L "$command_path" ]; then
  echo "Another executable exists at $command_path. Set BLINDERS_BIN_DIR to choose another folder." >&2
  exit 1
else
  ln -s "$repo/bin/blinders" "$command_path"
fi
printf 'Installed %s\nChrome extension folder: %s/browser\n' "$command_path" "$repo"
if [ "$agents" = true ]; then
  for client in codex claude; do
    if ! command -v "$client" >/dev/null 2>&1; then
      echo "$client is not installed or on PATH. Rerun install.sh --agents after installing it."
      continue
    fi
    if "$client" mcp get blinders >/dev/null 2>&1; then
      echo "$client already has an MCP entry named blinders; preserving its configuration."
    elif [ "$client" = claude ]; then
      claude mcp add --scope user --transport stdio blinders -- "$command_path" mcp
    else
      codex mcp add blinders -- "$command_path" mcp
    fi
  done
fi
printf 'Start: "%s" open\n' "$command_path"
