#!/usr/bin/env bash
# Runs a Python hook of this plugin with the first Python 3 that can run it, on Linux, macOS and
# Windows, where Claude Code runs hook commands through Git Bash:
#
#   bash run.sh <script.py>
#
# It always exits 0 and prints nothing but the script's own output, so a missing or broken Python
# only means that the reply is shown as written.
#
# - Each candidate gets the hook's input in turn; the first one that runs the script without error
#   wins, and one that cannot (missing, too old, the Microsoft Store stub) leaves it to the next.
# - On Windows `python3` is usually the Store stub, which fails unless Python came from the Store, so
#   `python` and the `py -3` launcher of a python.org install come first there.
# - Git Bash passes paths in POSIX form (/c/Users/...), which a Windows python.exe reads as a folder
#   on the current drive; cygpath -w turns them into C:\Users\....
# - PYTHONUTF8=1: otherwise Windows Python reads and writes text in the console's code page.

export PYTHONUTF8=1

if command -v cygpath >/dev/null 2>&1; then
    converted=()
    for a in "$@"; do
        case "$a" in
            /*) converted+=("$(cygpath -w "$a")") ;;
            *) converted+=("$a") ;;
        esac
    done
    set -- "${converted[@]}"
    candidates=("python" "py -3" "python3")
else
    candidates=("python3" "python")
fi

input=$(cat)
for cmd in "${candidates[@]}"; do
    # shellcheck disable=SC2086  # "py -3" is two words
    if out=$(printf '%s' "$input" | $cmd "$@" 2>/dev/null); then
        printf '%s' "$out"
        exit 0
    fi
done
exit 0
