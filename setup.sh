#!/bin/sh
# Public installer. Keep all effects inside main so an incomplete download cannot start setup.
main() {
  set -eu
  remote=https://github.com/Swixixle/Blinders.git
  app="${BLINDERS_INSTALL_DIR:-$HOME/.local/share/blinders/app}"
  if [ -e "$app" ]; then
    if [ ! -d "$app/.git" ] || [ "$(git -C "$app" remote get-url origin)" != "$remote" ]; then
      echo "Another folder occupies $app. Choose BLINDERS_INSTALL_DIR." >&2
      exit 1
    fi
    echo "Using existing Blinders checkout at $app."
  else
    mkdir -p "$(dirname "$app")"
    git clone -- "$remote" "$app"
  fi
  sh "$app/install.sh" --agents
  if [ "${1:-}" != '--no-open' ]; then
    exec "${BLINDERS_BIN_DIR:-$HOME/.local/bin}/blinders" open
  fi
}
main "$@"
