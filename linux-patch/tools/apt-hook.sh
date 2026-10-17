#!/usr/bin/env bash
# Patch the Claude desktop app again whenever an apt run replaces its patched app.asar, as every
# update and every reinstall of claude-desktop does.
#
#   sudo bash tools/apt-hook.sh install   copy what this git clone has committed of src/ and the
#                                         install tools to a folder of root's, patch the app from
#                                         that copy, and add the apt hook
#   sudo bash tools/apt-hook.sh remove    take the hook and its copy away; the patch stays on the app
#   tools/apt-hook.sh run                 what apt runs after each run of dpkg (DPkg::Post-Invoke)
#
# apt runs the hook as root with nobody watching, so the hook runs only the root-owned copy, never a
# folder another user can write to. It never fails apt: an error is printed, logged, and the hook
# exits 0. After tools/revert.sh it leaves the app alone until tools/install.sh runs again. The copy
# changes only when install runs again, so run it after each change to the patch.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
# DESKTOP_PATCH_TEST points every path into a test folder (test/test_scripts.sh)
asar="${DESKTOP_PATCH_ASAR:-/usr/lib/claude-desktop/resources/app.asar}"
backups="${DESKTOP_PATCH_BACKUPS:-/var/backups/claude-desktop-patch}"
lib="${DESKTOP_PATCH_LIB:-/usr/local/lib/claude-desktop-patch}"
conf="${DESKTOP_PATCH_APT_CONF:-/etc/apt/apt.conf.d/99claude-desktop-patch}"
parts=(src tools/patch_asar.py tools/install.sh tools/revert.sh tools/apt-hook.sh)

need_root() {
  [ "$(id -u)" -eq 0 ] || [ -n "${DESKTOP_PATCH_TEST:-}" ] || { echo "run with sudo: sudo bash $0 $1" >&2; exit 1; }
}

# The hook. What it prints also goes to the journal (journalctl -t claude-desktop-patch), since apt's
# output scrolls away.
run() {
  exec </dev/null
  [ -f "$asar" ] || return 0                                                    # claude-desktop is not installed
  python3 "$here/tools/patch_asar.py" --check "$asar" 2>/dev/null && return 0  # still patched
  [ ! -e "$backups/reverted" ] || return 0                                      # undone with revert.sh
  local out status=0 text
  out=$(bash "$here/tools/install.sh" 2>&1) || status=$?
  text="app.asar has no patch after this apt run; patching it again"$'\n'"$out"
  if [ "$status" -ne 0 ]; then
    text+=$'\n'"FAILED (exit $status); apt is not affected, and the app runs without the patch."
    text+=$'\n'"To try again: sudo bash $here/tools/install.sh; to stop trying: sudo bash $here/tools/revert.sh"
  fi
  printf '%s\n' "$text" | sed 's/^/claude-desktop-patch: /'
  [ -n "${DESKTOP_PATCH_TEST:-}" ] || printf '%s\n' "$text" | logger -t claude-desktop-patch 2>/dev/null || true
}

install_hook() {
  need_root install
  umask 022
  local owner as_owner=() changes tmp
  [ -d "$(dirname "$conf")" ] || { echo "no $(dirname "$conf"): this system does not use apt" >&2; exit 1; }
  case "$lib" in *[\"\'\\]*|*$'\n'*) echo "$lib cannot be written into an apt setting" >&2; exit 1 ;; esac
  [ ! -e "$lib" ] || [ -f "$lib/tools/apt-hook.sh" ] || { echo "$lib exists and is not this hook's copy" >&2; exit 1; }
  # git runs as the clone's owner: root running git in a folder another user owns is what
  # safe.directory forbids, since the clone's own settings can run commands
  owner="$(stat -c %U "$here")"
  if [ "$(id -u)" -eq 0 ] && [ "$owner" != root ]; then as_owner=(runuser -u "$owner" --); fi
  "${as_owner[@]}" git -C "$here" ls-files --error-unmatch -- "${parts[@]}" >/dev/null 2>&1 \
    || { echo "run this from a git clone that has ${parts[*]} committed" >&2; exit 1; }
  changes="$("${as_owner[@]}" git -C "$here" status --porcelain -- "${parts[@]}")"
  [ -z "$changes" ] || { echo "commit src/ and tools/ first: only what is committed is installed" >&2; exit 1; }

  trap 'rm -rf "$lib.new"' EXIT
  rm -rf "$lib.new" "$lib.old"
  mkdir -p "$lib.new"
  "${as_owner[@]}" git -C "$here" archive HEAD "${parts[@]}" \
    | tar -x -f - --no-same-owner --no-same-permissions -C "$lib.new"
  [ -z "$(find "$lib.new" ! -type f ! -type d)" ] || { echo "only plain files can be installed" >&2; exit 1; }
  chmod -R u=rwX,go=rX "$lib.new"
  [ "$(id -u)" -ne 0 ] || chown -R root:root "$lib.new"
  [ ! -e "$lib" ] || mv "$lib" "$lib.old"
  mv "$lib.new" "$lib"
  if ! bash "$lib/tools/install.sh"; then
    rm -rf "$lib"
    [ ! -e "$lib.old" ] || mv "$lib.old" "$lib"
    echo "patching failed, so the apt hook and its copy are as they were" >&2
    exit 1
  fi
  rm -rf "$lib.old"

  tmp="$(dirname "$conf")/.$(basename "$conf").new"   # apt skips hidden files
  cat > "$tmp" <<EOF
// Added by claude-desktop-patch: after each apt run, patch the Claude desktop app's app.asar again
// if an update or a reinstall of claude-desktop replaced it. To remove this and its copy:
// sudo bash $lib/tools/apt-hook.sh remove
DPkg::Post-Invoke { "if [ -f '$lib/tools/apt-hook.sh' ]; then /bin/bash '$lib/tools/apt-hook.sh' run || true; fi"; };
EOF
  chmod 644 "$tmp"
  mv -f "$tmp" "$conf"
  echo "added the apt hook $conf; after an app update it patches the app from $lib"
  echo "to remove it: sudo bash $lib/tools/apt-hook.sh remove"
}

remove_hook() {
  need_root remove
  rm -f "$conf"
  echo "removed the apt hook $conf"
  if [ -f "$lib/tools/apt-hook.sh" ]; then
    rm -rf "$lib"
    echo "removed its copy $lib"
  fi
  echo "the patch stays on the app until its next update; tools/revert.sh takes it off now"
}

case "${1:-}" in
  install) install_hook ;;
  remove) remove_hook ;;
  run) run || true ;;
  *) echo "usage: sudo bash $0 install|remove" >&2; exit 2 ;;
esac
