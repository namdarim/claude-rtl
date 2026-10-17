#!/usr/bin/env bash
# Put back the original app.asar that tools/install.sh saved for the installed version.
# Run with sudo, then restart the app. The apt hook (tools/apt-hook.sh) then leaves the app
# unpatched, through updates too, until tools/install.sh runs again.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || [ -n "${DESKTOP_PATCH_TEST:-}" ] || { echo "run with sudo: sudo bash $0" >&2; exit 1; }

here="$(cd "$(dirname "$0")/.." && pwd)"
# DESKTOP_PATCH_TEST points every path into a test folder (test/test_scripts.sh)
asar="${DESKTOP_PATCH_ASAR:-/usr/lib/claude-desktop/resources/app.asar}"
version="$(dpkg-query -W -f='${Version}' claude-desktop)"
backups="${DESKTOP_PATCH_BACKUPS:-/var/backups/claude-desktop-patch}"
backup="$backups/app.asar.$version"

# Before anything else, so a reinstall of the package that follows a failed revert stays unpatched too
if [ -d "$backups" ]; then
  echo "tools/revert.sh ran; the apt hook leaves the app unpatched until tools/install.sh runs" > "$backups/reverted"
fi
if ! python3 "$here/tools/patch_asar.py" --check "$asar"; then
  echo "app.asar is not patched; nothing to undo"
  exit 0
fi
[ -f "$backup" ] || { echo "no saved original for $version; run: sudo apt-get install --reinstall claude-desktop" >&2; exit 1; }
cp -p "$backup" "$asar.revert-new"
mv -f "$asar.revert-new" "$asar"
echo "claude-desktop $version is back to its original app.asar; restart the app"
