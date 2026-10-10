#!/usr/bin/env python3
"""MessageDisplay hook of the rtl-display plugin.

The Claude desktop app gives each block of a reply (a paragraph, a list item, a heading, a table cell)
the direction of its first strong letter, so a Persian line that starts with a Latin word, a path or
code is laid out left to right. This hook adds U+200F (RIGHT-TO-LEFT MARK), which counts as a
right-to-left letter, to the start of each such block before the app shows the reply. Only what is
shown changes: the transcript and what Claude reads keep the reply as written.

It never stands in Claude's way: on any error it prints nothing and exits 0, so the reply is shown
exactly as it would be without the plugin.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rtl_marks  # noqa: E402


def on_message_display(data: dict) -> dict | None:
    """The desktop app hands over each completed message in one call: index 0, final. The terminal
    streams a message in batches of lines; a message that takes more than one batch is shown as
    written, because a batch alone does not tell whether it starts inside a code block."""
    if data.get("hook_event_name") != "MessageDisplay" or data.get("index") != 0 or not data.get("final"):
        return None
    text = data.get("delta")
    if not isinstance(text, str):
        return None
    marked = rtl_marks.mark_markdown(text)
    if marked == text:
        return None
    return {"hookSpecificOutput": {"hookEventName": "MessageDisplay", "displayContent": marked}}


def main() -> None:
    try:
        out = on_message_display(json.loads(sys.stdin.buffer.read().decode("utf-8")))
        if out:
            sys.stdout.write(json.dumps(out))  # ASCII escapes: right whatever the console's code page
    except Exception:  # never stand in Claude's way
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
