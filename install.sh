#!/bin/sh
# Link this skill into ~/.claude/skills so Claude Code finds it.
#
# A symlink rather than a copy, so edits to the repo take effect with no
# reinstall — just /reload-plugins in a running session.
#
#   ./install.sh              link it
#   ./install.sh --uninstall  remove the link
set -eu

repo=$(cd "$(dirname "$0")" && pwd)
src="$repo/skills/numbers"
dest="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
link="$dest/numbers"

case "${1:-}" in
  --uninstall)
    # Only remove our own link. A real directory there is someone else's
    # skill and is not ours to delete.
    if [ -L "$link" ] && [ "$(readlink "$link")" = "$src" ]; then
      rm "$link"
      echo "unlinked $link"
    else
      echo "nothing to do: $link is not a link into this repo" >&2
    fi
    exit 0
    ;;
  "") ;;
  *) echo "usage: $0 [--uninstall]" >&2; exit 2 ;;
esac

[ -d "$src" ] || { echo "missing $src — is this a complete clone?" >&2; exit 1; }

# `ln -s` into an existing directory silently nests the link inside it, which
# leaves the skill not loading and nothing to show why. Refuse instead.
if [ -d "$link" ] && [ ! -L "$link" ]; then
  echo "$link already exists and is a real directory." >&2
  echo "Move or remove it, then re-run." >&2
  exit 1
fi

mkdir -p "$dest"
ln -sfn "$src" "$link"   # -n so re-running replaces the link rather than nesting

echo "linked $link -> $src"
echo "Run /reload-plugins in a running Claude Code session to pick it up."
