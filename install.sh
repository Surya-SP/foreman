#!/usr/bin/env bash
set -euo pipefail

# Usage: ./install.sh /path/to/project

FOREMAN_HOME="$(cd "$(dirname "$0")" && pwd)"

if [ $# -lt 1 ]; then
  echo "Usage: $0 /path/to/project" >&2; exit 1
fi
TARGET="$(cd "$1" 2>/dev/null && pwd)" || { echo "Error: '$1' not found" >&2; exit 1; }

echo "Installing Foreman in: $TARGET"

# Runtime state dir only — hidden, per-project.
mkdir -p "$TARGET/.foreman/handoffs"

# Skill: symlink directly to the source of truth. No copy.
mkdir -p "$TARGET/.opencode/skills"
ln -sf "$FOREMAN_HOME/skills/foreman.md" "$TARGET/.opencode/skills/foreman.md"

# Wrapper on PATH.
mkdir -p "$HOME/.local/bin"
ln -sf "$FOREMAN_HOME/bin/foreman" "$HOME/.local/bin/foreman"

cat <<EOF

Done.
  Runtime state:  $TARGET/.foreman/          (hidden; created on first tool run)
  Skill:          $TARGET/.opencode/skills/foreman.md -> $FOREMAN_HOME/skills/foreman.md
  CLI wrapper:    $HOME/.local/bin/foreman   -> $FOREMAN_HOME/bin/foreman

Ensure ~/.local/bin is on PATH:
  export PATH="\$HOME/.local/bin:\$PATH"

Test:
  foreman doctor
  foreman info --brief
EOF
