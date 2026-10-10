#!/usr/bin/env bash
# Patch the installed Claude desktop app with this folder's src/. Run with sudo, then restart the app.
# The original app.asar is kept in /var/backups/claude-desktop-patch/ under the app's version, and
# tools/revert.sh puts it back. After an app update, run this again.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || [ -n "${DESKTOP_PATCH_TEST:-}" ] || { echo "run with sudo: sudo bash $0" >&2; exit 1; }

here="$(cd "$(dirname "$0")/.." && pwd)"
# DESKTOP_PATCH_TEST points both paths into a test folder (test/test_scripts.sh)
asar="${DESKTOP_PATCH_ASAR:-/usr/lib/claude-desktop/resources/app.asar}"
version="$(dpkg-query -W -f='${Version}' claude-desktop)"
backups="${DESKTOP_PATCH_BACKUPS:-/var/backups/claude-desktop-patch}"
backup="$backups/app.asar.$version"

if python3 "$here/tools/patch_asar.py" --check "$asar"; then
  # Already patched: rebuild from the original, so the current src/ replaces the earlier patch
  [ -f "$backup" ] || { echo "app.asar is patched but $backup is missing; reinstall claude-desktop first" >&2; exit 1; }
else
  install -d -m 755 "$backups"
  cp -p "$asar" "$backup.tmp"
  mv -f "$backup.tmp" "$backup"
fi

python3 "$here/tools/patch_asar.py" "$backup" "$asar.patch-new" "$here/src"
chown --reference="$backup" "$asar.patch-new"
chmod --reference="$backup" "$asar.patch-new"
mv -f "$asar.patch-new" "$asar"
echo "patched claude-desktop $version; restart the app to load it"
echo "to undo: sudo bash $here/tools/revert.sh"
