#!/usr/bin/env bash
#
# Installs the local Blender MCP setup:
#   - builds the gemma4-blender Ollama variant (32k context)
#   - writes ~/.mcphost.yml and ~/.mcphost-blender-system.md
#
# Safe to re-run. Prompts before overwriting anything.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_NAME="gemma4-blender"
BASE_MODEL="gemma4:e4b"

MCPHOST_CFG="$HOME/.mcphost.yml"
SYSTEM_PROMPT="$HOME/.mcphost-blender-system.md"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
die()  { printf '  \033[31m✗\033[0m %s\n' "$1" >&2; exit 1; }

confirm() {
  read -r -p "  $1 [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]]
}

# --- 1. dependencies ---------------------------------------------------------
bold "Checking dependencies"

for cmd in ollama mcphost uvx; do
  if command -v "$cmd" >/dev/null 2>&1; then
    ok "$cmd — $(command -v "$cmd")"
  else
    die "$cmd not found. See the requirements table in README.md"
  fi
done

if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
  ok "Ollama server is running"
else
  warn "Ollama server is not responding on :11434 — start it with 'ollama serve'"
fi

# --- 2. base model -----------------------------------------------------------
bold "Base model"

if ollama list | grep -q "^${BASE_MODEL}"; then
  ok "$BASE_MODEL present"
else
  warn "$BASE_MODEL not found locally"
  if confirm "Pull it now (~9.6GB)?"; then
    ollama pull "$BASE_MODEL"
  else
    die "Cannot continue without $BASE_MODEL"
  fi
fi

# --- 3. build the variant ----------------------------------------------------
bold "Building $MODEL_NAME"

ollama create "$MODEL_NAME" -f "$REPO/ollama/Modelfile.blender" >/dev/null
ctx=$(ollama show "$MODEL_NAME" 2>/dev/null | awk '/num_ctx/ {print $2}')
ok "$MODEL_NAME created (num_ctx ${ctx:-unknown})"

# --- 4. install configs ------------------------------------------------------
bold "Installing configs"

install_file() {
  local src="$1" dst="$2"
  if [[ -f "$dst" ]]; then
    if cmp -s "$src" "$dst"; then
      ok "$dst already up to date"
      return
    fi
    warn "$dst exists and differs"
    if confirm "Overwrite it? (a .bak copy is kept)"; then
      cp "$dst" "$dst.bak"
      cp "$src" "$dst"
      ok "$dst updated (backup at $dst.bak)"
    else
      warn "Skipped $dst"
    fi
  else
    cp "$src" "$dst"
    ok "$dst written"
  fi
}

install_file "$REPO/config/blender-system-prompt.md" "$SYSTEM_PROMPT"
install_file "$REPO/config/mcphost.yml" "$MCPHOST_CFG"

# mcphost does not expand ~ in the system-prompt field, so the path has to be
# rewritten for whatever $HOME this is running under.
if [[ -f "$MCPHOST_CFG" ]]; then
  tmp=$(mktemp)
  sed -E "s|^system-prompt:.*|system-prompt: \"$SYSTEM_PROMPT\"|" "$MCPHOST_CFG" > "$tmp"
  mv "$tmp" "$MCPHOST_CFG"
  ok "system-prompt path set to $SYSTEM_PROMPT"
fi

# --- 5. done -----------------------------------------------------------------
bold "Done"
cat <<EOF

  Next:
    1. Open Blender, press N in the viewport, BlenderMCP tab → Connect
    2. Check it:  lsof -iTCP:9876 -sTCP:LISTEN
    3. Run:       mcphost

EOF
