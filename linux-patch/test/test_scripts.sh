#!/usr/bin/env bash
# Run tools/install.sh, tools/revert.sh and tools/apt-hook.sh against a copy of the installed app.asar
# in build/scripts; nothing outside build/ is touched. Run with: bash test/test_scripts.sh
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
dir="$root/build/scripts"
rm -rf "$dir"; mkdir -p "$dir/backups" "$dir/apt.conf.d"
installed=/usr/lib/claude-desktop/resources/app.asar
version="$(dpkg-query -W -f='${Version}' claude-desktop)"
# Start from the unpatched archive: the installed one, or the saved original once it is patched
source="$installed"
if python3 "$root/tools/patch_asar.py" --check "$installed"; then
  source="/var/backups/claude-desktop-patch/app.asar.$version"
fi
cp "$source" "$dir/app.asar"
export DESKTOP_PATCH_TEST=1 DESKTOP_PATCH_ASAR="$dir/app.asar" DESKTOP_PATCH_BACKUPS="$dir/backups" \
  DESKTOP_PATCH_LIB="$dir/lib" DESKTOP_PATCH_APT_CONF="$dir/apt.conf.d/99claude-desktop-patch"
original=$(sha256sum < "$dir/app.asar")
fail() { echo "FAIL: $*"; exit 1; }
patched() { python3 "$root/tools/patch_asar.py" --check "$dir/app.asar"; }
update() { cp "$source" "$dir/app.asar"; }   # what an update or a reinstall of claude-desktop does
asar_sum() { sha256sum < "$dir/app.asar"; }

# install keeps only the installed version's original
touch "$dir/backups/app.asar.0.1" "$dir/backups/app.asar.0.2" "$dir/backups/notes"
bash "$root/tools/install.sh" >/dev/null
patched || fail "not patched after install"
[ "$(ls "$dir/backups")" = "$(printf '%s\n' "app.asar.$version" notes)" ] \
  || fail "install kept other originals: $(ls "$dir/backups" | tr '\n' ' ')"
first=$(asar_sum)
bash "$root/tools/install.sh" >/dev/null   # again: rebuilt from the saved original, same result
[ "$(asar_sum)" = "$first" ] || fail "a second install differs"

# The apt hook leaves a patched app.asar alone and says nothing, and patches it again after an update
out=$(bash "$root/tools/apt-hook.sh" run) || fail "the hook failed"
[ -z "$out" ] && [ "$(asar_sum)" = "$first" ] || fail "the hook acted on a patched app.asar: $out"
out=$(DESKTOP_PATCH_ASAR="$dir/removed" bash "$root/tools/apt-hook.sh" run) || fail "the hook failed"
[ -z "$out" ] || fail "the hook spoke with claude-desktop removed: $out"
update
out=$(bash "$root/tools/apt-hook.sh" run) || fail "the hook failed"
grep -q "patched claude-desktop $version" <<<"$out" || fail "the hook did not patch after an update: $out"
[ "$(asar_sum)" = "$first" ] || fail "the hook's patch differs from install's"

# A hook that cannot patch says so, exits 0 for apt, and leaves app.asar as the update left it
mkdir -p "$dir/broken/tools" "$dir/broken/src"
cp "$root/tools/apt-hook.sh" "$root/tools/install.sh" "$root/tools/patch_asar.py" "$dir/broken/tools/"
cp "$root/src/loader.js" "$dir/broken/src/"   # no page.js or page.css
update
out=$(bash "$dir/broken/tools/apt-hook.sh" run 2>&1) || fail "a failing hook failed apt"
grep -q 'FAILED' <<<"$out" || fail "a failing hook did not say so: $out"
[ "$(asar_sum)" = "$original" ] || fail "a failing hook changed app.asar"

# revert puts the original back and keeps the hook from patching again until install runs
bash "$root/tools/apt-hook.sh" run >/dev/null
patched || fail "the hook did not patch after a failed run"
bash "$root/tools/revert.sh" >/dev/null
[ "$(asar_sum)" = "$original" ] || fail "revert did not restore the original"
out=$(bash "$root/tools/revert.sh")
grep -q 'nothing to undo' <<<"$out" || fail "a second revert: $out"
out=$(bash "$root/tools/apt-hook.sh" run) || fail "the hook failed"
[ -z "$out" ] && [ "$(asar_sum)" = "$original" ] || fail "the hook patched again after a revert: $out"
bash "$root/tools/install.sh" >/dev/null
update
bash "$root/tools/apt-hook.sh" run >/dev/null
patched || fail "the hook stayed off after install"

# apt-hook.sh install copies only what a git clone has committed into the root-owned folder
# (build/scripts/lib here), patches the app from that copy and writes the apt setting
repo="$dir/repo"
mkdir -p "$repo/tools"
cp -r "$root/src" "$repo/"
cp "$root/tools/patch_asar.py" "$root/tools/install.sh" "$root/tools/revert.sh" "$root/tools/apt-hook.sh" "$repo/tools/"
echo 'not for root' > "$repo/tools/other.sh"
git_() { git -C "$repo" -c user.name=test -c user.email=test@example.invalid -c commit.gpgsign=false \
  -c core.hooksPath=/dev/null "$@"; }
git_ init -q
git_ add -A
git_ commit -qm test
if bash "$dir/broken/tools/apt-hook.sh" install >/dev/null 2>&1; then fail "install ran outside a git clone"; fi
update
bash "$repo/tools/apt-hook.sh" install >/dev/null
patched || fail "not patched after apt-hook.sh install"
want=$(git_ ls-files src tools/patch_asar.py tools/install.sh tools/revert.sh tools/apt-hook.sh | sort)
[ "$(cd "$dir/lib" && find . -type f | sed 's|^\./||' | sort)" = "$want" ] || fail "the copy holds other files"
diff -r "$repo/src" "$dir/lib/src" >/dev/null || fail "the copy's src differs from the clone's"
conf="$DESKTOP_PATCH_APT_CONF"
cmd=$(apt-config -c "$conf" dump DPkg::Post-Invoke | grep -F "$dir/lib/tools/apt-hook.sh" \
  | sed -n 's/^DPkg::Post-Invoke:: "\(.*\)";$/\1/p') || true
[ -n "$cmd" ] || fail "apt reads no hook from $conf"
update
sh -c "$cmd" >/dev/null || fail "apt's command failed"
patched || fail "apt's command did not patch after an update"

# Nothing uncommitted reaches the copy; install.sh says when the copy differs from what it installed
echo '// not committed' >> "$repo/src/page.js"
if bash "$repo/tools/apt-hook.sh" install >/dev/null 2>&1; then fail "install took an uncommitted change"; fi
cmp -s "$dir/lib/src/page.js" "$root/src/page.js" || fail "a refused install changed the copy"
out=$(bash "$repo/tools/install.sh")
grep -q 'apt-hook.sh install' <<<"$out" || fail "install.sh did not say the hook's copy differs: $out"
git_ checkout -q -- src/page.js

# remove takes the setting and the copy away and leaves the patch; apt's command then does nothing
bash "$repo/tools/apt-hook.sh" remove >/dev/null
[ ! -e "$conf" ] && [ ! -e "$dir/lib" ] || fail "remove left the hook behind"
patched || fail "remove changed app.asar"
out=$(sh -c "$cmd" 2>&1) || fail "apt's command failed without its folder"
[ -z "$out" ] || fail "apt's command spoke without its folder: $out"
echo ok
