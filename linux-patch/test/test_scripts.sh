#!/usr/bin/env bash
# Run tools/install.sh and tools/revert.sh against a copy of the installed app.asar in build/scripts;
# nothing outside build/ is touched. Run with: bash test/test_scripts.sh
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
dir="$root/build/scripts"
rm -rf "$dir"; mkdir -p "$dir/backups"
installed=/usr/lib/claude-desktop/resources/app.asar
# Start from the unpatched archive: the installed one, or the saved original once it is patched
source="$installed"
if python3 "$root/tools/patch_asar.py" --check "$installed"; then
  source="/var/backups/claude-desktop-patch/app.asar.$(dpkg-query -W -f='${Version}' claude-desktop)"
fi
cp "$source" "$dir/app.asar"
export DESKTOP_PATCH_TEST=1 DESKTOP_PATCH_ASAR="$dir/app.asar" DESKTOP_PATCH_BACKUPS="$dir/backups"
original=$(sha256sum < "$dir/app.asar")

bash "$root/tools/install.sh" >/dev/null
python3 "$root/tools/patch_asar.py" --check "$dir/app.asar" || { echo "FAIL: not patched after install"; exit 1; }
first=$(sha256sum < "$dir/app.asar")
bash "$root/tools/install.sh" >/dev/null   # again: rebuilt from the saved original, same result
[ "$(sha256sum < "$dir/app.asar")" = "$first" ] || { echo "FAIL: a second install differs"; exit 1; }
bash "$root/tools/revert.sh" >/dev/null
[ "$(sha256sum < "$dir/app.asar")" = "$original" ] || { echo "FAIL: revert did not restore the original"; exit 1; }
bash "$root/tools/revert.sh" | grep -q 'nothing to undo' || { echo "FAIL: a second revert"; exit 1; }
echo ok
