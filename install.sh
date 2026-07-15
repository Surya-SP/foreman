#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./install.sh                  # global only (recommended) — works in every project
#   ./install.sh /path/to/project # global + project .foreman/ seed (optional)
#   ./install.sh --project /path  # same as above
#   ./install.sh --global-only    # explicit global only

FOREMAN_HOME="$(cd "$(dirname "$0")" && pwd)"
GLOBAL_OC="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"
TARGET=""
GLOBAL_ONLY=0

usage() {
  cat <<EOF
Usage: $0 [--global-only | /path/to/project]

  (no args) / --global-only
      Install once for all projects:
        ~/.local/bin/foreman
        ~/.config/opencode/agent/*.md      (foreman + 9 roles)
        ~/.config/opencode/command/ship.md
        ~/.config/opencode/skill/foreman/

  /path/to/project
      Same global install, plus create project/.foreman/ and
      optional project-local .opencode links (only if you want
      the agents committed with the repo).

You do NOT need to re-run this for every Flutter project after a global install.
Just:  cd project && foreman run
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --global-only) GLOBAL_ONLY=1; shift ;;
    --project) TARGET="$(cd "$2" 2>/dev/null && pwd)" || { echo "Error: '$2' not found" >&2; exit 1; }; shift 2 ;;
    -*)
      echo "Unknown flag: $1" >&2; usage; exit 1 ;;
    *)
      TARGET="$(cd "$1" 2>/dev/null && pwd)" || { echo "Error: '$1' not found" >&2; exit 1; }; shift ;;
  esac
done

echo "Foreman home: $FOREMAN_HOME"
echo "Installing globally → $GLOBAL_OC"

# ── Global CLI ──────────────────────────────────────────────────────────────
mkdir -p "$HOME/.local/bin"
ln -sfn "$FOREMAN_HOME/bin/foreman" "$HOME/.local/bin/foreman"

# Also link into common PATH dirs used by GUI apps / OpenCode (best-effort).
for bin_dir in /opt/homebrew/bin /usr/local/bin; do
  if [ -d "$bin_dir" ] && [ -w "$bin_dir" ]; then
    ln -sfn "$FOREMAN_HOME/bin/foreman" "$bin_dir/foreman"
    echo "  also:  $bin_dir/foreman"
  fi
done

# ── Global OpenCode agents / command / skill ────────────────────────────────
mkdir -p "$GLOBAL_OC/agent" "$GLOBAL_OC/command" "$GLOBAL_OC/skill/foreman"

for f in "$FOREMAN_HOME"/opencode/agent/*.md; do
  [ -f "$f" ] || continue
  ln -sfn "$f" "$GLOBAL_OC/agent/$(basename "$f")"
done
ln -sfn "$FOREMAN_HOME/opencode/command/ship.md" "$GLOBAL_OC/command/ship.md"
ln -sfn "$FOREMAN_HOME/opencode/skill/foreman/SKILL.md" "$GLOBAL_OC/skill/foreman/SKILL.md"

agent_count=$(find "$GLOBAL_OC/agent" -maxdepth 1 -name '*.md' 2>/dev/null | wc -l | tr -d ' ')

echo "  CLI:     $HOME/.local/bin/foreman"
echo "  Agents:  $GLOBAL_OC/agent/  ($agent_count files)"
echo "  Command: $GLOBAL_OC/command/ship.md  → /ship"
echo "  Skill:   $GLOBAL_OC/skill/foreman/"

# ── ripgrep (token-cheap code search for agents) ────────────────────────────
# Never fail install if rg is missing. Skip auto-install on CI / non-interactive.
if command -v rg >/dev/null 2>&1; then
  echo "  rg:      $(command -v rg)  ($(rg --version 2>/dev/null | head -1 || true))"
elif [ "${CI:-}" = "true" ] || [ "${FOREMAN_SKIP_RG_INSTALL:-}" = "1" ] || [ ! -t 0 ]; then
  echo "  rg:      not found (skip auto-install on CI/non-interactive)"
  echo "         optional: brew install ripgrep  |  apt install ripgrep"
else
  echo "  rg:      not found — installing ripgrep if package manager available…"
  installed=0
  if command -v brew >/dev/null 2>&1; then
    if brew list ripgrep >/dev/null 2>&1 || brew install ripgrep; then
      installed=1
      echo "  rg:      via brew → $(command -v rg || true)"
    fi
  fi
  if [ "$installed" -eq 0 ] && command -v apt-get >/dev/null 2>&1; then
    if (sudo -n apt-get install -y ripgrep 2>/dev/null) || true; then
      if command -v rg >/dev/null 2>&1; then
        installed=1
        echo "  rg:      via apt → $(command -v rg || true)"
      fi
    fi
  fi
  if [ "$installed" -eq 0 ] && command -v pacman >/dev/null 2>&1; then
    if sudo -n pacman -S --noconfirm ripgrep 2>/dev/null; then
      installed=1
      echo "  rg:      via pacman → $(command -v rg || true)"
    fi
  fi
  if ! command -v rg >/dev/null 2>&1; then
    echo "  rg:      STILL MISSING — install: brew install ripgrep  |  apt install ripgrep"
  fi
fi

# ── Optional per-project ────────────────────────────────────────────────────
if [ -n "$TARGET" ] && [ "$GLOBAL_ONLY" -eq 0 ]; then
  echo ""
  echo "Project seed: $TARGET"
  mkdir -p "$TARGET/.foreman/handoffs"
  # Project-local links are optional; global agents already apply.
  # Link only if user wants repo-local visibility (gitignore .opencode if not).
  mkdir -p "$TARGET/.opencode/agent" "$TARGET/.opencode/command" "$TARGET/.opencode/skill/foreman"
  for f in "$FOREMAN_HOME"/opencode/agent/*.md; do
    [ -f "$f" ] || continue
    ln -sfn "$f" "$TARGET/.opencode/agent/$(basename "$f")"
  done
  ln -sfn "$FOREMAN_HOME/opencode/command/ship.md" "$TARGET/.opencode/command/ship.md"
  ln -sfn "$FOREMAN_HOME/opencode/skill/foreman/SKILL.md" "$TARGET/.opencode/skill/foreman/SKILL.md"
  echo "  .foreman/ + .opencode/ linked (optional; global install is enough)"
fi

cat <<EOF

Done. Global install is enough for every project.

Ensure PATH:
  export PATH="\$HOME/.local/bin:\$PATH"

Build an app (any path — not inside this repo):
  flutter create my_app && cd my_app
  foreman doctor
  foreman discover
  foreman ready
  foreman design run && foreman design show && foreman design approve
  foreman run

Flow: discover → ready → design approve → run
Agent tools: foreman help --agent

EOF
